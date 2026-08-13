import math
from copy import deepcopy
from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from almondlab.biology_surrogate import BiologyParameters, PlantState, RootZoneForcing
from almondlab.contracts import CompartmentKind, ConservedEntity
from almondlab.errors import AlmondLabError
from almondlab.paper1_contracts import (
    AnalysisPopulation,
    CandidateSpec,
    CandidateState,
    H3Rule,
    Paper1DesignConfig,
    ScientificLabel,
    SyntheticScenarioConfig,
    load_candidate_specs,
    load_paper1_design,
    load_synthetic_scenarios,
)


CONFIGS = Path(__file__).parents[1] / "configs"


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
    source = (CONFIGS / "synthetic_scenarios.yaml").read_text(encoding="utf-8")
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


def test_synthetic_scenarios_fail_closed_when_any_required_input_is_absent() -> None:
    """Catches an implicit biological or measurement default in a scenario."""
    with pytest.raises(AlmondLabError) as exc_info:
        SyntheticScenarioConfig.model_validate(
            {"scenario_id": "perfect_control", "evidence_label": "synthetic_only"}
        )

    assert exc_info.value.code == "INCOMPLETE_SYNTHETIC_SCENARIO"
    assert exc_info.value.details == {
        "missing": ["forcing", "generator_parameters", "initial_state", "parameters"]
    }
    scenarios = load_synthetic_scenarios(CONFIGS / "synthetic_scenarios.yaml")
    assert {scenario.evidence_label.value for scenario in scenarios} <= {
        "synthetic_only",
        "hypothesis_prior",
    }


def test_synthetic_scenarios_expose_full_typed_biology_state_and_forcing() -> None:
    """Catches reintroduction of aggregate root stocks or hidden equation constants."""
    scenario = load_synthetic_scenarios(CONFIGS / "synthetic_scenarios.yaml")[0]

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
    payload = yaml.safe_load(
        (CONFIGS / "synthetic_scenarios.yaml").read_text(encoding="utf-8")
    )
    assert isinstance(payload, dict)
    if mutation == "missing":
        payload.pop("biology_parameters")
    elif mutation == "extra":
        payload["hidden_growth_constant"] = 1.25
    else:
        payload[7] = "hidden"

    with pytest.raises(AlmondLabError) as exc_info:
        load_synthetic_scenarios(_write_scenario_yaml(tmp_path, payload))

    assert exc_info.value.code == expected_code
    assert exc_info.value.field_path == expected_field_path


def test_synthetic_scenario_document_validates_detached_template_schema(
    tmp_path: Path,
) -> None:
    """Catches an unregistered template constant hidden from valid expansions."""
    payload = yaml.safe_load(
        (CONFIGS / "synthetic_scenarios.yaml").read_text(encoding="utf-8")
    )
    assert isinstance(payload, dict)
    scenarios = payload["scenarios"]
    assert isinstance(scenarios, list)
    for scenario in scenarios:
        scenario["parameters"] = deepcopy(scenario["parameters"])
    payload["biology_parameters"]["hidden_growth_constant"] = 1.25

    with pytest.raises(AlmondLabError) as exc_info:
        load_synthetic_scenarios(_write_scenario_yaml(tmp_path, payload))

    assert exc_info.value.code == "UNREGISTERED_SYNTHETIC_PARAMETER"
    assert exc_info.value.field_path == "biology_parameters"


def test_synthetic_scenario_document_requires_every_template_anchor_to_be_consumed(
    tmp_path: Path,
) -> None:
    """Catches a registered root template that no scenario actually consumes."""
    payload = yaml.safe_load(
        (CONFIGS / "synthetic_scenarios.yaml").read_text(encoding="utf-8")
    )
    assert isinstance(payload, dict)
    scenarios = payload["scenarios"]
    assert isinstance(scenarios, list)
    for scenario in scenarios:
        scenario["forcing"] = deepcopy(scenario["forcing"])

    with pytest.raises(AlmondLabError) as exc_info:
        load_synthetic_scenarios(_write_scenario_yaml(tmp_path, payload))

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
    source = (CONFIGS / "synthetic_scenarios.yaml").read_text(encoding="utf-8")
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
        load_synthetic_scenarios(malformed)

    assert exc_info.value.code == "SYNTHETIC_SCENARIO_INVALID"
    assert exc_info.value.field_path == "yaml"
    assert exc_info.value.details is not None
    assert exc_info.value.details["duplicate_key"] == duplicate_key


def test_synthetic_scenario_yaml_rejects_duplicate_explicit_merge_keys(
    tmp_path: Path,
) -> None:
    """Catches duplicate ``<<`` keys being skipped by unique-key validation."""
    source = (CONFIGS / "synthetic_scenarios.yaml").read_text(encoding="utf-8")
    source = source.replace(
        "      <<: *biology_parameters\n",
        "      <<: *biology_parameters\n      <<: *biology_parameters\n",
        1,
    )
    malformed = tmp_path / "duplicate-merge.yaml"
    malformed.write_text(source, encoding="utf-8")

    with pytest.raises(AlmondLabError) as exc_info:
        load_synthetic_scenarios(malformed)

    assert exc_info.value.code == "SYNTHETIC_SCENARIO_INVALID"
    assert exc_info.value.field_path == "yaml"
    assert exc_info.value.details is not None
    assert exc_info.value.details["duplicate_key"] == "<<"


def test_synthetic_scenario_yaml_rejects_self_referential_merge_alias(
    tmp_path: Path,
) -> None:
    """Catches an alias cycle at a nested mapping before recursive construction."""
    source = (CONFIGS / "synthetic_scenarios.yaml").read_text(encoding="utf-8")
    source = source.replace(
        "biology_parameters: &biology_parameters\n",
        "biology_parameters: &biology_parameters\n  <<: *biology_parameters\n",
        1,
    )
    malformed = tmp_path / "alias-cycle.yaml"
    malformed.write_text(source, encoding="utf-8")

    with pytest.raises(AlmondLabError) as exc_info:
        load_synthetic_scenarios(malformed)

    assert exc_info.value.code == "SYNTHETIC_SCENARIO_INVALID"
    assert exc_info.value.field_path == "yaml"
    assert exc_info.value.details is not None
    assert exc_info.value.details["cause_type"] == "YamlAliasCycleError"


def test_synthetic_scenario_yaml_accepts_merge_sequence_with_explicit_override(
    tmp_path: Path,
) -> None:
    """Catches rejecting legal YAML precedence: explicit keys override merged keys."""
    source = (CONFIGS / "synthetic_scenarios.yaml").read_text(encoding="utf-8")
    source = source.replace(
        "      <<: *biology_parameters\n",
        "      <<: [*biology_parameters, "
        "{root_cl_permeability_l_cm2_h: 99.0}]\n",
        1,
    )
    legal = tmp_path / "merge-sequence.yaml"
    legal.write_text(source, encoding="utf-8")

    scenarios = load_synthetic_scenarios(legal)

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
        load_synthetic_scenarios(malformed)

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

    scenarios = load_synthetic_scenarios(fixture)

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
        load_synthetic_scenarios(fixture)

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
        load_synthetic_scenarios(malformed)

    assert exc_info.value.code == "SYNTHETIC_SCENARIO_INVALID"
    assert exc_info.value.field_path == "yaml"
    assert exc_info.value.details is not None
    assert exc_info.value.details["cause_type"] == "ParserError"


def test_synthetic_scenario_yaml_rejects_non_string_mapping_keys_before_schema(
    tmp_path: Path,
) -> None:
    """Catches mixed bool/string keys reaching set sorting or schema coercion."""
    source = (CONFIGS / "synthetic_scenarios.yaml").read_text(encoding="utf-8")
    malformed = tmp_path / "mixed-key-scenario.yaml"
    malformed.write_text(
        source + "true: shadow\nextra_string: other\n",
        encoding="utf-8",
    )

    with pytest.raises(AlmondLabError) as exc_info:
        load_synthetic_scenarios(malformed)

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
    source = (CONFIGS / "synthetic_scenarios.yaml").read_text(encoding="utf-8")
    malformed = tmp_path / "scenario-depth.yaml"
    malformed.write_text(source + f"extra: {nested}\n", encoding="utf-8")

    with pytest.raises(AlmondLabError) as exc_info:
        load_synthetic_scenarios(malformed)

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
    source = (CONFIGS / "synthetic_scenarios.yaml").read_text(encoding="utf-8")
    malformed = tmp_path / "scenario-alias-bomb.yaml"
    malformed.write_text(
        source + f"unit: &unit [1]\nbomb: [{aliases}]\n",
        encoding="utf-8",
    )

    with pytest.raises(AlmondLabError) as exc_info:
        load_synthetic_scenarios(malformed)

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
        load_synthetic_scenarios(malformed)

    assert exc_info.value.code == "SYNTHETIC_SCENARIO_INVALID"
    assert exc_info.value.field_path == "yaml"
    assert exc_info.value.details is not None
    assert exc_info.value.details["cause_type"] in {
        "RecursionError",
        "YamlResourceLimitError",
    }


def _scenario_payload() -> dict[str, object]:
    raw = yaml.safe_load((CONFIGS / "synthetic_scenarios.yaml").read_text(encoding="utf-8"))
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
        SyntheticScenarioConfig.model_validate(payload)

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
        SyntheticScenarioConfig.model_validate(payload)

    assert exc_info.value.code == "UNREGISTERED_SYNTHETIC_PARAMETER"
    assert exc_info.value.field_path == section
    assert exc_info.value.details == {"extra": [field_name]}


def test_synthetic_scenario_revalidates_model_copy_and_nested_maps_are_deeply_frozen() -> None:
    """Catches Pydantic model-copy bypass or mutation of canonical stock maps."""
    scenario = load_synthetic_scenarios(CONFIGS / "synthetic_scenarios.yaml")[0]
    malformed = scenario.model_copy(update={"generator_parameters": {"plant_variance": True}})

    with pytest.raises(AlmondLabError) as exc_info:
        SyntheticScenarioConfig.model_validate(malformed)
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
