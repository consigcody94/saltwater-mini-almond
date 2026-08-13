from __future__ import annotations

import copy
from dataclasses import FrozenInstanceError, replace
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
from types import MappingProxyType

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

    with pytest.raises(RuntimeError, match="replaced|identity"):
        provenance.RunDirectory.create(
            runs_root,
            config_sha256="1" * 64,
            root_seed=42,
            deterministic_run_id="SYN_demo",
        )

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


def test_run_manifest_rejects_reserved_self_artifact_hash() -> None:
    with pytest.raises(ValueError, match="run_manifest.json"):
        _manifest(artifact_hashes={"run_manifest.json": "1" * 64})


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
        {**document, "run_id": "CON"},
        {**document, "run_id": "con.txt"},
        {**document, "run_id": "name."},
        {**document, "run_id": "a..b"},
        {**document, "run_id": "valid\n"},
        {**document, "bayesian_raw_draws": {"chain": [[10**5000]]}},
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
