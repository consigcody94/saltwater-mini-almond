from __future__ import annotations

import shutil
import subprocess
from importlib import resources
from pathlib import Path


CANONICAL_FIXTURES = frozenset(
    {
        "all_conserved_entities.yaml",
        "chained_transaction_ids.yaml",
        "candidate_effects.yaml",
        "chemistry_handcheck.yaml",
        "conservation_case_manifest.candidates.json",
        "conservation_case_manifest.yaml",
        "entity_units_density.yaml",
        "internal_plant_flux_cap.yaml",
        "ions_conservative.yaml",
        "no_purge.yaml",
        "perfect_na_exclusion.yaml",
        "ro_remineralization.yaml",
        "paper1_small.yaml",
        "shared_reservoir_trap.csv",
        "sufficient_purge.yaml",
        "water_one_day.yaml",
    }
)
CANONICAL_POLICIES = frozenset({"thresholds.yaml", "verification.yaml"})
HASH_LOCKED_ROOT_CONFIGS = CANONICAL_POLICIES | {"model_domains.yaml"}


def test_authoring_and_runtime_fixture_sets_are_exact_byte_mirrors() -> None:
    root = Path(__file__).parents[1]
    authoring = root / "tests" / "fixtures"
    packaged = resources.files("almondlab.resources").joinpath("fixtures")
    assert {path.name for path in authoring.iterdir() if path.is_file()} == CANONICAL_FIXTURES
    assert {path.name for path in packaged.iterdir() if path.is_file()} == CANONICAL_FIXTURES
    for name in CANONICAL_FIXTURES:
        assert (authoring / name).read_bytes() == packaged.joinpath(name).read_bytes()


def test_authoring_and_runtime_policy_sets_are_exact_byte_mirrors() -> None:
    root = Path(__file__).parents[1]
    authoring = root / "configs"
    packaged = resources.files("almondlab.resources").joinpath("configs")
    assert {
        path.name for path in packaged.iterdir() if path.is_file()
    } == CANONICAL_POLICIES | {"model_domains.yaml"}
    for name in CANONICAL_POLICIES:
        assert (authoring / name).read_bytes() == packaged.joinpath(name).read_bytes()


def test_hash_locked_resources_materialize_lf_under_windows_autocrlf(
    tmp_path: Path,
) -> None:
    root = Path(__file__).parents[1]
    repository = tmp_path / "repository"
    repository.mkdir()
    shutil.copy2(root / ".gitattributes", repository / ".gitattributes")
    relative_files = tuple(
        (root / "configs" / name).relative_to(root)
        for name in sorted(HASH_LOCKED_ROOT_CONFIGS)
    ) + tuple(
        path.relative_to(root)
        for directory in (
            root / "src" / "almondlab" / "resources" / "configs",
            root / "src" / "almondlab" / "resources" / "fixtures",
            root / "tests" / "fixtures",
        )
        for path in directory.iterdir()
        if path.is_file() and path.suffix in {".yaml", ".json", ".csv"}
    )
    expected: dict[Path, bytes] = {}
    for relative in relative_files:
        destination = repository / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(root / relative, destination)
        expected[relative] = (root / relative).read_bytes()
    unrelated_config = repository / "configs" / "not-verifier-owned.yaml"
    unrelated_config.write_bytes(b"scope_guard: true\n")
    subprocess.run(
        ["git", "init"], cwd=repository, check=True, capture_output=True
    )
    subprocess.run(
        ["git", "add", "."], cwd=repository, check=True, capture_output=True
    )
    attribute = subprocess.run(
        ["git", "check-attr", "eol", "--", "configs/not-verifier-owned.yaml"],
        cwd=repository,
        check=True,
        capture_output=True,
        text=True,
    )
    assert attribute.stdout.endswith("eol: unspecified\n")
    materialized = tmp_path / "materialized"
    materialized.mkdir()
    subprocess.run(
        [
            "git",
            "-c",
            "core.autocrlf=true",
            "checkout-index",
            "--all",
            "--force",
            f"--prefix={materialized.as_posix()}/",
        ],
        cwd=repository,
        check=True,
        capture_output=True,
    )

    for relative, exact_bytes in expected.items():
        received = (materialized / relative).read_bytes()
        assert received == exact_bytes
        assert b"\r\n" not in received
