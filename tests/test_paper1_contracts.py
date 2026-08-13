import math
from pathlib import Path

import pytest

from almondlab.errors import AlmondLabError
from almondlab.paper1_contracts import (
    AnalysisPopulation,
    CandidateState,
    H3Rule,
    ScientificLabel,
    SyntheticScenarioConfig,
    load_candidate_specs,
    load_paper1_design,
    load_synthetic_scenarios,
)


CONFIGS = Path(__file__).parents[1] / "configs"


def test_candidate_registry_freezes_order_h3_rules_and_decision_thresholds() -> None:
    """Catches a reordered candidate or changed registered H3/selection boundary."""
    registry = load_candidate_specs(CONFIGS / "candidates.yaml")

    assert [candidate.candidate_id for candidate in registry.candidates] == [
        "C1",
        "C2",
        "C3",
        "C4",
        "C5",
        "C6",
    ]
    assert registry.candidates[0].h3_rule.endpoint == (
        "root_surface_outward_na_flux_per_root_dry_mass"
    )
    assert registry.candidates[0].h3_rule.scale == "log_ratio"
    assert registry.candidates[0].h3_rule.direction == "ge"
    assert registry.candidates[0].h3_rule.margin == pytest.approx(math.log(1.20))
    assert registry.candidates[1].h3_rule.direction == "le"
    assert registry.candidates[1].h3_rule.margin == pytest.approx(math.log(0.80))
    assert registry.candidates[2].h3_rule.scale == "difference"
    assert registry.candidates[2].h3_rule.margin == pytest.approx(10.0)
    assert registry.thresholds.h1_claim_log_ratio == pytest.approx(math.log(1.20))
    assert registry.thresholds.h1_power_log_ratio == pytest.approx(math.log(1.30))
    assert registry.thresholds.finalist_cap == 4


def test_candidate_mappings_are_mechanisms_not_direct_outcomes() -> None:
    """Catches a candidate that bypasses its mechanistic model for an outcome."""
    registry = load_candidate_specs(CONFIGS / "candidates.yaml")
    forbidden = {"survival", "canopy_auc", "kernel_yield", "salt_tolerance"}

    assert {candidate.primary_parameter_id for candidate in registry.candidates}.isdisjoint(
        forbidden
    )
    c2 = registry.candidates[1]
    assert c2.sequence_accessions == ()
    assert c2.sequence_status == "pending_audit"
    assert c2.gates["sequence_build"] == "blocked"
    assert registry.candidates[2].primary_parameter_id == "mannitol_vmax_multiplier"
    assert "xylem" in registry.candidates[3].risk_warning.lower()


def test_composite_root_two_water_full_allocation_design_is_frozen() -> None:
    """Catches pseudoreplicated or incomplete Paper 1 allocation changes."""
    design = load_paper1_design(CONFIGS / "experiment_paper1.yaml")

    assert design.population is AnalysisPopulation.COMPOSITE_ROOT
    assert len(design.full_allocation_groups) == 9
    assert len(design.water_conditions) == 2
    assert len(design.runs) == 2
    assert design.reservoirs_per_water_run == 4
    assert design.independent_plants_per_group_reservoir == 5
    assert len(design.balanced_transformation_batches) >= 2
    assert design.construct_level_unit == "independently_transformed_plant"
    assert design.water_treatment_unit == "reservoir"


def test_synthetic_scenarios_fail_closed_when_any_required_input_is_absent() -> None:
    """Catches an implicit biological or measurement default in a scenario."""
    with pytest.raises(AlmondLabError) as exc_info:
        SyntheticScenarioConfig.model_validate(
            {"scenario_id": "perfect_control", "evidence_label": "synthetic_only"}
        )

    assert exc_info.value.code == "INCOMPLETE_SYNTHETIC_SCENARIO"
    assert "root_na_permeability" in exc_info.value.details["missing"]
    scenarios = load_synthetic_scenarios(CONFIGS / "synthetic_scenarios.yaml")
    assert {scenario.evidence_label.value for scenario in scenarios} <= {
        "synthetic_only",
        "hypothesis_prior",
    }


def test_public_contracts_have_only_registered_labels_and_no_forbidden_output_keys() -> None:
    """Catches an unsupported evidence label or a winner-like published field."""
    assert tuple(AnalysisPopulation) == (
        AnalysisPopulation.COMPOSITE_ROOT,
        AnalysisPopulation.STABLE_EVENT,
    )
    assert tuple(ScientificLabel) == (
        ScientificLabel.INCONCLUSIVE,
        ScientificLabel.PROVISIONAL_LEADER,
        ScientificLabel.CO_LEADING,
        ScientificLabel.NOT_EVALUABLE,
    )
    assert tuple(CandidateState) == (
        CandidateState.SCREENED_OUT,
        CandidateState.DISCOVERY_ELIGIBLE,
        CandidateState.CONFIRMATION_PASSED,
        CandidateState.FULLY_ADVANCEABLE,
    )
    assert H3Rule(
        endpoint="root_mannitol", unit="nmol/g fresh weight", scale="difference", direction="ge", margin=10
    ).min_probability == pytest.approx(0.90)

    registry = load_candidate_specs(CONFIGS / "candidates.yaml")
    design = load_paper1_design(CONFIGS / "experiment_paper1.yaml")
    scenarios = load_synthetic_scenarios(CONFIGS / "synthetic_scenarios.yaml")

    def serialized_field_names(value: object) -> set[str]:
        if isinstance(value, dict):
            return set(value) | set().union(
                *(serialized_field_names(item) for item in value.values())
            )
        if isinstance(value, list):
            return set().union(*(serialized_field_names(item) for item in value))
        return set()

    names = serialized_field_names(
        [
            registry.model_dump(mode="json"),
            design.model_dump(mode="json"),
            [scenario.model_dump(mode="json") for scenario in scenarios],
        ]
    )
    assert {"winner", "best_candidate"}.isdisjoint(names)
