from __future__ import annotations

from importlib import resources
from pathlib import Path


CANONICAL_FIXTURES = frozenset(
    {
        "all_conserved_entities.yaml",
        "chained_transaction_ids.yaml",
        "chemistry_handcheck.yaml",
        "conservation_case_manifest.candidates.json",
        "conservation_case_manifest.yaml",
        "entity_units_density.yaml",
        "internal_plant_flux_cap.yaml",
        "ions_conservative.yaml",
        "no_purge.yaml",
        "perfect_na_exclusion.yaml",
        "ro_remineralization.yaml",
        "sufficient_purge.yaml",
        "water_one_day.yaml",
    }
)
CANONICAL_POLICIES = frozenset({"thresholds.yaml", "verification.yaml"})


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
