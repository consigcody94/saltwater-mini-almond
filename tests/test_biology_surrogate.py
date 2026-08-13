from dataclasses import FrozenInstanceError, fields, replace
import math
from pathlib import Path

from hypothesis import given, settings, strategies as st
import pytest
import yaml

from almondlab.biology_surrogate import (
    BiologyParameters,
    CandidateEffects,
    PlantState,
    RootZoneForcing,
    StepHalvingConvergence,
    advance_plant,
    apply_candidate_effects,
    canopy_auc,
    load_candidate_effects,
    plant_fluxes,
    simulate_plant,
    stress_inputs,
)
from almondlab.contracts import (
    CompartmentKind,
    ConservedEntity,
    EvidenceLabel,
    GateState,
    InternalEntityFluxKind,
    LedgerCursor,
    OperatorPhase,
)
from almondlab.errors import AlmondLabError
from almondlab.hydraulics import HydraulicDomain
from almondlab.mass_balance import CompartmentState, NetworkState
from almondlab.paper1_contracts import load_candidate_specs


FIXTURES = Path(__file__).parent / "fixtures"
BIOLOGY_ENTITIES = frozenset(
    {ConservedEntity.NA, ConservedEntity.CL, ConservedEntity.K}
)


def test_biology_surrogate_module_is_available() -> None:
    """Catches omission of the registered Paper 1 biology module."""
    import almondlab.biology_surrogate as biology_surrogate

    assert biology_surrogate.__name__ == "almondlab.biology_surrogate"


def _compartment(
    compartment_id: str,
    kind: CompartmentKind,
    *,
    volume_l: float,
    na: float,
    cl: float,
    k: float,
    evidence_label: EvidenceLabel = EvidenceLabel.SYNTHETIC_ONLY,
) -> CompartmentState:
    return CompartmentState(
        compartment_id=compartment_id,
        kind=kind,
        loop_id="plant-loop",
        volume_l=volume_l,
        water_mass_kg=0.997 * volume_l,
        empty_reference_density_kg_l=0.997,
        stocks={
            ConservedEntity.NA: na,
            ConservedEntity.CL: cl,
            ConservedEntity.K: k,
        },
        evidence_label=evidence_label,
    )


def _network(
    *, evidence_label: EvidenceLabel = EvidenceLabel.SYNTHETIC_ONLY
) -> NetworkState:
    return NetworkState(
        compartments={
            "root-zone": _compartment(
                "root-zone", CompartmentKind.ROOT_ZONE,
                volume_l=1.0, na=4.0, cl=3.0, k=2.0,
                evidence_label=evidence_label,
            ),
            "root-apoplast": _compartment(
                "root-apoplast", CompartmentKind.ROOT_APOPLAST,
                volume_l=0.2, na=0.2, cl=0.2, k=0.1,
                evidence_label=evidence_label,
            ),
            "root-symplast": _compartment(
                "root-symplast", CompartmentKind.ROOT_SYMPLAST,
                volume_l=0.1, na=0.1, cl=0.1, k=0.1,
                evidence_label=evidence_label,
            ),
            "root-vacuole": _compartment(
                "root-vacuole", CompartmentKind.ROOT_VACUOLE,
                volume_l=0.1, na=0.05, cl=0.05, k=0.05,
                evidence_label=evidence_label,
            ),
            "xylem": _compartment(
                "xylem", CompartmentKind.XYLEM,
                volume_l=0.1, na=0.05, cl=0.05, k=0.05,
                evidence_label=evidence_label,
            ),
            "shoot": _compartment(
                "shoot", CompartmentKind.SHOOT_TISSUE,
                volume_l=0.5, na=0.2, cl=0.2, k=0.2,
                evidence_label=evidence_label,
            ),
        },
        tracked_entities=BIOLOGY_ENTITIES,
        evidence_label=evidence_label,
    )


def _state(**updates: object) -> PlantState:
    values: dict[str, object] = {
        "time_hours": 0.0,
        "biomass_g": 5.0,
        "canopy_area_cm2": 25.0,
        "ros_dimensionless": 0.2,
        "injury_dimensionless": 0.1,
        "mannitol_mmol": 0.2,
        "allocatable_energy_atp_eq": 10.0,
        "apx_expression_fraction": 0.5,
        "cipk_expression_fraction": 0.4,
        "injury_exposure_hours": 0.0,
        "alive": True,
        "death_time_hours": None,
        "network_state": _network(),
        "evidence_label": EvidenceLabel.SYNTHETIC_ONLY,
    }
    values.update(updates)
    return PlantState(**values)


def _parameters(**updates: object) -> BiologyParameters:
    values: dict[str, object] = {
        "schema_version": "1.3.0",
        "evidence_label": EvidenceLabel.HYPOTHESIS_PRIOR,
        "root_area_cm2": 10.0,
        "root_na_permeability_l_cm2_h": 0.01,
        "root_cl_permeability_l_cm2_h": 0.02,
        "root_k_permeability_l_cm2_h": 0.03,
        "na_partition_coefficient": 1.0,
        "cl_partition_coefficient": 2.0,
        "k_partition_coefficient": 1.0,
        "na_efflux_vmax_mmol_h": 0.4,
        "na_efflux_km_mmol_l": 1.0,
        "atp_cost_per_na_atp_eq_mmol_inv": 2.0,
        "na_sequestration_vmax_mmol_h": 0.1,
        "cl_sequestration_vmax_mmol_h": 0.2,
        "k_sequestration_vmax_mmol_h": 0.3,
        "na_sequestration_km_mmol_l": 1.0,
        "cl_sequestration_km_mmol_l": 1.0,
        "k_sequestration_km_mmol_l": 1.0,
        "na_vacuole_capacity_mmol": 2.0,
        "cl_vacuole_capacity_mmol": 2.0,
        "k_vacuole_capacity_mmol": 2.0,
        "na_vacuole_release_h_inv": 0.1,
        "cl_vacuole_release_h_inv": 0.2,
        "k_vacuole_release_h_inv": 0.3,
        "na_xylem_loading_l_h": 0.1,
        "cl_xylem_loading_l_h": 0.2,
        "k_xylem_loading_l_h": 0.3,
        "na_xylem_retrieval_l_h": 0.1,
        "cl_xylem_retrieval_l_h": 0.2,
        "k_xylem_retrieval_l_h": 0.3,
        "xylem_flow_l_h": 0.1,
        "shoot_partition_fraction": 1.0,
        "root_conductance_l_day_mpa": 0.5,
        "osmotic_reference_mpa": 0.1,
        "osmotic_scale_mpa": 0.5,
        "root_na_stress_weight": 0.5,
        "root_cl_stress_weight": 0.3,
        "root_k_stress_weight": 0.2,
        "root_na_critical_mmol_l": 0.5,
        "root_cl_critical_mmol_l": 0.5,
        "root_k_critical_mmol_l": 0.5,
        "root_na_stress_scale_mmol_l": 2.0,
        "root_cl_stress_scale_mmol_l": 2.0,
        "root_k_stress_scale_mmol_l": 2.0,
        "root_na_injury_multiplier": 1.0,
        "ion_weight_sum_tolerance": 1e-12,
        "ros_production_h_inv": 0.1,
        "ros_clearance_h_inv": 0.2,
        "injury_damage_h_inv": 0.3,
        "injury_repair_h_inv": 0.1,
        "mannitol_vmax_mmol_h": 0.2,
        "mannitol_km_dimensionless": 0.5,
        "mannitol_turnover_h_inv": 0.1,
        "mannitol_osmotic_coefficient_mpa_mmol_inv": 0.2,
        "mannitol_carbon_cost_mmol_c_mmol_inv": 0.4,
        "mannitol_adjustment_min_mpa": -0.5,
        "mannitol_adjustment_max_mpa": 0.5,
        "radiation_use_efficiency_g_mol_apar_inv": 0.5,
        "maintenance_cost_g_h": 0.01,
        "atp_to_biomass_g_atp_eq_inv": 0.1,
        "carbon_to_biomass_g_mmol_c_inv": 0.2,
        "redox_growth_penalty_h_inv": 0.01,
        "cipk_pleiotropy_penalty_h_inv": 0.02,
        "biomass_loss_h_inv": 0.03,
        "specific_leaf_area_cm2_g": 20.0,
        "leaf_allocation_fraction": 0.4,
        "senescence_h_inv": 0.01,
        "energy_epsilon_atp_eq": 1e-12,
        "integrator_max_step_hours": 0.25,
        "step_halving_absolute_tolerance": 1e-3,
        "step_halving_relative_tolerance": 0.05,
        "biomass_death_threshold_g": 0.05,
        "injury_death_threshold": 5.0,
        "sustained_injury_duration_hours": 24.0,
    }
    values.update(updates)
    return BiologyParameters(**values)


def _domain() -> HydraulicDomain:
    return HydraulicDomain(
        model_id="paper1-biology-v1",
        version="1.0.0",
        purpose="model_applicability",
        osmolality_min=0.0,
        osmolality_max=0.5,
        temperature_k_min=290.0,
        temperature_k_max=305.0,
        permitted_evidence_label=EvidenceLabel.PHYSICS_CONSTRAINED,
        extrapolation_policy="deny",
    )


def _forcing(**updates: object) -> RootZoneForcing:
    values: dict[str, object] = {
        "measured_osmolality_osmol_kg": 0.15,
        "temperature_k": 298.15,
        "water_density_kg_l": 0.997,
        "matric_potential_mpa": -0.1,
        "leaf_critical_potential_mpa": -2.0,
        "apar_mol_h": 1.0,
        "temperature_factor": 0.8,
        "potential_transpiration_l_day": 1.0,
        "duration_hours": 0.25,
        "evidence_label": EvidenceLabel.SYNTHETIC_ONLY,
        "hydraulic_domain": _domain(),
    }
    values.update(updates)
    return RootZoneForcing(**values)


def test_public_input_models_are_frozen_and_network_state_stays_deeply_immutable() -> None:
    """Catches mutation of a prevalidated equation input or nested plant stock."""
    state = _state()
    parameters = _parameters()
    forcing = _forcing()

    with pytest.raises(FrozenInstanceError):
        state.biomass_g = 10.0  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        parameters.root_area_cm2 = 99.0  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        forcing.duration_hours = 99.0  # type: ignore[misc]
    with pytest.raises(TypeError):
        state.network_state.compartments["root-zone"].stocks[ConservedEntity.NA] = 0.0  # type: ignore[index]


@pytest.mark.parametrize(
    "bad_value",
    [True, "1.0", object(), float("nan"), float("inf"), 10**10000],
    ids=["bool", "string", "object", "nan", "infinity", "overflow"],
)
def test_every_public_numeric_model_boundary_rejects_coercion_and_nonfinite(
    bad_value: object,
) -> None:
    """Catches coercive or nonfinite values crossing any biology model boundary."""
    constructors = (
        lambda: _state(biomass_g=bad_value),
        lambda: _parameters(root_area_cm2=bad_value),
        lambda: _forcing(apar_mol_h=bad_value),
    )

    for construct in constructors:
        with pytest.raises(AlmondLabError, match="BIOLOGY_NUMERIC_INVALID"):
            construct()
    with pytest.raises(AlmondLabError) as candidate:
        CandidateEffects(
            candidate_id="C1",
            schema_version="1.0.0",
            parameters={
                "na_efflux_vmax_multiplier": bad_value,
                "atp_cost_per_na": 1.0,
            },
            evidence_label=EvidenceLabel.HYPOTHESIS_PRIOR,
        )
    assert candidate.value.code == "CANDIDATE_PARAMETER_VIOLATION"


def test_parameter_constraints_enforce_exact_shoot_partition_and_stress_weights() -> None:
    """Catches reproductive partitioning or an unnormalized ion-stress mixture."""
    with pytest.raises(AlmondLabError) as partition:
        _parameters(shoot_partition_fraction=0.9)
    with pytest.raises(AlmondLabError) as weights:
        _parameters(root_k_stress_weight=0.3)

    assert partition.value.code == "BIOLOGY_PARAMETER_VIOLATION"
    assert partition.value.field_path == "shoot_partition_fraction"
    assert weights.value.code == "BIOLOGY_PARAMETER_VIOLATION"
    assert weights.value.field_path == "ion_stress_weights"


def test_state_death_invariants_and_public_fields_exclude_reproductive_or_claim_outputs() -> None:
    """Catches inconsistent death state or a forbidden claim-bearing output field."""
    with pytest.raises(AlmondLabError, match="BIOLOGY_STATE_VIOLATION"):
        _state(alive=False, death_time_hours=None)
    with pytest.raises(AlmondLabError, match="BIOLOGY_STATE_VIOLATION"):
        _state(alive=False, death_time_hours=0.0, canopy_area_cm2=1.0)

    public_names = {
        field.name
        for model in (PlantState, BiologyParameters, RootZoneForcing, CandidateEffects)
        for field in fields(model)
    }
    assert {
        "winner",
        "best_candidate",
        "kernel_yield",
        "survival_prediction",
        "salt_tolerance",
        "reproductive_biomass",
    }.isdisjoint(public_names)


@pytest.mark.parametrize(
    ("candidate_id", "effects", "changed"),
    [
        (
            "C1",
            {"na_efflux_vmax_multiplier": 2.0, "atp_cost_per_na": 3.0},
            {
                "na_efflux_vmax_mmol_h": 0.8,
                "atp_cost_per_na_atp_eq_mmol_inv": 3.0,
            },
        ),
        (
            "C2",
            {"ros_clearance_multiplier": 3.0, "redox_growth_penalty": 0.07},
            {"ros_clearance_h_inv": 0.6, "redox_growth_penalty_h_inv": 0.07},
        ),
        (
            "C3",
            {"mannitol_vmax_multiplier": 1.5, "mannitol_carbon_cost": 0.9},
            {
                "mannitol_vmax_mmol_h": 0.3,
                "mannitol_carbon_cost_mmol_c_mmol_inv": 0.9,
            },
        ),
        (
            "C4",
            {
                "na_efflux_vmax_multiplier": 1.5,
                "xylem_loading_leak_multiplier": 1.5,
            },
            {"na_efflux_vmax_mmol_h": 0.6, "na_xylem_loading_l_h": 0.15},
        ),
        (
            "C5",
            {
                "xylem_na_retrieval_multiplier": 4.0,
                "root_na_injury_multiplier": 1.7,
            },
            {"na_xylem_retrieval_l_h": 0.4, "root_na_injury_multiplier": 1.7},
        ),
        (
            "C6",
            {
                "sos_efflux_activation_multiplier": 1.3,
                "cipk_pleiotropy_penalty": 0.08,
            },
            {"na_efflux_vmax_mmol_h": 0.52, "cipk_pleiotropy_penalty_h_inv": 0.08},
        ),
    ],
)
def test_all_six_candidate_mappings_change_only_the_exact_isolation_whitelist(
    candidate_id: str, effects: dict[str, float], changed: dict[str, float]
) -> None:
    """Catches a candidate effect leaking into any unrelated equation input."""
    baseline = _parameters()
    baseline_values = {field.name: getattr(baseline, field.name) for field in fields(baseline)}
    candidate = next(
        item
        for item in load_candidate_specs(Path(__file__).parents[1] / "configs" / "candidates.yaml").candidates
        if item.candidate_id == candidate_id
    )
    effect = CandidateEffects(
        candidate_id=candidate_id,
        schema_version="1.0.0",
        parameters=effects,
        evidence_label=EvidenceLabel.HYPOTHESIS_PRIOR,
    )

    adjusted = apply_candidate_effects(baseline, effect, candidate)

    adjusted_values = {field.name: getattr(adjusted, field.name) for field in fields(adjusted)}
    for name, value in changed.items():
        assert adjusted_values.pop(name) == pytest.approx(value)
        baseline_values.pop(name)
    assert adjusted_values == baseline_values
    assert {field.name: getattr(baseline, field.name) for field in fields(baseline)} == baseline_values | {
        name: getattr(baseline, name) for name in changed
    }


def test_candidate_effect_mapping_is_copied_and_deeply_immutable() -> None:
    """Catches mutation of a previously validated candidate-effect anchor."""
    source = {"na_efflux_vmax_multiplier": 2.0, "atp_cost_per_na": 3.0}
    effects = CandidateEffects(
        candidate_id="C1",
        schema_version="1.0.0",
        parameters=source,
        evidence_label=EvidenceLabel.HYPOTHESIS_PRIOR,
    )
    source["atp_cost_per_na"] = 99.0

    assert effects.parameters["atp_cost_per_na"] == 3.0
    with pytest.raises(TypeError):
        effects.parameters["atp_cost_per_na"] = 5.0  # type: ignore[index]


@pytest.mark.parametrize(
    ("candidate_id", "parameters"),
    [
        ("C1", {"na_efflux_vmax_multiplier": 2.0}),
        (
            "C1",
            {
                "na_efflux_vmax_multiplier": 2.0,
                "atp_cost_per_na": 1.0,
                "external_osmolality": 0.0,
            },
        ),
        (
            "C2",
            {"na_efflux_vmax_multiplier": 2.0, "atp_cost_per_na": 1.0},
        ),
        ("C7", {"invented_multiplier": 1.0, "invented_cost": 0.0}),
        (
            "C1",
            {"na_efflux_vmax_multiplier": 0.0, "atp_cost_per_na": 1.0},
        ),
        (
            "C2",
            {"ros_clearance_multiplier": 1.0, "redox_growth_penalty": -0.1},
        ),
        (
            "C3",
            {"mannitol_vmax_multiplier": float("nan"), "mannitol_carbon_cost": 0.1},
        ),
        (
            "C4",
            {"na_efflux_vmax_multiplier": True, "xylem_loading_leak_multiplier": 1.0},
        ),
    ],
)
def test_candidate_effects_reject_missing_extra_mismatched_or_malformed_values(
    candidate_id: str, parameters: dict[str, object]
) -> None:
    """Catches every route around the exact C1-C6 parameter whitelist."""
    with pytest.raises(AlmondLabError) as exc_info:
        CandidateEffects(
            candidate_id=candidate_id,
            schema_version="1.0.0",
            parameters=parameters,
            evidence_label=EvidenceLabel.HYPOTHESIS_PRIOR,
        )

    assert exc_info.value.code == "CANDIDATE_PARAMETER_VIOLATION"


def test_apply_candidate_effects_revalidates_candidate_and_refuses_id_mismatch() -> None:
    """Catches copy-bypass or use of an effect with the wrong registered candidate."""
    registry = load_candidate_specs(Path(__file__).parents[1] / "configs" / "candidates.yaml")
    effects = CandidateEffects(
        candidate_id="C1",
        schema_version="1.0.0",
        parameters={"na_efflux_vmax_multiplier": 2.0, "atp_cost_per_na": 3.0},
        evidence_label=EvidenceLabel.HYPOTHESIS_PRIOR,
    )
    with pytest.raises(AlmondLabError) as mismatch:
        apply_candidate_effects(_parameters(), effects, registry.candidates[1])

    malformed = registry.candidates[0].model_copy(update={"primary_parameter_id": "wrong"})
    with pytest.raises(AlmondLabError) as copied:
        apply_candidate_effects(_parameters(), effects, malformed)

    assert mismatch.value.code == "CANDIDATE_PARAMETER_VIOLATION"
    assert copied.value.code == "CANDIDATE_PARAMETER_VIOLATION"


def _candidate_effect(candidate_id: str, parameters: dict[str, float]) -> BiologyParameters:
    candidate = next(
        item
        for item in load_candidate_specs(Path(__file__).parents[1] / "configs" / "candidates.yaml").candidates
        if item.candidate_id == candidate_id
    )
    return apply_candidate_effects(
        _parameters(),
        CandidateEffects(
            candidate_id=candidate_id,
            schema_version="1.0.0",
            parameters=parameters,
            evidence_label=EvidenceLabel.HYPOTHESIS_PRIOR,
        ),
        candidate,
    )


def test_stress_inputs_match_hand_calculation_and_keep_osmotic_and_ion_terms_separate() -> None:
    """Catches use of EC/Na as a substitute for measured bulk osmolality."""
    stress = stress_inputs(_state(), _parameters(), _forcing())

    assert stress.osmotic_potential_mpa == pytest.approx(-0.37072802377020436)
    assert stress.osmotic_excess_dimensionless == pytest.approx(0.5414560475404087)
    assert stress.root_na_excess_dimensionless == pytest.approx(0.25)
    assert stress.root_cl_excess_dimensionless == pytest.approx(0.25)
    assert stress.root_k_excess_dimensionless == pytest.approx(0.25)
    assert stress.ion_excess_dimensionless == pytest.approx(0.25)
    assert stress.specific_ion_factor == pytest.approx(math.exp(-0.1))
    assert stress.evidence_label is EvidenceLabel.SYNTHETIC_ONLY


def test_root_na_multiplier_changes_only_the_weighted_na_stress_contribution() -> None:
    """Catches a C5 root-Na tradeoff leaking into Cl, K, or osmotic stress."""
    baseline = stress_inputs(_state(), _parameters(), _forcing())
    adjusted = stress_inputs(
        _state(), _parameters(root_na_injury_multiplier=2.0), _forcing()
    )

    assert adjusted.root_na_excess_dimensionless == pytest.approx(0.5)
    assert adjusted.root_cl_excess_dimensionless == baseline.root_cl_excess_dimensionless
    assert adjusted.root_k_excess_dimensionless == baseline.root_k_excess_dimensionless
    assert adjusted.osmotic_excess_dimensionless == baseline.osmotic_excess_dimensionless
    assert adjusted.ion_excess_dimensionless == pytest.approx(0.375)


def test_plant_fluxes_match_all_seven_pre_step_transition_equations() -> None:
    """Catches a wrong concentration, endpoint, kind, or pre-step rate equation."""
    fluxes = plant_fluxes(_state(), _parameters(), _forcing())
    rates = {event.event_id: event.rate_per_hour for event in fluxes.events}

    assert rates == pytest.approx(
        {
            "uptake-na": 0.30,
            "uptake-cl": 0.50,
            "uptake-k": 0.45,
            "efflux-na": 0.20,
            "sequester-na": 0.04875,
            "sequester-cl": 0.0975,
            "sequester-k": 0.14625,
            "release-na": 0.005,
            "release-cl": 0.010,
            "release-k": 0.015,
            "load-na": 0.10,
            "load-cl": 0.20,
            "load-k": 0.30,
            "retrieve-na": 0.05,
            "retrieve-cl": 0.10,
            "retrieve-k": 0.15,
            "deposit-na": 0.05,
            "deposit-cl": 0.05,
            "deposit-k": 0.05,
        }
    )
    assert fluxes.efflux_demand_mmol_h == pytest.approx(0.20)
    assert fluxes.efflux_atp_fraction == pytest.approx(1.0)
    assert fluxes.mannitol_synthesis_mmol_h == pytest.approx(0.10398058541580463)
    assert fluxes.adjustment_mpa == pytest.approx(0.04)
    assert fluxes.electrochemical_interpretation is GateState.NOT_EVALUABLE
    assert fluxes.evidence_label is EvidenceLabel.SYNTHETIC_ONLY

    endpoint_oracle = {
        InternalEntityFluxKind.PLANT_UPTAKE: (
            CompartmentKind.ROOT_ZONE,
            CompartmentKind.ROOT_SYMPLAST,
        ),
        InternalEntityFluxKind.PLANT_EFFLUX: (
            CompartmentKind.ROOT_SYMPLAST,
            CompartmentKind.ROOT_ZONE,
        ),
        InternalEntityFluxKind.SEQUESTRATION: (
            CompartmentKind.ROOT_SYMPLAST,
            CompartmentKind.ROOT_VACUOLE,
        ),
        InternalEntityFluxKind.VACUOLE_RELEASE: (
            CompartmentKind.ROOT_VACUOLE,
            CompartmentKind.ROOT_SYMPLAST,
        ),
        InternalEntityFluxKind.XYLEM_LOADING: (
            CompartmentKind.ROOT_SYMPLAST,
            CompartmentKind.XYLEM,
        ),
        InternalEntityFluxKind.XYLEM_RETRIEVAL: (
            CompartmentKind.XYLEM,
            CompartmentKind.ROOT_SYMPLAST,
        ),
        InternalEntityFluxKind.TISSUE_DEPOSITION: (
            CompartmentKind.XYLEM,
            CompartmentKind.SHOOT_TISSUE,
        ),
    }
    network = _state().network_state
    for event in fluxes.events:
        assert event.phase is OperatorPhase.PLANT_ION_TRANSITIONS
        assert (
            network.compartments[event.source].kind,
            network.compartments[event.target].kind,
        ) == endpoint_oracle[event.kind]


def test_apx_candidate_preserves_the_complete_baseline_ion_event_set_and_rates() -> None:
    """Catches APX directly changing ordinary Na, Cl, or K transport."""
    baseline = plant_fluxes(_state(), _parameters(), _forcing())
    apx = plant_fluxes(
        _state(),
        _candidate_effect(
            "C2", {"ros_clearance_multiplier": 2.0, "redox_growth_penalty": 0.1}
        ),
        _forcing(),
    )

    assert apx.events == baseline.events


def test_c4_efflux_and_xylem_loading_leak_are_separate_directional_observables() -> None:
    """Catches conflation of C4 outward efflux with its xylem-loading risk."""
    baseline = plant_fluxes(_state(), _parameters(), _forcing())
    c4 = plant_fluxes(
        _state(),
        _candidate_effect(
            "C4",
            {
                "na_efflux_vmax_multiplier": 2.0,
                "xylem_loading_leak_multiplier": 3.0,
            },
        ),
        _forcing(),
    )
    base_rates = {event.event_id: event.rate_per_hour for event in baseline.events}
    c4_rates = {event.event_id: event.rate_per_hour for event in c4.events}

    assert c4_rates["efflux-na"] == pytest.approx(2.0 * base_rates["efflux-na"])
    assert c4_rates["load-na"] == pytest.approx(3.0 * base_rates["load-na"])
    for event_id in base_rates.keys() - {"efflux-na", "load-na"}:
        assert c4_rates[event_id] == base_rates[event_id]


def test_c3_adjustment_is_bounded_and_never_mutates_external_forcing() -> None:
    """Catches C3 rewriting osmolality or bypassing the ±0.50 MPa bound."""
    forcing = _forcing()
    forcing_snapshot = replace(forcing)
    c3 = _candidate_effect(
        "C3", {"mannitol_vmax_multiplier": 2.0, "mannitol_carbon_cost": 0.8}
    )

    fluxes = plant_fluxes(_state(mannitol_mmol=10.0), c3, forcing)

    assert fluxes.adjustment_mpa == 0.5
    assert forcing == forcing_snapshot
    assert forcing.measured_osmolality_osmol_kg == 0.15
    assert c3.mannitol_carbon_cost_mmol_c_mmol_inv == 0.8


def test_stress_and_flux_public_boundaries_revalidate_copy_bypasses_and_overflow() -> None:
    """Catches malformed copied inputs and nonfinite derived flux arithmetic."""
    malformed = _state()
    object.__setattr__(malformed, "injury_dimensionless", "0.1")
    with pytest.raises(AlmondLabError) as copied:
        stress_inputs(malformed, _parameters(), _forcing())

    with pytest.raises(AlmondLabError) as overflow:
        plant_fluxes(
            _state(),
            _parameters(
                root_area_cm2=1e308,
                root_na_permeability_l_cm2_h=1e308,
            ),
            _forcing(),
        )

    assert copied.value.code == "BIOLOGY_NUMERIC_INVALID"
    assert overflow.value.code == "BIOLOGY_NUMERIC_INVALID"


def _cursor() -> LedgerCursor:
    return LedgerCursor(run_id="BIO", chain_id="plant", next_ordinal=0)


def test_advance_plant_uses_canonical_core_literal_audit_and_matches_euler_hand_oracle() -> None:
    """Catches hidden transport, post-step derivatives, or unaudited ledger use."""
    before = _state()

    result = advance_plant(before, _parameters(), _forcing(), cursor=_cursor())

    assert result.substeps == 1
    assert len(result.states) == 2
    assert len(result.ledger) == 38
    assert len(result.expected_events) == 19
    assert len(result.expected_transactions) == 19
    assert len(result.audits) == 1
    assert result.audits[0].balanced, result.audits[0].structural_errors
    assert result.next_cursor.next_ordinal == 19
    assert result.state.biomass_g == pytest.approx(5.0364171884500815)
    assert result.state.canopy_area_cm2 == pytest.approx(25.285087507600654)
    assert result.state.ros_dimensionless == pytest.approx(0.20978640118851022)
    assert result.state.injury_dimensionless == pytest.approx(0.1125)
    assert result.state.mannitol_mmol == pytest.approx(0.22099514635395118)
    assert result.state.allocatable_energy_atp_eq == pytest.approx(9.9)
    step = result.steps[0]
    assert step.hydraulic.actual_l_day == pytest.approx(0.7846359881148979)
    assert step.applied_na_efflux_mmol_h == pytest.approx(0.2)
    assert step.gross_growth_g_h == pytest.approx(0.28398720063359123)
    assert step.total_cost_g_h == pytest.approx(0.1233184468332644)
    assert step.biomass_derivative_g_h == pytest.approx(0.14566875380032684)
    assert step.canopy_derivative_cm2_h == pytest.approx(1.1403500304026148)
    assert before == _state()
    for entity in BIOLOGY_ENTITIES:
        assert result.state.network_state.total_stock(entity) == pytest.approx(
            before.network_state.total_stock(entity)
        )


@pytest.mark.parametrize(
    ("max_step_hours", "duration_hours", "expected_substeps"),
    [
        (0.1, 1.0, 10),
        (0.2, 2 / 10, 1),
        (0.1, 1.1 / 10, 2),
    ],
)
def test_advance_plant_partitions_float_durations_without_tail_loss(
    max_step_hours: float,
    duration_hours: float,
    expected_substeps: int,
) -> None:
    """Catches float-tail rejection, omission, or an oversized biology substep."""
    before = _state()

    result = advance_plant(
        before,
        _parameters(integrator_max_step_hours=max_step_hours),
        _forcing(duration_hours=duration_hours),
        cursor=_cursor(),
    )

    step_durations = [step.duration_hours for step in result.steps]
    assert result.substeps == expected_substeps
    assert math.fsum(step_durations) == duration_hours
    assert all(0.0 < step <= max_step_hours for step in step_durations)
    assert result.state.time_hours == before.time_hours + duration_hours
    assert result.state == result.states[-1]
    assert result.state.biomass_g != before.biomass_g
    assert len(result.expected_events) == 19 * expected_substeps
    assert len(result.expected_transactions) == 19 * expected_substeps
    assert len(result.ledger) == 38 * expected_substeps
    assert result.next_cursor.next_ordinal == 19 * expected_substeps


def test_advance_plant_uses_the_exact_reported_duration_for_adversarial_partition() -> None:
    """Catches a bounded substep partition whose integrated dt is one ULP too long."""
    duration_hours = 0.03496126797633995
    maximum_step_hours = 0.0010197566398756233

    result = advance_plant(
        _state(),
        _parameters(integrator_max_step_hours=maximum_step_hours),
        _forcing(duration_hours=duration_hours),
        cursor=_cursor(),
    )

    integrated_duration = math.fsum(step.duration_hours for step in result.steps)
    assert integrated_duration == duration_hours
    assert result.state.time_hours == duration_hours
    assert all(
        0.0 < step.duration_hours <= maximum_step_hours for step in result.steps
    )


@settings(max_examples=60, deadline=None)
@given(
    maximum_step_hours=st.sampled_from(
        [
            math.nextafter(2e-14, math.inf),
            1e-12,
            math.nextafter(0.001, math.inf),
            0.1,
            0.25,
        ]
    ),
    factor=st.integers(min_value=1, max_value=64),
)
def test_substep_partition_property_preserves_binary64_duration_authority(
    maximum_step_hours: float,
    factor: int,
) -> None:
    """Catches ordinary or extreme accepted floats losing exact integrated dt."""
    import almondlab.biology_surrogate as biology_surrogate

    duration_hours = maximum_step_hours * factor
    partition = biology_surrogate._substep_partition(
        duration_hours,
        maximum_step_hours,
    )

    assert math.fsum(partition) == duration_hours
    assert all(0.0 < step <= maximum_step_hours for step in partition)


@pytest.mark.parametrize(
    "duration_hours",
    [math.nextafter(0.0, 1.0), math.ulp(0.0), 1e-15, 1e-14],
)
def test_root_zone_forcing_rejects_durations_outside_public_core_domain(
    duration_hours: float,
) -> None:
    """Catches a public forcing interval accepted only to hit a hidden core epsilon."""
    with pytest.raises(AlmondLabError) as exc_info:
        _forcing(duration_hours=duration_hours)

    assert exc_info.value.code == "BIOLOGY_FORCING_VIOLATION"
    assert exc_info.value.field_path == "duration_hours"


def test_duration_immediately_above_public_core_minimum_integrates() -> None:
    """Catches an explicit minimum-duration contract that rejects its open boundary."""
    duration_hours = math.nextafter(1e-14, math.inf)

    result = advance_plant(
        _state(),
        _parameters(),
        _forcing(duration_hours=duration_hours),
        cursor=_cursor(),
    )

    assert math.fsum(step.duration_hours for step in result.steps) == duration_hours
    assert result.state.time_hours == duration_hours


@pytest.mark.parametrize("maximum_step_hours", [1e-14, 2e-14])
def test_biology_parameters_reject_core_incompatible_integrator_maximum(
    maximum_step_hours: float,
) -> None:
    """Catches a registered maximum that can only produce core-rejected substeps."""
    with pytest.raises(AlmondLabError) as exc_info:
        _parameters(integrator_max_step_hours=maximum_step_hours)

    assert exc_info.value.code == "BIOLOGY_PARAMETER_VIOLATION"
    assert exc_info.value.field_path == "integrator_max_step_hours"


def test_advance_plant_rejects_unrepresentable_time_progress_before_flux_work() -> None:
    """Catches a positive interval that cannot advance binary64 public time."""
    before = _state(time_hours=1e308)
    cursor = _cursor()
    parameters = _parameters(
        root_area_cm2=1e308,
        root_na_permeability_l_cm2_h=1e308,
    )

    with pytest.raises(AlmondLabError) as exc_info:
        advance_plant(
            before,
            parameters,
            _forcing(duration_hours=0.1),
            cursor=cursor,
        )

    assert exc_info.value.code == "BIOLOGY_NUMERIC_INVALID"
    assert exc_info.value.field_path == "forcing.duration_hours"
    assert before == _state(time_hours=1e308)
    assert cursor == _cursor()


@pytest.mark.parametrize(
    ("duration_hours", "expected_fraction", "expected_energy"),
    [
        (0.25, 0.1 / (2.0 * 0.2 * 0.25 + 1e-12), 1e-12),
        (0.125, 1.0, 0.05),
    ],
)
def test_atp_limiting_compares_energy_to_interval_amount_demand(
    duration_hours: float,
    expected_fraction: float,
    expected_energy: float,
) -> None:
    """Catches comparing an ATP-equivalent amount directly with an hourly rate."""
    state = _state(allocatable_energy_atp_eq=0.1)
    parameters = _parameters(
        atp_cost_per_na_atp_eq_mmol_inv=2.0,
        energy_epsilon_atp_eq=1e-12,
    )
    forcing = _forcing(duration_hours=duration_hours)

    fluxes = plant_fluxes(state, parameters, forcing)
    result = advance_plant(state, parameters, forcing, cursor=_cursor())
    efflux = next(event for event in fluxes.events if event.event_id == "efflux-na")

    assert fluxes.efflux_demand_mmol_h == pytest.approx(0.2)
    assert fluxes.efflux_atp_fraction == pytest.approx(expected_fraction)
    assert efflux.rate_per_hour == pytest.approx(expected_fraction * 0.2)
    assert result.state.allocatable_energy_atp_eq == pytest.approx(
        expected_energy, abs=2e-12
    )


def test_zero_efflux_demand_has_full_atp_fraction_and_charges_no_energy() -> None:
    """Catches a zero-demand numerical floor being reported as ATP limitation."""
    state = _state(allocatable_energy_atp_eq=0.0)
    parameters = _parameters(na_efflux_vmax_mmol_h=0.0)

    fluxes = plant_fluxes(state, parameters, _forcing())
    result = advance_plant(state, parameters, _forcing(), cursor=_cursor())

    assert fluxes.efflux_demand_mmol_h == 0.0
    assert fluxes.efflux_atp_fraction == 1.0
    assert not any(event.event_id == "efflux-na" for event in fluxes.events)
    assert result.state.allocatable_energy_atp_eq == 0.0


def test_zero_atp_cost_allows_nonzero_ion_demand_with_zero_available_energy() -> None:
    """Catches treating zero ATP demand as energy-limited nonzero ion demand."""
    state = _state(allocatable_energy_atp_eq=0.0)
    parameters = _parameters(
        atp_cost_per_na_atp_eq_mmol_inv=0.0,
        na_sequestration_vmax_mmol_h=0.0,
        na_xylem_loading_l_h=0.0,
    )

    fluxes = plant_fluxes(state, parameters, _forcing(duration_hours=0.25))
    result = advance_plant(
        state,
        parameters,
        _forcing(duration_hours=0.25),
        cursor=_cursor(),
    )
    requested = next(event for event in fluxes.events if event.event_id == "efflux-na")
    applied = next(
        item
        for item in result.expected_transactions
        if item.event_id.endswith("-efflux-na")
    )

    assert fluxes.efflux_demand_mmol_h == pytest.approx(0.2)
    assert fluxes.efflux_atp_fraction == 1.0
    assert requested.rate_per_hour == pytest.approx(0.2)
    assert applied.amounts[ConservedEntity.NA] == pytest.approx(0.05)
    assert result.steps[0].applied_na_efflux_mmol_h == pytest.approx(0.2)
    assert result.state.allocatable_energy_atp_eq == 0.0


def test_cap_competition_literals_charge_energy_from_applied_not_requested_efflux() -> None:
    """Catches ATP cost based on uncapped efflux when Na outflows compete."""
    state = _state(allocatable_energy_atp_eq=100.0)
    parameters = _parameters(
        root_na_permeability_l_cm2_h=0.0,
        root_cl_permeability_l_cm2_h=0.0,
        root_k_permeability_l_cm2_h=0.0,
        na_efflux_vmax_mmol_h=4.0,
        na_sequestration_vmax_mmol_h=4.0,
        na_xylem_loading_l_h=4.0,
        atp_cost_per_na_atp_eq_mmol_inv=2.0,
    )

    result = advance_plant(state, parameters, _forcing(), cursor=_cursor())
    expectations = {
        item.event_id.rsplit("-", 2)[-2] + "-" + item.event_id.rsplit("-", 1)[-1]: item
        for item in result.expected_transactions
        if item.event_id.endswith(("efflux-na", "sequester-na", "load-na"))
    }
    expected_requests = {
        "efflux-na": 0.5,
        "sequester-na": 0.4875,
        "load-na": 1.0,
    }
    cap = 0.1 / sum(expected_requests.values())

    for event_id, requested in expected_requests.items():
        assert expectations[event_id].amounts[ConservedEntity.NA] == pytest.approx(
            requested * cap
        )
    applied_efflux = 0.5 * cap
    assert result.steps[0].applied_na_efflux_mmol_h == pytest.approx(
        applied_efflux / 0.25
    )
    assert result.state.allocatable_energy_atp_eq == pytest.approx(
        100.0 - 2.0 * applied_efflux
    )
    assert result.audits[0].balanced


def test_generated_fluxes_remain_order_invariant_with_independent_literal_authority() -> None:
    """Catches order-dependent cap allocation among generated biology events."""
    from almondlab.mass_balance import LedgerTransactionExpectation, audit_ledger, step_state

    state = _state()
    generated = plant_fluxes(state, _parameters(), _forcing()).events
    fluxes = tuple(
        event
        for event in generated
        if event.event_id in {"efflux-na", "load-na", "sequester-na"}
    )
    forward = step_state(
        state.network_state,
        dt_hours=0.25,
        cursor=_cursor(),
        entity_fluxes=fluxes,
    )
    reverse = step_state(
        state.network_state,
        dt_hours=0.25,
        cursor=_cursor(),
        entity_fluxes=tuple(reversed(fluxes)),
    )
    literal = (
        LedgerTransactionExpectation(
            transaction_id="tx:BIO:plant:000000000000",
            event_id="efflux-na",
            dt_hours=0.25,
            amounts={ConservedEntity.NA: 0.05},
        ),
        LedgerTransactionExpectation(
            transaction_id="tx:BIO:plant:000000000001",
            event_id="load-na",
            dt_hours=0.25,
            amounts={ConservedEntity.NA: 0.025},
        ),
        LedgerTransactionExpectation(
            transaction_id="tx:BIO:plant:000000000002",
            event_id="sequester-na",
            dt_hours=0.25,
            amounts={ConservedEntity.NA: 0.0121875},
        ),
    )

    assert forward.state == reverse.state
    assert forward.ledger == reverse.ledger
    assert audit_ledger(
        state.network_state,
        reverse.state,
        reverse.ledger,
        expected_events=fluxes,
        expected_transactions=literal,
    ).balanced


def test_c5_retrieval_redistributes_na_without_deleting_any_stock() -> None:
    """Catches a C5 retrieval implementation that treats root retention as removal."""
    parameters = _candidate_effect(
        "C5",
        {"xylem_na_retrieval_multiplier": 5.0, "root_na_injury_multiplier": 2.0},
    )
    before = _state()
    baseline = advance_plant(before, _parameters(), _forcing(), cursor=_cursor())
    c5 = advance_plant(before, parameters, _forcing(), cursor=_cursor())

    assert c5.state.network_state.compartments["xylem"].stocks[ConservedEntity.NA] < (
        baseline.state.network_state.compartments["xylem"].stocks[ConservedEntity.NA]
    )
    assert c5.state.network_state.compartments["root-symplast"].stocks[ConservedEntity.NA] > (
        baseline.state.network_state.compartments["root-symplast"].stocks[ConservedEntity.NA]
    )
    assert c5.state.network_state.total_stock(ConservedEntity.NA) == pytest.approx(
        before.network_state.total_stock(ConservedEntity.NA)
    )


def test_perfect_na_exclusion_still_has_registered_bulk_osmotic_hydraulic_penalty() -> None:
    """Catches ion exclusion erasing measured-osmolality water stress."""
    state = _state(injury_dimensionless=0.0, mannitol_mmol=0.0)
    parameters = _parameters(
        root_na_permeability_l_cm2_h=0.0,
        root_cl_permeability_l_cm2_h=0.0,
        root_k_permeability_l_cm2_h=0.0,
        root_conductance_l_day_mpa=0.5,
    )
    domain = HydraulicDomain(
        model_id="core-v1-acceptance-13",
        version="1.0.0",
        purpose="model_applicability",
        osmolality_min=0.05,
        osmolality_max=0.40,
        temperature_k_min=298.15,
        temperature_k_max=298.15,
        permitted_evidence_label=EvidenceLabel.PHYSICS_CONSTRAINED,
        extrapolation_policy="deny",
    )
    forcing = _forcing(
        measured_osmolality_osmol_kg=0.05,
        hydraulic_domain=domain,
        temperature_factor=0.0,
    )
    fresh = advance_plant(state, parameters, forcing, cursor=_cursor())
    saline = advance_plant(
        state,
        parameters,
        replace(forcing, measured_osmolality_osmol_kg=0.40),
        cursor=_cursor(),
    )
    fresh_uptake = fresh.steps[0].hydraulic.actual_l_day
    saline_uptake = saline.steps[0].hydraulic.actual_l_day

    assert fresh_uptake == pytest.approx(0.888212, abs=1e-6)
    assert saline_uptake == pytest.approx(0.455696, abs=1e-6)
    assert saline_uptake / fresh_uptake == pytest.approx(0.513049, abs=1e-6)


def test_death_sets_canopy_and_reported_ions_missing_while_physical_stocks_persist() -> None:
    """Catches zero-filled post-death ions or post-mortem physical transport."""
    dying = advance_plant(
        _state(biomass_g=0.1),
        _parameters(maintenance_cost_g_h=10.0),
        _forcing(),
        cursor=_cursor(),
    )

    assert dying.state.alive is False
    assert dying.state.canopy_area_cm2 == 0.0
    assert dying.state.death_time_hours == pytest.approx(0.25)
    assert dying.state.reported_ion_stocks_mmol is None
    physical = dying.state.network_state

    post = advance_plant(
        dying.state,
        _parameters(),
        _forcing(),
        cursor=dying.next_cursor,
    )
    assert post.state.network_state == physical
    assert post.state.reported_ion_stocks_mmol is None
    assert post.ledger == ()
    assert post.state.canopy_area_cm2 == 0.0


def test_sustained_injury_adjudication_uses_updated_state_and_resets_below_threshold() -> None:
    """Catches one-step injury death or failure to reset sustained exposure."""
    parameters = _parameters(
        injury_death_threshold=1.0,
        sustained_injury_duration_hours=1.0,
        injury_damage_h_inv=0.0,
        injury_repair_h_inv=0.0,
    )
    reset = advance_plant(
        _state(injury_dimensionless=0.9, injury_exposure_hours=0.9),
        parameters,
        _forcing(),
        cursor=_cursor(),
    )
    death = advance_plant(
        _state(injury_dimensionless=1.0, injury_exposure_hours=0.75),
        parameters,
        _forcing(),
        cursor=_cursor(),
    )

    assert reset.state.alive is True
    assert reset.state.injury_exposure_hours == 0.0
    assert death.state.alive is False
    assert death.state.injury_exposure_hours == pytest.approx(1.0)


@pytest.mark.parametrize(
    ("times", "canopy", "pretreatment"),
    [
        ([0.0], [2.0], 2.0),
        ([0.0, 1.0], [2.0], 2.0),
        ([0.0, 0.0], [2.0, 2.0], 2.0),
        ([0.0, 1.0], [2.0, -1.0], 2.0),
        ([0.0, float("nan")], [2.0, 2.0], 2.0),
        ([0.0, 1.0], [2.0, 2.0], 0.0),
        ([[0.0], [1.0]], [2.0, 2.0], 2.0),
        ([False, 1.0], [2.0, 2.0], 2.0),
        ("0,1", [2.0, 2.0], 2.0),
    ],
)
def test_canopy_auc_rejects_malformed_arrays(
    times: object, canopy: object, pretreatment: object
) -> None:
    """Catches malformed time/canopy inputs reaching the trapezoidal endpoint."""
    with pytest.raises(AlmondLabError) as exc_info:
        canopy_auc(times, canopy, pretreatment)

    assert exc_info.value.code == "CANOPY_AUC_INVALID"


def test_canopy_auc_matches_exact_normalized_trapezoid_literal() -> None:
    """Catches omission of normalization or use of a non-trapezoidal integral."""
    assert canopy_auc([0.0, 1.0, 2.0], [2.0, 4.0, 2.0], 2.0) == 3.0


def test_canopy_auc_normalizes_endpoints_before_summing_large_values() -> None:
    """Catches raw endpoint addition overflowing before valid normalization."""
    assert canopy_auc([0.0, 1.0], [1e308, 1e308], 1e308) == 1.0


def test_canopy_auc_reports_derived_overflow_at_its_stable_public_boundary() -> None:
    """Catches internal numeric errors escaping the canopy-AUC error contract."""
    with pytest.raises(AlmondLabError) as exc_info:
        canopy_auc([-1e308, 1e308], [1.0, 1.0], 1.0)

    assert exc_info.value.code == "CANOPY_AUC_INVALID"
    assert exc_info.value.field_path == "canopy_auc"


def test_simulate_plant_runs_registered_step_halving_convergence_oracle() -> None:
    """Catches a trajectory accepted without its registered half-step comparison."""
    result = simulate_plant(
        _state(),
        _parameters(
            step_halving_absolute_tolerance=0.1,
            step_halving_relative_tolerance=0.1,
        ),
        (_forcing(duration_hours=0.5),),
        cursor=_cursor(),
    )

    assert result.convergence.converged is True
    assert result.convergence.coarse_step_hours == pytest.approx(0.25)
    assert result.convergence.fine_step_hours == pytest.approx(0.125)
    assert result.substeps == 2
    assert len(result.states) == 3
    assert result.evidence_label is EvidenceLabel.SYNTHETIC_ONLY


def test_step_halving_rejects_different_death_adjudication_substeps() -> None:
    """Catches convergence that ignores coarse/fine death-event timing."""
    with pytest.raises(AlmondLabError) as exc_info:
        simulate_plant(
            _state(biomass_g=0.1),
            _parameters(
                maintenance_cost_g_h=10.0,
                step_halving_absolute_tolerance=1e6,
                step_halving_relative_tolerance=1e6,
            ),
            (_forcing(duration_hours=0.25),),
            cursor=_cursor(),
        )

    assert exc_info.value.code == "BIOLOGY_STEP_CONVERGENCE_FAILURE"
    assert exc_info.value.details is not None
    assert exc_info.value.details["coarse_death_time_hours"] == 0.25
    assert exc_info.value.details["fine_death_time_hours"] == 0.125


def test_step_halving_scaled_difference_uses_the_actual_nonzero_scale() -> None:
    """Catches an undeclared denominator floor for tiny nonzero coordinates."""
    parameters = _parameters(
        root_na_permeability_l_cm2_h=0.0,
        root_cl_permeability_l_cm2_h=0.0,
        root_k_permeability_l_cm2_h=0.0,
        na_efflux_vmax_mmol_h=0.0,
        na_sequestration_vmax_mmol_h=0.0,
        cl_sequestration_vmax_mmol_h=0.0,
        k_sequestration_vmax_mmol_h=0.0,
        na_vacuole_release_h_inv=0.0,
        cl_vacuole_release_h_inv=0.0,
        k_vacuole_release_h_inv=0.0,
        na_xylem_loading_l_h=0.0,
        cl_xylem_loading_l_h=0.0,
        k_xylem_loading_l_h=0.0,
        na_xylem_retrieval_l_h=0.0,
        cl_xylem_retrieval_l_h=0.0,
        k_xylem_retrieval_l_h=0.0,
        xylem_flow_l_h=0.0,
        ros_production_h_inv=0.0,
        ros_clearance_h_inv=0.1,
        injury_damage_h_inv=0.0,
        injury_repair_h_inv=0.0,
        mannitol_vmax_mmol_h=0.0,
        mannitol_turnover_h_inv=0.0,
        radiation_use_efficiency_g_mol_apar_inv=0.0,
        maintenance_cost_g_h=0.0,
        redox_growth_penalty_h_inv=0.0,
        cipk_pleiotropy_penalty_h_inv=0.0,
        biomass_loss_h_inv=0.0,
        senescence_h_inv=0.0,
        step_halving_absolute_tolerance=1.0,
        step_halving_relative_tolerance=1.0,
    )

    result = simulate_plant(
        _state(
            ros_dimensionless=1e-35,
            injury_dimensionless=0.0,
            mannitol_mmol=0.0,
            allocatable_energy_atp_eq=0.0,
        ),
        parameters,
        (_forcing(duration_hours=0.25, apar_mol_h=0.0),),
        cursor=_cursor(),
    )
    coarse_ros = 9.75e-36
    fine_ros = 9.7515625e-36

    assert result.convergence.maximum_absolute_difference == pytest.approx(
        fine_ros - coarse_ros
    )
    assert result.convergence.maximum_scaled_difference == pytest.approx(
        (fine_ros - coarse_ros) / fine_ros
    )


def test_step_halving_rejects_overflow_in_registered_tolerance_arithmetic() -> None:
    """Catches an infinite tolerance silently accepting a finite comparison."""
    with pytest.raises(AlmondLabError) as exc_info:
        simulate_plant(
            _state(),
            _parameters(
                step_halving_absolute_tolerance=1e308,
                step_halving_relative_tolerance=1e308,
            ),
            (_forcing(duration_hours=0.25),),
            cursor=_cursor(),
        )

    assert exc_info.value.code == "BIOLOGY_NUMERIC_INVALID"
    assert exc_info.value.field_path.startswith("step_halving.coordinates.")


def test_step_halving_metadata_rejects_any_unregistered_half_step_slack() -> None:
    """Catches an undeclared absolute tolerance in exact step-plan metadata."""
    with pytest.raises(AlmondLabError) as exc_info:
        StepHalvingConvergence(
            converged=True,
            coarse_step_hours=0.1,
            fine_step_hours=0.05 + 5e-16,
            maximum_absolute_difference=0.0,
            maximum_scaled_difference=0.0,
            absolute_tolerance=0.1,
            relative_tolerance=0.1,
        )

    assert exc_info.value.code == "BIOLOGY_STATE_VIOLATION"
    assert exc_info.value.field_path == "fine_step_hours"


def test_advance_and_simulation_refuse_derived_overflow_and_never_strengthen_labels() -> None:
    """Catches native overflow or evidence promotion in integrated public APIs."""
    with pytest.raises(AlmondLabError) as overflow:
        advance_plant(
            _state(),
            _parameters(radiation_use_efficiency_g_mol_apar_inv=1e308),
            _forcing(apar_mol_h=1e308),
            cursor=_cursor(),
        )
    weak = advance_plant(
        _state(evidence_label=EvidenceLabel.HYPOTHESIS_PRIOR, network_state=_network(evidence_label=EvidenceLabel.HYPOTHESIS_PRIOR)),
        _parameters(),
        _forcing(evidence_label=EvidenceLabel.SYNTHETIC_ONLY),
        cursor=_cursor(),
    )

    assert overflow.value.code == "BIOLOGY_NUMERIC_INVALID"
    assert weak.evidence_label is EvidenceLabel.SYNTHETIC_ONLY


def test_candidate_effect_fixture_mirrors_are_byte_identical_and_lf_portable() -> None:
    """Catches drift between test authoring inputs and packaged runtime inputs."""
    authoring = FIXTURES / "candidate_effects.yaml"
    runtime = Path(__file__).parents[1] / "src" / "almondlab" / "resources" / "fixtures" / "candidate_effects.yaml"
    authoring_bytes = authoring.read_bytes()

    assert authoring_bytes == runtime.read_bytes()
    assert b"\r" not in authoring_bytes
    assert authoring_bytes.endswith(b"\n")


def test_every_candidate_fixture_anchor_is_consumed_by_exact_mapping() -> None:
    """Catches an authored synthetic effect value that never reaches an equation input."""
    effects = load_candidate_effects(FIXTURES / "candidate_effects.yaml")
    candidates = {
        item.candidate_id: item
        for item in load_candidate_specs(Path(__file__).parents[1] / "configs" / "candidates.yaml").candidates
    }
    expected_anchors = {
        "C1": {"na_efflux_vmax_multiplier": 1.35, "atp_cost_per_na": 2.40},
        "C2": {"ros_clearance_multiplier": 1.50, "redox_growth_penalty": 0.015},
        "C3": {"mannitol_vmax_multiplier": 1.40, "mannitol_carbon_cost": 0.50},
        "C4": {"na_efflux_vmax_multiplier": 1.30, "xylem_loading_leak_multiplier": 1.20},
        "C5": {"xylem_na_retrieval_multiplier": 1.50, "root_na_injury_multiplier": 1.10},
        "C6": {"sos_efflux_activation_multiplier": 1.25, "cipk_pleiotropy_penalty": 0.025},
    }
    expected_consumed = {
        "C1": {"na_efflux_vmax_mmol_h": 0.54, "atp_cost_per_na_atp_eq_mmol_inv": 2.40},
        "C2": {"ros_clearance_h_inv": 0.30, "redox_growth_penalty_h_inv": 0.015},
        "C3": {"mannitol_vmax_mmol_h": 0.28, "mannitol_carbon_cost_mmol_c_mmol_inv": 0.50},
        "C4": {"na_efflux_vmax_mmol_h": 0.52, "na_xylem_loading_l_h": 0.12},
        "C5": {"na_xylem_retrieval_l_h": 0.15, "root_na_injury_multiplier": 1.10},
        "C6": {"na_efflux_vmax_mmol_h": 0.50, "cipk_pleiotropy_penalty_h_inv": 0.025},
    }

    assert set(effects) == set(expected_anchors)
    for candidate_id, anchors in expected_anchors.items():
        assert dict(effects[candidate_id].parameters) == anchors
        assert effects[candidate_id].evidence_label is EvidenceLabel.HYPOTHESIS_PRIOR
        adjusted = apply_candidate_effects(
            _parameters(), effects[candidate_id], candidates[candidate_id]
        )
        for field_name, expected in expected_consumed[candidate_id].items():
            assert getattr(adjusted, field_name) == pytest.approx(expected)


def test_candidate_fixture_has_strict_synthetic_design_interpretation_and_no_claim_keys() -> None:
    """Catches an effect fixture mislabeled as efficacy, survival, or preference evidence."""
    payload = yaml.safe_load((FIXTURES / "candidate_effects.yaml").read_text(encoding="utf-8"))
    forbidden = {
        "winner",
        "best_candidate",
        "kernel_yield",
        "survival_prediction",
        "salt_tolerance",
        "efficacy",
    }

    def keys(value: object) -> set[str]:
        if isinstance(value, dict):
            return set(value) | set().union(*(keys(item) for item in value.values()))
        if isinstance(value, list):
            return set().union(*(keys(item) for item in value))
        return set()

    assert payload["interpretation"] == "synthetic_design_input_only"
    assert payload["evidence_label"] == "hypothesis_prior"
    assert forbidden.isdisjoint(keys(payload))


def test_candidate_fixture_loader_fails_closed_on_top_level_or_candidate_drift(tmp_path: Path) -> None:
    """Catches fixture metadata drift or an incomplete C1-C6 runtime registry."""
    source = yaml.safe_load((FIXTURES / "candidate_effects.yaml").read_text(encoding="utf-8"))
    source["interpretation"] = "validated_efficacy"
    source["candidates"].pop("C6")
    malformed = tmp_path / "candidate_effects.yaml"
    malformed.write_text(yaml.safe_dump(source), encoding="utf-8")

    with pytest.raises(AlmondLabError) as exc_info:
        load_candidate_effects(malformed)

    assert exc_info.value.code == "CANDIDATE_PARAMETER_VIOLATION"


@pytest.mark.parametrize(
    ("mutation", "duplicate_key"),
    [
        ("root", "schema_version"),
        ("candidate", "C1"),
        ("nested", "na_efflux_vmax_multiplier"),
    ],
)
def test_candidate_effect_yaml_rejects_duplicate_keys_at_every_mapping_depth(
    tmp_path: Path,
    mutation: str,
    duplicate_key: str,
) -> None:
    """Catches root, candidate, or parameter duplicates silently taking last value."""
    source = (FIXTURES / "candidate_effects.yaml").read_text(encoding="utf-8")
    if mutation == "root":
        source = source.replace(
            'schema_version: "1.0.0"\n',
            'schema_version: "1.0.0"\nschema_version: "9.9.9"\n',
            1,
        )
    elif mutation == "candidate":
        source = source.replace(
            "  C2:\n",
            "  C1:\n    na_efflux_vmax_multiplier: 1.10\n"
            "    atp_cost_per_na: 2.00\n  C2:\n",
            1,
        )
    else:
        source = source.replace(
            "    na_efflux_vmax_multiplier: 1.35\n",
            "    na_efflux_vmax_multiplier: 1.35\n"
            "    na_efflux_vmax_multiplier: 1.10\n",
            1,
        )
    malformed = tmp_path / f"duplicate-{mutation}.yaml"
    malformed.write_text(source, encoding="utf-8")

    with pytest.raises(AlmondLabError) as exc_info:
        load_candidate_effects(malformed)

    assert exc_info.value.code == "CANDIDATE_PARAMETER_VIOLATION"
    assert exc_info.value.field_path == "candidate_effects"
    assert exc_info.value.details is not None
    assert exc_info.value.details["duplicate_key"] == duplicate_key


def test_candidate_effect_yaml_rejects_self_referential_merge_alias(tmp_path: Path) -> None:
    """Catches a nested alias cycle reaching recursive merge construction."""
    source = (FIXTURES / "candidate_effects.yaml").read_text(encoding="utf-8")
    source = source.replace(
        "  C1:\n",
        "  C1: &cycle\n    <<: *cycle\n",
        1,
    )
    malformed = tmp_path / "candidate-cycle.yaml"
    malformed.write_text(source, encoding="utf-8")

    with pytest.raises(AlmondLabError) as exc_info:
        load_candidate_effects(malformed)

    assert exc_info.value.code == "CANDIDATE_PARAMETER_VIOLATION"
    assert exc_info.value.field_path == "candidate_effects"
    assert exc_info.value.details is not None
    assert exc_info.value.details["cause_type"] == "YamlAliasCycleError"


def test_candidate_mapping_and_loader_reject_non_string_keys_or_path_with_stable_error() -> None:
    """Catches native sorting/path exceptions leaking from malformed public inputs."""
    with pytest.raises(AlmondLabError) as key_error:
        CandidateEffects(
            candidate_id="C1",
            schema_version="1.0.0",
            parameters={
                "na_efflux_vmax_multiplier": 1.0,
                "atp_cost_per_na": 1.0,
                object(): 1.0,
            },
            evidence_label=EvidenceLabel.HYPOTHESIS_PRIOR,
        )
    with pytest.raises(AlmondLabError) as path_error:
        load_candidate_effects(object())

    assert key_error.value.code == "CANDIDATE_PARAMETER_VIOLATION"
    assert path_error.value.code == "CANDIDATE_PARAMETER_VIOLATION"
