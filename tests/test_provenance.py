from __future__ import annotations

import copy
from dataclasses import FrozenInstanceError, replace
from datetime import datetime, timedelta, timezone
import errno
import json
import os
from pathlib import Path
import platform
import shutil
import stat
import subprocess
import sys
from types import MappingProxyType
from types import SimpleNamespace

import pytest

import almondlab.provenance as provenance


def test_canonical_json_ignores_mapping_order() -> None:
    left = provenance.canonical_json_bytes({"b": 2, "a": 1})
    right = provenance.canonical_json_bytes({"a": 1, "b": 2})

    assert left == b'{"a":1,"b":2}'
    assert left == right
    assert provenance.sha256_bytes(left) == provenance.sha256_bytes(right)


@pytest.mark.parametrize(
    "value",
    [
        {1: "integer key"},
        {"nested": {False: "boolean key"}},
        {"nested": [{"ok": 1}, {2.5: "float key"}]},
    ],
)
def test_canonical_json_rejects_non_string_mapping_keys(value: object) -> None:
    with pytest.raises(TypeError, match="string keys"):
        provenance.canonical_json_bytes(value)


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_canonical_json_rejects_nonfinite_numbers(value: float) -> None:
    with pytest.raises(ValueError, match="finite"):
        provenance.canonical_json_bytes({"nested": [value]})


def test_canonical_json_preserves_utf8_and_recursively_sorts_keys() -> None:
    payload = {"z": {"β": 2, "a": 1}, "é": [True, None, "1"]}

    assert provenance.canonical_json_bytes(payload) == (
        '{"z":{"a":1,"β":2},"é":[true,null,"1"]}'.encode("utf-8")
    )


@pytest.mark.parametrize(
    "value",
    [
        2**53,
        -(2**53),
        {"nested": [10**5000]},
    ],
)
def test_canonical_json_rejects_integers_outside_interoperable_range(
    value: object,
) -> None:
    with pytest.raises(ValueError, match="integer|interoperable"):
        provenance.canonical_json_bytes(value)


@pytest.mark.parametrize(
    "value",
    [
        float(2**53),
        -float(2**53),
        float("1e100"),
        -float("1e100"),
    ],
)
def test_canonical_json_rejects_floats_outside_interoperable_range(
    value: float,
) -> None:
    with pytest.raises(ValueError, match="number|float|interoperable"):
        provenance.canonical_json_bytes({"value": value})


def test_sha256_file_hashes_exact_file_bytes(tmp_path: Path) -> None:
    source = tmp_path / "source.bin"
    source.write_bytes(b"science\r\n\x00")

    assert provenance.sha256_file(source) == (
        "6f9db27b83f652374f90477b6270a79a5f21feee412179f06c2d7ed24bb934db"
    )


def test_atomic_failure_leaves_no_partial_or_temporary_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    destination = tmp_path / "result.json"

    def fail_replace(source: Path, target: Path) -> None:
        raise OSError("forced")

    monkeypatch.setattr(provenance.os, "replace", fail_replace)

    with pytest.raises(OSError, match="forced"):
        provenance.atomic_write_bytes(destination, b"science")

    assert not destination.exists()
    assert list(tmp_path.iterdir()) == []


def test_atomic_replace_failure_preserves_existing_destination(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    destination = tmp_path / "result.json"
    destination.write_bytes(b"established")

    def fail_replace(source: Path, target: Path) -> None:
        raise OSError("forced")

    monkeypatch.setattr(provenance.os, "replace", fail_replace)

    with pytest.raises(OSError, match="forced"):
        provenance.atomic_write_bytes(destination, b"replacement")

    assert destination.read_bytes() == b"established"
    assert list(tmp_path.iterdir()) == [destination]


def test_atomic_write_syncs_parent_directory_after_replace(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    destination = tmp_path / "result.json"
    calls: list[tuple[Path, tuple[int, int] | None]] = []

    def record_sync(
        directory: Path, expected_identity: tuple[int, int] | None
    ) -> None:
        calls.append((directory, expected_identity))

    monkeypatch.setattr(provenance, "_fsync_directory", record_sync, raising=False)

    provenance.atomic_write_bytes(destination, b"science")

    assert destination.read_bytes() == b"science"
    assert calls == [(tmp_path, None)]


def test_filesystem_confinement_capability_is_explicit() -> None:
    if os.name == "nt":
        assert provenance.FILESYSTEM_CONFINEMENT_MODE == (
            "windows-reparse-identity-guarded"
        )
        limitation = provenance.FILESYSTEM_CONFINEMENT_LIMITATION
        assert limitation is not None
        assert "concurrent reparse swap" in limitation
        assert "native handle-relative backend" in limitation
    else:
        assert provenance.FILESYSTEM_CONFINEMENT_MODE == (
            "descriptor-relative-nofollow"
        )
        assert provenance.FILESYSTEM_CONFINEMENT_LIMITATION is None


def test_seed_tree_is_name_sorted_reproducible_and_fully_recorded() -> None:
    left = provenance.SeedTree.from_seed(
        20260812,
        {
            "simulation": {"missingness": None, "biology": None},
            "design": None,
            "analysis": None,
        },
    )
    right = provenance.SeedTree.from_seed(
        20260812,
        {
            "analysis": None,
            "design": None,
            "simulation": {"biology": None, "missingness": None},
        },
    )

    assert left.to_dict() == right.to_dict()
    assert left.node("analysis").spawn_key == (0,)
    assert left.node("design").spawn_key == (1,)
    assert left.node("simulation", "biology").spawn_key == (2, 0)
    assert left.node("simulation", "missingness").spawn_key == (2, 1)
    assert left.root.n_children_spawned == 3
    assert left.node("simulation").n_children_spawned == 2
    assert left.node("simulation", "biology").n_children_spawned == 0
    assert left.node("simulation", "biology").state == (
        584251348,
        65396705,
        3828765313,
        1142723630,
    )
    assert left.seed_sequence("simulation", "biology").generate_state(4).tolist() == [
        584251348,
        65396705,
        3828765313,
        1142723630,
    ]
    next_child = left.seed_sequence("simulation").spawn(1)[0]
    assert next_child.spawn_key == (2, 2)


def test_seed_tree_children_are_deeply_immutable() -> None:
    tree = provenance.SeedTree.from_seed(7, {"simulation": {"biology": None}})

    assert isinstance(tree.children, MappingProxyType)
    assert isinstance(tree.node("simulation").children, MappingProxyType)
    with pytest.raises(TypeError):
        tree.children["invented"] = tree.root  # type: ignore[index]
    with pytest.raises(FrozenInstanceError):
        tree.root_seed = 8  # type: ignore[misc]


def test_seed_node_defensively_freezes_direct_constructor_sequences() -> None:
    generated = provenance.SeedTree.from_seed(7, {"analysis": None})
    spawn_key = [0]
    state = list(generated.node("analysis").state)
    child = provenance.SeedNode(
        name="analysis",
        entropy=7,
        spawn_key=spawn_key,  # type: ignore[arg-type]
        pool_size=4,
        n_children_spawned=0,
        state=state,  # type: ignore[arg-type]
        children={},
    )
    children = {"analysis": child}
    root = provenance.SeedNode(
        name="root",
        entropy=7,
        spawn_key=(),
        pool_size=4,
        n_children_spawned=1,
        state=generated.root.state,
        children=children,
    )
    spawn_key.append(999)
    state.append(999)
    children.clear()

    assert child.spawn_key == (0,)
    assert child.state == generated.node("analysis").state
    assert root.children == {"analysis": child}
    assert isinstance(root.children, MappingProxyType)


def test_seed_node_rejects_invented_seedsequence_state() -> None:
    with pytest.raises(ValueError, match="state|SeedSequence"):
        provenance.SeedNode(
            name="root",
            entropy=7,
            spawn_key=(),
            pool_size=4,
            n_children_spawned=0,
            state=(1, 2, 3, 4),
            children={},
        )


def test_seed_node_rejects_unregistered_pool_size_before_numpy_allocation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    invoked = False

    def refuse_numpy_allocation(*args: object, **kwargs: object) -> object:
        nonlocal invoked
        invoked = True
        raise AssertionError("NumPy allocation must not be attempted")

    monkeypatch.setattr(provenance.np.random, "SeedSequence", refuse_numpy_allocation)

    with pytest.raises(ValueError, match="pool_size|pool size"):
        provenance.SeedNode(
            name="root",
            entropy=7,
            spawn_key=(),
            pool_size=provenance.JSON_INTEGER_MAX,
            n_children_spawned=0,
            state=(1, 2, 3, 4),
            children={},
        )

    assert invoked is False


@pytest.mark.parametrize(
    "changes",
    [
        {"entropy": True},
        {"spawn_key": (False,)},
        {"pool_size": "4"},
        {"n_children_spawned": 0.0},
        {"state": (1, 2, 3, True)},
        {"children": {1: None}},
    ],
)
def test_seed_node_rejects_coerced_numeric_fields_and_nonstring_child_keys(
    changes: dict[str, object],
) -> None:
    values: dict[str, object] = {
        "name": "root",
        "entropy": 7,
        "spawn_key": (),
        "pool_size": 4,
        "n_children_spawned": 0,
        "state": (1, 2, 3, 4),
        "children": {},
    }
    values.update(changes)

    with pytest.raises((TypeError, ValueError), match="seed|children"):
        provenance.SeedNode(**values)  # type: ignore[arg-type]


@pytest.mark.parametrize("root_seed", [True, False, "7", 7.0, -1])
def test_seed_tree_rejects_coerced_or_negative_root_seeds(root_seed: object) -> None:
    with pytest.raises((TypeError, ValueError), match="root_seed"):
        provenance.SeedTree.from_seed(root_seed, {"simulation": None})  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "structure",
    [
        {1: None},
        {"simulation": {False: None}},
        {"": None},
        {"../escape": None},
        ["same", "same"],
    ],
)
def test_seed_tree_rejects_invalid_or_duplicate_names(structure: object) -> None:
    with pytest.raises((TypeError, ValueError), match="seed child|seed name"):
        provenance.SeedTree.from_seed(7, structure)  # type: ignore[arg-type]


def test_file_provenance_records_exact_relative_path_hash_and_size(
    tmp_path: Path,
) -> None:
    lockfile = tmp_path / "uv.lock"
    lockfile.write_bytes(b"version = 1\r\n")

    record = provenance.capture_file_provenance(lockfile, base_directory=tmp_path)

    assert record.to_dict() == {
        "path": "uv.lock",
        "sha256": "14b179a542d2d10339e2a532110851ed598682772324985007282df82d5963fc",
        "size_bytes": 13,
        "state": "available",
        "unavailable_reason": None,
    }
    with pytest.raises(FrozenInstanceError):
        record.size_bytes = 0  # type: ignore[misc]


def test_missing_file_provenance_has_stable_unavailable_state(tmp_path: Path) -> None:
    first_root = tmp_path / "first"
    second_root = tmp_path / "second"

    first = provenance.capture_file_provenance(
        first_root / "uv.lock", base_directory=first_root
    )
    second = provenance.capture_file_provenance(
        second_root / "uv.lock", base_directory=second_root
    )

    assert first == second
    assert first.to_dict() == {
        "path": "uv.lock",
        "sha256": None,
        "size_bytes": None,
        "state": "unavailable",
        "unavailable_reason": "missing",
    }


def test_nonregular_file_provenance_has_stable_unavailable_state(
    tmp_path: Path,
) -> None:
    directory = tmp_path / "uv.lock"
    directory.mkdir()

    record = provenance.capture_file_provenance(
        directory, base_directory=tmp_path
    )

    assert record.to_dict() == {
        "path": "uv.lock",
        "sha256": None,
        "size_bytes": None,
        "state": "unavailable",
        "unavailable_reason": "not_regular_file",
    }


def test_file_provenance_refuses_linked_parent_without_following_it(
    tmp_path: Path,
) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "uv.lock").write_bytes(b"outside")
    base = tmp_path / "base"
    base.mkdir()
    link = base / "linked"
    _directory_link_or_skip(outside, link)

    record = provenance.capture_file_provenance(
        link / "uv.lock", base_directory=base
    )

    assert record.to_dict() == {
        "path": "linked/uv.lock",
        "sha256": None,
        "size_bytes": None,
        "state": "unavailable",
        "unavailable_reason": "link",
    }
    assert (outside / "uv.lock").read_bytes() == b"outside"
    _remove_directory_link(link)


def test_relative_file_provenance_is_anchored_to_declared_base(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    base = tmp_path / "repository"
    base.mkdir()
    (base / "uv.lock").write_bytes(b"locked\n")
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)

    record = provenance.capture_file_provenance(
        Path("uv.lock"), base_directory=base
    )

    assert record.path == "uv.lock"
    assert record.state == "available"
    assert record.sha256 == "3a52732e0c98263090a2cd2509e7d2244d7194bd65f78b29e6ef6448e8143666"


@pytest.mark.skipif(shutil.which("git") is None, reason="Git executable unavailable")
def test_git_provenance_captures_exact_head_dirty_state_and_status_hash(
    tmp_path: Path,
) -> None:
    repository = tmp_path / "repository"
    repository.mkdir()
    _git(repository, "init", "--quiet")
    _git(repository, "config", "user.email", "test@example.invalid")
    _git(repository, "config", "user.name", "Provenance Test")
    (repository / "tracked.txt").write_bytes(b"tracked\n")
    _git(repository, "add", "tracked.txt")
    _git(repository, "commit", "--quiet", "-m", "fixture")
    expected_commit = _git(repository, "rev-parse", "HEAD").stdout.decode().strip()

    clean = provenance.capture_git_provenance(repository)

    assert clean.commit_sha == expected_commit
    assert clean.dirty is False
    assert clean.status_sha256 == "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
    assert clean.state == "available"
    assert clean.unavailable_reason is None
    assert clean.unavailable == ()

    (repository / "untracked.txt").write_bytes(b"untracked\n")
    dirty = provenance.capture_git_provenance(repository / "tracked.txt")

    assert dirty.commit_sha == expected_commit
    assert dirty.dirty is True
    assert dirty.status_sha256 == "7138fe5f9075b57cd3722a52f7476b97004b7cb9c29b783ea1e408c129c693e9"
    assert dirty.unavailable == ()


@pytest.mark.skipif(shutil.which("git") is None, reason="Git executable unavailable")
def test_git_provenance_hash_identifies_dirty_file_contents(tmp_path: Path) -> None:
    repository = tmp_path / "repository"
    repository.mkdir()
    _git(repository, "init", "--quiet")
    _git(repository, "config", "user.email", "test@example.invalid")
    _git(repository, "config", "user.name", "Provenance Test")
    tracked = repository / "tracked.txt"
    tracked.write_bytes(b"baseline\n")
    _git(repository, "add", "tracked.txt")
    _git(repository, "commit", "--quiet", "-m", "fixture")

    tracked.write_bytes(b"first dirty content\n")
    first = provenance.capture_git_provenance(repository)
    tracked.write_bytes(b"second dirty content\n")
    second = provenance.capture_git_provenance(repository)

    assert first.dirty is True
    assert second.dirty is True
    assert first.commit_sha == second.commit_sha
    assert first.status_sha256 != second.status_sha256


@pytest.mark.skipif(shutil.which("git") is None, reason="Git executable unavailable")
def test_git_provenance_hash_identifies_hidden_staged_contents(tmp_path: Path) -> None:
    repository = tmp_path / "repository"
    repository.mkdir()
    _git(repository, "init", "--quiet")
    _git(repository, "config", "user.email", "test@example.invalid")
    _git(repository, "config", "user.name", "Provenance Test")
    tracked = repository / "tracked.txt"
    baseline = b"baseline\n"
    tracked.write_bytes(baseline)
    _git(repository, "add", "tracked.txt")
    _git(repository, "commit", "--quiet", "-m", "fixture")

    tracked.write_bytes(b"first staged content\n")
    _git(repository, "add", "tracked.txt")
    tracked.write_bytes(baseline)
    first = provenance.capture_git_provenance(repository)

    tracked.write_bytes(b"second staged content\n")
    _git(repository, "add", "tracked.txt")
    tracked.write_bytes(baseline)
    second = provenance.capture_git_provenance(repository)

    assert first.dirty is True
    assert second.dirty is True
    assert first.commit_sha == second.commit_sha
    assert first.status_sha256 != second.status_sha256


@pytest.mark.skipif(shutil.which("git") is None, reason="Git executable unavailable")
def test_git_provenance_fails_closed_on_assume_unchanged_tracked_mutation(
    tmp_path: Path,
) -> None:
    repository = tmp_path / "repository"
    repository.mkdir()
    _git(repository, "init", "--quiet")
    _git(repository, "config", "user.email", "test@example.invalid")
    _git(repository, "config", "user.name", "Provenance Test")
    tracked = repository / "tracked.txt"
    tracked.write_bytes(b"baseline\n")
    _git(repository, "add", "tracked.txt")
    _git(repository, "commit", "--quiet", "-m", "fixture")
    _git(repository, "update-index", "--assume-unchanged", "tracked.txt")
    tracked.write_bytes(b"hidden mutation\n")

    record = provenance.capture_git_provenance(repository)

    assert record.state == "unavailable"
    assert record.unavailable_reason == "special_index_flags"


@pytest.mark.skipif(shutil.which("git") is None, reason="Git executable unavailable")
def test_git_provenance_hashes_tracked_bytes_without_trusting_textconv(
    tmp_path: Path,
) -> None:
    repository = tmp_path / "repository"
    repository.mkdir()
    _git(repository, "init", "--quiet")
    _git(repository, "config", "user.email", "test@example.invalid")
    _git(repository, "config", "user.name", "Provenance Test")
    (repository / ".gitattributes").write_bytes(b"tracked.txt diff=constant\n")
    (repository / "constant.sh").write_bytes(b"#!/bin/sh\nprintf 'same\\n'\n")
    tracked = repository / "tracked.txt"
    tracked.write_bytes(b"baseline\n")
    _git(repository, "add", ".")
    _git(repository, "commit", "--quiet", "-m", "fixture")
    _git(repository, "config", "diff.constant.textconv", "sh constant.sh")

    tracked.write_bytes(b"first hidden by textconv\n")
    first = provenance.capture_git_provenance(repository)
    tracked.write_bytes(b"second hidden by textconv\n")
    second = provenance.capture_git_provenance(repository)

    assert first.state == second.state == "available"
    assert first.dirty is second.dirty is True
    assert first.status_sha256 != second.status_sha256


@pytest.mark.skipif(shutil.which("git") is None, reason="Git executable unavailable")
def test_nonrepository_git_provenance_has_stable_unavailable_state(
    tmp_path: Path,
) -> None:
    first = tmp_path / "first"
    second = tmp_path / "second"
    first.mkdir()
    second.mkdir()

    first_record = provenance.capture_git_provenance(first)
    second_record = provenance.capture_git_provenance(second)

    assert first_record == second_record
    assert first_record.to_dict() == {
        "commit_sha": None,
        "dirty": None,
        "status_sha256": None,
        "state": "unavailable",
        "unavailable_reason": "not_a_git_repository",
        "unavailable": ["commit_sha", "dirty", "status_sha256"],
    }


@pytest.mark.skipif(shutil.which("git") is None, reason="Git executable unavailable")
def test_git_provenance_refuses_dirty_submodule_content(tmp_path: Path) -> None:
    submodule = tmp_path / "submodule"
    submodule.mkdir()
    _git(submodule, "init", "--quiet")
    _git(submodule, "config", "user.email", "test@example.invalid")
    _git(submodule, "config", "user.name", "Provenance Test")
    tracked = submodule / "tracked.txt"
    tracked.write_bytes(b"baseline\n")
    _git(submodule, "add", "tracked.txt")
    _git(submodule, "commit", "--quiet", "-m", "fixture")

    repository = tmp_path / "repository"
    repository.mkdir()
    _git(repository, "init", "--quiet")
    _git(repository, "config", "user.email", "test@example.invalid")
    _git(repository, "config", "user.name", "Provenance Test")
    _git(repository, "clone", "--quiet", submodule.as_posix(), "vendor/submodule")
    submodule_commit = _git(submodule, "rev-parse", "HEAD").stdout.decode().strip()
    _git(
        repository,
        "update-index",
        "--add",
        "--cacheinfo",
        f"160000,{submodule_commit},vendor/submodule",
    )
    _git(repository, "commit", "--quiet", "-m", "add submodule")

    (repository / "vendor" / "submodule" / "tracked.txt").write_bytes(b"dirty\n")
    record = provenance.capture_git_provenance(repository)

    assert record.state == "unavailable"
    assert record.unavailable_reason == "dirty_submodule"


def test_runtime_provenance_captures_exact_interpreter_and_platform() -> None:
    runtime = provenance.capture_runtime_provenance()

    assert Path(runtime.interpreter_path).resolve() == Path(sys.executable).resolve()
    assert runtime.python_version == platform.python_version()
    assert runtime.python_implementation == platform.python_implementation()
    assert runtime.os_text == platform.platform()
    with pytest.raises(FrozenInstanceError):
        runtime.python_version = "invented"  # type: ignore[misc]


def test_run_manifest_deep_freezes_caller_owned_records() -> None:
    config_hashes = {"configs/experiment.yaml": "1" * 64}
    input_hashes = {"data/input.csv": "2" * 64}
    artifact_hashes = {"tables/result.csv": "3" * 64}
    model_versions = {"chemistry": "1.0.0"}
    draws: dict[str, object] = {"chain": [[0.25, 0.5]]}

    manifest = _manifest(
        config_hashes=config_hashes,
        input_hashes=input_hashes,
        artifact_hashes=artifact_hashes,
        model_versions=model_versions,
        bayesian_raw_draws=draws,
    )
    config_hashes["invented"] = "f" * 64
    input_hashes.clear()
    artifact_hashes.clear()
    model_versions["chemistry"] = "invented"
    cast_draws = draws["chain"]
    assert isinstance(cast_draws, list)
    cast_draws.append([999.0])

    assert isinstance(manifest.config_hashes, MappingProxyType)
    assert isinstance(manifest.bayesian_raw_draws, MappingProxyType)
    assert manifest.config_hashes == {"configs/experiment.yaml": "1" * 64}
    assert manifest.input_hashes == {"data/input.csv": "2" * 64}
    assert manifest.artifact_hashes == {"tables/result.csv": "3" * 64}
    assert manifest.model_versions == {"chemistry": "1.0.0"}
    assert manifest.bayesian_raw_draws["chain"] == ((0.25, 0.5),)
    with pytest.raises(TypeError):
        manifest.config_hashes["invented"] = "f" * 64  # type: ignore[index]
    with pytest.raises(FrozenInstanceError):
        manifest.run_id = "invented"  # type: ignore[misc]


@pytest.mark.parametrize("root_seed", [True, "42", 42.0])
def test_run_manifest_rejects_root_seed_coercion(root_seed: object) -> None:
    with pytest.raises(TypeError, match="root_seed"):
        _manifest(root_seed=root_seed)  # type: ignore[arg-type]


@pytest.mark.parametrize("deterministic_demo_id", [0, 1, "false", None])
def test_run_manifest_rejects_boolean_coercion(
    deterministic_demo_id: object,
) -> None:
    with pytest.raises(TypeError, match="deterministic_demo_id"):
        _manifest(deterministic_demo_id=deterministic_demo_id)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"started_at": "2026-08-12T12:00:00Z"}, "started_at"),
        ({"ended_at": "2026-08-12T13:00:00Z"}, "ended_at"),
        ({"config_hashes": {1: "1" * 64}}, "string keys"),
        ({"input_hashes": {"data/input.csv": "not-a-digest"}}, "SHA-256"),
        ({"model_versions": {"chemistry": 1}}, "model version"),
        ({"bayesian_raw_draws": {"chain": [float("nan")]}}, "finite"),
        ({"bayesian_raw_draws": {1: [0.5]}}, "string keys"),
    ],
)
def test_run_manifest_rejects_permissive_or_noncanonical_values(
    changes: dict[str, object], message: str
) -> None:
    with pytest.raises((TypeError, ValueError), match=message):
        _manifest(**changes)


@pytest.mark.parametrize(
    "changes",
    [
        {"root_seed": 2**53},
        {"bayesian_raw_draws": {"chain": [[10**5000]]}},
    ],
)
def test_run_manifest_rejects_out_of_range_integers_at_construction(
    changes: dict[str, object],
) -> None:
    with pytest.raises(ValueError, match="integer|interoperable|root_seed"):
        _manifest(**changes)


def test_huge_integral_float_is_refused_before_manifest_publication(
    tmp_path: Path,
) -> None:
    run = provenance.RunDirectory.create(
        tmp_path / "outputs" / "runs",
        config_sha256="1" * 64,
        root_seed=42,
        deterministic_run_id="SYN_demo",
    )

    with pytest.raises(ValueError, match="number|float|interoperable"):
        manifest = _manifest(
            run_id="SYN_demo",
            deterministic_demo_id=True,
            artifact_hashes={},
            bayesian_raw_draws={"attack": float(2**53)},
        )
        provenance.finalize_manifest(manifest, run)

    assert not (run.path / "run_manifest.json").exists()


@pytest.mark.parametrize(
    "run_id", ["CON", "con.txt", "name.", "a..b", "valid\n"]
)
def test_run_manifest_rejects_nonportable_run_ids(run_id: str) -> None:
    with pytest.raises(ValueError, match="run_id|portable"):
        _manifest(run_id=run_id)


@pytest.mark.parametrize(
    "path",
    [
        "configs//experiment.yaml",
        "configs/./experiment.yaml",
        "configs/con.txt",
        "configs/name.",
        "configs/trailing ",
    ],
)
def test_run_manifest_rejects_every_nonportable_path_segment(path: str) -> None:
    with pytest.raises(ValueError, match="portable|path"):
        _manifest(config_hashes={path: "1" * 64})


@pytest.mark.parametrize(
    "component",
    [
        "a" * 256,
        "é" * 128,
    ],
)
def test_run_manifest_rejects_portable_components_over_255_utf8_bytes(
    component: str,
) -> None:
    with pytest.raises(ValueError, match="portable|path|255|byte"):
        _manifest(config_hashes={f"configs/{component}": "1" * 64})


def test_canonical_science_hash_excludes_only_declared_volatile_fields() -> None:
    base = _manifest()
    volatile = _manifest(
        run_id="other-run",
        started_at=base.started_at + timedelta(days=1),
        ended_at=base.started_at + timedelta(days=1, hours=2),
        git=replace(base.git, dirty=True),
        runtime=replace(
            base.runtime,
            interpreter_path="C:/different/python.exe",
            os_text="different operating system",
        ),
        bayesian_raw_draws={"chain": [[999.0]]},
    )

    assert "run_id" not in base.canonical_science_payload()
    assert "started_at" not in base.canonical_science_payload()
    assert "ended_at" not in base.canonical_science_payload()
    assert "dirty" not in base.canonical_science_payload()["git"]
    assert "interpreter_path" not in base.canonical_science_payload()["runtime"]
    assert "os_text" not in base.canonical_science_payload()["runtime"]
    assert "bayesian_raw_draws" not in base.canonical_science_payload()
    assert base.canonical_science_hash == volatile.canonical_science_hash
    assert base.manifest_hash != volatile.manifest_hash


def test_canonical_science_hash_changes_for_scientific_provenance() -> None:
    base = _manifest()
    changed_config = _manifest(
        config_hashes={"configs/experiment.yaml": "a" * 64}
    )
    changed_seed = _manifest(
        root_seed=43,
        seed_tree=provenance.SeedTree.from_seed(43, {"simulation": None}),
    )
    changed_model = _manifest(model_versions={"chemistry": "2.0.0"})
    changed_status = _manifest(
        git=replace(base.git, status_sha256="b" * 64, dirty=True)
    )

    hashes = {
        base.canonical_science_hash,
        changed_config.canonical_science_hash,
        changed_seed.canonical_science_hash,
        changed_model.canonical_science_hash,
        changed_status.canonical_science_hash,
    }
    assert len(hashes) == 5
    assert all(len(digest) == 64 for digest in hashes)


@pytest.mark.parametrize(
    "changes",
    [
        {"run_id": "other-run"},
        {"started_at": datetime(2026, 8, 12, 11, tzinfo=timezone.utc)},
        {"ended_at": datetime(2026, 8, 12, 15, tzinfo=timezone.utc)},
        {"git_dirty": True},
        {"interpreter_path": "C:/different/python.exe"},
        {"os_text": "different operating system"},
        {"bayesian_raw_draws": {"chain": [[999.0]]}},
    ],
)
def test_manifest_hash_includes_each_volatile_field(changes: dict[str, object]) -> None:
    base = _manifest()
    git_dirty = changes.pop("git_dirty", None)
    interpreter_path = changes.pop("interpreter_path", None)
    os_text = changes.pop("os_text", None)
    if git_dirty is not None:
        changes["git"] = replace(base.git, dirty=git_dirty)
    if interpreter_path is not None or os_text is not None:
        changes["runtime"] = replace(
            base.runtime,
            interpreter_path=(
                base.runtime.interpreter_path
                if interpreter_path is None
                else interpreter_path
            ),
            os_text=base.runtime.os_text if os_text is None else os_text,
        )

    changed = _manifest(**changes)

    assert base.manifest_hash != changed.manifest_hash


def test_manifest_document_contains_both_derived_hashes() -> None:
    manifest = _manifest()

    document = manifest.to_dict()

    assert document["canonical_science_hash"] == manifest.canonical_science_hash
    assert document["manifest_hash"] == manifest.manifest_hash
    assert document["seed_tree"] == manifest.seed_tree.to_dict()
    assert document["started_at"] == "2026-08-12T12:00:00Z"
    assert document["ended_at"] == "2026-08-12T14:00:00Z"
    document["config_hashes"]["invented"] = "f" * 64  # type: ignore[index]
    assert "invented" not in manifest.config_hashes


def test_run_directory_generates_utc_identity_hash_under_outputs_runs(
    tmp_path: Path,
) -> None:
    runs_root = tmp_path / "outputs" / "runs"

    run = provenance.RunDirectory.create(
        runs_root,
        config_sha256="1" * 64,
        root_seed=42,
        timestamp=datetime(2026, 8, 12, 12, 0, 0, 123456, tzinfo=timezone.utc),
    )

    assert run.run_id == "20260812T120000123456Z-52cfb796da9b"
    assert run.path == runs_root / run.run_id
    assert run.path.is_dir()
    assert run.runs_root == runs_root
    assert run.deterministic_demo_id is False
    assert run.creation_root_seed == 42
    assert run.creation_config_sha256 == "1" * 64


def test_run_directory_refuses_generated_and_deterministic_collisions(
    tmp_path: Path,
) -> None:
    runs_root = tmp_path / "outputs" / "runs"
    timestamp = datetime(2026, 8, 12, 12, tzinfo=timezone.utc)
    generated = provenance.RunDirectory.create(
        runs_root,
        config_sha256="1" * 64,
        root_seed=42,
        timestamp=timestamp,
    )
    sentinel = generated.path / "sentinel.txt"
    sentinel.write_bytes(b"preserve")

    with pytest.raises(FileExistsError):
        provenance.RunDirectory.create(
            runs_root,
            config_sha256="1" * 64,
            root_seed=42,
            timestamp=timestamp,
        )
    deterministic = provenance.RunDirectory.create(
        runs_root,
        config_sha256="1" * 64,
        root_seed=42,
        deterministic_run_id="SYN_demo",
    )
    with pytest.raises(FileExistsError):
        provenance.RunDirectory.create(
            runs_root,
            config_sha256="1" * 64,
            root_seed=42,
            deterministic_run_id="SYN_demo",
        )

    assert sentinel.read_bytes() == b"preserve"
    assert deterministic.deterministic_demo_id is True
    assert sorted(path.name for path in runs_root.iterdir()) == sorted(
        [generated.run_id, "SYN_demo"]
    )


def test_run_directory_cannot_be_constructed_for_an_existing_collision(
    tmp_path: Path,
) -> None:
    runs_root = tmp_path / "outputs" / "runs"
    collided = runs_root / "SYN_existing"
    collided.mkdir(parents=True)
    sentinel = collided / "sentinel.txt"
    sentinel.write_bytes(b"preserve")

    with pytest.raises(TypeError, match="RunDirectory.create"):
        provenance.RunDirectory(
            runs_root=runs_root,
            path=collided,
            run_id="SYN_existing",
            deterministic_demo_id=True,
        )

    assert sentinel.read_bytes() == b"preserve"


@pytest.mark.parametrize(
    "deterministic_run_id",
    ["../escape", "nested/escape", "nested\\escape", ".", "..", "", "C:escape"],
)
def test_run_directory_refuses_run_id_traversal_before_writing(
    tmp_path: Path, deterministic_run_id: str
) -> None:
    runs_root = tmp_path / "outputs" / "runs"
    runs_root.mkdir(parents=True)

    with pytest.raises(ValueError, match="run_id"):
        provenance.RunDirectory.create(
            runs_root,
            config_sha256="1" * 64,
            root_seed=42,
            deterministic_run_id=deterministic_run_id,
        )

    assert list(runs_root.iterdir()) == []
    assert not (tmp_path / "outputs" / "escape").exists()


@pytest.mark.parametrize("deterministic_run_id", ["CON", "con.txt", "name."])
def test_run_directory_refuses_nonportable_windows_components(
    tmp_path: Path, deterministic_run_id: str
) -> None:
    runs_root = tmp_path / "outputs" / "runs"

    with pytest.raises(ValueError, match="portable|run_id"):
        provenance.RunDirectory.create(
            runs_root,
            config_sha256="1" * 64,
            root_seed=42,
            deterministic_run_id=deterministic_run_id,
        )

    assert not runs_root.exists()


@pytest.mark.parametrize(
    "relative_root",
    [
        Path("other") / "runs",
        Path("outputs") / "not-runs",
        Path("outputs") / ".." / "outside" / "runs",
    ],
)
def test_run_directory_requires_literal_outputs_runs_root(
    tmp_path: Path, relative_root: Path
) -> None:
    runs_root = tmp_path / relative_root

    with pytest.raises(ValueError, match="outputs/runs"):
        provenance.RunDirectory.create(
            runs_root,
            config_sha256="1" * 64,
            root_seed=42,
            deterministic_run_id="SYN_demo",
        )

    assert not runs_root.exists()


def test_run_directory_artifact_path_refuses_absolute_and_traversal(
    tmp_path: Path,
) -> None:
    run = provenance.RunDirectory.create(
        tmp_path / "outputs" / "runs",
        config_sha256="1" * 64,
        root_seed=42,
        deterministic_run_id="SYN_demo",
    )

    assert run.artifact_path("tables/result.csv") == run.path / "tables" / "result.csv"
    for unsafe in ("../escape", "nested/../../escape", str(tmp_path / "absolute")):
        with pytest.raises(ValueError, match="artifact path"):
            run.artifact_path(unsafe)


@pytest.mark.parametrize(
    "unsafe", ["tables/CON", "tables/con.txt", "tables/name.", "tables/name "]
)
def test_run_directory_artifact_path_refuses_nonportable_components(
    tmp_path: Path, unsafe: str
) -> None:
    run = provenance.RunDirectory.create(
        tmp_path / "outputs" / "runs",
        config_sha256="1" * 64,
        root_seed=42,
        deterministic_run_id="SYN_demo",
    )

    with pytest.raises(ValueError, match="portable|artifact path"):
        run.artifact_path(unsafe)


def test_run_directory_detects_replaced_claim_before_artifact_resolution(
    tmp_path: Path,
) -> None:
    run = provenance.RunDirectory.create(
        tmp_path / "outputs" / "runs",
        config_sha256="1" * 64,
        root_seed=42,
        deterministic_run_id="SYN_demo",
    )
    displaced = run.runs_root / "SYN_displaced"
    run.path.rename(displaced)
    run.path.mkdir()

    with pytest.raises(RuntimeError, match="replaced|identity"):
        run.artifact_path("tables/result.csv")


def test_run_directory_detects_runs_root_swap_during_collision_claim(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runs_root = tmp_path / "outputs" / "runs"
    runs_root.mkdir(parents=True)
    displaced = tmp_path / "outputs" / "displaced-runs"
    real_mkdir = provenance.os.mkdir
    swapped = False

    def swap_root_then_mkdir(path: Path, *args: object, **kwargs: object) -> None:
        nonlocal swapped
        if not swapped and Path(path).parent == runs_root:
            swapped = True
            runs_root.rename(displaced)
            real_mkdir(runs_root)
        real_mkdir(path, *args, **kwargs)

    monkeypatch.setattr(provenance.os, "mkdir", swap_root_then_mkdir)

    with pytest.raises(RuntimeError, match="replaced|identity"):
        provenance.RunDirectory.create(
            runs_root,
            config_sha256="1" * 64,
            root_seed=42,
            deterministic_run_id="SYN_demo",
        )

    assert list(displaced.iterdir()) == []
    assert list(runs_root.iterdir()) == []


def test_run_directory_prepublication_identity_failure_reports_retained_claim(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runs_root = tmp_path / "outputs" / "runs"
    staging_name = ".claim-" + "0" * 32
    cleanup_called = False
    fake_os = SimpleNamespace(
        name="posix",
        O_RDONLY=os.O_RDONLY,
        O_DIRECTORY=getattr(os, "O_DIRECTORY", 0),
        O_NOFOLLOW=getattr(os, "O_NOFOLLOW", 0),
        O_CLOEXEC=getattr(os, "O_CLOEXEC", 0),
        mkdir=lambda name, mode=0o777, *, dir_fd=None: (runs_root / name).mkdir(
            mode=mode
        ),
        open=lambda *args, **kwargs: (_ for _ in ()).throw(
            OSError("claim identity unavailable")
        ),
        close=lambda descriptor: None,
    )

    def refuse_unverified_cleanup(*args: object, **kwargs: object) -> bool:
        nonlocal cleanup_called
        cleanup_called = True
        return True

    monkeypatch.setattr(provenance, "os", fake_os)
    monkeypatch.setattr(provenance.secrets, "token_hex", lambda count: "0" * 32)
    monkeypatch.setattr(
        provenance,
        "_open_directory_descriptor",
        lambda path, create=False: (path.mkdir(parents=True, exist_ok=True) or 70),
    )
    monkeypatch.setattr(
        provenance,
        "_require_path_matches_descriptor",
        lambda path, descriptor, expected: (1, 2),
    )
    monkeypatch.setattr(provenance, "_rmdir_name_if_identity", refuse_unverified_cleanup)

    with pytest.raises(provenance.AtomicCleanupRetainedError) as captured:
        provenance.RunDirectory.create(
            runs_root,
            config_sha256="1" * 64,
            root_seed=42,
            deterministic_run_id="SYN_demo",
        )

    assert captured.value.committed is False
    assert captured.value.destination == runs_root / "SYN_demo"
    assert captured.value.retained_path == runs_root / staging_name
    assert captured.value.retained_path.is_dir()
    assert cleanup_called is False


@pytest.mark.parametrize("private_quarantine", [False, True])
def test_run_directory_postpublication_retention_is_reported_as_committed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    private_quarantine: bool,
) -> None:
    runs_root = tmp_path / "outputs" / "runs"
    destination = runs_root / "SYN_demo"
    retained_name = ".almondlab-quarantine-retained-run"
    closed: list[int] = []

    fake_os = SimpleNamespace(
        name="posix",
        O_RDONLY=os.O_RDONLY,
        O_DIRECTORY=getattr(os, "O_DIRECTORY", 0),
        O_NOFOLLOW=getattr(os, "O_NOFOLLOW", 0),
        O_CLOEXEC=getattr(os, "O_CLOEXEC", 0),
        mkdir=lambda name, mode=0o777, *, dir_fd=None: (runs_root / name).mkdir(
            mode=mode
        ),
        open=lambda name, flags, *, dir_fd=None: 71,
        close=lambda descriptor: closed.append(descriptor),
    )

    def fail_after_publication(
        cls: type[provenance.RunDirectory], **kwargs: object
    ) -> object:
        raise RuntimeError("forced post-publication validation failure")

    def retain_cleanup(
        parent_descriptor: int,
        name: str,
        expected_identity: tuple[int, int],
    ) -> bool:
        del parent_descriptor, expected_identity
        assert name == "SYN_demo"
        if private_quarantine:
            destination.rename(runs_root / retained_name)
            raise provenance._RetainedCleanupIdentityError(retained_name)
        return False

    monkeypatch.setattr(provenance, "os", fake_os)
    monkeypatch.setattr(
        provenance,
        "_open_directory_descriptor",
        lambda path, create=False: (path.mkdir(parents=True, exist_ok=True) or 70),
    )
    monkeypatch.setattr(
        provenance,
        "_require_path_matches_descriptor",
        lambda path, descriptor, expected: (1, 2),
    )
    monkeypatch.setattr(
        provenance,
        "_require_descriptor_object",
        lambda descriptor, *, expected_identity, is_directory: (3, 4),
    )
    monkeypatch.setattr(provenance, "_descriptor_identity", lambda descriptor: (3, 4))
    monkeypatch.setattr(provenance, "_directory_identity", lambda path: (3, 4))
    monkeypatch.setattr(
        provenance,
        "_observe_posix_name",
        lambda parent_descriptor, name, expected_identity, *, is_directory: (
            provenance._PosixNameObservation(
                "exact" if (runs_root / name).exists() else "absent",
                None,
                expected_identity if (runs_root / name).exists() else None,
            )
        ),
    )
    monkeypatch.setattr(
        provenance,
        "_rename_directory_noreplace",
        lambda parent_descriptor, source_name, target_name: (
            runs_root / source_name
        ).rename(runs_root / target_name),
    )
    monkeypatch.setattr(
        provenance.RunDirectory,
        "_from_claim",
        classmethod(fail_after_publication),
    )
    monkeypatch.setattr(provenance, "_rmdir_name_if_identity", retain_cleanup)

    with pytest.raises(provenance.AtomicCommitUncertainError) as captured:
        provenance.RunDirectory.create(
            runs_root,
            config_sha256="1" * 64,
            root_seed=42,
            deterministic_run_id="SYN_demo",
        )

    assert captured.value.committed is True
    assert captured.value.destination == destination
    assert captured.value.retained_path == (
        runs_root / retained_name if private_quarantine else destination
    )
    assert captured.value.retained_path.is_dir()
    assert closed == [71, 70]


class _ScheduledPosixRunPublication:
    """Descriptor-level run-directory claim schedule for rename phase tests."""

    name = "posix"
    O_RDONLY = os.O_RDONLY
    O_DIRECTORY = getattr(os, "O_DIRECTORY", 0)
    O_NOFOLLOW = getattr(os, "O_NOFOLLOW", 0)
    O_CLOEXEC = getattr(os, "O_CLOEXEC", 0)
    O_NONBLOCK = getattr(os, "O_NONBLOCK", 0)

    def __init__(
        self,
        root: Path,
        *,
        rename_mode: str,
        precheck_attack_kind: str | None = None,
        parent_failure_at: int | None = None,
    ) -> None:
        self.root = root
        self.rename_mode = rename_mode
        self.precheck_attack_kind = precheck_attack_kind
        self.parent_failure_at = parent_failure_at
        self.parent_descriptor = 70
        self.stage_identity = (71, 81)
        self.attacker_identity = (71, 89)
        self.nodes: dict[str, dict[str, object]] = {}
        self.descriptors: dict[int, dict[str, object]] = {}
        self.next_descriptor = 71
        self.staging_name: str | None = None
        self.target_name = "SYN_demo"
        self.parent_checks = 0
        self.rename_calls = 0
        self.cleanup_calls: list[str] = []
        if rename_mode == "collision":
            self.nodes[self.target_name] = self._node("directory", self.attacker_identity)

    def __getattr__(self, name: str) -> object:
        return getattr(os, name)

    @staticmethod
    def _node(kind: str, identity: tuple[int, int]) -> dict[str, object]:
        mode = {
            "directory": stat.S_IFDIR | 0o700,
            "regular": stat.S_IFREG | 0o600,
            "symlink": stat.S_IFLNK | 0o777,
        }[kind]
        return {"kind": kind, "identity": identity, "mode": mode}

    def open_root(self, path: Path, *, create: bool = False) -> int:
        assert path == self.root
        if create:
            path.mkdir(parents=True, exist_ok=True)
        return self.parent_descriptor

    def mkdir(
        self,
        name: str,
        mode: int = 0o777,
        *,
        dir_fd: int | None = None,
    ) -> None:
        del mode
        assert dir_fd == self.parent_descriptor
        self.staging_name = name
        self.nodes[name] = self._node("directory", self.stage_identity)

    def open(
        self,
        name: str,
        flags: int,
        mode: int = 0o777,
        *,
        dir_fd: int | None = None,
    ) -> int:
        del mode
        assert dir_fd == self.parent_descriptor
        node = self.nodes.get(name)
        if node is None:
            raise FileNotFoundError(errno.ENOENT, "scheduled absence", name)
        if node["kind"] == "symlink" and flags & self.O_NOFOLLOW:
            raise OSError(errno.ELOOP, "scheduled symlink refusal", name)
        if flags & self.O_DIRECTORY and node["kind"] != "directory":
            raise NotADirectoryError(errno.ENOTDIR, "scheduled non-directory", name)
        descriptor = self.next_descriptor
        self.next_descriptor += 1
        self.descriptors[descriptor] = node
        return descriptor

    def fstat(self, descriptor: int) -> SimpleNamespace:
        node = self.descriptors[descriptor]
        identity = node["identity"]
        assert isinstance(identity, tuple)
        return SimpleNamespace(
            st_dev=identity[0],
            st_ino=identity[1],
            st_mode=node["mode"],
        )

    def close(self, descriptor: int) -> None:
        self.descriptors.pop(descriptor, None)

    def require_parent(
        self,
        path: Path,
        descriptor: int,
        expected_identity: tuple[int, int] | None,
    ) -> tuple[int, int]:
        del path, expected_identity
        assert descriptor == self.parent_descriptor
        self.parent_checks += 1
        if self.parent_checks == self.parent_failure_at:
            raise RuntimeError("scheduled parent identity failure")
        if self.parent_checks == 2 and self.precheck_attack_kind is not None:
            assert self.staging_name is not None
            self.nodes[self.staging_name] = self._node(
                self.precheck_attack_kind,
                self.attacker_identity,
            )
        return (1, 2)

    def _move_stage(self) -> None:
        assert self.staging_name is not None
        if self.target_name in self.nodes:
            raise FileExistsError(errno.EEXIST, "scheduled collision", self.target_name)
        self.nodes[self.target_name] = self.nodes.pop(self.staging_name)

    def rename(
        self, parent_descriptor: int, source_name: str, target_name: str
    ) -> None:
        assert parent_descriptor == self.parent_descriptor
        assert source_name == self.staging_name
        assert target_name == self.target_name
        self.rename_calls += 1
        if self.rename_mode == "raise_before":
            raise RuntimeError("scheduled run exception before rename")
        if self.rename_mode == "collision":
            raise FileExistsError(errno.EEXIST, "scheduled run collision", target_name)
        if self.rename_mode == "missing_both":
            self.nodes.pop(source_name, None)
            self.nodes.pop(target_name, None)
            raise RuntimeError("scheduled run exception with both names missing")
        if self.rename_mode == "race_attacker":
            self.nodes[source_name] = self._node(
                "directory", self.attacker_identity
            )
            self._move_stage()
            return
        if self.rename_mode == "link_return":
            self.nodes[target_name] = self.nodes[source_name]
            return
        self._move_stage()
        if self.rename_mode == "post_swap":
            self.nodes[target_name] = self._node("directory", self.attacker_identity)
            return
        if self.rename_mode == "post_exact_with_attacker_temp":
            self.nodes[source_name] = self._node(
                "directory", self.attacker_identity
            )
            return
        if self.rename_mode == "raise_after":
            raise RuntimeError("scheduled run exception after rename")

    def directory_identity(self, path: Path) -> tuple[int, int]:
        node = self.nodes.get(path.name)
        if node is None:
            raise FileNotFoundError(path)
        identity = node["identity"]
        assert isinstance(identity, tuple)
        return identity

    def cleanup(
        self,
        parent_descriptor: int,
        name: str,
        expected_identity: tuple[int, int],
    ) -> bool:
        assert parent_descriptor == self.parent_descriptor
        self.cleanup_calls.append(name)
        node = self.nodes.get(name)
        if node is None:
            return True
        if node["identity"] != expected_identity:
            return False
        retained_name = ".almondlab-quarantine-scheduled-run"
        self.nodes[retained_name] = self.nodes.pop(name)
        raise provenance._RetainedCleanupIdentityError(retained_name)

    def fsync(self, descriptor: int) -> None:
        assert descriptor == self.parent_descriptor
        assert self.has_open_target_identity(self.stage_identity)
        if self.rename_mode == "sync_missing_raise":
            self.nodes.pop(self.target_name, None)
            raise OSError("scheduled run directory fsync failure")

    def has_open_identity(self, identity: tuple[int, int]) -> bool:
        return any(node["identity"] == identity for node in self.descriptors.values())

    def has_open_target_identity(self, identity: tuple[int, int]) -> bool:
        target = self.nodes.get(self.target_name)
        return target is not None and target["identity"] == identity and any(
            node is target for node in self.descriptors.values()
        )

    def install(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(provenance, "os", self)
        monkeypatch.setattr(provenance, "_open_directory_descriptor", self.open_root)
        monkeypatch.setattr(
            provenance, "_require_path_matches_descriptor", self.require_parent
        )
        monkeypatch.setattr(provenance, "_rename_directory_noreplace", self.rename)
        monkeypatch.setattr(provenance, "_directory_identity", self.directory_identity)
        monkeypatch.setattr(provenance, "_rmdir_name_if_identity", self.cleanup)
        monkeypatch.setattr(provenance.secrets, "token_hex", lambda count: "0" * 32)


@pytest.mark.parametrize("attack_kind", ["directory", "regular", "symlink"])
def test_posix_run_claim_rejects_staging_name_swap_before_rename(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    attack_kind: str,
) -> None:
    root = tmp_path / "outputs" / "runs"
    schedule = _ScheduledPosixRunPublication(
        root,
        rename_mode="normal",
        precheck_attack_kind=attack_kind,
    )
    schedule.install(monkeypatch)

    with pytest.raises(provenance.AtomicCommitUncertainError) as captured:
        provenance.RunDirectory.create(
            root,
            config_sha256="1" * 64,
            root_seed=42,
            deterministic_run_id="SYN_demo",
        )

    assert captured.value.committed is True
    assert schedule.rename_calls == 0
    assert schedule.descriptors == {}


def test_posix_run_claim_holds_stage_and_verified_target_through_fsync(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "outputs" / "runs"
    schedule = _ScheduledPosixRunPublication(root, rename_mode="normal")
    schedule.install(monkeypatch)
    sentinel = object()

    def validate_claim(
        cls: type[provenance.RunDirectory], **kwargs: object
    ) -> object:
        del cls, kwargs
        assert schedule.has_open_identity(schedule.stage_identity)
        assert schedule.has_open_target_identity(schedule.stage_identity)
        return sentinel

    monkeypatch.setattr(
        provenance.RunDirectory, "_from_claim", classmethod(validate_claim)
    )

    claimed = provenance.RunDirectory.create(
        root,
        config_sha256="1" * 64,
        root_seed=42,
        deterministic_run_id="SYN_demo",
    )

    assert claimed is sentinel
    assert schedule.rename_calls == 1
    assert schedule.cleanup_calls == []
    assert schedule.staging_name not in schedule.nodes
    assert schedule.nodes["SYN_demo"]["identity"] == schedule.stage_identity
    assert schedule.descriptors == {}


def test_posix_run_claim_cleans_identity_bound_stage_after_setup_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "outputs" / "runs"
    schedule = _ScheduledPosixRunPublication(
        root,
        rename_mode="normal",
        parent_failure_at=2,
    )
    schedule.install(monkeypatch)

    with pytest.raises(provenance.AtomicCleanupRetainedError) as captured:
        provenance.RunDirectory.create(
            root,
            config_sha256="1" * 64,
            root_seed=42,
            deterministic_run_id="SYN_demo",
        )

    assert captured.value.committed is False
    assert isinstance(captured.value.__cause__, RuntimeError)
    assert captured.value.retained_path == (
        root / ".almondlab-quarantine-scheduled-run"
    )
    assert schedule.rename_calls == 0


def test_posix_run_claim_requires_native_success_to_consume_staged_name(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "outputs" / "runs"
    schedule = _ScheduledPosixRunPublication(root, rename_mode="link_return")
    schedule.install(monkeypatch)

    with pytest.raises(provenance.AtomicCommitUncertainError) as captured:
        provenance.RunDirectory.create(
            root,
            config_sha256="1" * 64,
            root_seed=42,
            deterministic_run_id="SYN_demo",
        )

    assert schedule.staging_name is not None
    assert captured.value.committed is True
    assert captured.value.retained_paths == (
        root / "SYN_demo",
        root / schedule.staging_name,
    )
    assert schedule.descriptors == {}


@pytest.mark.parametrize(
    ("rename_mode", "expected_committed", "cause_type"),
    [
        ("raise_after", True, RuntimeError),
        ("raise_before", False, RuntimeError),
        ("collision", False, FileExistsError),
        ("missing_both", True, RuntimeError),
        ("post_swap", True, RuntimeError),
        ("race_attacker", True, RuntimeError),
        ("post_exact_with_attacker_temp", True, RuntimeError),
    ],
)
def test_posix_run_claim_reconciles_native_rename_phase(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    rename_mode: str,
    expected_committed: bool,
    cause_type: type[BaseException],
) -> None:
    root = tmp_path / "outputs" / "runs"
    schedule = _ScheduledPosixRunPublication(root, rename_mode=rename_mode)
    schedule.install(monkeypatch)

    error_type = (
        provenance.AtomicCommitUncertainError
        if expected_committed
        else provenance.AtomicCleanupRetainedError
    )
    with pytest.raises(error_type) as captured:
        provenance.RunDirectory.create(
            root,
            config_sha256="1" * 64,
            root_seed=42,
            deterministic_run_id="SYN_demo",
        )

    assert captured.value.committed is expected_committed
    assert isinstance(captured.value.__cause__, cause_type)
    if rename_mode == "raise_after":
        assert captured.value.retained_path == root / "SYN_demo"
        assert schedule.cleanup_calls == []
    elif rename_mode in {"raise_before", "collision"}:
        assert captured.value.retained_path == (
            root / ".almondlab-quarantine-scheduled-run"
        )
        if rename_mode == "collision":
            assert schedule.nodes["SYN_demo"]["identity"] == schedule.attacker_identity
    elif rename_mode == "missing_both":
        assert captured.value.retained_path is None
    elif rename_mode == "post_exact_with_attacker_temp":
        assert captured.value.retained_path == root / "SYN_demo"
        assert schedule.staging_name is not None
        assert (
            root / schedule.staging_name
        ) not in captured.value.retained_paths
    else:
        assert captured.value.retained_path == root / "SYN_demo"
    assert schedule.descriptors == {}


def test_posix_run_claim_fsync_failure_does_not_report_a_stale_target_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "outputs" / "runs"
    schedule = _ScheduledPosixRunPublication(
        root, rename_mode="sync_missing_raise"
    )
    schedule.install(monkeypatch)
    monkeypatch.setattr(
        provenance.RunDirectory,
        "_from_claim",
        classmethod(lambda cls, **kwargs: object()),
    )

    with pytest.raises(provenance.AtomicCommitUncertainError) as captured:
        provenance.RunDirectory.create(
            root,
            config_sha256="1" * 64,
            root_seed=42,
            deterministic_run_id="SYN_demo",
        )

    assert captured.value.committed is True
    assert isinstance(captured.value.__cause__, OSError)
    assert captured.value.retained_path is None
    assert schedule.descriptors == {}


@pytest.mark.skipif(os.name != "nt", reason="Windows path-publication fallback")
def test_windows_run_claim_detects_post_publish_replacement_without_deleting_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runs_root = tmp_path / "outputs" / "runs"
    displaced = tmp_path / "outputs" / "displaced-run"
    destination = runs_root / "SYN_demo"
    real_rename = provenance.os.rename
    real_mkdir = provenance.os.mkdir

    def replace_after_publish(source: Path, target: Path) -> None:
        real_rename(source, target)
        real_rename(target, displaced)
        real_mkdir(target)
        (target / "sentinel.txt").write_bytes(b"preserve replacement")

    monkeypatch.setattr(provenance.os, "rename", replace_after_publish)

    with pytest.raises(provenance.AtomicCommitUncertainError) as captured:
        provenance.RunDirectory.create(
            runs_root,
            config_sha256="1" * 64,
            root_seed=42,
            deterministic_run_id="SYN_demo",
        )

    assert captured.value.committed is True
    assert captured.value.retained_path == destination
    assert (destination / "sentinel.txt").read_bytes() == b"preserve replacement"
    assert list(displaced.iterdir()) == []


def test_run_directory_refuses_symlinked_destination_and_artifact_parent(
    tmp_path: Path,
) -> None:
    runs_root = tmp_path / "outputs" / "runs"
    runs_root.mkdir(parents=True)
    outside = tmp_path / "outside"
    outside.mkdir()
    destination_link = runs_root / "SYN_link"
    _directory_link_or_skip(outside, destination_link)

    with pytest.raises(ValueError, match="link|symlink"):
        provenance.RunDirectory.create(
            runs_root,
            config_sha256="1" * 64,
            root_seed=42,
            deterministic_run_id="SYN_link",
        )

    _remove_directory_link(destination_link)
    run = provenance.RunDirectory.create(
        runs_root,
        config_sha256="1" * 64,
        root_seed=42,
        deterministic_run_id="SYN_demo",
    )
    artifact_link = run.path / "tables"
    _directory_link_or_skip(outside, artifact_link)
    with pytest.raises(ValueError, match="link|symlink"):
        run.artifact_path("tables/result.csv")

    assert list(outside.iterdir()) == []
    _remove_directory_link(artifact_link)


def test_run_directory_refuses_symlinked_runs_root(tmp_path: Path) -> None:
    real_runs = tmp_path / "real" / "runs"
    real_runs.mkdir(parents=True)
    outputs = tmp_path / "outputs"
    outputs.mkdir()
    linked_runs = outputs / "runs"
    _directory_link_or_skip(real_runs, linked_runs)

    with pytest.raises(ValueError, match="link|symlink"):
        provenance.RunDirectory.create(
            linked_runs,
            config_sha256="1" * 64,
            root_seed=42,
            deterministic_run_id="SYN_demo",
        )

    assert list(real_runs.iterdir()) == []
    _remove_directory_link(linked_runs)


def test_finalize_manifest_hashes_artifacts_and_writes_canonical_document(
    tmp_path: Path,
) -> None:
    run = provenance.RunDirectory.create(
        tmp_path / "outputs" / "runs",
        config_sha256="1" * 64,
        root_seed=42,
        deterministic_run_id="SYN_demo",
    )
    artifact = run.artifact_path("tables/result.csv")
    artifact.parent.mkdir()
    artifact.write_bytes(b"result\n")
    manifest = _manifest(
        run_id=run.run_id,
        deterministic_demo_id=True,
        ended_at=None,
        artifact_hashes={},
    )
    ended_at = datetime(2026, 8, 12, 15, tzinfo=timezone.utc)

    finalized = provenance.finalize_manifest(
        manifest,
        run,
        ended_at=ended_at,
        artifact_paths={"tables/result.csv": "tables/result.csv"},
    )

    assert finalized.ended_at == ended_at
    assert finalized.artifact_hashes == {
        "tables/result.csv": "5656fafa00d4f294bcb606cf4f7d4fa877390e46f583e8b3c8744ace104a31d1"
    }
    manifest_path = run.path / "run_manifest.json"
    expected_bytes = provenance.canonical_json_bytes(finalized.to_dict()) + b"\n"
    assert manifest_path.read_bytes() == expected_bytes
    assert json.loads(manifest_path.read_bytes()) == finalized.to_dict()


def test_finalize_manifest_snapshots_stateful_artifact_items_once(
    tmp_path: Path,
) -> None:
    run = provenance.RunDirectory.create(
        tmp_path / "outputs" / "runs",
        config_sha256="1" * 64,
        root_seed=42,
        deterministic_run_id="SYN_demo",
    )
    artifact = run.artifact_path("tables/result.csv")
    artifact.parent.mkdir()
    artifact.write_bytes(b"result\n")

    class OneShotArtifactPaths(dict[str, str]):
        items_calls = 0

        def items(self) -> object:  # type: ignore[override]
            self.items_calls += 1
            if self.items_calls > 1:
                return ()
            exposed = list(super().items())
            self.clear()
            return exposed

    artifact_paths = OneShotArtifactPaths(
        {"tables/result.csv": "tables/result.csv"}
    )

    finalized = provenance.finalize_manifest(
        _manifest(
            run_id="SYN_demo",
            deterministic_demo_id=True,
            artifact_hashes={},
        ),
        run,
        artifact_paths=artifact_paths,
    )

    assert artifact_paths.items_calls == 1
    assert artifact_paths == {}
    assert finalized.artifact_hashes == {
        "tables/result.csv": "5656fafa00d4f294bcb606cf4f7d4fa877390e46f583e8b3c8744ace104a31d1"
    }


def test_finalize_manifest_source_mapping_mutation_cannot_disable_held_checks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    run = provenance.RunDirectory.create(
        tmp_path / "outputs" / "runs",
        config_sha256="1" * 64,
        root_seed=42,
        deterministic_run_id="SYN_demo",
    )
    artifact = run.artifact_path("tables/result.csv")
    artifact.parent.mkdir()
    artifact.write_bytes(b"first\n")
    artifact_paths = {"tables/result.csv": "tables/result.csv"}
    real_replace = provenance.replace
    real_create = provenance.atomic_create_bytes

    def mutate_mapping_after_initial_capture(
        instance: object, **changes: object
    ) -> object:
        artifact_paths.clear()
        return real_replace(instance, **changes)

    def mutate_artifact_after_create(
        destination: str | Path, payload: bytes, **keywords: object
    ) -> Path:
        result = real_create(destination, payload, **keywords)  # type: ignore[arg-type]
        artifact.write_bytes(b"second\n")
        return result

    monkeypatch.setattr(provenance, "replace", mutate_mapping_after_initial_capture)
    monkeypatch.setattr(provenance, "atomic_create_bytes", mutate_artifact_after_create)

    with pytest.raises(
        (ValueError, provenance.AtomicCommitUncertainError),
        match="changed|artifact|uncertain",
    ):
        provenance.finalize_manifest(
            _manifest(
                run_id="SYN_demo",
                deterministic_demo_id=True,
                artifact_hashes={},
            ),
            run,
            artifact_paths=artifact_paths,
        )

    assert artifact_paths == {}
    assert not (run.path / "run_manifest.json").exists()


def test_finalize_manifest_rejects_duplicate_items_from_stateful_mapping(
    tmp_path: Path,
) -> None:
    run = provenance.RunDirectory.create(
        tmp_path / "outputs" / "runs",
        config_sha256="1" * 64,
        root_seed=42,
        deterministic_run_id="SYN_demo",
    )
    artifact = run.artifact_path("tables/result.csv")
    artifact.parent.mkdir()
    artifact.write_bytes(b"result\n")

    class DuplicateArtifactPaths(dict[str, str]):
        def items(self) -> object:  # type: ignore[override]
            return [
                ("tables/result.csv", "tables/result.csv"),
                ("tables/result.csv", "tables/result.csv"),
            ]

    with pytest.raises(ValueError, match="duplicate|collision"):
        provenance.finalize_manifest(
            _manifest(
                run_id="SYN_demo",
                deterministic_demo_id=True,
                artifact_hashes={},
            ),
            run,
            artifact_paths=DuplicateArtifactPaths(
                {"tables/result.csv": "tables/result.csv"}
            ),
        )

    assert not (run.path / "run_manifest.json").exists()


def test_finalize_manifest_refuses_mismatched_run_identity_before_write(
    tmp_path: Path,
) -> None:
    run = provenance.RunDirectory.create(
        tmp_path / "outputs" / "runs",
        config_sha256="1" * 64,
        root_seed=42,
        deterministic_run_id="SYN_demo",
    )

    with pytest.raises(ValueError, match="run_id"):
        provenance.finalize_manifest(
            _manifest(run_id="other-run", deterministic_demo_id=True), run
        )
    with pytest.raises(ValueError, match="deterministic_demo_id"):
        provenance.finalize_manifest(
            _manifest(run_id="SYN_demo", deterministic_demo_id=False), run
        )

    assert list(run.path.iterdir()) == []


def test_finalize_manifest_binds_claimed_root_seed_and_config_digest(
    tmp_path: Path,
) -> None:
    run = provenance.RunDirectory.create(
        tmp_path / "outputs" / "runs",
        config_sha256="1" * 64,
        root_seed=42,
        deterministic_run_id="SYN_demo",
    )

    with pytest.raises(ValueError, match="root_seed|creation"):
        provenance.finalize_manifest(
            _manifest(
                run_id="SYN_demo",
                deterministic_demo_id=True,
                root_seed=43,
                seed_tree=provenance.SeedTree.from_seed(
                    43, {"simulation": None}
                ),
                artifact_hashes={},
            ),
            run,
        )
    with pytest.raises(ValueError, match="config|creation"):
        provenance.finalize_manifest(
            _manifest(
                run_id="SYN_demo",
                deterministic_demo_id=True,
                creation_config_sha256="2" * 64,
                artifact_hashes={},
            ),
            run,
        )

    assert list(run.path.iterdir()) == []


@pytest.mark.skipif(os.name != "nt", reason="Windows hardlink publication fallback")
def test_finalize_manifest_exclusive_commit_failure_leaves_no_manifest_or_temp(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    run = provenance.RunDirectory.create(
        tmp_path / "outputs" / "runs",
        config_sha256="1" * 64,
        root_seed=42,
        deterministic_run_id="SYN_demo",
    )
    manifest_path = run.path / "run_manifest.json"

    def fail_link(
        source: Path, target: Path, *, follow_symlinks: bool = True
    ) -> None:
        raise OSError("forced")

    monkeypatch.setattr(provenance.os, "link", fail_link)

    with pytest.raises(OSError, match="forced"):
        provenance.finalize_manifest(
            _manifest(
                run_id="SYN_demo",
                deterministic_demo_id=True,
                ended_at=None,
                artifact_hashes={},
            ),
            run,
            ended_at=datetime(2026, 8, 12, 15, tzinfo=timezone.utc),
        )

    assert not manifest_path.exists()
    assert list(run.path.iterdir()) == []


def test_finalize_manifest_refuses_artifact_escape_before_manifest_write(
    tmp_path: Path,
) -> None:
    run = provenance.RunDirectory.create(
        tmp_path / "outputs" / "runs",
        config_sha256="1" * 64,
        root_seed=42,
        deterministic_run_id="SYN_demo",
    )
    outside = tmp_path / "outside.txt"
    outside.write_bytes(b"outside")

    with pytest.raises(ValueError, match="artifact path"):
        provenance.finalize_manifest(
            _manifest(
                run_id="SYN_demo",
                deterministic_demo_id=True,
                ended_at=None,
                artifact_hashes={},
            ),
            run,
            artifact_paths={"outside": "../../../outside.txt"},
        )

    assert list(run.path.iterdir()) == []
    assert outside.read_bytes() == b"outside"


@pytest.mark.parametrize(
    "reserved_path",
    [
        "run_manifest.json",
        "RUN_MANIFEST.JSON",
        "nested/Run_Manifest.JsOn",
    ],
)
def test_run_manifest_rejects_casefolded_reserved_artifact_components(
    reserved_path: str,
) -> None:
    with pytest.raises(ValueError, match="run_manifest.json|reserved"):
        _manifest(artifact_hashes={reserved_path: "1" * 64})


@pytest.mark.parametrize(
    "reserved_path", ["RUN_MANIFEST.JSON", "nested/Run_Manifest.JsOn"]
)
def test_finalize_manifest_rejects_casefolded_reserved_artifact_paths(
    tmp_path: Path, reserved_path: str
) -> None:
    run = provenance.RunDirectory.create(
        tmp_path / "outputs" / "runs",
        config_sha256="1" * 64,
        root_seed=42,
        deterministic_run_id="SYN_demo",
    )

    with pytest.raises(ValueError, match="run_manifest.json|reserved"):
        provenance.finalize_manifest(
            _manifest(
                run_id="SYN_demo",
                deterministic_demo_id=True,
                ended_at=None,
                artifact_hashes={},
            ),
            run,
            artifact_paths={reserved_path: reserved_path},
        )

    assert list(run.path.iterdir()) == []


def test_finalize_manifest_rechecks_reserved_artifact_hashes(tmp_path: Path) -> None:
    run = provenance.RunDirectory.create(
        tmp_path / "outputs" / "runs",
        config_sha256="1" * 64,
        root_seed=42,
        deterministic_run_id="SYN_demo",
    )
    manifest = _manifest(
        run_id="SYN_demo",
        deterministic_demo_id=True,
        artifact_hashes={},
    )
    object.__setattr__(
        manifest,
        "artifact_hashes",
        MappingProxyType({"RUN_MANIFEST.JSON": "1" * 64}),
    )

    with pytest.raises(ValueError, match="run_manifest.json|reserved"):
        provenance.finalize_manifest(manifest, run)


@pytest.mark.parametrize(
    ("field_name", "value"),
    [
        ("config_hashes", {"../config.yaml": "1" * 64}),
        ("config_hashes", {"configs/CON": "1" * 64}),
        ("input_hashes", {"C:/outside.csv": "2" * 64}),
    ],
)
def test_run_manifest_refuses_nonportable_file_identity_keys(
    field_name: str, value: object
) -> None:
    with pytest.raises(ValueError, match="portable|path"):
        _manifest(**{field_name: value})


def test_file_provenance_refuses_nonportable_recorded_path() -> None:
    with pytest.raises(ValueError, match="portable|path"):
        provenance.FileProvenance(
            path="../uv.lock",
            sha256=None,
            size_bytes=None,
            state="unavailable",
            unavailable_reason="missing",
        )


def test_finalize_manifest_requires_every_artifact_hash_to_be_verified(
    tmp_path: Path,
) -> None:
    run = provenance.RunDirectory.create(
        tmp_path / "outputs" / "runs",
        config_sha256="1" * 64,
        root_seed=42,
        deterministic_run_id="SYN_demo",
    )
    artifact = run.artifact_path("tables/result.csv")
    artifact.parent.mkdir()
    artifact.write_bytes(b"result\n")
    manifest = _manifest(
        run_id="SYN_demo",
        deterministic_demo_id=True,
        ended_at=None,
        artifact_hashes={"tables/result.csv": "5" * 64},
    )

    with pytest.raises(ValueError, match="artifact_paths"):
        provenance.finalize_manifest(manifest, run, artifact_paths={})

    assert not (run.path / "run_manifest.json").exists()


def test_finalize_manifest_requires_artifact_key_to_equal_portable_path(
    tmp_path: Path,
) -> None:
    run = provenance.RunDirectory.create(
        tmp_path / "outputs" / "runs",
        config_sha256="1" * 64,
        root_seed=42,
        deterministic_run_id="SYN_demo",
    )
    artifact = run.artifact_path("tables/result.csv")
    artifact.parent.mkdir()
    artifact.write_bytes(b"result\n")

    with pytest.raises(ValueError, match="key.*path"):
        provenance.finalize_manifest(
            _manifest(
                run_id="SYN_demo",
                deterministic_demo_id=True,
                ended_at=None,
                artifact_hashes={},
            ),
            run,
            artifact_paths={"result": "tables/result.csv"},
        )

    assert not (run.path / "run_manifest.json").exists()


def test_finalize_manifest_rechecks_artifacts_immediately_before_commit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    run = provenance.RunDirectory.create(
        tmp_path / "outputs" / "runs",
        config_sha256="1" * 64,
        root_seed=42,
        deterministic_run_id="SYN_demo",
    )
    artifact = run.artifact_path("tables/result.csv")
    artifact.parent.mkdir()
    artifact.write_bytes(b"first\n")
    real_capture = provenance.capture_file_provenance
    captures = 0

    def mutate_after_first_capture(
        path: str | Path, *, base_directory: str | Path | None = None
    ) -> provenance.FileProvenance:
        nonlocal captures
        record = real_capture(path, base_directory=base_directory)
        if Path(path) == artifact:
            captures += 1
            if captures == 1:
                artifact.write_bytes(b"second\n")
        return record

    monkeypatch.setattr(provenance, "capture_file_provenance", mutate_after_first_capture)

    with pytest.raises(ValueError, match="changed.*finalization|artifact"):
        provenance.finalize_manifest(
            _manifest(
                run_id="SYN_demo",
                deterministic_demo_id=True,
                ended_at=None,
                artifact_hashes={},
            ),
            run,
            artifact_paths={"tables/result.csv": "tables/result.csv"},
        )

    assert captures == 2
    assert not (run.path / "run_manifest.json").exists()


def test_finalize_manifest_validates_inside_exclusive_create(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    run = provenance.RunDirectory.create(
        tmp_path / "outputs" / "runs",
        config_sha256="1" * 64,
        root_seed=42,
        deterministic_run_id="SYN_demo",
    )
    artifact = run.artifact_path("tables/result.csv")
    artifact.parent.mkdir()
    artifact.write_bytes(b"first\n")
    real_create = provenance.atomic_create_bytes

    def mutate_immediately_before_create(
        destination: str | Path,
        payload: bytes,
        **keywords: object,
    ) -> Path:
        artifact.write_bytes(b"second\n")
        return real_create(destination, payload, **keywords)  # type: ignore[arg-type]

    monkeypatch.setattr(
        provenance, "atomic_create_bytes", mutate_immediately_before_create
    )

    with pytest.raises(ValueError, match="changed|artifact"):
        provenance.finalize_manifest(
            _manifest(
                run_id="SYN_demo",
                deterministic_demo_id=True,
                artifact_hashes={},
            ),
            run,
            artifact_paths={"tables/result.csv": "tables/result.csv"},
        )

    assert not (run.path / "run_manifest.json").exists()


def test_finalize_manifest_revalidates_after_exclusive_create(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    run = provenance.RunDirectory.create(
        tmp_path / "outputs" / "runs",
        config_sha256="1" * 64,
        root_seed=42,
        deterministic_run_id="SYN_demo",
    )
    artifact = run.artifact_path("tables/result.csv")
    artifact.parent.mkdir()
    artifact.write_bytes(b"first\n")
    real_create = provenance.atomic_create_bytes

    def mutate_immediately_after_create(
        destination: str | Path,
        payload: bytes,
        **keywords: object,
    ) -> Path:
        result = real_create(destination, payload, **keywords)  # type: ignore[arg-type]
        artifact.write_bytes(b"second\n")
        return result

    monkeypatch.setattr(
        provenance, "atomic_create_bytes", mutate_immediately_after_create
    )

    with pytest.raises(
        (ValueError, provenance.AtomicCommitUncertainError),
        match="changed|artifact|uncertain",
    ):
        provenance.finalize_manifest(
            _manifest(
                run_id="SYN_demo",
                deterministic_demo_id=True,
                artifact_hashes={},
            ),
            run,
            artifact_paths={"tables/result.csv": "tables/result.csv"},
        )

    assert not (run.path / "run_manifest.json").exists()


def test_finalize_manifest_translates_postpublication_cleanup_retention(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    run = provenance.RunDirectory.create(
        tmp_path / "outputs" / "runs",
        config_sha256="1" * 64,
        root_seed=42,
        deterministic_run_id="SYN_demo",
    )
    manifest_path = run.path / "run_manifest.json"
    retained_path = run.path / ".almondlab-quarantine-retained-manifest"

    def create_then_corrupt(
        destination: str | Path,
        payload: bytes,
        *,
        _expected_parent_identity: tuple[int, int] | None = None,
        _validator: object = None,
        _committed_identity: list[tuple[int, int]] | None = None,
    ) -> Path:
        del _expected_parent_identity, _validator
        target = Path(destination)
        target.write_bytes(payload + b"corrupt")
        metadata = target.stat(follow_symlinks=False)
        assert _committed_identity is not None
        _committed_identity.append((metadata.st_dev, metadata.st_ino))
        return target

    def retain_manifest(
        path: Path, expected_identity: tuple[int, int]
    ) -> bool:
        del expected_identity
        path.rename(retained_path)
        raise provenance.AtomicCommitUncertainError(
            path, retained_path=retained_path
        )

    monkeypatch.setattr(provenance, "atomic_create_bytes", create_then_corrupt)
    monkeypatch.setattr(provenance, "_unlink_path_if_identity", retain_manifest)

    with pytest.raises(provenance.AtomicCommitUncertainError) as captured:
        provenance.finalize_manifest(
            _manifest(
                run_id="SYN_demo",
                deterministic_demo_id=True,
                artifact_hashes={},
            ),
            run,
        )

    assert captured.value.committed is True
    assert captured.value.destination == manifest_path
    assert captured.value.retained_path == retained_path
    assert retained_path.is_file()


def test_finalize_manifest_validates_emitted_document_before_publication(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    run = provenance.RunDirectory.create(
        tmp_path / "outputs" / "runs",
        config_sha256="1" * 64,
        root_seed=42,
        deterministic_run_id="SYN_demo",
    )

    def refuse_document(schema: object, document: object) -> None:
        raise ValueError("manifest schema refusal")

    monkeypatch.setattr(provenance, "validate_run_manifest_document", refuse_document)

    with pytest.raises(ValueError, match="schema"):
        provenance.finalize_manifest(
            _manifest(
                run_id="SYN_demo",
                deterministic_demo_id=True,
                artifact_hashes={},
            ),
            run,
        )

    assert not (run.path / "run_manifest.json").exists()


def test_finalize_manifest_always_revalidates_seed_tree_semantics(
    tmp_path: Path,
) -> None:
    run = provenance.RunDirectory.create(
        tmp_path / "outputs" / "runs",
        config_sha256="1" * 64,
        root_seed=42,
        deterministic_run_id="SYN_demo",
    )
    manifest = _manifest(
        run_id="SYN_demo",
        deterministic_demo_id=True,
        artifact_hashes={},
    )
    object.__setattr__(manifest.seed_tree.root, "state", (0, 0, 0, 0))

    with pytest.raises(ValueError, match="state|SeedSequence|manifest"):
        provenance.finalize_manifest(manifest, run)

    assert not (run.path / "run_manifest.json").exists()


def test_finalize_manifest_refuses_to_overwrite_existing_manifest(
    tmp_path: Path,
) -> None:
    run = provenance.RunDirectory.create(
        tmp_path / "outputs" / "runs",
        config_sha256="1" * 64,
        root_seed=42,
        deterministic_run_id="SYN_demo",
    )
    manifest_path = run.path / "run_manifest.json"
    manifest_path.write_bytes(b"established manifest\n")

    with pytest.raises(FileExistsError):
        provenance.finalize_manifest(
            _manifest(
                run_id="SYN_demo",
                deterministic_demo_id=True,
                ended_at=None,
                artifact_hashes={},
            ),
            run,
            ended_at=datetime(2026, 8, 12, 15, tzinfo=timezone.utc),
        )

    assert manifest_path.read_bytes() == b"established manifest\n"


def test_atomic_postcommit_failure_has_explicit_uncertain_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    destination = tmp_path / "result.json"
    destination.write_bytes(b"established")

    def fail_sync(
        directory: Path, expected_identity: tuple[int, int] | None
    ) -> None:
        raise OSError("forced postcommit sync failure")

    monkeypatch.setattr(provenance, "_fsync_directory", fail_sync)

    with pytest.raises(provenance.AtomicCommitUncertainError) as captured:
        provenance.atomic_write_bytes(destination, b"replacement")

    assert captured.value.destination == destination
    assert captured.value.committed is True
    assert destination.read_bytes() == b"replacement"


@pytest.mark.skipif(os.name != "nt", reason="Windows temporary cleanup path")
def test_atomic_create_temp_cleanup_failure_is_explicitly_postcommit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    destination = tmp_path / "result.json"
    real_unlink = provenance._unlink_path_if_identity
    calls = 0

    def fail_first_cleanup(
        path: Path, expected_identity: tuple[int, int]
    ) -> bool:
        nonlocal calls
        calls += 1
        if calls == 1:
            return False
        return real_unlink(path, expected_identity)

    monkeypatch.setattr(provenance, "_unlink_path_if_identity", fail_first_cleanup)

    with pytest.raises(provenance.AtomicCommitUncertainError) as captured:
        provenance.atomic_create_bytes(destination, b"created")

    assert captured.value.committed is True
    assert destination.read_bytes() == b"created"
    assert list(tmp_path.iterdir()) == [destination]


class _PosixAtomicSyscallHarness:
    """Run the POSIX atomic state machine against a real Windows temp directory."""

    name = "posix"

    def __init__(
        self,
        parent: Path,
        *,
        rename_error: BaseException | None = None,
    ) -> None:
        self.parent = parent.absolute()
        self.rename_error = rename_error
        self._next_directory_descriptor = 90_000
        self._directory_descriptors: dict[int, Path] = {}
        self._file_descriptors: dict[int, Path] = {}
        self.rename_calls: list[tuple[str, str]] = []
        self.link_calls: list[tuple[str, str]] = []
        self.cleanup_calls: list[str] = []
        self.directory_syncs: list[Path] = []

    def __getattr__(self, name: str) -> object:
        return getattr(os, name)

    def open_directory(self, path: Path, *, create: bool = False) -> int:
        directory = Path(path).absolute()
        if create:
            directory.mkdir(parents=True, exist_ok=True)
        assert directory == self.parent
        descriptor = self._next_directory_descriptor
        self._next_directory_descriptor += 1
        self._directory_descriptors[descriptor] = directory
        return descriptor

    def open(
        self,
        path: str | bytes | os.PathLike[str] | os.PathLike[bytes],
        flags: int,
        mode: int = 0o777,
        *,
        dir_fd: int | None = None,
    ) -> int:
        if dir_fd in self._directory_descriptors:
            directory = self._directory_descriptors[dir_fd]
            descriptor = os.open(directory / os.fsdecode(path), flags, mode)
            self._file_descriptors[descriptor] = directory / os.fsdecode(path)
            return descriptor
        return os.open(path, flags, mode)

    def fdopen(self, descriptor: int, mode: str) -> object:
        assert mode in {"rb", "wb"}
        if mode == "rb":
            self._file_descriptors.pop(descriptor, None)
            return os.fdopen(descriptor, mode)
        return os.fdopen(descriptor, mode, closefd=False)

    def fstat(self, descriptor: int) -> os.stat_result:
        return os.fstat(descriptor)

    def close(self, descriptor: int) -> None:
        if descriptor in self._directory_descriptors:
            del self._directory_descriptors[descriptor]
            return
        self._file_descriptors.pop(descriptor, None)
        os.close(descriptor)

    def link(
        self,
        source_name: str,
        target_name: str,
        *,
        src_dir_fd: int,
        dst_dir_fd: int,
        follow_symlinks: bool,
    ) -> None:
        assert follow_symlinks is False
        source_parent = self._directory_descriptors[src_dir_fd]
        target_parent = self._directory_descriptors[dst_dir_fd]
        self.link_calls.append((source_name, target_name))
        os.link(source_parent / source_name, target_parent / target_name)

    def rename_noreplace(
        self, parent_descriptor: int, source_name: str, target_name: str
    ) -> None:
        assert self._directory_descriptors[parent_descriptor] == self.parent
        self.rename_calls.append((source_name, target_name))
        if self.rename_error is not None:
            raise self.rename_error
        source = self.parent / source_name
        target = self.parent / target_name
        if target.exists():
            raise FileExistsError(target)
        for descriptor, path in tuple(self._file_descriptors.items()):
            if path == source:
                os.close(descriptor)
                del self._file_descriptors[descriptor]
        os.rename(source, target)

    def require_path_matches_descriptor(
        self,
        path: Path,
        descriptor: int,
        expected_identity: tuple[int, int] | None,
    ) -> tuple[int, int]:
        directory = Path(path).absolute()
        assert self._directory_descriptors[descriptor] == directory
        metadata = directory.stat(follow_symlinks=False)
        identity = (metadata.st_dev, metadata.st_ino)
        if expected_identity is not None:
            assert identity == expected_identity
        return identity

    def cleanup_retained(
        self,
        parent_descriptor: int,
        name: str,
        expected_identity: tuple[int, int],
    ) -> bool:
        del parent_descriptor, expected_identity
        self.cleanup_calls.append(name)
        raise provenance._RetainedCleanupIdentityError(name)

    def observe(
        self,
        parent_descriptor: int,
        name: str,
        expected_identity: tuple[int, int],
        *,
        is_directory: bool,
    ) -> provenance._PosixNameObservation:
        del is_directory
        assert self._directory_descriptors[parent_descriptor] == self.parent
        path = self.parent / name
        if not path.exists():
            return provenance._PosixNameObservation("absent")
        metadata = path.stat(follow_symlinks=False)
        identity = (metadata.st_dev, metadata.st_ino)
        state = "exact" if identity == expected_identity else "different"
        return provenance._PosixNameObservation(state, None, identity)

    def install(
        self,
        monkeypatch: pytest.MonkeyPatch,
        *,
        fake_retained_cleanup: bool = True,
    ) -> None:
        monkeypatch.setattr(provenance, "os", self)
        monkeypatch.setattr(provenance, "_open_directory_descriptor", self.open_directory)
        monkeypatch.setattr(
            provenance,
            "_require_path_matches_descriptor",
            self.require_path_matches_descriptor,
        )
        monkeypatch.setattr(provenance, "_rename_name_noreplace", self.rename_noreplace)
        monkeypatch.setattr(provenance, "_observe_posix_name", self.observe)
        monkeypatch.setattr(
            provenance,
            "_directory_identity",
            lambda path: (
                Path(path).stat(follow_symlinks=False).st_dev,
                Path(path).stat(follow_symlinks=False).st_ino,
            ),
        )
        monkeypatch.setattr(
            provenance,
            "_fsync_directory",
            lambda directory, expected_identity: self.directory_syncs.append(
                Path(directory)
            ),
        )
        if fake_retained_cleanup:
            monkeypatch.setattr(
                provenance, "_unlink_name_if_identity", self.cleanup_retained
            )


def test_posix_atomic_create_renames_temp_without_hardlink_or_cleanup(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    destination = tmp_path / "result.json"
    harness = _PosixAtomicSyscallHarness(tmp_path)
    harness.install(monkeypatch)
    validation_states: list[tuple[bool, tuple[str, ...]]] = []
    committed_identity: list[tuple[int, int]] = []

    def validate() -> None:
        validation_states.append(
            (
                destination.exists(),
                tuple(
                    sorted(
                        path.name
                        for path in tmp_path.iterdir()
                        if path != destination
                    )
                ),
            )
        )

    result = provenance.atomic_create_bytes(
        destination,
        b"created",
        _validator=validate,
        _committed_identity=committed_identity,
    )

    assert result == destination
    assert destination.read_bytes() == b"created"
    assert validation_states[0][0] is False
    assert len(validation_states[0][1]) == 1
    assert validation_states[0][1][0].startswith(".result.json.")
    assert validation_states[0][1][0].endswith(".tmp")
    assert validation_states[1] == (True, ())
    assert harness.rename_calls == [(validation_states[0][1][0], "result.json")]
    assert harness.link_calls == []
    assert harness.cleanup_calls == []
    assert list(tmp_path.iterdir()) == [destination]
    metadata = destination.stat(follow_symlinks=False)
    assert committed_identity == [(metadata.st_dev, metadata.st_ino)]


def test_finalize_manifest_succeeds_through_posix_noreplace_rename(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    run = provenance.RunDirectory.create(
        tmp_path / "outputs" / "runs",
        config_sha256="1" * 64,
        root_seed=42,
        deterministic_run_id="SYN_posix_finalize",
    )
    manifest = _manifest(
        run_id="SYN_posix_finalize",
        deterministic_demo_id=True,
        ended_at=None,
        artifact_hashes={},
    )
    destination = run.path / "run_manifest.json"
    harness = _PosixAtomicSyscallHarness(run.path)
    harness.install(monkeypatch)

    finalized = provenance.finalize_manifest(
        manifest,
        run,
        ended_at=datetime(2026, 8, 12, 15, tzinfo=timezone.utc),
    )

    assert finalized.ended_at == datetime(2026, 8, 12, 15, tzinfo=timezone.utc)
    assert json.loads(destination.read_text(encoding="utf-8")) == finalized.to_dict()
    assert len(harness.rename_calls) == 1
    assert harness.rename_calls[0][0].startswith(".run_manifest.json.")
    assert harness.rename_calls[0][0].endswith(".tmp")
    assert harness.rename_calls[0][1] == "run_manifest.json"
    assert harness.link_calls == []
    assert harness.cleanup_calls == []
    assert list(run.path.iterdir()) == [destination]


def test_posix_atomic_create_unavailable_noreplace_fails_before_publication(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    destination = tmp_path / "result.json"
    harness = _PosixAtomicSyscallHarness(
        tmp_path,
        rename_error=RuntimeError("secure no-replace publication is unavailable"),
    )
    harness.install(monkeypatch, fake_retained_cleanup=False)
    validation_calls = 0

    def validate() -> None:
        nonlocal validation_calls
        validation_calls += 1

    with pytest.raises(provenance.AtomicCleanupRetainedError) as captured:
        provenance.atomic_create_bytes(destination, b"created", _validator=validate)

    assert captured.value.committed is False
    assert destination.exists() is False
    assert captured.value.retained_path is not None
    assert captured.value.retained_path.exists()
    assert captured.value.retained_path.read_bytes() == b"created"
    assert validation_calls == 1
    assert harness.link_calls == []
    assert len(harness.rename_calls) == 2
    assert harness.rename_calls[0][1] == "result.json"
    assert harness.rename_calls[1][1].startswith(".almondlab-quarantine-")


class _ScheduledPosixFilePublication:
    """Descriptor-level POSIX syscall schedule with controllable rename races."""

    name = "posix"
    O_WRONLY = os.O_WRONLY
    O_RDONLY = os.O_RDONLY
    O_CREAT = os.O_CREAT
    O_EXCL = os.O_EXCL
    O_NOFOLLOW = getattr(os, "O_NOFOLLOW", 0)
    O_CLOEXEC = getattr(os, "O_CLOEXEC", 0)
    O_NONBLOCK = getattr(os, "O_NONBLOCK", 0)
    O_DIRECTORY = getattr(os, "O_DIRECTORY", 0)

    def __init__(
        self,
        *,
        rename_mode: str = "normal",
        precheck_attack_kind: str | None = None,
    ) -> None:
        self.rename_mode = rename_mode
        self.precheck_attack_kind = precheck_attack_kind
        self.stage_identity = (31, 41)
        self.attacker_identity = (31, 99)
        self.parent_descriptor = 50
        self.temp_name: str | None = None
        self.target_name = "result.json"
        self.nodes: dict[str, dict[str, object]] = {}
        self.descriptors: dict[int, dict[str, object]] = {}
        self.next_descriptor = 51
        self.parent_checks = 0
        self.rename_calls = 0
        self.cleanup_calls: list[str] = []
        self.directory_sync_calls = 0
        self.closed_descriptors: list[int] = []
        self.link_calls = 0
        self.replaced_target_node: dict[str, object] | None = None
        if rename_mode == "collision":
            self.nodes[self.target_name] = self._node("regular", self.attacker_identity)
        elif rename_mode in {"replace_existing", "replace_raise_before"}:
            self.replaced_target_node = self._node(
                "regular", self.attacker_identity
            )
            self.replaced_target_node["payload"] = b"established"
            self.nodes[self.target_name] = self.replaced_target_node

    def __getattr__(self, name: str) -> object:
        return getattr(os, name)

    @staticmethod
    def _node(kind: str, identity: tuple[int, int]) -> dict[str, object]:
        mode = {
            "regular": stat.S_IFREG | 0o600,
            "directory": stat.S_IFDIR | 0o700,
            "symlink": stat.S_IFLNK | 0o777,
        }[kind]
        return {"kind": kind, "identity": identity, "mode": mode, "payload": b""}

    def _allocate(self, node: dict[str, object]) -> int:
        descriptor = self.next_descriptor
        self.next_descriptor += 1
        self.descriptors[descriptor] = node
        return descriptor

    def open_directory(self, path: Path, *, create: bool = False) -> int:
        del path, create
        return self.parent_descriptor

    def require_parent(
        self,
        path: Path,
        descriptor: int,
        expected_identity: tuple[int, int] | None,
    ) -> tuple[int, int]:
        del path, expected_identity
        assert descriptor == self.parent_descriptor
        self.parent_checks += 1
        if self.parent_checks == 2 and self.precheck_attack_kind is not None:
            assert self.temp_name is not None
            staged = self.nodes[self.temp_name]
            attacker = self._node(
                self.precheck_attack_kind,
                self.attacker_identity,
            )
            if self.precheck_attack_kind == "regular":
                attacker["payload"] = staged["payload"]
            self.nodes[self.temp_name] = attacker
        return (1, 2)

    def open(
        self,
        name: str,
        flags: int,
        mode: int = 0o777,
        *,
        dir_fd: int | None = None,
    ) -> int:
        del mode
        assert dir_fd == self.parent_descriptor
        if flags & self.O_CREAT:
            assert self.temp_name is None
            self.temp_name = name
            node = self._node("regular", self.stage_identity)
            self.nodes[name] = node
            return self._allocate(node)
        node = self.nodes.get(name)
        if node is None:
            raise FileNotFoundError(errno.ENOENT, "scheduled absence", name)
        if node["kind"] == "symlink" and flags & self.O_NOFOLLOW:
            raise OSError(errno.ELOOP, "scheduled symlink refusal", name)
        if flags & self.O_DIRECTORY and node["kind"] != "directory":
            raise NotADirectoryError(errno.ENOTDIR, "scheduled non-directory", name)
        return self._allocate(node)

    def fstat(self, descriptor: int) -> SimpleNamespace:
        node = self.descriptors[descriptor]
        identity = node["identity"]
        assert isinstance(identity, tuple)
        payload = node["payload"]
        assert isinstance(payload, bytes)
        return SimpleNamespace(
            st_dev=identity[0],
            st_ino=identity[1],
            st_mode=node["mode"],
            st_size=len(payload),
            st_mtime_ns=1,
            st_ctime_ns=1,
        )

    class _Handle:
        def __init__(self, owner: "_ScheduledPosixFilePublication", descriptor: int) -> None:
            self.owner = owner
            self.descriptor = descriptor

        def __enter__(self) -> "_ScheduledPosixFilePublication._Handle":
            return self

        def __exit__(self, *args: object) -> None:
            self.close()

        def write(self, payload: bytes) -> None:
            self.owner.descriptors[self.descriptor]["payload"] = payload

        def flush(self) -> None:
            return None

        def fileno(self) -> int:
            return self.descriptor

        def close(self) -> None:
            self.owner.close(self.descriptor)

    def fdopen(self, descriptor: int, mode: str) -> "_Handle":
        assert mode == "wb"
        return self._Handle(self, descriptor)

    def fsync(self, descriptor: int) -> None:
        assert descriptor in self.descriptors

    def close(self, descriptor: int) -> None:
        if descriptor == self.parent_descriptor:
            self.closed_descriptors.append(descriptor)
            return
        if descriptor in self.descriptors:
            del self.descriptors[descriptor]
            self.closed_descriptors.append(descriptor)

    def _move_temp_to_target(self) -> None:
        assert self.temp_name is not None
        if self.target_name in self.nodes:
            raise FileExistsError(errno.EEXIST, "scheduled collision", self.target_name)
        self.nodes[self.target_name] = self.nodes.pop(self.temp_name)

    def replace(
        self,
        source_name: str,
        target_name: str,
        *,
        src_dir_fd: int,
        dst_dir_fd: int,
    ) -> None:
        assert src_dir_fd == self.parent_descriptor
        assert dst_dir_fd == self.parent_descriptor
        assert source_name == self.temp_name
        assert target_name == self.target_name
        self.rename_calls += 1
        if self.rename_mode == "replace_raise_before":
            raise RuntimeError("scheduled replace exception before rename")
        self.nodes[target_name] = self.nodes.pop(source_name)
        if self.rename_mode == "replace_raise_after":
            raise RuntimeError("scheduled replace exception after rename")
        if self.rename_mode == "replace_post_swap":
            self.nodes[target_name] = self._node(
                "regular", self.attacker_identity
            )

    def rename(
        self, parent_descriptor: int, source_name: str, target_name: str
    ) -> None:
        assert parent_descriptor == self.parent_descriptor
        assert source_name == self.temp_name
        assert target_name == self.target_name
        self.rename_calls += 1
        if self.rename_mode in {"raise_before", "arbitrary_before"}:
            raise RuntimeError("scheduled exception before rename")
        if self.rename_mode == "collision":
            raise FileExistsError(errno.EEXIST, "scheduled collision", target_name)
        if self.rename_mode == "race_attacker":
            staged = self.nodes[source_name]
            attacker = self._node("regular", self.attacker_identity)
            attacker["payload"] = staged["payload"]
            self.nodes[source_name] = attacker
            self._move_temp_to_target()
            return
        if self.rename_mode == "missing_both":
            self.nodes.pop(source_name, None)
            self.nodes.pop(target_name, None)
            raise RuntimeError("scheduled exception with both names missing")
        if self.rename_mode == "return_without_rename":
            return
        if self.rename_mode == "link_return":
            self.nodes[target_name] = self.nodes[source_name]
            return
        self._move_temp_to_target()
        if self.rename_mode == "post_swap":
            self.nodes[target_name] = self._node("regular", self.attacker_identity)
            return
        if self.rename_mode == "post_exact_with_attacker_temp":
            self.nodes[source_name] = self._node(
                "regular", self.attacker_identity
            )
            return
        if self.rename_mode == "raise_after":
            raise RuntimeError("scheduled exception after rename")

    def cleanup(
        self,
        parent_descriptor: int,
        name: str,
        expected_identity: tuple[int, int],
    ) -> bool:
        assert parent_descriptor == self.parent_descriptor
        self.cleanup_calls.append(name)
        node = self.nodes.get(name)
        if node is None:
            return True
        if node["identity"] != expected_identity:
            return False
        retained_name = ".almondlab-quarantine-scheduled"
        self.nodes[retained_name] = self.nodes.pop(name)
        raise provenance._RetainedCleanupIdentityError(retained_name)

    def directory_sync(
        self, directory: Path, expected_identity: tuple[int, int] | None
    ) -> None:
        del directory, expected_identity
        self.directory_sync_calls += 1
        assert self.has_open_target_identity(self.stage_identity)
        if self.rename_mode == "sync_missing_raise":
            self.nodes.pop(self.target_name, None)
            raise OSError("scheduled file directory fsync failure")

    def link(self, *args: object, **kwargs: object) -> None:
        del args, kwargs
        self.link_calls += 1
        raise AssertionError("POSIX publication must not invoke os.link")

    def has_open_identity(self, identity: tuple[int, int]) -> bool:
        return any(node["identity"] == identity for node in self.descriptors.values())

    def has_open_target_identity(self, identity: tuple[int, int]) -> bool:
        target = self.nodes.get(self.target_name)
        return target is not None and target["identity"] == identity and any(
            node is target for node in self.descriptors.values()
        )

    def install(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(provenance, "os", self)
        monkeypatch.setattr(provenance, "_open_directory_descriptor", self.open_directory)
        monkeypatch.setattr(
            provenance, "_require_path_matches_descriptor", self.require_parent
        )
        monkeypatch.setattr(provenance, "_rename_name_noreplace", self.rename)
        monkeypatch.setattr(provenance, "_unlink_name_if_identity", self.cleanup)
        monkeypatch.setattr(provenance, "_fsync_directory", self.directory_sync)


@pytest.mark.parametrize(
    "attack_kind",
    ["regular", "directory", "symlink"],
)
def test_posix_atomic_create_rejects_temp_name_swap_before_rename(
    monkeypatch: pytest.MonkeyPatch,
    attack_kind: str,
) -> None:
    schedule = _ScheduledPosixFilePublication(precheck_attack_kind=attack_kind)
    schedule.install(monkeypatch)
    committed_identity: list[tuple[int, int]] = []

    with pytest.raises(provenance.AtomicCommitUncertainError) as captured:
        provenance.atomic_create_bytes(
            Path("/sandbox/result.json"),
            b"same bytes" if attack_kind == "regular" else b"created",
            _committed_identity=committed_identity,
        )

    assert captured.value.committed is True
    assert committed_identity == []
    assert schedule.rename_calls == 0
    assert schedule.link_calls == 0
    assert schedule.descriptors == {}
    if attack_kind == "regular":
        assert schedule.temp_name is not None
        assert schedule.nodes[schedule.temp_name]["payload"] == b"same bytes"


def test_posix_atomic_create_detects_swap_between_precheck_and_rename(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    schedule = _ScheduledPosixFilePublication(rename_mode="race_attacker")
    schedule.install(monkeypatch)
    committed_identity: list[tuple[int, int]] = []

    with pytest.raises(provenance.AtomicCommitUncertainError) as captured:
        provenance.atomic_create_bytes(
            Path("/sandbox/result.json"),
            b"created",
            _committed_identity=committed_identity,
        )

    assert captured.value.committed is True
    assert captured.value.retained_path == Path("/sandbox/result.json")
    assert committed_identity == []
    assert schedule.nodes[schedule.target_name]["payload"] == b"created"
    assert schedule.descriptors == {}


@pytest.mark.parametrize(
    "rename_mode",
    ["post_swap", "return_without_rename", "post_exact_with_attacker_temp"],
)
def test_posix_atomic_create_never_trusts_native_success_without_identity_proof(
    monkeypatch: pytest.MonkeyPatch,
    rename_mode: str,
) -> None:
    schedule = _ScheduledPosixFilePublication(rename_mode=rename_mode)
    schedule.install(monkeypatch)

    with pytest.raises(
        (provenance.AtomicCommitUncertainError, provenance.AtomicCleanupRetainedError)
    ) as captured:
        provenance.atomic_create_bytes(Path("/sandbox/result.json"), b"created")

    if rename_mode in {"post_swap", "post_exact_with_attacker_temp"}:
        assert captured.value.committed is True
    else:
        assert captured.value.committed is False
    if rename_mode == "post_exact_with_attacker_temp":
        assert captured.value.retained_path == Path("/sandbox/result.json")
        assert schedule.temp_name is not None
        assert Path("/sandbox") / schedule.temp_name not in captured.value.retained_paths
    assert schedule.descriptors == {}


def test_posix_atomic_create_requires_native_success_to_consume_staged_name(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    schedule = _ScheduledPosixFilePublication(rename_mode="link_return")
    schedule.install(monkeypatch)
    committed_identity: list[tuple[int, int]] = []

    with pytest.raises(provenance.AtomicCommitUncertainError) as captured:
        provenance.atomic_create_bytes(
            Path("/sandbox/result.json"),
            b"created",
            _committed_identity=committed_identity,
        )

    assert captured.value.committed is True
    assert captured.value.retained_paths == (
        Path("/sandbox/result.json"),
        Path("/sandbox") / schedule.temp_name,
    )
    assert committed_identity == []
    assert schedule.descriptors == {}


def test_posix_atomic_create_holds_stage_and_verified_target_through_fsync(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    schedule = _ScheduledPosixFilePublication()
    schedule.install(monkeypatch)
    validation_calls = 0

    def validate() -> None:
        nonlocal validation_calls
        validation_calls += 1
        if validation_calls == 1:
            assert schedule.has_open_identity(schedule.stage_identity)
        else:
            assert schedule.has_open_target_identity(schedule.stage_identity)

    committed_identity: list[tuple[int, int]] = []
    result = provenance.atomic_create_bytes(
        Path("/sandbox/result.json"),
        b"created",
        _validator=validate,
        _committed_identity=committed_identity,
    )

    assert result == Path("/sandbox/result.json")
    assert validation_calls == 2
    assert schedule.directory_sync_calls == 1
    assert schedule.link_calls == 0
    assert committed_identity == [schedule.stage_identity]
    assert schedule.descriptors == {}


def test_posix_atomic_fsync_failure_does_not_report_a_stale_target_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    schedule = _ScheduledPosixFilePublication(rename_mode="sync_missing_raise")
    schedule.install(monkeypatch)
    committed_identity: list[tuple[int, int]] = []

    with pytest.raises(provenance.AtomicCommitUncertainError) as captured:
        provenance.atomic_create_bytes(
            Path("/sandbox/result.json"),
            b"created",
            _committed_identity=committed_identity,
        )

    assert captured.value.committed is True
    assert isinstance(captured.value.__cause__, OSError)
    assert captured.value.retained_path is None
    assert committed_identity == []
    assert schedule.descriptors == {}


@pytest.mark.parametrize(
    ("rename_mode", "expected_committed", "expected_cause"),
    [
        ("raise_after", True, RuntimeError),
        ("raise_before", False, RuntimeError),
        ("collision", False, FileExistsError),
        ("missing_both", True, RuntimeError),
    ],
)
def test_posix_atomic_create_reconciles_native_rename_exceptions(
    monkeypatch: pytest.MonkeyPatch,
    rename_mode: str,
    expected_committed: bool,
    expected_cause: type[BaseException],
) -> None:
    schedule = _ScheduledPosixFilePublication(rename_mode=rename_mode)
    schedule.install(monkeypatch)

    expected_error = (
        provenance.AtomicCommitUncertainError
        if expected_committed
        else provenance.AtomicCleanupRetainedError
    )
    with pytest.raises(expected_error) as captured:
        provenance.atomic_create_bytes(Path("/sandbox/result.json"), b"created")

    assert captured.value.committed is expected_committed
    assert isinstance(captured.value.__cause__, expected_cause)
    if rename_mode == "raise_after":
        assert captured.value.retained_path == Path("/sandbox/result.json")
        assert schedule.cleanup_calls == []
    elif rename_mode in {"raise_before", "collision"}:
        assert captured.value.retained_path == Path(
            "/sandbox/.almondlab-quarantine-scheduled"
        )
        if rename_mode == "collision":
            assert (
                schedule.nodes[schedule.target_name]["identity"]
                == schedule.attacker_identity
            )
        else:
            assert schedule.target_name not in schedule.nodes
    else:
        assert captured.value.retained_path is None
    assert schedule.descriptors == {}


@pytest.mark.parametrize(
    ("rename_mode", "expected_committed"),
    [
        ("replace_existing", True),
        ("replace_raise_after", True),
        ("replace_raise_before", False),
        ("replace_post_swap", True),
    ],
)
def test_posix_atomic_write_reconciles_replace_and_preserves_existing_on_failure(
    monkeypatch: pytest.MonkeyPatch,
    rename_mode: str,
    expected_committed: bool,
) -> None:
    schedule = _ScheduledPosixFilePublication(rename_mode=rename_mode)
    schedule.install(monkeypatch)

    if rename_mode == "replace_existing":
        result = provenance.atomic_write_bytes(
            Path("/sandbox/result.json"), b"replacement"
        )
        assert result == Path("/sandbox/result.json")
        assert schedule.nodes["result.json"]["payload"] == b"replacement"
        assert schedule.replaced_target_node is not None
        assert schedule.replaced_target_node["payload"] == b"established"
    else:
        error_type = (
            provenance.AtomicCommitUncertainError
            if expected_committed
            else provenance.AtomicCleanupRetainedError
        )
        with pytest.raises(error_type) as captured:
            provenance.atomic_write_bytes(
                Path("/sandbox/result.json"), b"replacement"
            )
        assert captured.value.committed is expected_committed
        if rename_mode == "replace_post_swap":
            assert schedule.nodes["result.json"]["identity"] == (
                schedule.attacker_identity
            )
        elif expected_committed:
            assert schedule.nodes["result.json"]["payload"] == b"replacement"
        else:
            assert schedule.nodes["result.json"]["payload"] == b"established"
    assert schedule.descriptors == {}


@pytest.mark.parametrize("exclusive", [False, True])
def test_posix_atomic_precommit_cleanup_retention_fails_safely(
    monkeypatch: pytest.MonkeyPatch, exclusive: bool
) -> None:
    retained_name = ".almondlab-quarantine-retained-temp"
    closed_descriptors: list[int] = []

    def fake_open_directory(path: Path, *, create: bool = False) -> int:
        del path, create
        return 50

    def fake_open(
        name: str,
        flags: int,
        mode: int = 0o777,
        *,
        dir_fd: int | None = None,
    ) -> int:
        del name, flags, mode
        assert dir_fd == 50
        return 51

    def fail_write(descriptor: int, mode: str) -> object:
        del descriptor, mode
        raise OSError("forced precommit failure")

    def retain_cleanup(
        parent_descriptor: int,
        name: str,
        expected_identity: tuple[int, int],
    ) -> bool:
        del parent_descriptor, name, expected_identity
        raise provenance._RetainedCleanupIdentityError(retained_name)

    monkeypatch.setattr(provenance, "_open_directory_descriptor", fake_open_directory)
    monkeypatch.setattr(
        provenance, "_require_path_matches_descriptor", lambda *args: (1, 2)
    )
    monkeypatch.setattr(provenance.os, "open", fake_open)
    monkeypatch.setattr(
        provenance,
        "_require_descriptor_object",
        lambda descriptor, expected_identity, is_directory: (3, 4),
    )
    monkeypatch.setattr(provenance.os, "fdopen", fail_write)
    monkeypatch.setattr(provenance, "_unlink_name_if_identity", retain_cleanup)

    def close_parent(descriptor: int) -> None:
        closed_descriptors.append(descriptor)

    monkeypatch.setattr(provenance.os, "close", close_parent)

    with pytest.raises(provenance.AtomicCleanupRetainedError) as captured:
        provenance._atomic_commit_posix(
            Path("/sandbox/result.json"),
            b"created",
            expected_parent_identity=None,
            exclusive=exclusive,
            validator=None,
        )

    assert captured.value.committed is False
    assert captured.value.retained_path == Path("/sandbox") / retained_name
    assert captured.value.__cause__ is not None
    assert "forced precommit failure" in str(captured.value.__cause__)
    assert closed_descriptors == [51, 50]


def test_posix_atomic_identity_capture_failure_reports_retained_temp(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    temporary_name = ".result.json." + "0" * 32 + ".tmp"
    cleanup_called = False
    closed_descriptors: list[int] = []

    monkeypatch.setattr(provenance, "_open_directory_descriptor", lambda *args, **kwargs: 50)
    monkeypatch.setattr(
        provenance, "_require_path_matches_descriptor", lambda *args: (1, 2)
    )
    monkeypatch.setattr(provenance.os, "open", lambda *args, **kwargs: 51)
    monkeypatch.setattr(
        provenance,
        "_require_descriptor_object",
        lambda descriptor, expected_identity, is_directory: (_ for _ in ()).throw(
            OSError("identity unavailable")
        ),
    )
    monkeypatch.setattr(provenance.secrets, "token_hex", lambda count: "0" * 32)

    def refuse_unverified_cleanup(*args: object, **kwargs: object) -> bool:
        nonlocal cleanup_called
        cleanup_called = True
        return True

    monkeypatch.setattr(provenance, "_unlink_name_if_identity", refuse_unverified_cleanup)
    monkeypatch.setattr(
        provenance.os, "close", lambda descriptor: closed_descriptors.append(descriptor)
    )

    with pytest.raises(provenance.AtomicCleanupRetainedError) as captured:
        provenance._atomic_commit_posix(
            Path("/sandbox/result.json"),
            b"created",
            expected_parent_identity=None,
            exclusive=True,
            validator=None,
        )

    assert captured.value.committed is False
    assert captured.value.retained_path == Path("/sandbox") / temporary_name
    assert cleanup_called is False
    assert closed_descriptors == [51, 50]


def test_posix_atomic_postcommit_retention_reports_consumed_temp_only_as_target(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cleanup_names: list[str] = []
    validation_calls = 0

    class FakeHandle:
        def __enter__(self) -> "FakeHandle":
            return self

        def __exit__(self, *args: object) -> None:
            return None

        def write(self, payload: bytes) -> None:
            assert payload == b"created"

        def flush(self) -> None:
            return None

        def fileno(self) -> int:
            return 51

    def validate() -> None:
        nonlocal validation_calls
        validation_calls += 1
        if validation_calls == 2:
            raise ValueError("forced postcommit validation failure")

    def retain_cleanup(
        parent_descriptor: int,
        name: str,
        expected_identity: tuple[int, int],
    ) -> bool:
        del parent_descriptor, expected_identity
        cleanup_names.append(name)
        if name == "result.json":
            raise provenance._RetainedCleanupIdentityError(
                ".almondlab-quarantine-retained-target"
            )
        raise provenance._RetainedCleanupIdentityError(
            ".almondlab-quarantine-retained-temp"
        )

    monkeypatch.setattr(provenance, "_open_directory_descriptor", lambda *args, **kwargs: 50)
    monkeypatch.setattr(
        provenance, "_require_path_matches_descriptor", lambda *args: (1, 2)
    )
    monkeypatch.setattr(provenance.os, "open", lambda *args, **kwargs: 51)
    monkeypatch.setattr(
        provenance,
        "_require_descriptor_object",
        lambda descriptor, expected_identity, is_directory: (3, 4),
    )
    monkeypatch.setattr(provenance.os, "fdopen", lambda descriptor, mode: FakeHandle())
    monkeypatch.setattr(provenance.os, "fsync", lambda descriptor: None)
    monkeypatch.setattr(
        provenance, "_rename_name_noreplace", lambda *args, **kwargs: None
    )
    observation_calls = 0

    def observe_published_target(
        parent_descriptor: int,
        name: str,
        expected_identity: tuple[int, int],
        *,
        is_directory: bool,
    ) -> provenance._PosixNameObservation:
        nonlocal observation_calls
        del parent_descriptor, expected_identity, is_directory
        observation_calls += 1
        if observation_calls == 1:
            assert name.startswith(".result.json.")
            return provenance._PosixNameObservation("exact", 61, (3, 4))
        if observation_calls == 2:
            assert name == "result.json"
            return provenance._PosixNameObservation("exact", 62, (3, 4))
        assert name.startswith(".result.json.")
        return provenance._PosixNameObservation("absent")

    monkeypatch.setattr(provenance, "_observe_posix_name", observe_published_target)
    monkeypatch.setattr(provenance.os, "close", lambda descriptor: None)
    monkeypatch.setattr(provenance, "_unlink_name_if_identity", retain_cleanup)

    with pytest.raises(provenance.AtomicCommitUncertainError) as captured:
        provenance._atomic_commit_posix(
            Path("/sandbox/result.json"),
            b"created",
            expected_parent_identity=None,
            exclusive=True,
            validator=validate,
        )

    assert captured.value.committed is True
    assert captured.value.retained_paths == (
        Path("/sandbox/.almondlab-quarantine-retained-target"),
    )
    assert cleanup_names == ["result.json"]


@pytest.mark.skipif(os.name != "nt", reason="Windows handle-relative cleanup")
def test_windows_identity_checked_unlink_never_deletes_attacker_replacement(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "temporary"
    displaced = tmp_path / "displaced"
    target.write_bytes(b"original")
    metadata = target.stat(follow_symlinks=False)
    expected = (metadata.st_dev, metadata.st_ino)
    replacement = b"attacker replacement"
    attacked = False
    real_path_stat = Path.stat
    real_handle_identity = getattr(provenance, "_windows_handle_identity", None)

    def attack() -> None:
        nonlocal attacked
        if attacked:
            return
        attacked = True
        target.rename(displaced)
        target.write_bytes(replacement)

    def attacked_path_stat(
        path: Path, *args: object, **kwargs: object
    ) -> os.stat_result:
        result = real_path_stat(path, *args, **kwargs)
        if path == target:
            attack()
        return result

    def attacked_handle_identity(handle: object) -> tuple[int, int]:
        assert real_handle_identity is not None
        result = real_handle_identity(handle)
        attack()
        return result

    monkeypatch.setattr(Path, "stat", attacked_path_stat)
    if real_handle_identity is not None:
        monkeypatch.setattr(
            provenance, "_windows_handle_identity", attacked_handle_identity
        )

    provenance._unlink_path_if_identity(target, expected)

    assert attacked is True
    assert target.read_bytes() == replacement


@pytest.mark.skipif(os.name != "nt", reason="Windows handle-relative cleanup")
def test_windows_identity_checked_rmdir_never_deletes_attacker_replacement(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "temporary"
    displaced = tmp_path / "displaced"
    target.mkdir()
    metadata = target.stat(follow_symlinks=False)
    expected = (metadata.st_dev, metadata.st_ino)
    attacked = False
    real_path_stat = Path.stat
    real_handle_identity = getattr(provenance, "_windows_handle_identity", None)

    def attack() -> None:
        nonlocal attacked
        if attacked:
            return
        attacked = True
        target.rename(displaced)
        target.mkdir()

    def attacked_path_stat(
        path: Path, *args: object, **kwargs: object
    ) -> os.stat_result:
        result = real_path_stat(path, *args, **kwargs)
        if path == target:
            attack()
        return result

    def attacked_handle_identity(handle: object) -> tuple[int, int]:
        assert real_handle_identity is not None
        result = real_handle_identity(handle)
        attack()
        return result

    monkeypatch.setattr(Path, "stat", attacked_path_stat)
    if real_handle_identity is not None:
        monkeypatch.setattr(
            provenance, "_windows_handle_identity", attacked_handle_identity
        )

    provenance._rmdir_path_if_identity(target, expected)

    assert attacked is True
    assert target.is_dir()


def _assert_posix_quarantine_retains_post_fstat_replacement(
    monkeypatch: pytest.MonkeyPatch, *, is_directory: bool
) -> None:
    """Exercise the real cleanup state machine with deterministic POSIX syscalls."""

    expected_identity = (101, 202)
    original_descriptor = 10
    quarantine_descriptor = 11
    expected_mode = stat.S_IFDIR if is_directory else stat.S_IFREG
    quarantine_name = ".almondlab-quarantine-" + "0" * 32
    active_quarantine_identity = "expected"
    pathname_deletes: list[tuple[str, str]] = []

    def fake_open(
        name: str,
        flags: int,
        mode: int = 0o777,
        *,
        dir_fd: int | None = None,
    ) -> int:
        del flags, mode
        assert dir_fd == 99
        if name == "temporary":
            return original_descriptor
        assert name == quarantine_name
        return quarantine_descriptor

    def fake_fstat(descriptor: int) -> SimpleNamespace:
        nonlocal active_quarantine_identity
        assert descriptor in {original_descriptor, quarantine_descriptor}
        metadata = SimpleNamespace(
            st_dev=expected_identity[0],
            st_ino=expected_identity[1],
            st_mode=expected_mode,
        )
        if descriptor == quarantine_descriptor:
            # The kernel has returned the expected handle metadata.  Before a
            # later pathname delete could run, an attacker replaces that name.
            active_quarantine_identity = "attacker replacement"
        return metadata

    def fake_rename(
        parent_descriptor: int, source_name: str, target_name: str
    ) -> None:
        assert (parent_descriptor, source_name, target_name) == (
            99,
            "temporary",
            quarantine_name,
        )

    def record_unlink(
        name: str, *, dir_fd: int | None = None
    ) -> None:
        assert dir_fd == 99
        pathname_deletes.append((name, active_quarantine_identity))

    def record_rmdir(name: str, *, dir_fd: int | None = None) -> None:
        assert dir_fd == 99
        pathname_deletes.append((name, active_quarantine_identity))

    monkeypatch.setattr(provenance.os, "name", "posix")
    monkeypatch.setattr(provenance.os, "open", fake_open)
    monkeypatch.setattr(provenance.os, "fstat", fake_fstat)
    monkeypatch.setattr(provenance.os, "close", lambda descriptor: None)
    monkeypatch.setattr(provenance.os, "unlink", record_unlink)
    monkeypatch.setattr(provenance.os, "rmdir", record_rmdir)
    monkeypatch.setattr(provenance.secrets, "token_hex", lambda count: "0" * 32)
    monkeypatch.setattr(provenance, "_rename_name_noreplace", fake_rename)

    with pytest.raises(provenance._RetainedCleanupIdentityError) as captured:
        provenance._remove_name_via_private_quarantine(
            99,
            "temporary",
            expected_identity,
            is_directory=is_directory,
        )

    assert captured.value.retained_name == quarantine_name
    assert active_quarantine_identity == "attacker replacement"
    assert pathname_deletes == []


def test_posix_file_quarantine_never_path_deletes_post_fstat_replacement(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _assert_posix_quarantine_retains_post_fstat_replacement(
        monkeypatch, is_directory=False
    )


def test_posix_directory_quarantine_never_path_deletes_post_fstat_replacement(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _assert_posix_quarantine_retains_post_fstat_replacement(
        monkeypatch, is_directory=True
    )


@pytest.mark.skipif(os.name == "nt", reason="POSIX descriptor-relative cleanup")
def test_posix_identity_checked_unlink_quarantines_racing_replacement(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "temporary"
    displaced = tmp_path / "displaced"
    target.write_bytes(b"expected temporary")
    metadata = target.stat(follow_symlinks=False)
    expected = (metadata.st_dev, metadata.st_ino)
    attacked = False
    quarantine: Path | None = None
    real_rename = provenance._rename_directory_noreplace

    def replace_immediately_before_quarantine(
        parent_descriptor: int, source_name: str, target_name: str
    ) -> None:
        nonlocal attacked, quarantine
        attacked = True
        target.rename(displaced)
        target.write_bytes(b"attacker replacement")
        quarantine = tmp_path / target_name
        real_rename(parent_descriptor, source_name, target_name)

    monkeypatch.setattr(
        provenance,
        "_rename_name_noreplace",
        replace_immediately_before_quarantine,
        raising=False,
    )
    parent_descriptor = provenance._open_directory_descriptor(tmp_path)
    try:
        with pytest.raises(provenance._RetainedCleanupIdentityError) as captured:
            provenance._unlink_name_if_identity(
                parent_descriptor, target.name, expected
            )
    finally:
        os.close(parent_descriptor)

    assert attacked is True
    assert displaced.read_bytes() == b"expected temporary"
    assert quarantine is not None
    assert captured.value.retained_name == quarantine.name
    assert quarantine.read_bytes() == b"attacker replacement"


@pytest.mark.skipif(os.name == "nt", reason="POSIX descriptor-relative cleanup")
def test_posix_identity_checked_rmdir_quarantines_racing_replacement(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "temporary"
    displaced = tmp_path / "displaced"
    target.mkdir()
    metadata = target.stat(follow_symlinks=False)
    expected = (metadata.st_dev, metadata.st_ino)
    attacked = False
    quarantine: Path | None = None
    real_rename = provenance._rename_directory_noreplace

    def replace_immediately_before_quarantine(
        parent_descriptor: int, source_name: str, target_name: str
    ) -> None:
        nonlocal attacked, quarantine
        attacked = True
        target.rename(displaced)
        target.mkdir()
        (target / "sentinel.txt").write_bytes(b"attacker replacement")
        quarantine = tmp_path / target_name
        real_rename(parent_descriptor, source_name, target_name)

    monkeypatch.setattr(
        provenance,
        "_rename_name_noreplace",
        replace_immediately_before_quarantine,
        raising=False,
    )
    parent_descriptor = provenance._open_directory_descriptor(tmp_path)
    try:
        with pytest.raises(provenance._RetainedCleanupIdentityError) as captured:
            provenance._rmdir_name_if_identity(
                parent_descriptor, target.name, expected
            )
    finally:
        os.close(parent_descriptor)

    assert attacked is True
    assert displaced.is_dir()
    assert quarantine is not None
    assert captured.value.retained_name == quarantine.name
    assert (quarantine / "sentinel.txt").read_bytes() == b"attacker replacement"


@pytest.mark.skipif(os.name == "nt", reason="POSIX descriptor-relative cleanup")
def test_posix_cleanup_retains_and_reports_verified_quarantine(
    tmp_path: Path,
) -> None:
    target = tmp_path / "temporary"
    target.write_bytes(b"retained expected identity")
    metadata = target.stat(follow_symlinks=False)
    expected = (metadata.st_dev, metadata.st_ino)
    with pytest.raises(provenance.AtomicCommitUncertainError) as captured:
        provenance._unlink_path_if_identity(target, expected)

    assert captured.value.retained_path is not None
    assert captured.value.retained_path.read_bytes() == b"retained expected identity"
    assert not target.exists()


def test_schema_integer_type_uses_draft_2020_12_mathematical_semantics() -> None:
    integer_schema = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "type": "integer",
    }
    noninteger_number_schema = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "type": "number",
        "not": {"type": "integer"},
    }

    provenance.validate_json_schema_subset(integer_schema, 1.0)
    provenance.validate_json_schema_subset(noninteger_number_schema, 1.5)
    with pytest.raises(ValueError, match="schema"):
        provenance.validate_json_schema_subset(noninteger_number_schema, 1.0)


def test_manifest_pool_size_attack_is_rejected_before_numpy_allocation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    schema_path = Path(__file__).parents[1] / "schemas" / "run_manifest.schema.json"
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    document = _golden_manifest_document()
    root = document["seed_tree"]["root"]  # type: ignore[index]
    root["pool_size"] = provenance.JSON_INTEGER_MAX  # type: ignore[index]
    child = root["children"]["simulation"]  # type: ignore[index]
    child["pool_size"] = provenance.JSON_INTEGER_MAX  # type: ignore[index]
    invoked = False

    def refuse_numpy_allocation(*args: object, **kwargs: object) -> object:
        nonlocal invoked
        invoked = True
        raise AssertionError("NumPy allocation must not be attempted")

    monkeypatch.setattr(provenance.np.random, "SeedSequence", refuse_numpy_allocation)

    with pytest.raises(ValueError, match="schema|pool_size|pool size"):
        provenance.validate_run_manifest_document(schema, document)

    assert invoked is False


def test_run_manifest_schema_accepts_document_and_rejects_boundary_corruptions() -> None:
    schema_path = Path(__file__).parents[1] / "schemas" / "run_manifest.schema.json"
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    document = _golden_manifest_document()

    assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
    assert schema["additionalProperties"] is False
    provenance.check_json_schema_subset(schema)
    provenance.validate_json_schema_subset(schema, document)

    corruptions = [
        {**document, "root_seed": True},
        {**document, "root_seed": "42"},
        {**document, "root_seed": 2**53},
        {**document, "deterministic_demo_id": 1},
        {**document, "started_at": "2026-08-12T12:00:00+00:00"},
        {**document, "started_at": "2026-08-12T12:00:00Z\n"},
        {**document, "started_at": "2026-02-30T12:00:00Z"},
        {
            **document,
            "git": {**document["git"], "dirty": "false"},  # type: ignore[dict-item]
        },
        {
            **document,
            "git": {  # type: ignore[dict-item]
                **document["git"],
                "commit_sha": "4" * 40 + "\n",
            },
        },
        {
            **document,
            "git": {  # type: ignore[dict-item]
                **document["git"],
                "state": "available",
                "commit_sha": None,
                "dirty": None,
                "status_sha256": None,
                "unavailable_reason": None,
                "unavailable": [],
            },
        },
        {
            **document,
            "lockfile": {  # type: ignore[dict-item]
                **document["lockfile"],
                "state": "available",
                "sha256": None,
                "size_bytes": None,
            },
        },
        {**document, "config_hashes": {"": "1" * 64}},
        {**document, "config_hashes": {"config.yaml": "1" * 64 + "\n"}},
        {**document, "config_hashes": {"../config.yaml": "1" * 64}},
        {**document, "config_hashes": {"configs//config.yaml": "1" * 64}},
        {**document, "config_hashes": {"configs/con.txt": "1" * 64}},
        {**document, "config_hashes": {"configs/name.": "1" * 64}},
        {**document, "config_hashes": {"a" * 256: "1" * 64}},
        {**document, "config_hashes": {"é" * 128: "1" * 64}},
        {**document, "run_id": "CON"},
        {**document, "run_id": "con.txt"},
        {**document, "run_id": "name."},
        {**document, "run_id": "a..b"},
        {**document, "run_id": "valid\n"},
        {**document, "bayesian_raw_draws": {"chain": [[10**5000]]}},
        {**document, "bayesian_raw_draws": {"chain": [[float(2**53)]]}},
        {
            **document,
            "lockfile": {  # type: ignore[dict-item]
                **document["lockfile"],
                "path": "C:/outside/uv.lock",
            },
        },
        {**document, "model_versions": {"": "1.0.0"}},
        {**document, "evidence_labels": ["synthetic_only", "synthetic_only"]},
        {
            **document,
            "seed_tree": {  # type: ignore[dict-item]
                **document["seed_tree"],
                "root": {
                    **document["seed_tree"]["root"],  # type: ignore[index]
                    "state": [0, 0, 0, 2**32],
                },
            },
        },
        {**document, "unexpected": "field"},
    ]

    for corrupted in corruptions:
        with pytest.raises(ValueError, match="schema"):
            provenance.validate_json_schema_subset(schema, corrupted)

    with pytest.raises(ValueError, match="unsupported schema keyword"):
        provenance.check_json_schema_subset({**schema, "inventedKeyword": True})


@pytest.mark.parametrize(
    "reserved_path", ["RUN_MANIFEST.JSON", "nested/Run_Manifest.JsOn"]
)
def test_run_manifest_schema_rejects_casefolded_reserved_artifact_components(
    reserved_path: str,
) -> None:
    schema_path = Path(__file__).parents[1] / "schemas" / "run_manifest.schema.json"
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    document = _golden_manifest_document()
    document["artifact_hashes"] = {reserved_path: "1" * 64}

    with pytest.raises(ValueError, match="schema"):
        provenance.validate_json_schema_subset(schema, document)


@pytest.mark.parametrize(
    "reserved_path", ["RUN_MANIFEST.JSON", "nested/Run_Manifest.JsOn"]
)
def test_run_manifest_document_validator_rejects_casefolded_reserved_artifacts(
    reserved_path: str,
) -> None:
    schema_path = Path(__file__).parents[1] / "schemas" / "run_manifest.schema.json"
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    schema["properties"]["artifact_hashes"] = {  # type: ignore[index]
        "$ref": "#/$defs/digest_map"
    }
    document = _golden_manifest_document()
    document["artifact_hashes"] = {reserved_path: "1" * 64}

    with pytest.raises(ValueError, match="hash itself|reserved"):
        provenance.validate_run_manifest_document(schema, document)


def test_run_manifest_document_validator_checks_cross_field_semantics() -> None:
    schema_path = Path(__file__).parents[1] / "schemas" / "run_manifest.schema.json"
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    document = _golden_manifest_document()

    provenance.validate_run_manifest_document(schema, document)

    wrong_seed = copy.deepcopy(document)
    wrong_seed["root_seed"] = 43
    wrong_child_name = copy.deepcopy(document)
    wrong_child_name["seed_tree"]["root"]["children"]["simulation"]["name"] = (  # type: ignore[index]
        "analysis"
    )
    reversed_times = copy.deepcopy(document)
    reversed_times["ended_at"] = "2026-08-12T11:00:00Z"
    wrong_science_hash = copy.deepcopy(document)
    wrong_science_hash["canonical_science_hash"] = "0" * 64
    wrong_manifest_hash = copy.deepcopy(document)
    wrong_manifest_hash["manifest_hash"] = "0" * 64

    for corrupted in (
        wrong_seed,
        wrong_child_name,
        reversed_times,
        wrong_science_hash,
        wrong_manifest_hash,
    ):
        with pytest.raises(ValueError, match="manifest"):
            provenance.validate_run_manifest_document(schema, corrupted)


def test_manifest_matches_independent_golden_document_and_hashes() -> None:
    manifest = _manifest()

    assert manifest.to_dict() == _golden_manifest_document()
    assert (
        manifest.canonical_science_hash
        == "a996babe2890e75893eb1d51cc5499acd3d7cd4eaad4e214a10688bf73a00c40"
    )
    assert (
        manifest.manifest_hash
        == "b235d72389fa7ef81433b11de1657ead4803907aba44f674caca0df2db121a78"
    )


def _git(repository: Path, *arguments: str) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        ["git", *arguments],
        cwd=repository,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


def _directory_link_or_skip(target: Path, link: Path) -> None:
    try:
        link.symlink_to(target, target_is_directory=True)
    except (OSError, NotImplementedError) as error:
        if sys.platform != "win32":
            pytest.skip(f"directory symlinks unavailable: {error}")
        result = subprocess.run(
            ["cmd.exe", "/d", "/c", "mklink", "/J", str(link), str(target)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        if result.returncode != 0:
            pytest.skip("directory symlinks and junctions are unavailable")


def _remove_directory_link(link: Path) -> None:
    if getattr(link, "is_junction", lambda: False)():
        link.rmdir()
    else:
        link.unlink()


def _golden_manifest_document() -> dict[str, object]:
    return {
        "schema_version": "1.1.0",
        "run_id": "20260812T120000Z-123456789abc",
        "deterministic_demo_id": False,
        "root_seed": 42,
        "creation_config_sha256": "1" * 64,
        "seed_tree": {
            "algorithm": "numpy.random.SeedSequence",
            "root_seed": 42,
            "root": {
                "name": "root",
                "entropy": 42,
                "spawn_key": [],
                "pool_size": 4,
                "n_children_spawned": 1,
                "state": [3444837047, 2669555309, 2046530742, 3581440988],
                "children": {
                    "simulation": {
                        "name": "simulation",
                        "entropy": 42,
                        "spawn_key": [0],
                        "pool_size": 4,
                        "n_children_spawned": 0,
                        "state": [2684470948, 3757501821, 1691896351, 1126406280],
                        "children": {},
                    }
                },
            },
        },
        "started_at": "2026-08-12T12:00:00Z",
        "ended_at": "2026-08-12T14:00:00Z",
        "git": {
            "commit_sha": "4" * 40,
            "dirty": False,
            "status_sha256": "5" * 64,
            "state": "available",
            "unavailable_reason": None,
            "unavailable": [],
        },
        "lockfile": {
            "path": "uv.lock",
            "sha256": "6" * 64,
            "size_bytes": 123,
            "state": "available",
            "unavailable_reason": None,
        },
        "config_hashes": {"configs/experiment.yaml": "1" * 64},
        "input_hashes": {"data/input.csv": "2" * 64},
        "artifact_hashes": {"tables/result.csv": "3" * 64},
        "model_versions": {"chemistry": "1.0.0"},
        "runtime": {
            "interpreter_path": "C:/Python312/python.exe",
            "python_version": "3.12.13",
            "python_implementation": "CPython",
            "os_text": "test operating system",
        },
        "evidence_labels": ["synthetic_only"],
        "bayesian_raw_draws": {"chain": [[0.25, 0.5]]},
        "canonical_science_hash": (
            "a996babe2890e75893eb1d51cc5499acd3d7cd4eaad4e214a10688bf73a00c40"
        ),
        "manifest_hash": (
            "b235d72389fa7ef81433b11de1657ead4803907aba44f674caca0df2db121a78"
        ),
    }


def _manifest(**changes: object) -> provenance.RunManifest:
    root_seed = changes.pop("root_seed", 42)
    seed_tree = changes.pop(
        "seed_tree",
        provenance.SeedTree.from_seed(42, {"simulation": None}),
    )
    values: dict[str, object] = {
        "run_id": "20260812T120000Z-123456789abc",
        "deterministic_demo_id": False,
        "root_seed": root_seed,
        "creation_config_sha256": "1" * 64,
        "seed_tree": seed_tree,
        "started_at": datetime(2026, 8, 12, 12, tzinfo=timezone.utc),
        "ended_at": datetime(2026, 8, 12, 14, tzinfo=timezone.utc),
        "git": provenance.GitProvenance(
            commit_sha="4" * 40,
            dirty=False,
            status_sha256="5" * 64,
            state="available",
            unavailable_reason=None,
            unavailable=(),
        ),
        "lockfile": provenance.FileProvenance(
            path="uv.lock",
            sha256="6" * 64,
            size_bytes=123,
            state="available",
            unavailable_reason=None,
        ),
        "config_hashes": {"configs/experiment.yaml": "1" * 64},
        "input_hashes": {"data/input.csv": "2" * 64},
        "artifact_hashes": {"tables/result.csv": "3" * 64},
        "model_versions": {"chemistry": "1.0.0"},
        "runtime": provenance.RuntimeProvenance(
            interpreter_path="C:/Python312/python.exe",
            python_version="3.12.13",
            python_implementation="CPython",
            os_text="test operating system",
        ),
        "evidence_labels": ("synthetic_only",),
        "bayesian_raw_draws": {"chain": [[0.25, 0.5]]},
    }
    values.update(changes)
    return provenance.RunManifest(**values)  # type: ignore[arg-type]
