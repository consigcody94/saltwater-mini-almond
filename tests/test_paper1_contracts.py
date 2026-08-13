import hashlib
from io import BytesIO
import math
from copy import deepcopy
from pathlib import Path
import subprocess
import tarfile

import pytest
import yaml
from pydantic import ValidationError

import almondlab.paper1_contracts as paper1_contracts
from almondlab.biology_surrogate import BiologyParameters, PlantState, RootZoneForcing
from almondlab.contracts import CompartmentKind, ConservedEntity
from almondlab.errors import AlmondLabError
from almondlab.paper1_contracts import (
    AnalysisPopulation,
    CandidateSpec,
    CandidateState,
    H3Rule,
    LegacySyntheticScenarioConfig,
    Paper1DesignConfig,
    ScientificLabel,
    load_candidate_specs,
    load_paper1_design,
    load_synthetic_scenarios,
)


CONFIGS = Path(__file__).parents[1] / "configs"
LEGACY_SCENARIOS = CONFIGS / "archive" / "synthetic_scenarios_v1_3.yaml"


def _load_legacy_synthetic_scenarios(
    path: Path = LEGACY_SCENARIOS,
) -> tuple[LegacySyntheticScenarioConfig, ...]:
    return paper1_contracts._load_legacy_synthetic_scenarios(path)


def _scenario_merge_power_sequence(
    *,
    prefix: str,
    levels: int,
    extra_powers: tuple[int, ...] = (),
) -> str:
    """Build an acyclic merge DAG using one overridden registered key."""

    lines = ["  <<:", f"    - &{prefix}0 {{root_area_cm2: 1.0}}"]
    for level in range(1, levels):
        lines.append(
            f"    - &{prefix}{level} "
            f"{{<<: [*{prefix}{level - 1}, *{prefix}{level - 1}]}}"
        )
    lines.extend(f"    - *{prefix}{level}" for level in extra_powers)
    return "\n".join(lines) + "\n"


def _scenario_source_with_biology_merge(sequence: str) -> str:
    source = LEGACY_SCENARIOS.read_text(encoding="utf-8")
    marker = "biology_parameters: &biology_parameters\n"
    return source.replace(marker, marker + sequence, 1)


EXPECTED_CANDIDATE_IDENTITIES = {
    "C1": {
        "construct_name": "PyKPA1",
        "donor_species": "Pyropia yezoensis (Neopyropia yezoensis)",
        "sequence_accessions": ("AJ972674.1", "CAI99405.1"),
        "sequence_status": "accession_verified",
        "evidence_tier": "E2",
        "evidence_label": "hypothesis_prior",
        "primary_parameter_id": "na_efflux_vmax_multiplier",
        "gates": {"sequence_build": "required", "directional_assay": "required"},
    },
    "C2": {
        "construct_name": "PyAPX",
        "donor_species": "Pyropia yezoensis",
        "sequence_accessions": ("AY282755.1",),
        "sequence_status": "accession_verified",
        "evidence_tier": "E2",
        "evidence_label": "hypothesis_prior",
        "primary_parameter_id": "ros_clearance_multiplier",
        "gates": {"sequence_build": "blocked", "directional_assay": "required"},
    },
    "C3": {
        "construct_name": "EsM1PDH1+EsM1Pase2",
        "donor_species": "Ectocarpus sp. Ec32",
        "sequence_accessions": ("Esi0017_0062", "Esi0100_0020"),
        "sequence_status": "crosswalk_pending",
        "evidence_tier": "E2",
        "evidence_label": "hypothesis_prior",
        "primary_parameter_id": "mannitol_vmax_multiplier",
        "gates": {"sequence_build": "required", "directional_assay": "required"},
    },
    "C4": {
        "construct_name": "SbSOS1",
        "donor_species": "Salicornia brachiata Roxb.",
        "sequence_accessions": ("EU879059.1", "ACJ63441.1"),
        "sequence_status": "accession_verified",
        "evidence_tier": "E2",
        "evidence_label": "hypothesis_prior",
        "primary_parameter_id": "na_efflux_vmax_multiplier",
        "gates": {
            "sequence_build": "required",
            "cortex_localization": "required",
            "directional_assay": "required",
        },
    },
    "C5": {
        "construct_name": "PpHKT1",
        "donor_species": "Prunus persica 'Nemaguard'",
        "sequence_accessions": ("Prupe.1G067100",),
        "sequence_status": "verified",
        "evidence_tier": "E1",
        "evidence_label": "hypothesis_prior",
        "primary_parameter_id": "xylem_na_retrieval_multiplier",
        "gates": {"sequence_build": "required", "directional_assay": "required"},
    },
    "C6": {
        "construct_name": "PpSOS2_PpCIPK24",
        "donor_species": "Prunus persica 'Nemaguard'",
        "sequence_accessions": ("Prupe.7G244500.1", "XP_020424233.1"),
        "sequence_status": "verified",
        "evidence_tier": "E1",
        "evidence_label": "hypothesis_prior",
        "primary_parameter_id": "sos_efflux_activation_multiplier",
        "gates": {"sequence_build": "required", "directional_assay": "required"},
    },
}

EXPECTED_H3_RULES = {
    "C1": (
        "root_surface_outward_na_flux_per_root_dry_mass",
        "umol Na g_root_dry_mass^-1 h^-1",
        "log_ratio",
        "ge",
        math.log(1.20),
    ),
    "C2": (
        "root_h2o2_concentration_time_auc",
        "umol H2O2 g_root_fresh_mass^-1 h",
        "log_ratio",
        "le",
        math.log(0.80),
    ),
    "C3": (
        "root_mannitol_concentration_above_empty_vector",
        "nmol g_root_fresh_mass^-1",
        "difference",
        "ge",
        10.0,
    ),
    "C4": (
        "root_surface_outward_na_flux_per_root_dry_mass",
        "umol Na g_root_dry_mass^-1 h^-1",
        "log_ratio",
        "ge",
        math.log(1.20),
    ),
    "C5": (
        "xylem_sap_na_concentration_time_auc",
        "mmol Na L^-1 h",
        "log_ratio",
        "le",
        math.log(0.80),
    ),
    "C6": (
        "root_surface_outward_na_flux_per_root_dry_mass",
        "umol Na g_root_dry_mass^-1 h^-1",
        "log_ratio",
        "ge",
        math.log(1.20),
    ),
}


def test_candidate_registry_matches_independent_v13_identity_oracle() -> None:
    """Catches a candidate whose donor, sequence, mechanism, or safety gate drifts."""
    registry = load_candidate_specs(CONFIGS / "candidates.yaml")

    actual = {
        candidate.candidate_id: {
            "construct_name": candidate.construct_name,
            "donor_species": candidate.donor_species,
            "sequence_accessions": candidate.sequence_accessions,
            "sequence_status": candidate.sequence_status,
            "evidence_tier": candidate.evidence_tier,
            "evidence_label": candidate.evidence_label.value,
            "primary_parameter_id": candidate.primary_parameter_id,
            "gates": candidate.gates,
        }
        for candidate in registry.candidates
    }

    assert actual == EXPECTED_CANDIDATE_IDENTITIES


def test_candidate_nested_gate_mapping_is_deeply_immutable() -> None:
    """Catches mutation of a gate after frozen CandidateSpec validation."""
    candidate = load_candidate_specs(CONFIGS / "candidates.yaml").candidates[0]

    with pytest.raises(TypeError):
        candidate.gates["sequence_build"] = "blocked"  # type: ignore[index]


@pytest.mark.parametrize("candidate_id", ["C1", "C2", "C3", "C4", "C5", "C6"])
def test_each_candidate_h3_rule_matches_independent_v13_oracle(candidate_id: str) -> None:
    """Catches mutation of any registered candidate-specific H3 rule."""
    candidates = {
        candidate.candidate_id: candidate
        for candidate in load_candidate_specs(CONFIGS / "candidates.yaml").candidates
    }
    rule = candidates[candidate_id].h3_rule
    endpoint, unit, scale, direction, margin = EXPECTED_H3_RULES[candidate_id]

    assert (rule.endpoint, rule.unit, rule.scale, rule.direction) == (
        endpoint,
        unit,
        scale,
        direction,
    )
    assert rule.margin == pytest.approx(margin)
    assert rule.min_probability == pytest.approx(0.90)


@pytest.mark.parametrize(
    ("candidate_id", "field_path", "mutated_value"),
    [
        ("C1", ("donor_species",), "different donor"),
        ("C2", ("construct_name",), "different module"),
        ("C3", ("sequence_accessions",), ["fabricated_accession"]),
        ("C4", ("primary_parameter_id",), "unregistered_transition"),
        ("C5", ("h3_rule", "direction"), "ge"),
        ("C6", ("gates",), {"sequence_build": "required"}),
    ],
)
def test_candidate_model_rejects_v13_identity_or_gate_mutation(
    candidate_id: str, field_path: tuple[str, ...], mutated_value: object
) -> None:
    """Catches acceptance of candidate metadata that no longer identifies v1.3."""
    candidate = next(
        item
        for item in load_candidate_specs(CONFIGS / "candidates.yaml").candidates
        if item.candidate_id == candidate_id
    )
    payload = candidate.model_dump(mode="json")
    target = payload
    for field_name in field_path[:-1]:
        target = target[field_name]
    target[field_path[-1]] = mutated_value

    with pytest.raises(ValidationError, match=f"candidate {candidate_id}"):
        CandidateSpec.model_validate(payload)


def test_candidate_model_rejects_substitution_for_verified_c2_record() -> None:
    """Catches substitution of a fabricated ID for verified AY282755.1."""
    c2 = load_candidate_specs(CONFIGS / "candidates.yaml").candidates[1]
    payload = deepcopy(c2.model_dump(mode="json"))
    payload["sequence_accessions"] = ["FABRICATED_C2_ACCESSION"]

    with pytest.raises(ValidationError, match="candidate C2"):
        CandidateSpec.model_validate(payload)


@pytest.mark.parametrize(
    ("field_name", "mutated_value"),
    [
        ("sequence_status", "verified"),
        ("gates", {"sequence_build": "required", "directional_assay": "required"}),
    ],
)
def test_candidate_model_rejects_inconsistent_c2_accession_or_build_gate(
    field_name: str, mutated_value: object
) -> None:
    """Catches a PyAPX record that overstates verification or build readiness."""
    c2 = load_candidate_specs(CONFIGS / "candidates.yaml").candidates[1]
    payload = deepcopy(c2.model_dump(mode="json"))
    payload[field_name] = mutated_value

    with pytest.raises(ValidationError, match="candidate C2"):
        CandidateSpec.model_validate(payload)


@pytest.mark.parametrize(
    ("field_name", "invalid_value"),
    [
        ("scale", "ratio"),
        ("direction", "gt"),
        ("min_probability", -0.01),
        ("min_probability", 1.01),
    ],
)
def test_h3_rule_rejects_unregistered_kind_or_probability_boundary(
    field_name: str, invalid_value: object
) -> None:
    """Catches permissive H3 validation outside the registered vocabulary/range."""
    payload = {
        "endpoint": "root_surface_outward_na_flux_per_root_dry_mass",
        "unit": "umol Na g_root_dry_mass^-1 h^-1",
        "scale": "log_ratio",
        "direction": "ge",
        "margin": math.log(1.20),
        "min_probability": 0.90,
    }
    payload[field_name] = invalid_value

    with pytest.raises(ValidationError):
        H3Rule.model_validate(payload)


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
    assert c2.sequence_accessions == ("AY282755.1",)
    assert c2.sequence_status == "accession_verified"
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


def test_design_matches_independent_registered_identity_oracle() -> None:
    """Catches a renamed arm, run, water, batch, or changed allocation count."""
    design = load_paper1_design(CONFIGS / "experiment_paper1.yaml")

    assert design.schema_version == "1.3"
    assert design.evidence_label.value == "synthetic_only"
    assert design.full_allocation_groups == (
        "C1",
        "C2",
        "C3",
        "C4",
        "C5",
        "C6",
        "empty_vector",
        "sham_transformation",
        "unmodified_parent",
    )
    assert tuple(water.water_id for water in design.water_conditions) == (
        "nonsaline_nutrient_matched_control",
        "pilot_selected_full_ion_marine_challenge",
    )
    assert design.runs == ("discovery_run_1", "discovery_run_2")
    assert design.reservoirs_per_water_run == 4
    assert design.independent_plants_per_group_reservoir == 5
    assert design.balanced_transformation_batches == ("batch_a", "batch_b")


@pytest.mark.parametrize(
    ("field_name", "invalid_value"),
    [
        ("reservoirs_per_water_run", True),
        ("reservoirs_per_water_run", "4"),
        ("independent_plants_per_group_reservoir", False),
        ("independent_plants_per_group_reservoir", "5"),
    ],
)
def test_design_rejects_coercive_integer_counts(
    field_name: str, invalid_value: object
) -> None:
    """Catches bool or numeric-string allocation counts at the Task 1 boundary."""
    payload = load_paper1_design(CONFIGS / "experiment_paper1.yaml").model_dump(
        mode="json"
    )
    payload[field_name] = invalid_value

    with pytest.raises(ValidationError):
        Paper1DesignConfig.model_validate(payload)


@pytest.mark.parametrize(
    ("field_name", "invalid_value"),
    [
        ("runs", [" discovery_run_1", "discovery_run_2"]),
        ("runs", ["discovery_run_1", "discovery_run_1"]),
        ("full_allocation_groups", ["C1"] * 9),
        ("balanced_transformation_batches", ["batch_a", "batch_a"]),
    ],
)
def test_design_rejects_whitespace_and_duplicate_ids(
    field_name: str, invalid_value: object
) -> None:
    """Catches trim-normalized or duplicate design identities."""
    payload = load_paper1_design(CONFIGS / "experiment_paper1.yaml").model_dump(
        mode="json"
    )
    payload[field_name] = invalid_value

    with pytest.raises(ValidationError):
        Paper1DesignConfig.model_validate(payload)


@pytest.mark.parametrize(
    ("field_name", "item_index"),
    [
        ("full_allocation_groups", 0),
        ("runs", 0),
        ("balanced_transformation_batches", 0),
    ],
)
def test_design_rejects_string_subclasses_before_canonicalization(
    field_name: str, item_index: int
) -> None:
    """Catches hostile string subclasses being normalized into registered IDs."""

    class HostileText(str):
        pass

    payload = load_paper1_design(CONFIGS / "experiment_paper1.yaml").model_dump(
        mode="json"
    )
    payload[field_name][item_index] = HostileText(payload[field_name][item_index])

    with pytest.raises(ValidationError):
        Paper1DesignConfig.model_validate(payload)


@pytest.mark.parametrize(
    "field_name",
    ("full_allocation_groups", "runs", "balanced_transformation_batches"),
)
def test_design_rejects_list_subclasses_before_canonicalization(
    field_name: str,
) -> None:
    """Catches hostile list subclasses being normalized into immutable ID tuples."""

    class HostileList(list):
        pass

    payload = load_paper1_design(CONFIGS / "experiment_paper1.yaml").model_dump(
        mode="json"
    )
    payload[field_name] = HostileList(payload[field_name])

    with pytest.raises(ValidationError):
        Paper1DesignConfig.model_validate(payload)


def test_design_rejects_water_id_string_subclass_before_canonicalization() -> None:
    """Catches a hostile water identity subclass at the nested public boundary."""

    class HostileText(str):
        pass

    payload = load_paper1_design(CONFIGS / "experiment_paper1.yaml").model_dump(
        mode="json"
    )
    payload["water_conditions"][0]["water_id"] = HostileText(
        payload["water_conditions"][0]["water_id"]
    )

    with pytest.raises(ValidationError):
        Paper1DesignConfig.model_validate(payload)


@pytest.mark.parametrize(
    ("field_path", "mutated_value"),
    [
        (
            ("full_allocation_groups",),
            [
                "C2",
                "C1",
                "C3",
                "C4",
                "C5",
                "C6",
                "empty_vector",
                "sham_transformation",
                "unmodified_parent",
            ],
        ),
        (("water_conditions", 0, "water_id"), "renamed_control"),
        (("runs",), ["renamed_run", "discovery_run_2"]),
        (("reservoirs_per_water_run",), 5),
        (("independent_plants_per_group_reservoir",), 6),
        (("balanced_transformation_batches",), ["batch_a", "batch_c"]),
    ],
)
def test_design_model_rejects_frozen_identity_mutation(
    field_path: tuple[str | int, ...], mutated_value: object
) -> None:
    """Catches an internally valid but unregistered primary-design mutation."""
    payload = load_paper1_design(CONFIGS / "experiment_paper1.yaml").model_dump(
        mode="json"
    )
    target = payload
    for component in field_path[:-1]:
        target = target[component]
    target[field_path[-1]] = mutated_value

    with pytest.raises(ValidationError, match="Paper 1 design identity is frozen"):
        Paper1DesignConfig.model_validate(payload)


def test_registered_quantity_requires_an_exact_finite_float_and_trimmed_unit() -> None:
    """Catches numeric coercion, booleans, nonfinite values, or malformed units."""

    quantity = paper1_contracts.RegisteredQuantity(
        value=0.02,
        unit="log-ratio^2",
        evidence_label="hypothesis_prior",
    )

    assert type(quantity.value) is float
    assert quantity.unit == "log-ratio^2"
    for invalid_value in (True, 2, "0.02", float("nan"), float("inf")):
        with pytest.raises(ValidationError):
            paper1_contracts.RegisteredQuantity(
                value=invalid_value,
                unit="log-ratio^2",
                evidence_label="hypothesis_prior",
            )
    for invalid_unit in ("", " log-ratio^2", "log-ratio^2 ", "log\nratio"):
        with pytest.raises(ValidationError):
            paper1_contracts.RegisteredQuantity(
                value=0.02,
                unit=invalid_unit,
                evidence_label="hypothesis_prior",
            )


def test_registered_count_requires_an_exact_nonnegative_integer() -> None:
    """Catches booleans, floats, strings, negative counts, or unit substitution."""

    count = paper1_contracts.RegisteredCount(
        value=64,
        unit="count",
        evidence_label="hypothesis_prior",
    )

    assert type(count.value) is int
    for invalid_value in (True, 64.0, "64", -1):
        with pytest.raises(ValidationError):
            paper1_contracts.RegisteredCount(
                value=invalid_value,
                unit="count",
                evidence_label="hypothesis_prior",
            )
    with pytest.raises(ValidationError):
        paper1_contracts.RegisteredCount(
            value=64,
            unit="panels",
            evidence_label="hypothesis_prior",
        )


def test_registered_count_stays_within_the_interoperable_json_integer_domain() -> None:
    """Catches a count that cannot be represented exactly by JSON consumers."""

    maximum = 2**53 - 1
    count = paper1_contracts.RegisteredCount(
        value=maximum,
        unit="count",
        evidence_label="hypothesis_prior",
    )

    assert count.value == maximum
    with pytest.raises(ValidationError):
        paper1_contracts.RegisteredCount(
            value=maximum + 1,
            unit="count",
            evidence_label="hypothesis_prior",
        )


def _rq(value: float, unit: str) -> dict[str, object]:
    return {
        "value": value,
        "unit": unit,
        "evidence_label": "hypothesis_prior",
    }


def _rc(value: int) -> dict[str, object]:
    return {
        "value": value,
        "unit": "count",
        "evidence_label": "hypothesis_prior",
    }


ENDPOINT_IDS = (
    "green_canopy_area",
    "root_zone_na_concentration",
    "root_zone_cl_concentration",
    "root_zone_k_concentration",
    "xylem_sap_na_concentration",
    "drainage_total_b_concentration",
    "root_surface_outward_na_flux_per_root_dry_mass",
    "root_h2o2_concentration_time_auc",
    "root_mannitol_concentration_above_empty_vector",
    "xylem_sap_na_concentration_time_auc",
)
H3_ENDPOINT_IDS = ENDPOINT_IDS[-4:]
WATER_IDS = (
    "nonsaline_nutrient_matched_control",
    "pilot_selected_full_ion_marine_challenge",
)
ENDPOINT_UNITS = {
    "green_canopy_area": "cm^2",
    "root_zone_na_concentration": "mmol Na L^-1",
    "root_zone_cl_concentration": "mmol Cl L^-1",
    "root_zone_k_concentration": "mmol K L^-1",
    "xylem_sap_na_concentration": "mmol Na L^-1",
    "drainage_total_b_concentration": "mmol B L^-1",
    "root_surface_outward_na_flux_per_root_dry_mass": (
        "umol Na g_root_dry_mass^-1 h^-1"
    ),
    "root_h2o2_concentration_time_auc": (
        "umol H2O2 g_root_fresh_mass^-1 h"
    ),
    "root_mannitol_concentration_above_empty_vector": (
        "nmol g_root_fresh_mass^-1"
    ),
    "xylem_sap_na_concentration_time_auc": "mmol Na L^-1 h",
}
H3_ERROR_AUTHORITIES = {
    "C1": (
        "root_surface_outward_na_flux_per_root_dry_mass",
        "log_ratio",
        "umol Na g_root_dry_mass^-1 h^-1",
        0.05,
        "log-ratio",
    ),
    "C2": (
        "root_h2o2_concentration_time_auc",
        "log_ratio",
        "umol H2O2 g_root_fresh_mass^-1 h",
        0.05,
        "log-ratio",
    ),
    "C3": (
        "root_mannitol_concentration_above_empty_vector",
        "difference",
        "nmol g_root_fresh_mass^-1",
        2.0,
        "nmol g_root_fresh_mass^-1",
    ),
    "C4": (
        "root_surface_outward_na_flux_per_root_dry_mass",
        "log_ratio",
        "umol Na g_root_dry_mass^-1 h^-1",
        0.05,
        "log-ratio",
    ),
    "C5": (
        "xylem_sap_na_concentration_time_auc",
        "log_ratio",
        "mmol Na L^-1 h",
        0.05,
        "log-ratio",
    ),
    "C6": (
        "root_surface_outward_na_flux_per_root_dry_mass",
        "log_ratio",
        "umol Na g_root_dry_mass^-1 h^-1",
        0.05,
        "log-ratio",
    ),
}


def _v14_generator_payload() -> dict[str, object]:
    endpoint_limits = {
        endpoint_id: None if endpoint_id in {
            "green_canopy_area",
            "root_mannitol_concentration_above_empty_vector",
        } else _rq(0.01, ENDPOINT_UNITS[endpoint_id])
        for endpoint_id in ENDPOINT_IDS
    }
    endpoint_loqs = {
        endpoint_id: None if endpoint_id in {
            "green_canopy_area",
            "root_mannitol_concentration_above_empty_vector",
        } else _rq(0.03, ENDPOINT_UNITS[endpoint_id])
        for endpoint_id in ENDPOINT_IDS
    }
    endpoint_log_sds = {
        endpoint_id: None if endpoint_id in {
            "green_canopy_area",
            "root_mannitol_concentration_above_empty_vector",
        } else _rq(0.05, "log-ratio")
        for endpoint_id in ENDPOINT_IDS
    }
    return {
        "hierarchy": {
            "run_variance": _rq(0.02, "log-ratio^2"),
            "batch_variance": _rq(0.02, "log-ratio^2"),
            "reservoir_variance": _rq(0.04, "log-ratio^2"),
            "plant_variance": _rq(0.10, "log-ratio^2"),
        },
        "climate": {
            "temperature_ar1_phi": _rq(0.70, "dimensionless"),
            "temperature_innovation_sd_k": _rq(0.35, "K"),
            "apar_ar1_phi": _rq(0.60, "dimensionless"),
            "apar_log_innovation_sd": _rq(0.10, "log-ratio"),
            "matric_potential_ar1_phi": _rq(0.80, "dimensionless"),
            "matric_potential_innovation_sd_mpa": _rq(0.006, "MPa"),
            "potential_transpiration_log_innovation_sd": _rq(0.08, "log-ratio"),
            "climate_initialization_burnin_steps": _rc(64),
        },
        "chemistry": {
            "common_ion_log_sd": _rq(0.03, "log-ratio"),
            "boron_log_sd": _rq(0.08, "log-ratio"),
            "ec_measurement_sd_ds_m": _rq(0.05, "dS m^-1"),
            "osmolality_measurement_sd_osmol_kg": _rq(0.002, "osmol kg^-1"),
            "ph_measurement_sd": _rq(0.03, "pH"),
            "temperature_measurement_sd_k": _rq(0.20, "K"),
            "charge_balance_tolerance_percent": _rq(1.00, "percent"),
        },
        "water_loop": {
            "reservoir_initial_volume_l": _rq(120.0, "L"),
            "water_batch_volume_l": _rq(5000.0, "L"),
            "irrigation_volume_l_per_plant_day": _rq(0.60, "L plant^-1 day^-1"),
            "drainage_return_fraction": _rq(0.70, "dimensionless"),
            "purge_volume_l_day": _rq(1.20, "L day^-1"),
            "sampling_volume_l_per_sample": _rq(0.05, "L sample^-1"),
            "reservoir_min_volume_l": _rq(80.0, "L"),
            "reservoir_max_volume_l": _rq(160.0, "L"),
            "operator_event_times_days": tuple(
                _rq(float(index) + 0.25, "day") for index in range(84)
            ),
        },
        "observation": {
            "canopy_observation_error_sd": _rq(0.05, "log-ratio"),
            "ion_observation_error_sd": _rq(0.04, "log-ratio"),
            "h3_observation_error_by_endpoint": {
                candidate_id: {
                    "candidate_id": candidate_id,
                    "endpoint_id": authority[0],
                    "analysis_scale": authority[1],
                    "endpoint_unit": authority[2],
                    "error_sd": _rq(authority[3], authority[4]),
                }
                for candidate_id, authority in H3_ERROR_AUTHORITIES.items()
            },
            "canopy_heteroscedastic_log_slope": _rq(0.10, "log/log"),
            "ion_heteroscedastic_log_slope": _rq(0.08, "log/log"),
            "canopy_observation_times_days": tuple(
                _rq(float(day), "day")
                for day in (0, 3, 7, 14, 21, 28, 35, 42, 49, 56, 63, 70, 77, 84)
            ),
            "ion_observation_times_days": tuple(
                _rq(float(day), "day") for day in (0, 14, 28, 42, 56, 70, 84)
            ),
            "h3_observation_times_days_by_endpoint": {
                endpoint_id: (_rq(84.0, "day"),) for endpoint_id in H3_ENDPOINT_IDS
            },
            "h3_measurement_links": {
                "root_dry_matter_fraction": _rq(0.20, "dimensionless"),
                "h2o2_umol_g_root_fresh_mass_inv_per_ros_dimensionless": _rq(
                    1.0,
                    "umol H2O2 g_root_fresh_mass^-1 per ros_dimensionless",
                ),
            },
        },
        "censoring": {
            "lod_by_endpoint": endpoint_limits,
            "loq_by_endpoint": endpoint_loqs,
            "lod_log_sd_by_endpoint": endpoint_log_sds,
            "loq_log_sd_by_endpoint": deepcopy(endpoint_log_sds),
        },
        "drift": {
            "canopy_drift_per_day": _rq(0.0, "log-ratio day^-1"),
            "ion_drift_per_day_by_endpoint": {
                endpoint_id: _rq(0.0, "log-ratio day^-1")
                for endpoint_id in ENDPOINT_IDS[1:6]
            },
            "h3_drift_per_day_by_endpoint": {
                endpoint_id: _rq(
                    0.0,
                    "nmol g_root_fresh_mass^-1 day^-1"
                    if endpoint_id
                    == "root_mannitol_concentration_above_empty_vector"
                    else "log-ratio day^-1",
                )
                for endpoint_id in H3_ENDPOINT_IDS
            },
            "calibration_interval_days": _rq(7.0, "day"),
            "calibration_phase_offset_days": _rq(0.0, "day"),
            "post_calibration_residual_sd_by_endpoint": {
                endpoint_id: _rq(
                    0.25
                    if endpoint_id
                    == "root_mannitol_concentration_above_empty_vector"
                    else 0.01,
                    "nmol g_root_fresh_mass^-1"
                    if endpoint_id
                    == "root_mannitol_concentration_above_empty_vector"
                    else "log-ratio",
                )
                for endpoint_id in ENDPOINT_IDS
            },
        },
        "death": {
            "biomass_death_threshold_log_sd": _rq(0.10, "log-ratio"),
            "injury_death_threshold_log_sd": _rq(0.10, "log-ratio"),
            "sustained_injury_duration_log_sd": _rq(0.10, "log-ratio"),
        },
        "missingness": {
            "missingness_intercept": _rq(-3.0, "logit"),
            "missingness_stress_slope": _rq(
                0.20, "logit per standardized-proxy SD"
            ),
            "mnar_tipping_delta": _rq(
                0.10, "logit per standardized-endpoint SD"
            ),
            "observable_stress_proxy_fields": (
                "challenge_water_indicator",
                "scheduled_time_days",
                "prior_observed_canopy_log_ratio",
            ),
            "observable_stress_proxy_center_by_field": {
                "challenge_water_indicator": _rq(0.5, "dimensionless"),
                "scheduled_time_days": _rq(42.0, "day"),
                "prior_observed_canopy_log_ratio": _rq(0.0, "log-ratio"),
            },
            "observable_stress_proxy_scale_by_field": {
                "challenge_water_indicator": _rq(0.5, "dimensionless"),
                "scheduled_time_days": _rq(42.0, "day"),
                "prior_observed_canopy_log_ratio": _rq(0.25, "log-ratio"),
            },
            "mnar_endpoints": (
                "green_canopy_area",
                *H3_ENDPOINT_IDS,
            ),
        },
        "calibration": {
            "parameter_xtol": _rq(1.0e-6, "dimensionless"),
            "parameter_rtol": _rq(1.0e-6, "dimensionless"),
            "objective_residual_tolerance_log_ratio": _rq(1.0e-6, "log-ratio"),
            "max_iterations": _rc(100),
            "fit_panel_size": _rc(64),
            "holdout_panel_size": _rc(64),
            "holdout_tolerance_log_ratio": _rq(0.020, "log-ratio"),
        },
        "design": {
            "duration_days": _rq(84.0, "day"),
            "confirmation_plants_per_group_reservoir": _rc(6),
        },
    }


def test_v14_generator_requires_every_registered_section_without_defaults() -> None:
    """Catches omission, renaming, or an unregistered top-level generator section."""

    payload = _v14_generator_payload()
    generator = paper1_contracts.SyntheticGeneratorConfig.model_validate(payload)

    assert generator.water_loop.water_batch_volume_l.value == 5000.0
    assert generator.calibration.parameter_xtol.unit == "dimensionless"
    for section in tuple(payload):
        incomplete = deepcopy(payload)
        incomplete.pop(section)
        with pytest.raises(ValidationError):
            paper1_contracts.SyntheticGeneratorConfig.model_validate(incomplete)
    extra = deepcopy(payload)
    extra["unregistered"] = {}
    with pytest.raises(ValidationError):
        paper1_contracts.SyntheticGeneratorConfig.model_validate(extra)


def test_v14_generator_sections_enforce_registered_units_and_exact_map_keys() -> None:
    """Catches a unit alias or missing endpoint hidden inside a required section."""

    wrong_unit = _v14_generator_payload()
    wrong_unit["hierarchy"]["run_variance"]["unit"] = "variance"
    with pytest.raises(ValidationError):
        paper1_contracts.SyntheticGeneratorConfig.model_validate(wrong_unit)

    missing_endpoint = _v14_generator_payload()
    missing_endpoint["censoring"]["lod_by_endpoint"].pop("xylem_sap_na_concentration")
    with pytest.raises(ValidationError):
        paper1_contracts.SyntheticGeneratorConfig.model_validate(missing_endpoint)


def test_v14_generator_rejects_mapping_and_string_key_subclasses() -> None:
    """Catches normalization of hostile nested map objects or identity keys."""

    class HostileMap(dict):
        pass

    class HostileText(str):
        pass

    hostile_map = _v14_generator_payload()
    hostile_map["censoring"]["lod_by_endpoint"] = HostileMap(
        hostile_map["censoring"]["lod_by_endpoint"]
    )
    with pytest.raises(ValidationError):
        paper1_contracts.SyntheticGeneratorConfig.model_validate(hostile_map)

    hostile_key = _v14_generator_payload()
    errors = hostile_key["observation"]["h3_observation_error_by_endpoint"]
    hostile_key["observation"]["h3_observation_error_by_endpoint"] = {
        HostileText(candidate_id) if candidate_id == "C1" else candidate_id: record
        for candidate_id, record in errors.items()
    }
    with pytest.raises(ValidationError):
        paper1_contracts.SyntheticGeneratorConfig.model_validate(hostile_key)


def test_v14_generator_rejects_model_copy_nan_and_nested_model_subclasses() -> None:
    """Catches trusted-instance bypasses that skip nested quantity validation."""

    generator = paper1_contracts.SyntheticGeneratorConfig.model_validate(
        _v14_generator_payload()
    )
    forged_quantity = generator.hierarchy.run_variance.model_copy(
        update={"value": float("nan")}
    )
    forged_hierarchy = generator.hierarchy.model_copy(
        update={"run_variance": forged_quantity}
    )
    forged_generator = generator.model_copy(update={"hierarchy": forged_hierarchy})
    with pytest.raises(ValidationError):
        paper1_contracts.SyntheticGeneratorConfig.model_validate(forged_generator)

    class HostileHierarchy(paper1_contracts.HierarchyGeneratorConfig):
        covert_outcome_effect: float

    hostile = HostileHierarchy.model_validate(
        {
            **_v14_generator_payload()["hierarchy"],
            "covert_outcome_effect": 4.0,
        }
    )
    payload = _v14_generator_payload()
    payload["hierarchy"] = hostile
    with pytest.raises(ValidationError):
        paper1_contracts.SyntheticGeneratorConfig.model_validate(payload)


@pytest.mark.parametrize(
    ("section", "field_name", "bad_value"),
    [
        ("hierarchy", "run_variance", -0.01),
        ("climate", "temperature_ar1_phi", 2.0),
        ("water_loop", "drainage_return_fraction", 2.0),
        ("water_loop", "reservoir_min_volume_l", 170.0),
        ("observation", "canopy_observation_error_sd", -0.1),
        ("death", "injury_death_threshold_log_sd", -0.1),
        ("calibration", "parameter_xtol", 0.0),
        ("water_loop", "irrigation_volume_l_per_plant_day", 1.0e308),
    ],
)
def test_v14_generator_rejects_invalid_semantic_ranges(
    section: str, field_name: str, bad_value: float
) -> None:
    """Catches finite-but-destructive values that violate generator semantics."""

    payload = _v14_generator_payload()
    payload[section][field_name]["value"] = bad_value

    with pytest.raises(ValidationError):
        paper1_contracts.SyntheticGeneratorConfig.model_validate(payload)


def test_v14_generator_rejects_zero_scales_counts_and_unregistered_cell_size() -> None:
    """Catches divisions by zero, no-op solvers, and an unfrozen confirmation n."""

    mutations = (
        ("missingness", "observable_stress_proxy_scale_by_field", "scheduled_time_days", 0.0),
        ("calibration", "max_iterations", None, 0),
        ("design", "confirmation_plants_per_group_reservoir", None, 4),
    )
    for section, field_name, map_key, value in mutations:
        payload = _v14_generator_payload()
        target = payload[section][field_name]
        if map_key is None:
            target["value"] = value
        else:
            target[map_key]["value"] = value
        with pytest.raises(ValidationError):
            paper1_contracts.SyntheticGeneratorConfig.model_validate(payload)


@pytest.mark.parametrize(
    ("section", "map_name", "key", "bad_unit"),
    [
        (
            "censoring",
            "lod_by_endpoint",
            "root_zone_na_concentration",
            "bananas",
        ),
        (
            "drift",
            "ion_drift_per_day_by_endpoint",
            "root_zone_na_concentration",
            "bananas",
        ),
        (
            "missingness",
            "observable_stress_proxy_scale_by_field",
            "scheduled_time_days",
            "bananas",
        ),
    ],
)
def test_v14_generator_rejects_unknown_endpoint_and_proxy_units(
    section: str, map_name: str, key: str, bad_unit: str
) -> None:
    """Catches a well-typed quantity carrying the wrong registered unit."""

    payload = _v14_generator_payload()
    payload[section][map_name][key]["unit"] = bad_unit
    with pytest.raises(ValidationError):
        paper1_contracts.SyntheticGeneratorConfig.model_validate(payload)


def test_h3_error_records_are_cross_bound_to_candidate_rules() -> None:
    """Catches candidate-keyed SDs that omit or misstate their H3 authority."""

    generator = paper1_contracts.SyntheticGeneratorConfig.model_validate(
        _v14_generator_payload()
    )
    for candidate_id, expected in H3_ERROR_AUTHORITIES.items():
        record = generator.observation.h3_observation_error_by_endpoint[
            candidate_id
        ]
        assert (
            record.candidate_id,
            record.endpoint_id,
            record.analysis_scale,
            record.endpoint_unit,
            record.error_sd.value,
            record.error_sd.unit,
        ) == (candidate_id, *expected)

    for field_name, replacement in (
        ("candidate_id", "C6"),
        ("endpoint_id", "root_h2o2_concentration_time_auc"),
        ("analysis_scale", "difference"),
        ("endpoint_unit", "bananas"),
    ):
        payload = _v14_generator_payload()
        payload["observation"]["h3_observation_error_by_endpoint"]["C1"][
            field_name
        ] = replacement
        with pytest.raises(ValidationError):
            paper1_contracts.SyntheticGeneratorConfig.model_validate(payload)


def test_observation_schedules_are_strict_ordered_and_censor_limits_are_coherent() -> None:
    """Catches duplicate times, reversed assay limits, and mismatched nullability."""

    mutations = []
    duplicate = _v14_generator_payload()
    duplicate["observation"]["canopy_observation_times_days"][1]["value"] = 0.0
    mutations.append(duplicate)
    reversed_limits = _v14_generator_payload()
    reversed_limits["censoring"]["loq_by_endpoint"][
        "root_zone_na_concentration"
    ]["value"] = 0.005
    mutations.append(reversed_limits)
    negative_lod = _v14_generator_payload()
    negative_lod["censoring"]["lod_by_endpoint"][
        "root_zone_na_concentration"
    ]["value"] = -0.01
    mutations.append(negative_lod)
    null_mismatch = _v14_generator_payload()
    null_mismatch["censoring"]["loq_by_endpoint"][
        "root_zone_na_concentration"
    ] = None
    mutations.append(null_mismatch)
    unequal_log_sds = _v14_generator_payload()
    unequal_log_sds["censoring"]["loq_log_sd_by_endpoint"][
        "root_zone_na_concentration"
    ]["value"] = 0.10
    mutations.append(unequal_log_sds)

    for payload in mutations:
        with pytest.raises(ValidationError):
            paper1_contracts.SyntheticGeneratorConfig.model_validate(payload)


def _v14_scenario_payload(scenario_id: str = "perfect_control") -> dict[str, object]:
    legacy = yaml.safe_load(LEGACY_SCENARIOS.read_text(encoding="utf-8"))
    forcing = deepcopy(legacy["forcing"])
    forcing["duration_hours"] = 12.0
    return {
        "scenario_id": scenario_id,
        "schema_version": "1.4.0",
        "evidence_label": "synthetic_only",
        "parameters": deepcopy(legacy["biology_parameters"]),
        "initial_state": deepcopy(legacy["initial_state"]),
        "forcings_by_water_id": {
            water_id: tuple(deepcopy(forcing) for _ in range(168))
            for water_id in WATER_IDS
        },
        "generator": _v14_generator_payload(),
        "mechanism": {
            "biology_parameter_overrides": {},
            "candidate_parameter_overrides_by_id": {},
            "onset_time_days": None,
            "post_onset_biology_parameter_overrides": {},
            "chassis_id": None,
            "candidate_chassis_mechanism_modifiers": {},
        },
    }


def test_v14_scenario_contract_replaces_scalar_forcing_and_generator_mapping() -> None:
    """Catches accepting the retired v1.3 forcing/generator shape as v1.4."""

    scenario = paper1_contracts.SyntheticScenarioConfig.model_validate(
        _v14_scenario_payload()
    )

    assert scenario.schema_version == "1.4.0"
    assert tuple(scenario.forcings_by_water_id) == WATER_IDS
    assert isinstance(scenario.generator, paper1_contracts.SyntheticGeneratorConfig)
    for removed_name in ("forcing", "generator_parameters"):
        malformed = _v14_scenario_payload()
        malformed[removed_name] = malformed.pop(
            "forcings_by_water_id" if removed_name == "forcing" else "generator"
        )
        with pytest.raises((ValidationError, AlmondLabError)):
            paper1_contracts.SyntheticScenarioConfig.model_validate(malformed)


def test_v14_scenario_requires_exact_168_by_12_hour_water_schedules() -> None:
    """Catches alternate partitions that preserve only the 2,016-hour sum."""

    malformed_schedules = []

    one_coordinate = _v14_scenario_payload()
    one_coordinate["forcings_by_water_id"][WATER_IDS[0]] = (
        one_coordinate["forcings_by_water_id"][WATER_IDS[0]][0],
    )
    malformed_schedules.append(one_coordinate)

    variable_steps = _v14_scenario_payload()
    variable_steps["forcings_by_water_id"][WATER_IDS[0]][0][
        "duration_hours"
    ] = 6.0
    variable_steps["forcings_by_water_id"][WATER_IDS[0]][1][
        "duration_hours"
    ] = 18.0
    malformed_schedules.append(variable_steps)

    wrong_count_same_total = _v14_scenario_payload()
    forcing = wrong_count_same_total["forcings_by_water_id"][WATER_IDS[0]][0]
    forcing["duration_hours"] = 2016.0 / 167.0
    wrong_count_same_total["forcings_by_water_id"][WATER_IDS[0]] = tuple(
        deepcopy(forcing) for _ in range(167)
    )
    malformed_schedules.append(wrong_count_same_total)

    for payload in malformed_schedules:
        with pytest.raises(ValidationError):
            paper1_contracts.SyntheticScenarioConfig.model_validate(payload)


def test_v14_scenario_revalidates_corrupted_dataclasses_and_detaches_nested_inputs() -> None:
    """Catches object.__setattr__ corruption and retained nested identities."""

    scenario = paper1_contracts.SyntheticScenarioConfig.model_validate(
        _v14_scenario_payload()
    )
    object.__setattr__(scenario.parameters, "root_area_cm2", float("nan"))

    with pytest.raises((ValidationError, AlmondLabError)):
        paper1_contracts.SyntheticScenarioConfig.model_validate(scenario)

    clean = paper1_contracts.SyntheticScenarioConfig.model_validate(
        _v14_scenario_payload()
    )
    detached = paper1_contracts.SyntheticScenarioConfig.model_validate(clean)
    assert detached is not clean
    assert detached.parameters is not clean.parameters
    assert detached.initial_state is not clean.initial_state
    assert detached.initial_state.network_state is not clean.initial_state.network_state
    assert detached.generator is not clean.generator
    assert detached.generator.hierarchy is not clean.generator.hierarchy
    assert (
        detached.generator.hierarchy.run_variance
        is not clean.generator.hierarchy.run_variance
    )


def test_v14_scenario_rejects_hostile_nested_physical_state_keys() -> None:
    """Catches string-subclass keys reaching compartment and stock registries."""

    class HostileText(str):
        pass

    for section in ("compartments", "stocks"):
        payload = _v14_scenario_payload()
        compartments = payload["initial_state"]["network_state"]["compartments"]
        compartment_id = next(iter(compartments))
        if section == "compartments":
            payload["initial_state"]["network_state"]["compartments"] = {
                HostileText(key) if key == compartment_id else key: value
                for key, value in compartments.items()
            }
        else:
            stocks = compartments[compartment_id]["stocks"]
            stock_id = next(iter(stocks))
            compartments[compartment_id]["stocks"] = {
                HostileText(key) if key == stock_id else key: value
                for key, value in stocks.items()
            }
        with pytest.raises((ValidationError, AlmondLabError)):
            paper1_contracts.SyntheticScenarioConfig.model_validate(payload)


def _make_all_nonscenario_inputs_hypothesis_prior(
    payload: dict[str, object]
) -> None:
    payload["parameters"]["evidence_label"] = "hypothesis_prior"
    payload["initial_state"]["evidence_label"] = "hypothesis_prior"
    payload["initial_state"]["network_state"]["evidence_label"] = (
        "hypothesis_prior"
    )
    for compartment in payload["initial_state"]["network_state"][
        "compartments"
    ].values():
        compartment["evidence_label"] = "hypothesis_prior"
    for schedule in payload["forcings_by_water_id"].values():
        for forcing in schedule:
            forcing["evidence_label"] = "hypothesis_prior"


def test_v14_scenario_evidence_composes_generator_and_mechanism_inputs() -> None:
    """Catches promoting a synthetic generator or mechanism to hypothesis_prior."""

    generator_case = _v14_scenario_payload()
    _make_all_nonscenario_inputs_hypothesis_prior(generator_case)
    generator_case["generator"]["hierarchy"]["run_variance"][
        "evidence_label"
    ] = "synthetic_only"
    generator_case["evidence_label"] = "hypothesis_prior"
    with pytest.raises(ValidationError):
        paper1_contracts.SyntheticScenarioConfig.model_validate(generator_case)

    mechanism_case = _v14_scenario_payload("true_ion_exclusion")
    _make_all_nonscenario_inputs_hypothesis_prior(mechanism_case)
    for section in mechanism_case["generator"].values():
        # The recursive helper below changes only explicit registration labels.
        stack = [section]
        while stack:
            value = stack.pop()
            if isinstance(value, dict):
                if "evidence_label" in value:
                    value["evidence_label"] = "hypothesis_prior"
                stack.extend(value.values())
            elif isinstance(value, (list, tuple)):
                stack.extend(value)
    mechanism_case["mechanism"]["biology_parameter_overrides"] = {
        "root_na_permeability_l_cm2_h": 0.0
    }
    mechanism_case["evidence_label"] = "hypothesis_prior"
    with pytest.raises(ValidationError):
        paper1_contracts.SyntheticScenarioConfig.model_validate(mechanism_case)


def test_v14_registry_requires_the_exact_ten_scenarios_in_registered_order() -> None:
    """Catches a missing, duplicate, aliased, or reordered Task 4 scenario."""

    scenario_ids = (
        "perfect_control",
        "true_ion_exclusion",
        "root_na_accumulation",
        "marker_only",
        "nonsaline_penalty",
        "chassis_interaction",
        "delayed_toxicity",
        "sensor_drift_missingness",
        "insufficient_purge",
        "selection_bias_false_leader",
    )
    payload = {
        "schema_version": "1.4.0",
        "water_recipe_registry_sha256": "a" * 64,
        "anchor": _v14_scenario_payload(scenario_ids[0]),
        "scenarios": [
            _v14_scenario_payload(scenario_id) for scenario_id in scenario_ids[1:]
        ],
    }
    registry = paper1_contracts.SyntheticScenarioRegistry.model_validate(payload)

    assert tuple(item.scenario_id for item in registry.all_scenarios) == scenario_ids
    reordered = deepcopy(payload)
    reordered["scenarios"][0], reordered["scenarios"][1] = (
        reordered["scenarios"][1],
        reordered["scenarios"][0],
    )
    with pytest.raises(ValidationError):
        paper1_contracts.SyntheticScenarioRegistry.model_validate(reordered)


def test_active_loader_rejects_v13_with_explicit_migration_error() -> None:
    """Catches transparent acceptance of the retired v1.3 scenario document."""

    with pytest.raises(AlmondLabError) as exc_info:
        load_synthetic_scenarios(LEGACY_SCENARIOS)

    assert exc_info.value.code == "SCENARIO_SCHEMA_MIGRATION_REQUIRED"
    assert exc_info.value.field_path == "schema_version"


def test_v13_archives_preserve_the_approved_source_bytes_exactly() -> None:
    """Catches rebuilding either archive from a later working-tree config."""

    expected = {
        "synthetic_scenarios_v1_3.yaml": (
            "46286eb006fbfbaf13281dfe52d4c63c9dc00ff7b3ef0a8ee704146908f759cb"
        ),
        "experiment_paper1_v1_3.yaml": (
            "d402889dac8b4580b0d2f01e65b6caf750b8af65e0550fe6283c630109e465e0"
        ),
    }

    for name, expected_sha256 in expected.items():
        archive = CONFIGS / "archive" / name
        assert hashlib.sha256(archive.read_bytes()).hexdigest() == expected_sha256
        git_archive = subprocess.check_output(
            [
                "git",
                "archive",
                "--format=tar",
                "HEAD",
                archive.relative_to(CONFIGS.parent).as_posix(),
            ],
            cwd=CONFIGS.parent,
        )
        with tarfile.open(fileobj=BytesIO(git_archive), mode="r:") as stream:
            member = stream.extractfile(
                archive.relative_to(CONFIGS.parent).as_posix()
            )
            assert member is not None
            archived_bytes = member.read()
        assert archived_bytes == archive.read_bytes()


def test_v13_inventory_has_no_dropped_generator_value() -> None:
    """Catches silently ignored, multiply classified, or unregistered old knobs."""

    source = CONFIGS / "archive" / "synthetic_scenarios_v1_3.yaml"
    inventory = paper1_contracts.inspect_v13_scenario_migration(source)
    by_source = {
        item.source_path: item
        for item in inventory.items
        if item.source_path is not None
    }
    legacy_generator_paths = {
        f"generator_parameters.{name}"
        for name in {
            "run_variance",
            "batch_variance",
            "reservoir_variance",
            "plant_variance",
            "canopy_observation_error_sd",
            "ion_observation_error_sd",
            "h3_observation_error_sd",
            "missingness_intercept",
            "missingness_stress_slope",
            "mnar_tipping_delta",
            "duration_days",
        }
    }

    assert inventory.source_schema_version == "1.3.0"
    assert inventory.source_raw_sha256 == (
        "46286eb006fbfbaf13281dfe52d4c63c9dc00ff7b3ef0a8ee704146908f759cb"
    )
    assert legacy_generator_paths <= set(by_source)
    assert inventory.unclassified_source_paths == ()
    assert inventory.multiply_classified_source_paths == ()
    h3 = by_source["generator_parameters.h3_observation_error_sd"]
    assert h3.disposition is paper1_contracts.MigrationDisposition.SPLIT_REQUIRES_REGISTRATION
    assert h3.destination_paths == tuple(
        "anchor.generator.observation."
        f"h3_observation_error_by_endpoint.{candidate}.error_sd"
        for candidate in ("C1", "C2", "C4", "C5", "C6")
    )
    assert h3.owner_required_paths == (
        "anchor.generator.observation."
        "h3_observation_error_by_endpoint.C3.error_sd",
    )


def test_v13_inventory_classifies_every_legacy_leaf_exactly_once() -> None:
    """Catches migration coverage that audits only the eleven headline scalars."""

    source = CONFIGS / "archive" / "synthetic_scenarios_v1_3.yaml"
    inventory = paper1_contracts.inspect_v13_scenario_migration(source)
    paths = tuple(
        item.source_path for item in inventory.items if item.source_path is not None
    )

    assert len(paths) == len(set(paths))
    assert {
        "biology_parameters.root_area_cm2",
        "initial_state.network_state.compartments.root-zone.stocks.na",
        "forcing.duration_hours",
        "scenarios[scenario_id=chassis_interaction].parameters.root_conductance_l_day_mpa",
        "scenarios[scenario_id=insufficient_purge].forcing.measured_osmolality_osmol_kg",
    } <= set(paths)
    assert all(item.rationale for item in inventory.items)


def _v14_registry_payload() -> dict[str, object]:
    scenario_ids = (
        "perfect_control",
        "true_ion_exclusion",
        "root_na_accumulation",
        "marker_only",
        "nonsaline_penalty",
        "chassis_interaction",
        "delayed_toxicity",
        "sensor_drift_missingness",
        "insufficient_purge",
        "selection_bias_false_leader",
    )
    rows = {
        scenario_id: _v14_scenario_payload(scenario_id)
        for scenario_id in scenario_ids
    }
    rows["true_ion_exclusion"]["mechanism"]["biology_parameter_overrides"] = {
        "root_na_permeability_l_cm2_h": 0.0
    }
    rows["root_na_accumulation"]["mechanism"]["biology_parameter_overrides"] = {
        "na_efflux_vmax_mmol_h": 0.10
    }
    rows["marker_only"]["mechanism"]["biology_parameter_overrides"] = {
        "ros_clearance_h_inv": 0.40
    }
    rows["nonsaline_penalty"]["mechanism"]["biology_parameter_overrides"] = {
        "mannitol_carbon_cost_mmol_c_mmol_inv": 0.80
    }
    rows["delayed_toxicity"]["mechanism"][
        "post_onset_biology_parameter_overrides"
    ] = {"senescence_h_inv": 0.06}
    rows["sensor_drift_missingness"]["generator"]["observation"][
        "canopy_observation_error_sd"
    ] = _rq(0.12, "log-ratio")
    rows["sensor_drift_missingness"]["generator"]["missingness"][
        "missingness_stress_slope"
    ] = _rq(0.60, "logit per standardized-proxy SD")
    rows["selection_bias_false_leader"]["generator"]["hierarchy"][
        "plant_variance"
    ] = _rq(0.20, "log-ratio^2")
    return {
        "schema_version": "1.4.0",
        "water_recipe_registry_sha256": "a" * 64,
        "anchor": rows[scenario_ids[0]],
        "scenarios": [rows[scenario_id] for scenario_id in scenario_ids[1:]],
    }


def _migration_registration_payload(
    inventory: paper1_contracts.ScenarioMigrationInventory,
) -> dict[str, object]:
    retired = tuple(
        item.source_path
        for item in inventory.items
        if item.disposition is paper1_contracts.MigrationDisposition.RETIRED
        and item.source_path is not None
    )
    return {
        "schema_version": "1.0.0",
        "source_raw_sha256": inventory.source_raw_sha256,
        "target_registry": _v14_registry_payload(),
        "accepted_retired_source_paths": retired,
        "evidence_label": "synthetic_only",
    }


def test_migration_rejects_caller_forged_inventory_even_with_approved_raw_hash() -> None:
    """Catches an empty caller-authored inventory masquerading as the archive audit."""

    inventory = paper1_contracts.inspect_v13_scenario_migration(
        CONFIGS / "archive" / "synthetic_scenarios_v1_3.yaml"
    )
    forged = inventory.model_copy(
        update={
            "items": (),
            "unclassified_source_paths": (),
            "multiply_classified_source_paths": (),
        }
    )
    registration_payload = _migration_registration_payload(inventory)
    registration_payload["accepted_retired_source_paths"] = ()
    registration = paper1_contracts.ScenarioMigrationRegistration.model_validate(
        registration_payload
    )

    with pytest.raises(AlmondLabError) as exc_info:
        paper1_contracts.migrate_v13_scenario_document(forged, registration)

    assert exc_info.value.code == "SCENARIO_MIGRATION_INVALID"


def test_migration_retires_only_the_explicitly_withdrawn_legacy_authorities() -> None:
    """Catches blanket retirement of expanded scenario biology/generator leaves."""

    inventory = paper1_contracts.inspect_v13_scenario_migration(
        CONFIGS / "archive" / "synthetic_scenarios_v1_3.yaml"
    )
    retired = tuple(
        item.source_path
        for item in inventory.items
        if item.disposition is paper1_contracts.MigrationDisposition.RETIRED
        and item.source_path is not None
    )

    assert retired
    assert all(
        path.startswith("forcing.")
        or ".forcing." in path
        or path
        == (
            "scenarios[scenario_id=chassis_interaction].parameters."
            "root_conductance_l_day_mpa"
        )
        for path in retired
    )
    assert not any(
        ".parameters.root_area_cm2" in path
        or ".generator_parameters.run_variance" in path
        for path in retired
    )


def test_migration_checks_expanded_nonanchor_generator_copies_against_target() -> None:
    """Catches a non-anchor legacy duplicate being changed behind RETIRED status."""

    inventory = paper1_contracts.inspect_v13_scenario_migration(
        CONFIGS / "archive" / "synthetic_scenarios_v1_3.yaml"
    )
    payload = _migration_registration_payload(inventory)
    payload["target_registry"]["scenarios"][0]["generator"]["hierarchy"][
        "run_variance"
    ]["value"] = 0.90
    registration = paper1_contracts.ScenarioMigrationRegistration.model_validate(
        payload
    )

    with pytest.raises(AlmondLabError) as exc_info:
        paper1_contracts.migrate_v13_scenario_document(inventory, registration)

    assert exc_info.value.code == "SCENARIO_MIGRATION_INVALID"


def test_explicit_v13_migration_requires_exact_retirement_inventory() -> None:
    """Catches a migration registration silently dropping a retired source leaf."""

    inventory = paper1_contracts.inspect_v13_scenario_migration(
        CONFIGS / "archive" / "synthetic_scenarios_v1_3.yaml"
    )
    registration_payload = _migration_registration_payload(inventory)
    retired = registration_payload["accepted_retired_source_paths"]
    registration = paper1_contracts.ScenarioMigrationRegistration.model_validate(
        registration_payload
    )
    migrated = paper1_contracts.migrate_v13_scenario_document(
        inventory, registration
    )

    assert migrated is not registration.target_registry
    assert migrated.model_dump(mode="json") == registration.target_registry.model_dump(
        mode="json"
    )
    assert migrated.anchor is not registration.target_registry.anchor
    assert migrated.anchor.parameters is not registration.target_registry.anchor.parameters
    assert migrated.anchor.initial_state is not registration.target_registry.anchor.initial_state
    assert migrated.anchor.generator is not registration.target_registry.anchor.generator
    assert (
        migrated.anchor.generator.hierarchy.run_variance
        is not registration.target_registry.anchor.generator.hierarchy.run_variance
    )
    incomplete = deepcopy(registration_payload)
    incomplete["accepted_retired_source_paths"] = retired[:-1]
    with pytest.raises((ValidationError, AlmondLabError)):
        paper1_contracts.migrate_v13_scenario_document(
            inventory,
            paper1_contracts.ScenarioMigrationRegistration.model_validate(incomplete),
        )


def test_synthetic_scenarios_fail_closed_when_any_required_input_is_absent() -> None:
    """Catches an implicit biological or measurement default in a scenario."""
    with pytest.raises(AlmondLabError) as exc_info:
        LegacySyntheticScenarioConfig.model_validate(
            {"scenario_id": "perfect_control", "evidence_label": "synthetic_only"}
        )

    assert exc_info.value.code == "INCOMPLETE_SYNTHETIC_SCENARIO"
    assert exc_info.value.details == {
        "missing": ["forcing", "generator_parameters", "initial_state", "parameters"]
    }
    scenarios = _load_legacy_synthetic_scenarios()
    assert {scenario.evidence_label.value for scenario in scenarios} <= {
        "synthetic_only",
        "hypothesis_prior",
    }


def test_synthetic_scenarios_expose_full_typed_biology_state_and_forcing() -> None:
    """Catches reintroduction of aggregate root stocks or hidden equation constants."""
    scenario = _load_legacy_synthetic_scenarios()[0]

    assert isinstance(scenario.parameters, BiologyParameters)
    assert isinstance(scenario.initial_state, PlantState)
    assert isinstance(scenario.forcing, RootZoneForcing)
    assert scenario.parameters.schema_version == "1.3.0"
    assert scenario.parameters.shoot_partition_fraction == 1.0
    assert scenario.forcing.hydraulic_domain.purpose == "model_applicability"
    assert scenario.initial_state.network_state.tracked_entities >= {
        ConservedEntity.NA,
        ConservedEntity.CL,
        ConservedEntity.K,
    }
    assert {
        item.kind for item in scenario.initial_state.network_state.compartments.values()
    } >= {
        CompartmentKind.ROOT_ZONE,
        CompartmentKind.ROOT_APOPLAST,
        CompartmentKind.ROOT_SYMPLAST,
        CompartmentKind.ROOT_VACUOLE,
        CompartmentKind.XYLEM,
        CompartmentKind.SHOOT_TISSUE,
    }
    with pytest.raises(TypeError):
        scenario.generator_parameters["plant_variance"] = 100.0  # type: ignore[index]


def _write_scenario_yaml(tmp_path: Path, payload: object) -> Path:
    path = tmp_path / "synthetic_scenarios.yaml"
    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
    return path


@pytest.mark.parametrize(
    ("mutation", "expected_code", "expected_field_path"),
    [
        ("missing", "INCOMPLETE_SYNTHETIC_SCENARIO", "root"),
        ("extra", "UNREGISTERED_SYNTHETIC_PARAMETER", "root"),
        ("non_string", "SYNTHETIC_SCENARIO_INVALID", "yaml"),
    ],
)
def test_synthetic_scenario_document_rejects_nonexact_root_schema(
    tmp_path: Path,
    mutation: str,
    expected_code: str,
    expected_field_path: str,
) -> None:
    """Catches hidden, omitted, or non-string constants at the document root."""
    payload = yaml.safe_load(LEGACY_SCENARIOS.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    if mutation == "missing":
        payload.pop("biology_parameters")
    elif mutation == "extra":
        payload["hidden_growth_constant"] = 1.25
    else:
        payload[7] = "hidden"

    with pytest.raises(AlmondLabError) as exc_info:
        _load_legacy_synthetic_scenarios(_write_scenario_yaml(tmp_path, payload))

    assert exc_info.value.code == expected_code
    assert exc_info.value.field_path == expected_field_path


def test_synthetic_scenario_document_validates_detached_template_schema(
    tmp_path: Path,
) -> None:
    """Catches an unregistered template constant hidden from valid expansions."""
    payload = yaml.safe_load(LEGACY_SCENARIOS.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    scenarios = payload["scenarios"]
    assert isinstance(scenarios, list)
    for scenario in scenarios:
        scenario["parameters"] = deepcopy(scenario["parameters"])
    payload["biology_parameters"]["hidden_growth_constant"] = 1.25

    with pytest.raises(AlmondLabError) as exc_info:
        _load_legacy_synthetic_scenarios(_write_scenario_yaml(tmp_path, payload))

    assert exc_info.value.code == "UNREGISTERED_SYNTHETIC_PARAMETER"
    assert exc_info.value.field_path == "biology_parameters"


def test_synthetic_scenario_document_requires_every_template_anchor_to_be_consumed(
    tmp_path: Path,
) -> None:
    """Catches a registered root template that no scenario actually consumes."""
    payload = yaml.safe_load(LEGACY_SCENARIOS.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    scenarios = payload["scenarios"]
    assert isinstance(scenarios, list)
    for scenario in scenarios:
        scenario["forcing"] = deepcopy(scenario["forcing"])

    with pytest.raises(AlmondLabError) as exc_info:
        _load_legacy_synthetic_scenarios(_write_scenario_yaml(tmp_path, payload))

    assert exc_info.value.code == "SYNTHETIC_SCENARIO_INVALID"
    assert exc_info.value.field_path == "forcing"


@pytest.mark.parametrize(
    ("mutation", "duplicate_key"),
    [
        ("root", "hidden_growth_constant"),
        ("scenario", "scenario_id"),
        ("merged_nested", "root_na_permeability_l_cm2_h"),
    ],
)
def test_synthetic_scenario_yaml_rejects_duplicate_keys_before_merge_expansion(
    tmp_path: Path,
    mutation: str,
    duplicate_key: str,
) -> None:
    """Catches duplicate YAML keys hidden at root, scenario, or merged nesting."""
    source = LEGACY_SCENARIOS.read_text(encoding="utf-8")
    if mutation == "root":
        source += "\nhidden_growth_constant: 1.0\nhidden_growth_constant: 2.0\n"
    elif mutation == "scenario":
        source = source.replace(
            "  - scenario_id: perfect_control\n",
            "  - scenario_id: perfect_control\n    scenario_id: shadowed\n",
            1,
        )
    else:
        source = source.replace(
            "      root_na_permeability_l_cm2_h: 0.0\n",
            "      root_na_permeability_l_cm2_h: 0.0\n"
            "      root_na_permeability_l_cm2_h: 0.1\n",
            1,
        )
    malformed = tmp_path / f"duplicate-{mutation}.yaml"
    malformed.write_text(source, encoding="utf-8")

    with pytest.raises(AlmondLabError) as exc_info:
        _load_legacy_synthetic_scenarios(malformed)

    assert exc_info.value.code == "SYNTHETIC_SCENARIO_INVALID"
    assert exc_info.value.field_path == "yaml"
    assert exc_info.value.details is not None
    assert exc_info.value.details["duplicate_key"] == duplicate_key


def test_synthetic_scenario_yaml_rejects_duplicate_explicit_merge_keys(
    tmp_path: Path,
) -> None:
    """Catches duplicate ``<<`` keys being skipped by unique-key validation."""
    source = LEGACY_SCENARIOS.read_text(encoding="utf-8")
    source = source.replace(
        "      <<: *biology_parameters\n",
        "      <<: *biology_parameters\n      <<: *biology_parameters\n",
        1,
    )
    malformed = tmp_path / "duplicate-merge.yaml"
    malformed.write_text(source, encoding="utf-8")

    with pytest.raises(AlmondLabError) as exc_info:
        _load_legacy_synthetic_scenarios(malformed)

    assert exc_info.value.code == "SYNTHETIC_SCENARIO_INVALID"
    assert exc_info.value.field_path == "yaml"
    assert exc_info.value.details is not None
    assert exc_info.value.details["duplicate_key"] == "<<"


def test_synthetic_scenario_yaml_rejects_self_referential_merge_alias(
    tmp_path: Path,
) -> None:
    """Catches an alias cycle at a nested mapping before recursive construction."""
    source = LEGACY_SCENARIOS.read_text(encoding="utf-8")
    source = source.replace(
        "biology_parameters: &biology_parameters\n",
        "biology_parameters: &biology_parameters\n  <<: *biology_parameters\n",
        1,
    )
    malformed = tmp_path / "alias-cycle.yaml"
    malformed.write_text(source, encoding="utf-8")

    with pytest.raises(AlmondLabError) as exc_info:
        _load_legacy_synthetic_scenarios(malformed)

    assert exc_info.value.code == "SYNTHETIC_SCENARIO_INVALID"
    assert exc_info.value.field_path == "yaml"
    assert exc_info.value.details is not None
    assert exc_info.value.details["cause_type"] == "YamlAliasCycleError"


def test_synthetic_scenario_yaml_accepts_merge_sequence_with_explicit_override(
    tmp_path: Path,
) -> None:
    """Catches rejecting legal YAML precedence: explicit keys override merged keys."""
    source = LEGACY_SCENARIOS.read_text(encoding="utf-8")
    source = source.replace(
        "      <<: *biology_parameters\n",
        "      <<: [*biology_parameters, "
        "{root_cl_permeability_l_cm2_h: 99.0}]\n",
        1,
    )
    legal = tmp_path / "merge-sequence.yaml"
    legal.write_text(source, encoding="utf-8")

    scenarios = _load_legacy_synthetic_scenarios(legal)

    assert scenarios[1].parameters.root_na_permeability_l_cm2_h == 0.0
    assert scenarios[1].parameters.root_cl_permeability_l_cm2_h == 0.02


def test_scenario_yaml_rejects_compact_exponential_merge_before_construction(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Catches a 30-map DAG reaching PyYAML's exponential merge flattener."""
    import almondlab.biology_surrogate as biology_surrogate

    sequence = _scenario_merge_power_sequence(
        prefix="scenario_bomb_",
        levels=30,
    )
    malformed = tmp_path / "scenario-merge-expansion.yaml"
    malformed.write_text(
        _scenario_source_with_biology_merge(sequence),
        encoding="utf-8",
    )

    construction_calls = 0

    def record_construction(*args: object, **kwargs: object) -> object:
        nonlocal construction_calls
        construction_calls += 1
        return {}

    monkeypatch.setattr(
        biology_surrogate._StrictSafeLoader,
        "construct_mapping",
        record_construction,
    )
    with pytest.raises(AlmondLabError) as exc_info:
        _load_legacy_synthetic_scenarios(malformed)

    assert construction_calls == 0
    assert exc_info.value.code == "SYNTHETIC_SCENARIO_INVALID"
    assert exc_info.value.field_path == "yaml"
    assert exc_info.value.details == {"cause_type": "YamlResourceLimitError"}


def test_scenario_yaml_accepts_exact_expanded_merge_pair_budget(
    tmp_path: Path,
) -> None:
    """Catches an inclusive 10,000-pair scenario merge limit being exclusive."""
    sequence = _scenario_merge_power_sequence(
        prefix="scenario_limit_",
        levels=13,
        # Definitions cost 8,191 and aliases 1,734, so biology costs
        # 9,999 with its 74 explicit pairs. A scenario's explicit override
        # makes its expanded mapping cost exactly 10,000.
        extra_powers=(10, 9, 7, 6, 2, 1),
    )
    fixture = tmp_path / "scenario-merge-at-limit.yaml"
    fixture.write_text(
        _scenario_source_with_biology_merge(sequence),
        encoding="utf-8",
    )

    scenarios = _load_legacy_synthetic_scenarios(fixture)

    assert scenarios[1].parameters.root_area_cm2 == 10.0
    assert scenarios[1].parameters.root_na_permeability_l_cm2_h == 0.0


def test_scenario_yaml_rejects_expanded_merge_pair_limit_plus_one(
    tmp_path: Path,
) -> None:
    """Catches a downstream scenario merge expanding to 10,001 pairs."""
    sequence = _scenario_merge_power_sequence(
        prefix="scenario_over_",
        levels=13,
        extra_powers=(10, 9, 7, 6, 2, 1, 0),
    )
    fixture = tmp_path / "scenario-merge-over-limit.yaml"
    fixture.write_text(
        _scenario_source_with_biology_merge(sequence),
        encoding="utf-8",
    )

    with pytest.raises(AlmondLabError) as exc_info:
        _load_legacy_synthetic_scenarios(fixture)

    assert exc_info.value.code == "SYNTHETIC_SCENARIO_INVALID"
    assert exc_info.value.field_path == "yaml"
    assert exc_info.value.details == {"cause_type": "YamlResourceLimitError"}


def test_synthetic_scenario_yaml_translates_malformed_parser_input(
    tmp_path: Path,
) -> None:
    """Catches a PyYAML ParserError escaping the scenario contract boundary."""
    malformed = tmp_path / "malformed-scenario.yaml"
    malformed.write_text("scenarios: [\n", encoding="utf-8")

    with pytest.raises(AlmondLabError) as exc_info:
        _load_legacy_synthetic_scenarios(malformed)

    assert exc_info.value.code == "SYNTHETIC_SCENARIO_INVALID"
    assert exc_info.value.field_path == "yaml"
    assert exc_info.value.details is not None
    assert exc_info.value.details["cause_type"] == "ParserError"


def test_synthetic_scenario_yaml_rejects_non_string_mapping_keys_before_schema(
    tmp_path: Path,
) -> None:
    """Catches mixed bool/string keys reaching set sorting or schema coercion."""
    source = LEGACY_SCENARIOS.read_text(encoding="utf-8")
    malformed = tmp_path / "mixed-key-scenario.yaml"
    malformed.write_text(
        source + "true: shadow\nextra_string: other\n",
        encoding="utf-8",
    )

    with pytest.raises(AlmondLabError) as exc_info:
        _load_legacy_synthetic_scenarios(malformed)

    assert exc_info.value.code == "SYNTHETIC_SCENARIO_INVALID"
    assert exc_info.value.field_path == "yaml"
    assert exc_info.value.details is not None
    assert exc_info.value.details["cause_type"] == "YamlKeyTypeError"


def test_synthetic_scenario_yaml_rejects_graph_beyond_code_owned_depth_limit(
    tmp_path: Path,
) -> None:
    """Catches recursive traversal beyond the documented scenario graph budget."""
    import almondlab.biology_surrogate as biology_surrogate

    depth = biology_surrogate.MAX_YAML_DEPTH + 1
    nested = "[" * depth + "0" + "]" * depth
    source = LEGACY_SCENARIOS.read_text(encoding="utf-8")
    malformed = tmp_path / "scenario-depth.yaml"
    malformed.write_text(source + f"extra: {nested}\n", encoding="utf-8")

    with pytest.raises(AlmondLabError) as exc_info:
        _load_legacy_synthetic_scenarios(malformed)

    assert exc_info.value.code == "SYNTHETIC_SCENARIO_INVALID"
    assert exc_info.value.field_path == "yaml"
    assert exc_info.value.details is not None
    assert exc_info.value.details["cause_type"] == "YamlResourceLimitError"


def test_synthetic_scenario_yaml_rejects_alias_expansion_bomb(tmp_path: Path) -> None:
    """Catches excessive repeated aliases before merge construction expands them."""
    import almondlab.biology_surrogate as biology_surrogate

    aliases = ", ".join(
        "*unit" for _ in range(biology_surrogate.MAX_YAML_ALIAS_REFERENCES + 1)
    )
    source = LEGACY_SCENARIOS.read_text(encoding="utf-8")
    malformed = tmp_path / "scenario-alias-bomb.yaml"
    malformed.write_text(
        source + f"unit: &unit [1]\nbomb: [{aliases}]\n",
        encoding="utf-8",
    )

    with pytest.raises(AlmondLabError) as exc_info:
        _load_legacy_synthetic_scenarios(malformed)

    assert exc_info.value.code == "SYNTHETIC_SCENARIO_INVALID"
    assert exc_info.value.field_path == "yaml"
    assert exc_info.value.details is not None
    assert exc_info.value.details["cause_type"] == "YamlResourceLimitError"


def test_synthetic_scenario_yaml_translates_depth_1500_recursion_failure(
    tmp_path: Path,
) -> None:
    """Catches parser/composer RecursionError escaping the scenario loader."""
    nested = "[" * 1500 + "0" + "]" * 1500
    malformed = tmp_path / "scenario-recursion.yaml"
    malformed.write_text(f"extra: {nested}\n", encoding="utf-8")

    with pytest.raises(AlmondLabError) as exc_info:
        _load_legacy_synthetic_scenarios(malformed)

    assert exc_info.value.code == "SYNTHETIC_SCENARIO_INVALID"
    assert exc_info.value.field_path == "yaml"
    assert exc_info.value.details is not None
    assert exc_info.value.details["cause_type"] in {
        "RecursionError",
        "YamlResourceLimitError",
    }


def _scenario_payload() -> dict[str, object]:
    raw = yaml.safe_load(LEGACY_SCENARIOS.read_text(encoding="utf-8"))
    assert isinstance(raw, dict)
    scenarios = raw["scenarios"]
    assert isinstance(scenarios, list)
    return deepcopy(scenarios[0])


@pytest.mark.parametrize(
    ("section", "field_name", "invalid_value"),
    [
        ("parameters", "root_area_cm2", True),
        ("parameters", "root_area_cm2", "10.0"),
        ("parameters", "root_area_cm2", float("nan")),
        ("parameters", "root_area_cm2", 10**10000),
        ("initial_state", "biomass_g", object()),
        ("forcing", "apar_mol_h", float("inf")),
        ("generator_parameters", "plant_variance", False),
    ],
    ids=["bool", "string", "nan", "overflow", "object", "infinity", "nested-bool"],
)
def test_synthetic_scenario_rejects_coercive_nonfinite_and_overflow_inputs(
    section: str, field_name: str, invalid_value: object
) -> None:
    """Catches bool/string/object/nonfinite/copy-bypass at scenario boundaries."""
    payload = _scenario_payload()
    payload[section][field_name] = invalid_value

    with pytest.raises(AlmondLabError) as exc_info:
        LegacySyntheticScenarioConfig.model_validate(payload)

    assert exc_info.value.code == "SYNTHETIC_SCENARIO_INVALID"


@pytest.mark.parametrize(
    ("section", "field_name"),
    [
        ("parameters", "unregistered_growth_magic"),
        ("generator_parameters", "unregistered_growth_magic"),
    ],
)
def test_synthetic_scenario_rejects_unregistered_parameter(
    section: str, field_name: str
) -> None:
    """Catches a hidden generator knob outside either frozen keyspace."""
    payload = _scenario_payload()
    payload[section][field_name] = 1.25

    with pytest.raises(AlmondLabError) as exc_info:
        LegacySyntheticScenarioConfig.model_validate(payload)

    assert exc_info.value.code == "UNREGISTERED_SYNTHETIC_PARAMETER"
    assert exc_info.value.field_path == section
    assert exc_info.value.details == {"extra": [field_name]}


def test_synthetic_scenario_revalidates_model_copy_and_nested_maps_are_deeply_frozen() -> None:
    """Catches Pydantic model-copy bypass or mutation of canonical stock maps."""
    scenario = _load_legacy_synthetic_scenarios()[0]
    malformed = scenario.model_copy(update={"generator_parameters": {"plant_variance": True}})

    with pytest.raises(AlmondLabError) as exc_info:
        LegacySyntheticScenarioConfig.model_validate(malformed)
    with pytest.raises(TypeError):
        scenario.initial_state.network_state.compartments["root-zone"].stocks[
            ConservedEntity.NA
        ] = 0.0  # type: ignore[index]

    assert exc_info.value.code in {
        "INCOMPLETE_SYNTHETIC_SCENARIO",
        "SYNTHETIC_SCENARIO_INVALID",
    }


def test_legacy_aggregate_biology_keys_are_absent_from_scenario_config() -> None:
    """Catches silent restoration of pre-addendum aggregate model knobs."""
    payload = _scenario_payload()
    registered_names = set(payload["parameters"]) | set(payload["forcing"])

    assert {
        "root_na_permeability",
        "root_water_conductivity",
        "na_efflux_capacity",
        "root_na_initial_stock",
        "forcing_ecw_ds_m",
    }.isdisjoint(registered_names)


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
    scenarios = _load_legacy_synthetic_scenarios()

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
