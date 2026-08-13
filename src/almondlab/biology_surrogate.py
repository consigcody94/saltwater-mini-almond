"""Transparent Paper 1 plant-response surrogate for synthetic design work.

The model in this module is deliberately small and auditable.  It is not an
efficacy, survival, or yield model: every trajectory is restricted to
``hypothesis_prior`` or ``synthetic_only`` evidence.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, fields, replace
from math import exp, fsum, isclose, isfinite
from numbers import Real
from pathlib import Path
from types import MappingProxyType
from typing import Final

from pydantic import ValidationError
import yaml

from almondlab.contracts import (
    CompartmentKind,
    ConservedEntity,
    EvidenceLabel,
    GateState,
    InternalEntityFluxKind,
    LedgerCursor,
    LedgerEntry,
    OperatorPhase,
)
from almondlab.errors import AlmondLabError, fail, finite_float
from almondlab.evidence_policy import compose_evidence_labels
from almondlab.hydraulics import (
    HydraulicDomain,
    HydraulicInputs,
    HydraulicUptake,
    hydraulic_uptake,
    osmotic_potential_mpa,
)
from almondlab.mass_balance import (
    BalanceAudit,
    CompartmentState,
    InternalEntityFlux,
    InternalFluxOutcome,
    LedgerTransactionExpectation,
    NetworkState,
    audit_ledger,
    step_state,
)


_NUMERIC_CODE: Final[str] = "BIOLOGY_NUMERIC_INVALID"
_PARAMETER_CODE: Final[str] = "BIOLOGY_PARAMETER_VIOLATION"
_STATE_CODE: Final[str] = "BIOLOGY_STATE_VIOLATION"
_WEAK_LABELS: Final[frozenset[EvidenceLabel]] = frozenset(
    {EvidenceLabel.HYPOTHESIS_PRIOR, EvidenceLabel.SYNTHETIC_ONLY}
)
_BIOLOGY_ENTITIES: Final[tuple[ConservedEntity, ...]] = (
    ConservedEntity.NA,
    ConservedEntity.CL,
    ConservedEntity.K,
)
_REQUIRED_COMPARTMENT_KINDS: Final[tuple[CompartmentKind, ...]] = (
    CompartmentKind.ROOT_ZONE,
    CompartmentKind.ROOT_APOPLAST,
    CompartmentKind.ROOT_SYMPLAST,
    CompartmentKind.ROOT_VACUOLE,
    CompartmentKind.XYLEM,
    CompartmentKind.SHOOT_TISSUE,
)
_CANDIDATE_KEYS: Final[Mapping[str, frozenset[str]]] = MappingProxyType(
    {
        "C1": frozenset({"na_efflux_vmax_multiplier", "atp_cost_per_na"}),
        "C2": frozenset({"ros_clearance_multiplier", "redox_growth_penalty"}),
        "C3": frozenset({"mannitol_vmax_multiplier", "mannitol_carbon_cost"}),
        "C4": frozenset(
            {"na_efflux_vmax_multiplier", "xylem_loading_leak_multiplier"}
        ),
        "C5": frozenset(
            {"xylem_na_retrieval_multiplier", "root_na_injury_multiplier"}
        ),
        "C6": frozenset(
            {"sos_efflux_activation_multiplier", "cipk_pleiotropy_penalty"}
        ),
    }
)
_MULTIPLIER_KEYS: Final[frozenset[str]] = frozenset(
    key
    for keys in _CANDIDATE_KEYS.values()
    for key in keys
    if key.endswith("_multiplier")
)
_PRIMARY_EFFECT_KEY: Final[Mapping[str, str]] = MappingProxyType(
    {
        "C1": "na_efflux_vmax_multiplier",
        "C2": "ros_clearance_multiplier",
        "C3": "mannitol_vmax_multiplier",
        "C4": "na_efflux_vmax_multiplier",
        "C5": "xylem_na_retrieval_multiplier",
        "C6": "sos_efflux_activation_multiplier",
    }
)


def _number(
    value: object,
    field_path: str,
    *,
    nonnegative: bool = False,
    positive: bool = False,
) -> float:
    return finite_float(
        value,
        code=_NUMERIC_CODE,
        field_path=field_path,
        nonnegative=nonnegative,
        positive=positive,
    )


def _result(value: object, field_path: str) -> float:
    """Validate a derived binary64 result without leaking native arithmetic."""

    return finite_float(value, code=_NUMERIC_CODE, field_path=field_path)


def _product(*values: float, field_path: str) -> float:
    result = 1.0
    for value in values:
        result *= value
        if not isfinite(result):
            fail(_NUMERIC_CODE, "derived product must remain finite", field_path)
    return result


def _sum(values: Sequence[float] | tuple[float, ...], field_path: str) -> float:
    try:
        result = fsum(values)
    except (OverflowError, ValueError):
        fail(_NUMERIC_CODE, "derived sum must remain finite", field_path)
    return _result(result, field_path)


def _ratio(numerator: float, denominator: float, field_path: str) -> float:
    if denominator == 0.0:
        fail(_NUMERIC_CODE, "derived ratio denominator must be nonzero", field_path)
    try:
        result = numerator / denominator
    except (OverflowError, ZeroDivisionError):
        fail(_NUMERIC_CODE, "derived ratio must remain finite", field_path)
    return _result(result, field_path)


def _weak_label(value: object, field_path: str) -> EvidenceLabel:
    if not isinstance(value, EvidenceLabel) or value not in _WEAK_LABELS:
        fail(
            "BIOLOGY_EVIDENCE_VIOLATION",
            "biology evidence must be hypothesis_prior or synthetic_only",
            field_path,
        )
    return value


def _schema_version(value: object, field_path: str = "schema_version") -> str:
    if not isinstance(value, str) or not value.strip():
        fail(_PARAMETER_CODE, "schema version must be a nonempty string", field_path)
    return value


def _canonical_compartment(compartment: object, field_path: str) -> CompartmentState:
    if not isinstance(compartment, CompartmentState):
        fail(_STATE_CODE, "network values must be CompartmentState", field_path)
    try:
        return CompartmentState(
            compartment_id=compartment.compartment_id,
            kind=compartment.kind,
            loop_id=compartment.loop_id,
            volume_l=compartment.volume_l,
            water_mass_kg=compartment.water_mass_kg,
            empty_reference_density_kg_l=compartment.empty_reference_density_kg_l,
            stocks=dict(compartment.stocks),
            evidence_label=compartment.evidence_label,
        )
    except AlmondLabError as error:
        fail(
            _STATE_CODE,
            "network compartment failed canonical validation",
            field_path,
            {"cause": error.code, "cause_field_path": error.field_path},
        )


def _canonical_network(value: object) -> NetworkState:
    if not isinstance(value, NetworkState):
        fail(_STATE_CODE, "network_state must be a NetworkState", "network_state")
    try:
        compartments = {
            compartment_id: _canonical_compartment(
                compartment, f"network_state.compartments.{compartment_id}"
            )
            for compartment_id, compartment in value.compartments.items()
        }
        network = NetworkState(
            compartments=compartments,
            tracked_entities=frozenset(value.tracked_entities),
            evidence_label=value.evidence_label,
        )
    except AlmondLabError as error:
        if error.code == _STATE_CODE:
            raise
        fail(
            _STATE_CODE,
            "network_state failed canonical validation",
            "network_state",
            {"cause": error.code, "cause_field_path": error.field_path},
        )

    missing_entities = frozenset(_BIOLOGY_ENTITIES) - network.tracked_entities
    if missing_entities:
        fail(
            _STATE_CODE,
            "network_state must track Na, Cl, and K explicitly",
            "network_state.tracked_entities",
            {"missing": sorted(entity.value for entity in missing_entities)},
        )
    by_kind: dict[CompartmentKind, list[str]] = {
        kind: [] for kind in _REQUIRED_COMPARTMENT_KINDS
    }
    for compartment_id, compartment in network.compartments.items():
        if compartment.kind in by_kind:
            by_kind[compartment.kind].append(compartment_id)
    invalid = {
        kind.value: identifiers
        for kind, identifiers in by_kind.items()
        if len(identifiers) != 1
    }
    if invalid:
        fail(
            _STATE_CODE,
            "network_state requires exactly one biology compartment of each kind",
            "network_state.compartments",
            {"invalid_kind_counts": {key: len(value) for key, value in invalid.items()}},
        )
    return network


def _canonical_domain(value: object) -> HydraulicDomain:
    if not isinstance(value, HydraulicDomain):
        fail(
            "BIOLOGY_FORCING_VIOLATION",
            "hydraulic_domain must be a validated HydraulicDomain",
            "hydraulic_domain",
        )
    try:
        domain = HydraulicDomain.model_validate(value.model_dump(mode="python"))
    except (ValidationError, ValueError, TypeError) as error:
        fail(
            "BIOLOGY_FORCING_VIOLATION",
            "hydraulic_domain failed canonical validation",
            "hydraulic_domain",
            {"validation_error_type": type(error).__name__},
        )
    if domain.purpose != "model_applicability":
        fail(
            "BIOLOGY_FORCING_VIOLATION",
            "biology requires a model_applicability hydraulic domain",
            "hydraulic_domain.purpose",
        )
    return domain


@dataclass(frozen=True, slots=True, kw_only=True)
class PlantState:
    """One immutable surrogate state plus the canonical physical ion network."""

    time_hours: float
    biomass_g: float
    canopy_area_cm2: float
    ros_dimensionless: float
    injury_dimensionless: float
    mannitol_mmol: float
    allocatable_energy_atp_eq: float
    apx_expression_fraction: float
    cipk_expression_fraction: float
    injury_exposure_hours: float
    alive: bool
    death_time_hours: float | None
    network_state: NetworkState
    evidence_label: EvidenceLabel

    def __post_init__(self) -> None:
        nonnegative = (
            "time_hours",
            "biomass_g",
            "canopy_area_cm2",
            "ros_dimensionless",
            "injury_dimensionless",
            "mannitol_mmol",
            "allocatable_energy_atp_eq",
            "injury_exposure_hours",
        )
        for name in nonnegative:
            object.__setattr__(self, name, _number(getattr(self, name), name, nonnegative=True))
        for name in ("apx_expression_fraction", "cipk_expression_fraction"):
            value = _number(getattr(self, name), name, nonnegative=True)
            if value > 1.0:
                fail(_STATE_CODE, "expression fraction must be in [0, 1]", name)
            object.__setattr__(self, name, value)
        if not isinstance(self.alive, bool):
            fail(_STATE_CODE, "alive must be a boolean", "alive")
        if self.death_time_hours is None:
            death_time = None
        else:
            death_time = _number(
                self.death_time_hours, "death_time_hours", nonnegative=True
            )
            if death_time > self.time_hours:
                fail(_STATE_CODE, "death time cannot exceed state time", "death_time_hours")
        if self.alive and death_time is not None:
            fail(_STATE_CODE, "a living state cannot have a death time", "death_time_hours")
        if not self.alive and death_time is None:
            fail(_STATE_CODE, "a dead state requires a death time", "death_time_hours")
        if not self.alive and self.canopy_area_cm2 != 0.0:
            fail(_STATE_CODE, "canopy must be exactly zero after death", "canopy_area_cm2")
        network = _canonical_network(self.network_state)
        label = _weak_label(self.evidence_label, "evidence_label")
        permitted = compose_evidence_labels(network.evidence_label, label)
        if permitted is not label:
            fail(
                "BIOLOGY_EVIDENCE_VIOLATION",
                "plant evidence cannot be stronger than network evidence",
                "evidence_label",
            )
        object.__setattr__(self, "death_time_hours", death_time)
        object.__setattr__(self, "network_state", network)
        object.__setattr__(self, "evidence_label", label)

    @property
    def reported_ion_stocks_mmol(
        self,
    ) -> Mapping[str, Mapping[ConservedEntity, float]] | None:
        """Return observable ion stocks while alive; missing after death.

        Physical stocks always remain available in :attr:`network_state` for
        conservation audits.  This reporting view deliberately returns
        ``None`` after death instead of manufacturing zero observations.
        """

        if not self.alive:
            return None
        return MappingProxyType(
            {
                compartment_id: MappingProxyType(
                    {
                        entity: compartment.stocks[entity]
                        for entity in _BIOLOGY_ENTITIES
                    }
                )
                for compartment_id, compartment in self.network_state.compartments.items()
            }
        )


@dataclass(frozen=True, slots=True, kw_only=True)
class BiologyParameters:
    """Every registered scalar used by the version-1 biology equations."""

    schema_version: str
    evidence_label: EvidenceLabel
    root_area_cm2: float
    root_na_permeability_l_cm2_h: float
    root_cl_permeability_l_cm2_h: float
    root_k_permeability_l_cm2_h: float
    na_partition_coefficient: float
    cl_partition_coefficient: float
    k_partition_coefficient: float
    na_efflux_vmax_mmol_h: float
    na_efflux_km_mmol_l: float
    atp_cost_per_na_atp_eq_mmol_inv: float
    na_sequestration_vmax_mmol_h: float
    cl_sequestration_vmax_mmol_h: float
    k_sequestration_vmax_mmol_h: float
    na_sequestration_km_mmol_l: float
    cl_sequestration_km_mmol_l: float
    k_sequestration_km_mmol_l: float
    na_vacuole_capacity_mmol: float
    cl_vacuole_capacity_mmol: float
    k_vacuole_capacity_mmol: float
    na_vacuole_release_h_inv: float
    cl_vacuole_release_h_inv: float
    k_vacuole_release_h_inv: float
    na_xylem_loading_l_h: float
    cl_xylem_loading_l_h: float
    k_xylem_loading_l_h: float
    na_xylem_retrieval_l_h: float
    cl_xylem_retrieval_l_h: float
    k_xylem_retrieval_l_h: float
    xylem_flow_l_h: float
    shoot_partition_fraction: float
    root_conductance_l_day_mpa: float
    osmotic_reference_mpa: float
    osmotic_scale_mpa: float
    root_na_stress_weight: float
    root_cl_stress_weight: float
    root_k_stress_weight: float
    root_na_critical_mmol_l: float
    root_cl_critical_mmol_l: float
    root_k_critical_mmol_l: float
    root_na_stress_scale_mmol_l: float
    root_cl_stress_scale_mmol_l: float
    root_k_stress_scale_mmol_l: float
    root_na_injury_multiplier: float
    ion_weight_sum_tolerance: float
    ros_production_h_inv: float
    ros_clearance_h_inv: float
    injury_damage_h_inv: float
    injury_repair_h_inv: float
    mannitol_vmax_mmol_h: float
    mannitol_km_dimensionless: float
    mannitol_turnover_h_inv: float
    mannitol_osmotic_coefficient_mpa_mmol_inv: float
    mannitol_carbon_cost_mmol_c_mmol_inv: float
    mannitol_adjustment_min_mpa: float
    mannitol_adjustment_max_mpa: float
    radiation_use_efficiency_g_mol_apar_inv: float
    maintenance_cost_g_h: float
    atp_to_biomass_g_atp_eq_inv: float
    carbon_to_biomass_g_mmol_c_inv: float
    redox_growth_penalty_h_inv: float
    cipk_pleiotropy_penalty_h_inv: float
    biomass_loss_h_inv: float
    specific_leaf_area_cm2_g: float
    leaf_allocation_fraction: float
    senescence_h_inv: float
    energy_epsilon_atp_eq_h: float
    integrator_max_step_hours: float
    step_halving_absolute_tolerance: float
    step_halving_relative_tolerance: float
    biomass_death_threshold_g: float
    injury_death_threshold: float
    sustained_injury_duration_hours: float

    def __post_init__(self) -> None:
        object.__setattr__(self, "schema_version", _schema_version(self.schema_version))
        object.__setattr__(
            self, "evidence_label", _weak_label(self.evidence_label, "evidence_label")
        )
        positive = {
            "root_area_cm2",
            "na_partition_coefficient",
            "cl_partition_coefficient",
            "k_partition_coefficient",
            "na_efflux_km_mmol_l",
            "na_sequestration_km_mmol_l",
            "cl_sequestration_km_mmol_l",
            "k_sequestration_km_mmol_l",
            "na_vacuole_capacity_mmol",
            "cl_vacuole_capacity_mmol",
            "k_vacuole_capacity_mmol",
            "osmotic_scale_mpa",
            "root_na_stress_scale_mmol_l",
            "root_cl_stress_scale_mmol_l",
            "root_k_stress_scale_mmol_l",
            "root_na_injury_multiplier",
            "ion_weight_sum_tolerance",
            "mannitol_km_dimensionless",
            "energy_epsilon_atp_eq_h",
            "integrator_max_step_hours",
            "step_halving_absolute_tolerance",
            "step_halving_relative_tolerance",
            "sustained_injury_duration_hours",
        }
        exact_finite = {
            "mannitol_adjustment_min_mpa",
            "mannitol_adjustment_max_mpa",
        }
        skip = {"schema_version", "evidence_label"}
        for field in fields(self):
            name = field.name
            if name in skip:
                continue
            value = _number(
                getattr(self, name),
                name,
                positive=name in positive,
                nonnegative=name not in positive and name not in exact_finite,
            )
            object.__setattr__(self, name, value)

        if self.shoot_partition_fraction != 1.0:
            fail(
                _PARAMETER_CODE,
                "version 1 deposits all xylem delivery into shoot tissue",
                "shoot_partition_fraction",
            )
        if (
            self.mannitol_adjustment_min_mpa != -0.5
            or self.mannitol_adjustment_max_mpa != 0.5
        ):
            fail(
                _PARAMETER_CODE,
                "mannitol adjustment bounds are frozen at [-0.50, 0.50] MPa",
                "mannitol_adjustment_bounds_mpa",
            )
        weights = (
            self.root_na_stress_weight,
            self.root_cl_stress_weight,
            self.root_k_stress_weight,
        )
        weight_sum = _sum(weights, "ion_stress_weights")
        if not isclose(
            weight_sum, 1.0, rel_tol=0.0, abs_tol=self.ion_weight_sum_tolerance
        ):
            fail(
                _PARAMETER_CODE,
                "ion stress weights must sum to one within the registered tolerance",
                "ion_stress_weights",
                {"sum": weight_sum, "tolerance": self.ion_weight_sum_tolerance},
            )
        if self.leaf_allocation_fraction > 1.0:
            fail(
                _PARAMETER_CODE,
                "leaf allocation fraction must be in [0, 1]",
                "leaf_allocation_fraction",
            )
        if self.integrator_max_step_hours > 0.25:
            fail(
                _PARAMETER_CODE,
                "biology integrator maximum step cannot exceed 0.25 hours",
                "integrator_max_step_hours",
            )


@dataclass(frozen=True, slots=True, kw_only=True)
class RootZoneForcing:
    """Measured external forcing and an explicit validated hydraulic domain."""

    measured_osmolality_osmol_kg: float
    temperature_k: float
    water_density_kg_l: float
    matric_potential_mpa: float
    leaf_critical_potential_mpa: float
    apar_mol_h: float
    temperature_factor: float
    potential_transpiration_l_day: float
    duration_hours: float
    evidence_label: EvidenceLabel
    hydraulic_domain: HydraulicDomain

    def __post_init__(self) -> None:
        positive = {
            "temperature_k",
            "water_density_kg_l",
            "potential_transpiration_l_day",
            "duration_hours",
        }
        nonnegative = {
            "measured_osmolality_osmol_kg",
            "apar_mol_h",
            "temperature_factor",
        }
        for name in (
            "measured_osmolality_osmol_kg",
            "temperature_k",
            "water_density_kg_l",
            "matric_potential_mpa",
            "leaf_critical_potential_mpa",
            "apar_mol_h",
            "temperature_factor",
            "potential_transpiration_l_day",
            "duration_hours",
        ):
            object.__setattr__(
                self,
                name,
                _number(
                    getattr(self, name),
                    name,
                    positive=name in positive,
                    nonnegative=name in nonnegative,
                ),
            )
        if self.temperature_factor > 1.0:
            fail(
                "BIOLOGY_FORCING_VIOLATION",
                "temperature factor must be in [0, 1]",
                "temperature_factor",
            )
        object.__setattr__(
            self, "evidence_label", _weak_label(self.evidence_label, "evidence_label")
        )
        object.__setattr__(self, "hydraulic_domain", _canonical_domain(self.hydraulic_domain))


@dataclass(frozen=True, slots=True, kw_only=True)
class CandidateEffects:
    """Exactly two registered synthetic mechanism inputs for one candidate."""

    candidate_id: str
    schema_version: str
    parameters: Mapping[str, float]
    evidence_label: EvidenceLabel

    def __post_init__(self) -> None:
        if not isinstance(self.candidate_id, str) or self.candidate_id not in _CANDIDATE_KEYS:
            fail(
                "CANDIDATE_PARAMETER_VIOLATION",
                "candidate_id must identify C1 through C6",
                "candidate_id",
            )
        object.__setattr__(
            self,
            "schema_version",
            _schema_version(self.schema_version, "schema_version"),
        )
        label = _weak_label(self.evidence_label, "evidence_label")
        if not isinstance(self.parameters, Mapping):
            fail(
                "CANDIDATE_PARAMETER_VIOLATION",
                "candidate parameters must be a mapping",
                "parameters",
            )
        if any(not isinstance(key, str) for key in self.parameters):
            fail(
                "CANDIDATE_PARAMETER_VIOLATION",
                "candidate parameter keys must be strings",
                "parameters",
            )
        supplied = set(self.parameters)
        expected = _CANDIDATE_KEYS[self.candidate_id]
        if supplied != expected:
            fail(
                "CANDIDATE_PARAMETER_VIOLATION",
                "candidate parameters must match the exact isolation whitelist",
                "parameters",
                {
                    "missing": sorted(expected - supplied),
                    "extra": sorted(supplied - expected),
                },
            )
        copied: dict[str, float] = {}
        for key, raw_value in self.parameters.items():
            try:
                value = finite_float(
                    raw_value,
                    code=_NUMERIC_CODE,
                    field_path=f"parameters.{key}",
                )
            except AlmondLabError as error:
                fail(
                    "CANDIDATE_PARAMETER_VIOLATION",
                    "candidate parameter must be a finite real number",
                    f"parameters.{key}",
                    {"cause": error.code},
                )
            if key in _MULTIPLIER_KEYS and value <= 0.0:
                fail(
                    "CANDIDATE_PARAMETER_VIOLATION",
                    "candidate multiplier must be positive",
                    f"parameters.{key}",
                )
            if key not in _MULTIPLIER_KEYS and value < 0.0:
                fail(
                    "CANDIDATE_PARAMETER_VIOLATION",
                    "candidate cost or penalty must be nonnegative",
                    f"parameters.{key}",
                )
            copied[key] = value
        object.__setattr__(self, "parameters", MappingProxyType(copied))
        object.__setattr__(self, "evidence_label", label)


def _canonical_state(value: object) -> PlantState:
    if not isinstance(value, PlantState):
        fail(_STATE_CODE, "state must be a PlantState", "state")
    try:
        return replace(value)
    except AlmondLabError:
        raise
    except Exception as error:
        fail(
            _STATE_CODE,
            "state failed canonical validation",
            "state",
            {"validation_error_type": type(error).__name__},
        )


def _canonical_parameters(value: object) -> BiologyParameters:
    if not isinstance(value, BiologyParameters):
        fail(_PARAMETER_CODE, "parameters must be BiologyParameters", "parameters")
    try:
        return replace(value)
    except AlmondLabError:
        raise
    except Exception as error:
        fail(
            _PARAMETER_CODE,
            "parameters failed canonical validation",
            "parameters",
            {"validation_error_type": type(error).__name__},
        )


def _canonical_forcing(value: object) -> RootZoneForcing:
    if not isinstance(value, RootZoneForcing):
        fail(
            "BIOLOGY_FORCING_VIOLATION",
            "forcing must be RootZoneForcing",
            "forcing",
        )
    try:
        return replace(value)
    except AlmondLabError:
        raise
    except Exception as error:
        fail(
            "BIOLOGY_FORCING_VIOLATION",
            "forcing failed canonical validation",
            "forcing",
            {"validation_error_type": type(error).__name__},
        )


def _canonical_effects(value: object) -> CandidateEffects:
    if not isinstance(value, CandidateEffects):
        fail(
            "CANDIDATE_PARAMETER_VIOLATION",
            "effects must be CandidateEffects",
            "effects",
        )
    try:
        return replace(value, parameters=dict(value.parameters))
    except AlmondLabError:
        raise
    except Exception as error:
        fail(
            "CANDIDATE_PARAMETER_VIOLATION",
            "effects failed canonical validation",
            "effects",
            {"validation_error_type": type(error).__name__},
        )


def load_candidate_effects(path: str | Path) -> Mapping[str, CandidateEffects]:
    """Load the exact C1-C6 synthetic-design effect registry."""

    try:
        payload = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    except (OSError, TypeError, ValueError, UnicodeError, yaml.YAMLError) as error:
        fail(
            "CANDIDATE_PARAMETER_VIOLATION",
            "candidate effect fixture could not be read",
            "candidate_effects",
            {"cause_type": type(error).__name__},
        )
    if not isinstance(payload, Mapping):
        fail(
            "CANDIDATE_PARAMETER_VIOLATION",
            "candidate effect fixture must be a mapping",
            "candidate_effects",
        )
    expected_top = {
        "schema_version",
        "evidence_label",
        "interpretation",
        "candidates",
    }
    if set(payload) != expected_top:
        fail(
            "CANDIDATE_PARAMETER_VIOLATION",
            "candidate effect fixture has incomplete or extra top-level fields",
            "candidate_effects",
            {
                "missing": sorted(expected_top - set(payload)),
                "extra": sorted(set(payload) - expected_top),
            },
        )
    version = _schema_version(payload["schema_version"], "schema_version")
    if payload["interpretation"] != "synthetic_design_input_only":
        fail(
            "CANDIDATE_PARAMETER_VIOLATION",
            "candidate effects are synthetic design inputs only",
            "interpretation",
        )
    try:
        label = (
            payload["evidence_label"]
            if isinstance(payload["evidence_label"], EvidenceLabel)
            else EvidenceLabel(payload["evidence_label"])
        )
    except (TypeError, ValueError) as error:
        fail(
            "CANDIDATE_PARAMETER_VIOLATION",
            "candidate effect fixture has an invalid evidence label",
            "evidence_label",
            {"cause_type": type(error).__name__},
        )
    if label is not EvidenceLabel.HYPOTHESIS_PRIOR:
        fail(
            "CANDIDATE_PARAMETER_VIOLATION",
            "candidate effect anchors must remain hypothesis_prior",
            "evidence_label",
        )
    raw_candidates = payload["candidates"]
    if not isinstance(raw_candidates, Mapping) or set(raw_candidates) != set(
        _CANDIDATE_KEYS
    ):
        received = set(raw_candidates) if isinstance(raw_candidates, Mapping) else set()
        fail(
            "CANDIDATE_PARAMETER_VIOLATION",
            "candidate effect fixture must contain exactly C1 through C6",
            "candidates",
            {
                "missing": sorted(set(_CANDIDATE_KEYS) - received),
                "extra": sorted(received - set(_CANDIDATE_KEYS)),
            },
        )
    effects = {
        candidate_id: CandidateEffects(
            candidate_id=candidate_id,
            schema_version=version,
            parameters=raw_candidates[candidate_id],
            evidence_label=label,
        )
        for candidate_id in _CANDIDATE_KEYS
    }
    return MappingProxyType(effects)


def _canonical_candidate(value: object) -> object:
    from almondlab.paper1_contracts import CandidateSpec

    if not isinstance(value, CandidateSpec):
        fail(
            "CANDIDATE_PARAMETER_VIOLATION",
            "candidate must be a validated CandidateSpec",
            "candidate",
        )
    try:
        return CandidateSpec.model_validate(value.model_dump(mode="python"))
    except (ValidationError, ValueError, TypeError) as error:
        fail(
            "CANDIDATE_PARAMETER_VIOLATION",
            "candidate failed frozen registry revalidation",
            "candidate",
            {"validation_error_type": type(error).__name__},
        )


def apply_candidate_effects(
    parameters: BiologyParameters,
    effects: CandidateEffects,
    candidate: object,
) -> BiologyParameters:
    """Return an isolated parameter copy for one revalidated candidate.

    Multipliers act on the corresponding baseline.  Cost and penalty anchors
    replace their baseline values because they are explicit candidate-specific
    design inputs.  Neither the baseline nor either registry input is mutated.
    """

    baseline = _canonical_parameters(parameters)
    effect = _canonical_effects(effects)
    spec = _canonical_candidate(candidate)
    if spec.candidate_id != effect.candidate_id:
        fail(
            "CANDIDATE_PARAMETER_VIOLATION",
            "candidate and effect identifiers must match",
            "candidate.candidate_id",
            {"candidate": spec.candidate_id, "effects": effect.candidate_id},
        )
    expected_primary = _PRIMARY_EFFECT_KEY[effect.candidate_id]
    if spec.primary_parameter_id != expected_primary:
        fail(
            "CANDIDATE_PARAMETER_VIOLATION",
            "candidate primary parameter disagrees with the isolation registry",
            "candidate.primary_parameter_id",
        )

    values = effect.parameters
    updates: dict[str, object]
    if effect.candidate_id == "C1":
        updates = {
            "na_efflux_vmax_mmol_h": _product(
                baseline.na_efflux_vmax_mmol_h,
                values["na_efflux_vmax_multiplier"],
                field_path="na_efflux_vmax_mmol_h",
            ),
            "atp_cost_per_na_atp_eq_mmol_inv": values["atp_cost_per_na"],
        }
    elif effect.candidate_id == "C2":
        updates = {
            "ros_clearance_h_inv": _product(
                baseline.ros_clearance_h_inv,
                values["ros_clearance_multiplier"],
                field_path="ros_clearance_h_inv",
            ),
            "redox_growth_penalty_h_inv": values["redox_growth_penalty"],
        }
    elif effect.candidate_id == "C3":
        updates = {
            "mannitol_vmax_mmol_h": _product(
                baseline.mannitol_vmax_mmol_h,
                values["mannitol_vmax_multiplier"],
                field_path="mannitol_vmax_mmol_h",
            ),
            "mannitol_carbon_cost_mmol_c_mmol_inv": values[
                "mannitol_carbon_cost"
            ],
        }
    elif effect.candidate_id == "C4":
        updates = {
            "na_efflux_vmax_mmol_h": _product(
                baseline.na_efflux_vmax_mmol_h,
                values["na_efflux_vmax_multiplier"],
                field_path="na_efflux_vmax_mmol_h",
            ),
            "na_xylem_loading_l_h": _product(
                baseline.na_xylem_loading_l_h,
                values["xylem_loading_leak_multiplier"],
                field_path="na_xylem_loading_l_h",
            ),
        }
    elif effect.candidate_id == "C5":
        updates = {
            "na_xylem_retrieval_l_h": _product(
                baseline.na_xylem_retrieval_l_h,
                values["xylem_na_retrieval_multiplier"],
                field_path="na_xylem_retrieval_l_h",
            ),
            "root_na_injury_multiplier": _product(
                baseline.root_na_injury_multiplier,
                values["root_na_injury_multiplier"],
                field_path="root_na_injury_multiplier",
            ),
        }
    else:
        updates = {
            "na_efflux_vmax_mmol_h": _product(
                baseline.na_efflux_vmax_mmol_h,
                values["sos_efflux_activation_multiplier"],
                field_path="na_efflux_vmax_mmol_h",
            ),
            "cipk_pleiotropy_penalty_h_inv": values[
                "cipk_pleiotropy_penalty"
            ],
        }
    updates["evidence_label"] = compose_evidence_labels(
        baseline.evidence_label,
        effect.evidence_label,
        spec.evidence_label,
    )
    try:
        return replace(baseline, **updates)
    except AlmondLabError:
        raise
    except Exception as error:
        fail(
            "CANDIDATE_PARAMETER_VIOLATION",
            "candidate effects produced invalid biology parameters",
            "effects",
            {"validation_error_type": type(error).__name__},
        )


@dataclass(frozen=True, slots=True, kw_only=True)
class StressInputs:
    """Separated osmotic and tissue-ion stress coordinates for one pre-step."""

    osmotic_potential_mpa: float
    osmotic_excess_dimensionless: float
    root_na_excess_dimensionless: float
    root_cl_excess_dimensionless: float
    root_k_excess_dimensionless: float
    ion_excess_dimensionless: float
    specific_ion_factor: float
    evidence_label: EvidenceLabel

    def __post_init__(self) -> None:
        for name in (
            "osmotic_potential_mpa",
            "osmotic_excess_dimensionless",
            "root_na_excess_dimensionless",
            "root_cl_excess_dimensionless",
            "root_k_excess_dimensionless",
            "ion_excess_dimensionless",
            "specific_ion_factor",
        ):
            value = _number(
                getattr(self, name),
                name,
                nonnegative=name != "osmotic_potential_mpa",
            )
            object.__setattr__(self, name, value)
        if self.specific_ion_factor > 1.0:
            fail(
                _STATE_CODE,
                "specific ion factor must be in [0, 1]",
                "specific_ion_factor",
            )
        object.__setattr__(
            self, "evidence_label", _weak_label(self.evidence_label, "evidence_label")
        )


@dataclass(frozen=True, slots=True, kw_only=True)
class PlantFluxes:
    """Canonical ion demands and non-ion pre-step mechanism diagnostics."""

    events: tuple[InternalEntityFlux, ...]
    stress: StressInputs
    efflux_demand_mmol_h: float
    efflux_atp_fraction: float
    mannitol_synthesis_mmol_h: float
    adjustment_mpa: float
    electrochemical_interpretation: GateState
    evidence_label: EvidenceLabel

    def __post_init__(self) -> None:
        if not isinstance(self.events, tuple) or any(
            not isinstance(event, InternalEntityFlux) for event in self.events
        ):
            fail(
                _STATE_CODE,
                "events must be a tuple of InternalEntityFlux values",
                "events",
            )
        if len({event.event_id for event in self.events}) != len(self.events):
            fail(_STATE_CODE, "plant flux event IDs must be unique", "events")
        if not isinstance(self.stress, StressInputs):
            fail(_STATE_CODE, "stress must be StressInputs", "stress")
        for name in (
            "efflux_demand_mmol_h",
            "efflux_atp_fraction",
            "mannitol_synthesis_mmol_h",
        ):
            object.__setattr__(
                self, name, _number(getattr(self, name), name, nonnegative=True)
            )
        if self.efflux_atp_fraction > 1.0:
            fail(
                _STATE_CODE,
                "efflux ATP fraction must be in [0, 1]",
                "efflux_atp_fraction",
            )
        adjustment = _number(self.adjustment_mpa, "adjustment_mpa")
        if not -0.5 <= adjustment <= 0.5:
            fail(
                _STATE_CODE,
                "mannitol adjustment must be in [-0.50, 0.50] MPa",
                "adjustment_mpa",
            )
        if self.electrochemical_interpretation is not GateState.NOT_EVALUABLE:
            fail(
                _STATE_CODE,
                "core_v1 electrochemical interpretation is not_evaluable",
                "electrochemical_interpretation",
            )
        object.__setattr__(self, "events", tuple(self.events))
        object.__setattr__(self, "adjustment_mpa", adjustment)
        object.__setattr__(
            self, "evidence_label", _weak_label(self.evidence_label, "evidence_label")
        )


def _compartment_ids(state: PlantState) -> Mapping[CompartmentKind, str]:
    return MappingProxyType(
        {
            compartment.kind: compartment_id
            for compartment_id, compartment in state.network_state.compartments.items()
            if compartment.kind in _REQUIRED_COMPARTMENT_KINDS
        }
    )


def stress_inputs(
    state: PlantState,
    parameters: BiologyParameters,
    forcing: RootZoneForcing,
) -> StressInputs:
    """Return the registered dimensionless stress inputs from pre-step values."""

    current = _canonical_state(state)
    params = _canonical_parameters(parameters)
    external = _canonical_forcing(forcing)
    osmotic = osmotic_potential_mpa(
        external.measured_osmolality_osmol_kg,
        external.temperature_k,
        external.water_density_kg_l,
    )
    osmotic_excess = max(
        0.0,
        _ratio(
            _sum(
                (-osmotic, -params.osmotic_reference_mpa),
                "osmotic_excess_dimensionless.numerator",
            ),
            params.osmotic_scale_mpa,
            "osmotic_excess_dimensionless",
        ),
    )
    ids = _compartment_ids(current)
    symplast_id = ids[CompartmentKind.ROOT_SYMPLAST]
    concentrations = {
        entity: current.network_state.concentration(symplast_id, entity)
        for entity in _BIOLOGY_ENTITIES
    }
    raw_excesses: dict[ConservedEntity, float] = {}
    for entity, critical, scale in (
        (
            ConservedEntity.NA,
            params.root_na_critical_mmol_l,
            params.root_na_stress_scale_mmol_l,
        ),
        (
            ConservedEntity.CL,
            params.root_cl_critical_mmol_l,
            params.root_cl_stress_scale_mmol_l,
        ),
        (
            ConservedEntity.K,
            params.root_k_critical_mmol_l,
            params.root_k_stress_scale_mmol_l,
        ),
    ):
        raw_excesses[entity] = max(
            0.0,
            _ratio(
                _sum(
                    (concentrations[entity], -critical),
                    f"root_{entity.value}_excess_dimensionless.numerator",
                ),
                scale,
                f"root_{entity.value}_excess_dimensionless",
            ),
        )
    na_excess = _product(
        raw_excesses[ConservedEntity.NA],
        params.root_na_injury_multiplier,
        field_path="root_na_excess_dimensionless",
    )
    cl_excess = raw_excesses[ConservedEntity.CL]
    k_excess = raw_excesses[ConservedEntity.K]
    ion_excess = _sum(
        (
            _product(
                params.root_na_stress_weight,
                na_excess,
                field_path="ion_excess_dimensionless.na",
            ),
            _product(
                params.root_cl_stress_weight,
                cl_excess,
                field_path="ion_excess_dimensionless.cl",
            ),
            _product(
                params.root_k_stress_weight,
                k_excess,
                field_path="ion_excess_dimensionless.k",
            ),
        ),
        "ion_excess_dimensionless",
    )
    specific_ion_factor = _result(
        exp(-current.injury_dimensionless), "specific_ion_factor"
    )
    label = compose_evidence_labels(
        current.evidence_label, params.evidence_label, external.evidence_label
    )
    return StressInputs(
        osmotic_potential_mpa=osmotic,
        osmotic_excess_dimensionless=osmotic_excess,
        root_na_excess_dimensionless=na_excess,
        root_cl_excess_dimensionless=cl_excess,
        root_k_excess_dimensionless=k_excess,
        ion_excess_dimensionless=ion_excess,
        specific_ion_factor=specific_ion_factor,
        evidence_label=label,
    )


def _event(
    *,
    event_id: str,
    source: str,
    target: str,
    kind: InternalEntityFluxKind,
    entity: ConservedEntity,
    rate: float,
    evidence_label: EvidenceLabel,
) -> InternalEntityFlux | None:
    rate = _result(rate, f"events.{event_id}.rate_per_hour")
    if rate < 0.0:
        fail(_STATE_CODE, "plant flux rates cannot be negative", f"events.{event_id}")
    if rate == 0.0:
        return None
    return InternalEntityFlux(
        event_id=event_id,
        source=source,
        target=target,
        kind=kind,
        entity=entity,
        rate_per_hour=rate,
        phase=OperatorPhase.PLANT_ION_TRANSITIONS,
        evidence_label=evidence_label,
    )


def plant_fluxes(
    state: PlantState,
    parameters: BiologyParameters,
    forcing: RootZoneForcing,
) -> PlantFluxes:
    """Build all seven typed plant-ion transition families from pre-step state."""

    current = _canonical_state(state)
    params = _canonical_parameters(parameters)
    external = _canonical_forcing(forcing)
    stress = stress_inputs(current, params, external)
    label = compose_evidence_labels(
        current.evidence_label,
        params.evidence_label,
        external.evidence_label,
        stress.evidence_label,
    )
    adjustment = min(
        params.mannitol_adjustment_max_mpa,
        max(
            params.mannitol_adjustment_min_mpa,
            _product(
                params.mannitol_osmotic_coefficient_mpa_mmol_inv,
                current.mannitol_mmol,
                field_path="adjustment_mpa",
            ),
        ),
    )
    mannitol_synthesis = _ratio(
        _product(
            params.mannitol_vmax_mmol_h,
            stress.osmotic_excess_dimensionless,
            field_path="mannitol_synthesis_mmol_h.numerator",
        ),
        _sum(
            (
                params.mannitol_km_dimensionless,
                stress.osmotic_excess_dimensionless,
            ),
            "mannitol_synthesis_mmol_h.denominator",
        ),
        "mannitol_synthesis_mmol_h",
    )
    if not current.alive:
        return PlantFluxes(
            events=(),
            stress=stress,
            efflux_demand_mmol_h=0.0,
            efflux_atp_fraction=0.0,
            mannitol_synthesis_mmol_h=0.0,
            adjustment_mpa=adjustment,
            electrochemical_interpretation=GateState.NOT_EVALUABLE,
            evidence_label=label,
        )

    ids = _compartment_ids(current)
    network = current.network_state
    root_zone = ids[CompartmentKind.ROOT_ZONE]
    apoplast = ids[CompartmentKind.ROOT_APOPLAST]
    symplast = ids[CompartmentKind.ROOT_SYMPLAST]
    vacuole = ids[CompartmentKind.ROOT_VACUOLE]
    xylem = ids[CompartmentKind.XYLEM]
    shoot = ids[CompartmentKind.SHOOT_TISSUE]
    concentrations = {
        location: {
            entity: network.concentration(location, entity)
            for entity in _BIOLOGY_ENTITIES
        }
        for location in (root_zone, apoplast, symplast, xylem)
    }
    rates: list[tuple[str, str, str, InternalEntityFluxKind, ConservedEntity, float]] = []
    entity_fields = (
        (
            ConservedEntity.NA,
            params.root_na_permeability_l_cm2_h,
            params.na_partition_coefficient,
            params.na_sequestration_vmax_mmol_h,
            params.na_sequestration_km_mmol_l,
            params.na_vacuole_capacity_mmol,
            params.na_vacuole_release_h_inv,
            params.na_xylem_loading_l_h,
            params.na_xylem_retrieval_l_h,
        ),
        (
            ConservedEntity.CL,
            params.root_cl_permeability_l_cm2_h,
            params.cl_partition_coefficient,
            params.cl_sequestration_vmax_mmol_h,
            params.cl_sequestration_km_mmol_l,
            params.cl_vacuole_capacity_mmol,
            params.cl_vacuole_release_h_inv,
            params.cl_xylem_loading_l_h,
            params.cl_xylem_retrieval_l_h,
        ),
        (
            ConservedEntity.K,
            params.root_k_permeability_l_cm2_h,
            params.k_partition_coefficient,
            params.k_sequestration_vmax_mmol_h,
            params.k_sequestration_km_mmol_l,
            params.k_vacuole_capacity_mmol,
            params.k_vacuole_release_h_inv,
            params.k_xylem_loading_l_h,
            params.k_xylem_retrieval_l_h,
        ),
    )
    for (
        entity,
        permeability,
        partition,
        seq_vmax,
        seq_km,
        vac_capacity,
        release_rate,
        loading_rate,
        retrieval_rate,
    ) in entity_fields:
        suffix = entity.value
        gradient = max(
            0.0,
            _sum(
                (
                    concentrations[root_zone][entity],
                    -_ratio(
                        concentrations[apoplast][entity],
                        partition,
                        f"uptake.{suffix}.partitioned_apoplast",
                    ),
                ),
                f"uptake.{suffix}.gradient",
            ),
        )
        uptake = _product(
            permeability,
            params.root_area_cm2,
            gradient,
            field_path=f"uptake.{suffix}.rate",
        )
        symplast_concentration = concentrations[symplast][entity]
        seq_saturation = _ratio(
            symplast_concentration,
            _sum(
                (seq_km, symplast_concentration),
                f"sequester.{suffix}.denominator",
            ),
            f"sequester.{suffix}.saturation",
        )
        capacity_fraction = max(
            0.0,
            _sum(
                (
                    1.0,
                    -_ratio(
                        network.compartments[vacuole].stocks[entity],
                        vac_capacity,
                        f"sequester.{suffix}.capacity_ratio",
                    ),
                ),
                f"sequester.{suffix}.capacity_fraction",
            ),
        )
        sequestration = _product(
            seq_vmax,
            seq_saturation,
            capacity_fraction,
            field_path=f"sequester.{suffix}.rate",
        )
        release = _product(
            release_rate,
            network.compartments[vacuole].stocks[entity],
            field_path=f"release.{suffix}.rate",
        )
        loading = _product(
            loading_rate,
            symplast_concentration,
            field_path=f"load.{suffix}.rate",
        )
        retrieval = _product(
            retrieval_rate,
            concentrations[xylem][entity],
            field_path=f"retrieve.{suffix}.rate",
        )
        deposition = _product(
            params.xylem_flow_l_h,
            concentrations[xylem][entity],
            params.shoot_partition_fraction,
            field_path=f"deposit.{suffix}.rate",
        )
        rates.extend(
            (
                (
                    f"uptake-{suffix}",
                    root_zone,
                    symplast,
                    InternalEntityFluxKind.PLANT_UPTAKE,
                    entity,
                    uptake,
                ),
                (
                    f"sequester-{suffix}",
                    symplast,
                    vacuole,
                    InternalEntityFluxKind.SEQUESTRATION,
                    entity,
                    sequestration,
                ),
                (
                    f"release-{suffix}",
                    vacuole,
                    symplast,
                    InternalEntityFluxKind.VACUOLE_RELEASE,
                    entity,
                    release,
                ),
                (
                    f"load-{suffix}",
                    symplast,
                    xylem,
                    InternalEntityFluxKind.XYLEM_LOADING,
                    entity,
                    loading,
                ),
                (
                    f"retrieve-{suffix}",
                    xylem,
                    symplast,
                    InternalEntityFluxKind.XYLEM_RETRIEVAL,
                    entity,
                    retrieval,
                ),
                (
                    f"deposit-{suffix}",
                    xylem,
                    shoot,
                    InternalEntityFluxKind.TISSUE_DEPOSITION,
                    entity,
                    deposition,
                ),
            )
        )

    symplast_na = concentrations[symplast][ConservedEntity.NA]
    efflux_demand = _ratio(
        _product(
            params.na_efflux_vmax_mmol_h,
            symplast_na,
            field_path="efflux_na_demand_mmol_h.numerator",
        ),
        _sum(
            (params.na_efflux_km_mmol_l, symplast_na),
            "efflux_na_demand_mmol_h.denominator",
        ),
        "efflux_na_demand_mmol_h",
    )
    atp_demand = _product(
        params.atp_cost_per_na_atp_eq_mmol_inv,
        efflux_demand,
        field_path="efflux_atp_demand_atp_eq_h",
    )
    atp_fraction = min(
        1.0,
        _ratio(
            current.allocatable_energy_atp_eq,
            _sum(
                (atp_demand, params.energy_epsilon_atp_eq_h),
                "efflux_atp_fraction.denominator",
            ),
            "efflux_atp_fraction",
        ),
    )
    efflux = _product(
        atp_fraction,
        efflux_demand,
        field_path="efflux_na_rate_mmol_h",
    )
    rates.append(
        (
            "efflux-na",
            symplast,
            root_zone,
            InternalEntityFluxKind.PLANT_EFFLUX,
            ConservedEntity.NA,
            efflux,
        )
    )
    events = tuple(
        event
        for event in (
            _event(
                event_id=event_id,
                source=source,
                target=target,
                kind=kind,
                entity=entity,
                rate=rate,
                evidence_label=label,
            )
            for event_id, source, target, kind, entity, rate in rates
        )
        if event is not None
    )
    return PlantFluxes(
        events=events,
        stress=stress,
        efflux_demand_mmol_h=efflux_demand,
        efflux_atp_fraction=atp_fraction,
        mannitol_synthesis_mmol_h=mannitol_synthesis,
        adjustment_mpa=adjustment,
        electrochemical_interpretation=GateState.NOT_EVALUABLE,
        evidence_label=label,
    )


@dataclass(frozen=True, slots=True, kw_only=True)
class BiologyStepDiagnostics:
    """Auditable pre-step rates and derivatives for one Euler substep."""

    start_time_hours: float
    duration_hours: float
    fluxes: PlantFluxes
    hydraulic: HydraulicUptake | None
    applied_na_efflux_mmol_h: float
    gross_growth_g_h: float
    maintenance_cost_g_h: float
    efflux_cost_g_h: float
    mannitol_cost_g_h: float
    redox_cost_g_h: float
    cipk_cost_g_h: float
    total_cost_g_h: float
    biomass_derivative_g_h: float
    canopy_derivative_cm2_h: float
    ros_derivative_h_inv: float
    injury_derivative_h_inv: float
    mannitol_derivative_mmol_h: float
    evidence_label: EvidenceLabel

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "start_time_hours",
            _number(self.start_time_hours, "start_time_hours", nonnegative=True),
        )
        object.__setattr__(
            self,
            "duration_hours",
            _number(self.duration_hours, "duration_hours", positive=True),
        )
        if not isinstance(self.fluxes, PlantFluxes):
            fail(_STATE_CODE, "fluxes must be PlantFluxes", "fluxes")
        if self.hydraulic is not None and not isinstance(self.hydraulic, HydraulicUptake):
            fail(_STATE_CODE, "hydraulic must be HydraulicUptake or None", "hydraulic")
        nonnegative = {
            "applied_na_efflux_mmol_h",
            "gross_growth_g_h",
            "maintenance_cost_g_h",
            "efflux_cost_g_h",
            "mannitol_cost_g_h",
            "redox_cost_g_h",
            "cipk_cost_g_h",
            "total_cost_g_h",
        }
        for name in (
            "applied_na_efflux_mmol_h",
            "gross_growth_g_h",
            "maintenance_cost_g_h",
            "efflux_cost_g_h",
            "mannitol_cost_g_h",
            "redox_cost_g_h",
            "cipk_cost_g_h",
            "total_cost_g_h",
            "biomass_derivative_g_h",
            "canopy_derivative_cm2_h",
            "ros_derivative_h_inv",
            "injury_derivative_h_inv",
            "mannitol_derivative_mmol_h",
        ):
            object.__setattr__(
                self,
                name,
                _number(getattr(self, name), name, nonnegative=name in nonnegative),
            )
        object.__setattr__(
            self, "evidence_label", _weak_label(self.evidence_label, "evidence_label")
        )


@dataclass(frozen=True, slots=True, kw_only=True)
class AdvancePlantResult:
    """One forcing interval with complete core and audit evidence."""

    state: PlantState
    states: tuple[PlantState, ...]
    steps: tuple[BiologyStepDiagnostics, ...]
    ledger: tuple[LedgerEntry, ...]
    flux_outcomes: tuple[InternalFluxOutcome, ...]
    expected_events: tuple[InternalEntityFlux, ...]
    expected_transactions: tuple[LedgerTransactionExpectation, ...]
    audits: tuple[BalanceAudit, ...]
    next_cursor: LedgerCursor
    substeps: int
    evidence_label: EvidenceLabel

    def __post_init__(self) -> None:
        if not isinstance(self.state, PlantState):
            fail(_STATE_CODE, "state must be PlantState", "state")
        if not isinstance(self.states, tuple) or len(self.states) != self.substeps + 1:
            fail(_STATE_CODE, "states must contain initial and every substep", "states")
        if self.states[-1] != self.state:
            fail(_STATE_CODE, "final state must equal the last trajectory state", "state")
        if isinstance(self.substeps, bool) or not isinstance(self.substeps, int) or self.substeps < 1:
            fail(_STATE_CODE, "substeps must be a positive integer", "substeps")
        if len(self.steps) != self.substeps or len(self.audits) != self.substeps:
            fail(_STATE_CODE, "every substep requires diagnostics and an audit", "steps")
        if any(not audit.balanced for audit in self.audits):
            fail("BIOLOGY_LEDGER_AUDIT_FAILED", "every substep audit must balance", "audits")
        if not isinstance(self.next_cursor, LedgerCursor):
            fail(_STATE_CODE, "next_cursor must be LedgerCursor", "next_cursor")
        object.__setattr__(self, "evidence_label", _weak_label(self.evidence_label, "evidence_label"))


@dataclass(frozen=True, slots=True, kw_only=True)
class StepHalvingConvergence:
    """Registered coarse-versus-half-step convergence decision."""

    converged: bool
    coarse_step_hours: float
    fine_step_hours: float
    maximum_absolute_difference: float
    maximum_scaled_difference: float
    absolute_tolerance: float
    relative_tolerance: float

    def __post_init__(self) -> None:
        if not isinstance(self.converged, bool):
            fail(_STATE_CODE, "converged must be boolean", "converged")
        for name in (
            "coarse_step_hours",
            "fine_step_hours",
            "absolute_tolerance",
            "relative_tolerance",
        ):
            object.__setattr__(self, name, _number(getattr(self, name), name, positive=True))
        for name in ("maximum_absolute_difference", "maximum_scaled_difference"):
            object.__setattr__(self, name, _number(getattr(self, name), name, nonnegative=True))
        if not isclose(
            self.fine_step_hours,
            0.5 * self.coarse_step_hours,
            rel_tol=0.0,
            abs_tol=1e-15,
        ):
            fail(_STATE_CODE, "fine step must equal half the coarse step", "fine_step_hours")


@dataclass(frozen=True, slots=True, kw_only=True)
class SimulationResult:
    """A complete synthetic trajectory plus its step-halving oracle."""

    state: PlantState
    states: tuple[PlantState, ...]
    intervals: tuple[AdvancePlantResult, ...]
    ledger: tuple[LedgerEntry, ...]
    next_cursor: LedgerCursor
    substeps: int
    convergence: StepHalvingConvergence
    evidence_label: EvidenceLabel

    def __post_init__(self) -> None:
        if not self.states or self.states[-1] != self.state:
            fail(_STATE_CODE, "simulation states must end at final state", "states")
        if sum(interval.substeps for interval in self.intervals) != self.substeps:
            fail(_STATE_CODE, "simulation substep count is inconsistent", "substeps")
        if not self.convergence.converged:
            fail(
                "BIOLOGY_STEP_CONVERGENCE_FAILURE",
                "simulation result requires a passing step-halving oracle",
                "convergence",
            )
        object.__setattr__(self, "evidence_label", _weak_label(self.evidence_label, "evidence_label"))


def _namespace_events(
    events: tuple[InternalEntityFlux, ...], cursor: LedgerCursor
) -> tuple[InternalEntityFlux, ...]:
    prefix = f"bio{cursor.next_ordinal:012d}"
    return tuple(
        replace(event, event_id=f"{prefix}-{event.event_id}") for event in events
    )


def _literal_transaction_authority(
    state: NetworkState,
    events: tuple[InternalEntityFlux, ...],
    duration_hours: float,
    cursor: LedgerCursor,
) -> tuple[
    tuple[LedgerTransactionExpectation, ...],
    Mapping[str, float],
]:
    """Author expected applied amounts from pre-step literals before execution."""

    demands: dict[tuple[str, ConservedEntity], list[tuple[str, float]]] = defaultdict(list)
    for event in events:
        requested = _product(
            event.rate_per_hour,
            duration_hours,
            field_path=f"expected_transactions.{event.event_id}.requested_amount",
        )
        demands[(event.source, event.entity)].append((event.event_id, requested))
    caps: dict[tuple[str, ConservedEntity], float] = {}
    for (source, entity), grouped in demands.items():
        total_requested = _sum(
            tuple(requested for _, requested in grouped),
            f"expected_transactions.{source}.{entity.value}.total_requested",
        )
        available = state.compartments[source].stocks[entity]
        caps[(source, entity)] = min(
            1.0,
            _ratio(
                available,
                total_requested,
                f"expected_transactions.{source}.{entity.value}.cap_fraction",
            ),
        )
    shadow = cursor
    expectations: list[LedgerTransactionExpectation] = []
    applied_by_event: dict[str, float] = {}
    for event in sorted(events, key=lambda item: item.event_id):
        transaction_id, shadow = shadow.issue()
        requested = next(
            value
            for event_id, value in demands[(event.source, event.entity)]
            if event_id == event.event_id
        )
        applied = _product(
            requested,
            caps[(event.source, event.entity)],
            field_path=f"expected_transactions.{event.event_id}.applied_amount",
        )
        expectations.append(
            LedgerTransactionExpectation(
                transaction_id=transaction_id,
                event_id=event.event_id,
                dt_hours=duration_hours,
                amounts={event.entity: applied},
            )
        )
        applied_by_event[event.event_id] = applied
    return tuple(expectations), MappingProxyType(applied_by_event)


def _hydraulic(
    state: PlantState,
    params: BiologyParameters,
    forcing: RootZoneForcing,
    fluxes: PlantFluxes,
) -> HydraulicUptake:
    label = compose_evidence_labels(
        state.evidence_label,
        params.evidence_label,
        forcing.evidence_label,
        fluxes.evidence_label,
    )
    return hydraulic_uptake(
        HydraulicInputs(
            osmolality_osmol_kg=forcing.measured_osmolality_osmol_kg,
            temperature_k=forcing.temperature_k,
            water_density_kg_l=forcing.water_density_kg_l,
            matric_mpa=forcing.matric_potential_mpa,
            leaf_critical_mpa=forcing.leaf_critical_potential_mpa,
            adjustment_mpa=fluxes.adjustment_mpa,
            root_conductance_l_day_mpa=params.root_conductance_l_day_mpa,
            potential_transpiration_l_day=forcing.potential_transpiration_l_day,
            specific_ion_factor=fluxes.stress.specific_ion_factor,
            evidence_label=label,
        ),
        domain=forcing.hydraulic_domain,
    )


def _euler_living_state(
    state: PlantState,
    network_state: NetworkState,
    params: BiologyParameters,
    forcing: RootZoneForcing,
    fluxes: PlantFluxes,
    hydraulic: HydraulicUptake,
    applied_na_efflux_mmol_h: float,
    duration_hours: float,
) -> tuple[PlantState, BiologyStepDiagnostics]:
    stress_total = _sum(
        (
            fluxes.stress.osmotic_excess_dimensionless,
            fluxes.stress.ion_excess_dimensionless,
        ),
        "ros_derivative_h_inv.stress_total",
    )
    ros_derivative = _sum(
        (
            _product(
                params.ros_production_h_inv,
                stress_total,
                field_path="ros_derivative_h_inv.production",
            ),
            -_product(
                params.ros_clearance_h_inv,
                state.ros_dimensionless,
                field_path="ros_derivative_h_inv.clearance",
            ),
        ),
        "ros_derivative_h_inv",
    )
    injury_derivative = _sum(
        (
            _product(
                params.injury_damage_h_inv,
                state.ros_dimensionless,
                field_path="injury_derivative_h_inv.damage",
            ),
            -_product(
                params.injury_repair_h_inv,
                state.injury_dimensionless,
                field_path="injury_derivative_h_inv.repair",
            ),
        ),
        "injury_derivative_h_inv",
    )
    mannitol_derivative = _sum(
        (
            fluxes.mannitol_synthesis_mmol_h,
            -_product(
                params.mannitol_turnover_h_inv,
                state.mannitol_mmol,
                field_path="mannitol_derivative_mmol_h.turnover",
            ),
        ),
        "mannitol_derivative_mmol_h",
    )
    hydraulic_ratio = min(
        1.0,
        _ratio(
            hydraulic.actual_l_day,
            forcing.potential_transpiration_l_day,
            "gross_growth_g_h.hydraulic_ratio",
        ),
    )
    gross_growth = _product(
        params.radiation_use_efficiency_g_mol_apar_inv,
        forcing.apar_mol_h,
        forcing.temperature_factor,
        hydraulic_ratio,
        fluxes.stress.specific_ion_factor,
        field_path="gross_growth_g_h",
    )
    maintenance = params.maintenance_cost_g_h
    efflux_cost = _product(
        params.atp_cost_per_na_atp_eq_mmol_inv,
        applied_na_efflux_mmol_h,
        params.atp_to_biomass_g_atp_eq_inv,
        field_path="efflux_cost_g_h",
    )
    mannitol_cost = _product(
        params.mannitol_carbon_cost_mmol_c_mmol_inv,
        fluxes.mannitol_synthesis_mmol_h,
        params.carbon_to_biomass_g_mmol_c_inv,
        field_path="mannitol_cost_g_h",
    )
    redox_cost = _product(
        params.redox_growth_penalty_h_inv,
        state.apx_expression_fraction,
        state.biomass_g,
        field_path="redox_cost_g_h",
    )
    cipk_cost = _product(
        params.cipk_pleiotropy_penalty_h_inv,
        state.cipk_expression_fraction,
        state.biomass_g,
        field_path="cipk_cost_g_h",
    )
    total_cost = _sum(
        (maintenance, efflux_cost, mannitol_cost, redox_cost, cipk_cost),
        "total_cost_g_h",
    )
    biomass_derivative = _sum(
        (
            gross_growth,
            -total_cost,
            -_product(
                params.biomass_loss_h_inv,
                state.injury_dimensionless,
                state.biomass_g,
                field_path="biomass_derivative_g_h.injury_loss",
            ),
        ),
        "biomass_derivative_g_h",
    )
    canopy_derivative = _sum(
        (
            _product(
                params.specific_leaf_area_cm2_g,
                params.leaf_allocation_fraction,
                max(biomass_derivative, 0.0),
                field_path="canopy_derivative_cm2_h.growth",
            ),
            -_product(
                params.senescence_h_inv,
                state.injury_dimensionless,
                state.canopy_area_cm2,
                field_path="canopy_derivative_cm2_h.senescence",
            ),
        ),
        "canopy_derivative_cm2_h",
    )

    def euler_nonnegative(value: float, derivative: float, field_path: str) -> float:
        return max(
            0.0,
            _sum(
                (
                    value,
                    _product(
                        duration_hours,
                        derivative,
                        field_path=f"{field_path}.increment",
                    ),
                ),
                field_path,
            ),
        )

    updated_ros = euler_nonnegative(
        state.ros_dimensionless, ros_derivative, "ros_dimensionless"
    )
    updated_injury = euler_nonnegative(
        state.injury_dimensionless, injury_derivative, "injury_dimensionless"
    )
    updated_mannitol = euler_nonnegative(
        state.mannitol_mmol, mannitol_derivative, "mannitol_mmol"
    )
    updated_biomass = euler_nonnegative(
        state.biomass_g, biomass_derivative, "biomass_g"
    )
    updated_canopy = euler_nonnegative(
        state.canopy_area_cm2, canopy_derivative, "canopy_area_cm2"
    )
    applied_efflux_amount = _product(
        applied_na_efflux_mmol_h,
        duration_hours,
        field_path="allocatable_energy_atp_eq.applied_efflux_amount",
    )
    energy_used = _product(
        params.atp_cost_per_na_atp_eq_mmol_inv,
        applied_efflux_amount,
        field_path="allocatable_energy_atp_eq.energy_used",
    )
    updated_energy = max(
        0.0,
        _sum(
            (state.allocatable_energy_atp_eq, -energy_used),
            "allocatable_energy_atp_eq",
        ),
    )
    new_time = _sum((state.time_hours, duration_hours), "time_hours")
    exposure = (
        _sum(
            (state.injury_exposure_hours, duration_hours),
            "injury_exposure_hours",
        )
        if updated_injury >= params.injury_death_threshold
        else 0.0
    )
    died = (
        updated_biomass <= params.biomass_death_threshold_g
        or exposure >= params.sustained_injury_duration_hours
    )
    label = compose_evidence_labels(
        state.evidence_label,
        params.evidence_label,
        forcing.evidence_label,
        fluxes.evidence_label,
        hydraulic.evidence_label,
        network_state.evidence_label,
    )
    updated = PlantState(
        time_hours=new_time,
        biomass_g=updated_biomass,
        canopy_area_cm2=0.0 if died else updated_canopy,
        ros_dimensionless=updated_ros,
        injury_dimensionless=updated_injury,
        mannitol_mmol=updated_mannitol,
        allocatable_energy_atp_eq=updated_energy,
        apx_expression_fraction=state.apx_expression_fraction,
        cipk_expression_fraction=state.cipk_expression_fraction,
        injury_exposure_hours=exposure,
        alive=not died,
        death_time_hours=new_time if died else None,
        network_state=network_state,
        evidence_label=label,
    )
    diagnostic = BiologyStepDiagnostics(
        start_time_hours=state.time_hours,
        duration_hours=duration_hours,
        fluxes=fluxes,
        hydraulic=hydraulic,
        applied_na_efflux_mmol_h=applied_na_efflux_mmol_h,
        gross_growth_g_h=gross_growth,
        maintenance_cost_g_h=maintenance,
        efflux_cost_g_h=efflux_cost,
        mannitol_cost_g_h=mannitol_cost,
        redox_cost_g_h=redox_cost,
        cipk_cost_g_h=cipk_cost,
        total_cost_g_h=total_cost,
        biomass_derivative_g_h=biomass_derivative,
        canopy_derivative_cm2_h=canopy_derivative,
        ros_derivative_h_inv=ros_derivative,
        injury_derivative_h_inv=injury_derivative,
        mannitol_derivative_mmol_h=mannitol_derivative,
        evidence_label=label,
    )
    return updated, diagnostic


def _dead_diagnostic(
    state: PlantState,
    duration_hours: float,
    fluxes: PlantFluxes,
    evidence_label: EvidenceLabel,
) -> BiologyStepDiagnostics:
    return BiologyStepDiagnostics(
        start_time_hours=state.time_hours,
        duration_hours=duration_hours,
        fluxes=fluxes,
        hydraulic=None,
        applied_na_efflux_mmol_h=0.0,
        gross_growth_g_h=0.0,
        maintenance_cost_g_h=0.0,
        efflux_cost_g_h=0.0,
        mannitol_cost_g_h=0.0,
        redox_cost_g_h=0.0,
        cipk_cost_g_h=0.0,
        total_cost_g_h=0.0,
        biomass_derivative_g_h=0.0,
        canopy_derivative_cm2_h=0.0,
        ros_derivative_h_inv=0.0,
        injury_derivative_h_inv=0.0,
        mannitol_derivative_mmol_h=0.0,
        evidence_label=evidence_label,
    )


def advance_plant(
    state: PlantState,
    parameters: BiologyParameters,
    forcing: RootZoneForcing,
    *,
    cursor: LedgerCursor,
) -> AdvancePlantResult:
    """Advance one forcing interval through audited core substeps and Euler ODEs."""

    current = _canonical_state(state)
    params = _canonical_parameters(parameters)
    external = _canonical_forcing(forcing)
    if not isinstance(cursor, LedgerCursor):
        fail("LEDGER_CURSOR_REQUIRED", "cursor must be LedgerCursor", "cursor")
    states = [current]
    diagnostics: list[BiologyStepDiagnostics] = []
    ledger: list[LedgerEntry] = []
    outcomes: list[InternalFluxOutcome] = []
    expected_events: list[InternalEntityFlux] = []
    expected_transactions: list[LedgerTransactionExpectation] = []
    audits: list[BalanceAudit] = []
    next_cursor = cursor
    elapsed = 0.0
    substeps = 0
    while elapsed < external.duration_hours:
        remaining = _sum(
            (external.duration_hours, -elapsed), "forcing.duration_hours.remaining"
        )
        duration = min(params.integrator_max_step_hours, remaining)
        if duration <= max(1e-15, 1e-14 * external.duration_hours):
            fail(
                _NUMERIC_CODE,
                "biology substep could not make finite progress",
                "forcing.duration_hours",
            )
        subforcing = replace(external, duration_hours=duration)
        raw_fluxes = plant_fluxes(current, params, subforcing)
        namespaced = _namespace_events(raw_fluxes.events, next_cursor)
        fluxes = replace(raw_fluxes, events=namespaced)
        expectations, applied = _literal_transaction_authority(
            current.network_state, namespaced, duration, next_cursor
        )
        core = step_state(
            current.network_state,
            dt_hours=duration,
            cursor=next_cursor,
            entity_fluxes=namespaced,
            max_substep_hours=duration,
        )
        audit = audit_ledger(
            current.network_state,
            core.state,
            core.ledger,
            expected_events=namespaced,
            expected_transactions=expectations,
        )
        if not audit.balanced:
            fail(
                "BIOLOGY_LEDGER_AUDIT_FAILED",
                "canonical plant-ion ledger failed independent authority audit",
                "ledger",
                {"structural_errors": list(audit.structural_errors)},
            )
        if current.alive:
            hydraulic = _hydraulic(current, params, subforcing, fluxes)
            efflux_amount = next(
                (
                    amount
                    for event_id, amount in applied.items()
                    if event_id.endswith("-efflux-na")
                ),
                0.0,
            )
            applied_efflux_rate = _ratio(
                efflux_amount, duration, "applied_na_efflux_mmol_h"
            )
            updated, diagnostic = _euler_living_state(
                current,
                core.state,
                params,
                subforcing,
                fluxes,
                hydraulic,
                applied_efflux_rate,
                duration,
            )
        else:
            label = compose_evidence_labels(
                current.evidence_label,
                params.evidence_label,
                subforcing.evidence_label,
                core.evidence_label,
            )
            updated = replace(
                current,
                time_hours=_sum((current.time_hours, duration), "time_hours"),
                network_state=core.state,
                evidence_label=label,
            )
            diagnostic = _dead_diagnostic(current, duration, fluxes, label)
        ledger.extend(core.ledger)
        outcomes.extend(core.internal_flux_outcomes)
        expected_events.extend(namespaced)
        expected_transactions.extend(expectations)
        audits.append(audit)
        diagnostics.append(diagnostic)
        next_cursor = core.next_cursor
        current = updated
        states.append(current)
        elapsed = _sum((elapsed, duration), "forcing.duration_hours.elapsed")
        substeps += 1
        if substeps > 1_000_000:
            fail(_NUMERIC_CODE, "biology substep limit exceeded", "forcing.duration_hours")
    label = compose_evidence_labels(
        current.evidence_label,
        *(step.evidence_label for step in diagnostics),
    )
    return AdvancePlantResult(
        state=current,
        states=tuple(states),
        steps=tuple(diagnostics),
        ledger=tuple(ledger),
        flux_outcomes=tuple(outcomes),
        expected_events=tuple(expected_events),
        expected_transactions=tuple(expected_transactions),
        audits=tuple(audits),
        next_cursor=next_cursor,
        substeps=substeps,
        evidence_label=label,
    )


def _auc_vector(value: object, field_path: str) -> tuple[float, ...]:
    if isinstance(value, (str, bytes, Mapping)):
        fail("CANOPY_AUC_INVALID", "input must be a finite one-dimensional array", field_path)
    try:
        raw = tuple(value)  # type: ignore[arg-type]
    except (TypeError, ValueError, OverflowError):
        fail("CANOPY_AUC_INVALID", "input must be a finite one-dimensional array", field_path)
    converted: list[float] = []
    for index, item in enumerate(raw):
        try:
            converted.append(
                finite_float(
                    item,
                    code="CANOPY_AUC_INVALID",
                    field_path=f"{field_path}.{index}",
                )
            )
        except AlmondLabError:
            raise
    return tuple(converted)


def canopy_auc(
    times_days: object,
    canopy_area_cm2: object,
    pretreatment_canopy_area_cm2: object,
) -> float:
    """Integrate canopy normalized to pretreatment area by the trapezoidal rule."""

    times = _auc_vector(times_days, "times_days")
    canopy = _auc_vector(canopy_area_cm2, "canopy_area_cm2")
    try:
        pretreatment = finite_float(
            pretreatment_canopy_area_cm2,
            code="CANOPY_AUC_INVALID",
            field_path="pretreatment_canopy_area_cm2",
            positive=True,
        )
    except AlmondLabError:
        raise
    if len(times) != len(canopy):
        fail("CANOPY_AUC_INVALID", "time and canopy arrays must have equal length", "canopy_area_cm2")
    if len(times) < 2:
        fail("CANOPY_AUC_INVALID", "at least two observations are required", "times_days")
    if any(value < 0.0 for value in canopy):
        fail("CANOPY_AUC_INVALID", "canopy values must be nonnegative", "canopy_area_cm2")
    if any(right <= left for left, right in zip(times, times[1:])):
        fail("CANOPY_AUC_INVALID", "times must be strictly increasing", "times_days")
    terms: list[float] = []
    for index in range(len(times) - 1):
        width = _sum((times[index + 1], -times[index]), f"canopy_auc.{index}.width")
        normalized_sum = _ratio(
            _sum((canopy[index], canopy[index + 1]), f"canopy_auc.{index}.canopy_sum"),
            pretreatment,
            f"canopy_auc.{index}.normalized_sum",
        )
        terms.append(
            _product(0.5, width, normalized_sum, field_path=f"canopy_auc.{index}.term")
        )
    try:
        return _sum(tuple(terms), "canopy_auc")
    except AlmondLabError as error:
        fail(
            "CANOPY_AUC_INVALID",
            "trapezoidal integral must remain finite",
            "canopy_auc",
            {"cause": error.code},
        )


def _forcing_tuple(value: object) -> tuple[RootZoneForcing, ...]:
    if isinstance(value, (str, bytes, Mapping)) or not isinstance(value, Iterable):
        fail("BIOLOGY_FORCING_VIOLATION", "forcings must be a nonempty iterable", "forcings")
    items = tuple(value)
    if not items:
        fail("BIOLOGY_FORCING_VIOLATION", "forcings cannot be empty", "forcings")
    return tuple(_canonical_forcing(item) for item in items)


def _run_forcings(
    state: PlantState,
    params: BiologyParameters,
    forcings: tuple[RootZoneForcing, ...],
    cursor: LedgerCursor,
) -> tuple[PlantState, tuple[PlantState, ...], tuple[AdvancePlantResult, ...], tuple[LedgerEntry, ...], LedgerCursor, int]:
    current = state
    states = [state]
    intervals: list[AdvancePlantResult] = []
    ledger: list[LedgerEntry] = []
    next_cursor = cursor
    substeps = 0
    for forcing in forcings:
        result = advance_plant(current, params, forcing, cursor=next_cursor)
        intervals.append(result)
        states.extend(result.states[1:])
        ledger.extend(result.ledger)
        substeps += result.substeps
        current = result.state
        next_cursor = result.next_cursor
    return current, tuple(states), tuple(intervals), tuple(ledger), next_cursor, substeps


def _state_coordinates(state: PlantState) -> tuple[float, ...]:
    return (
        state.biomass_g,
        state.canopy_area_cm2,
        state.ros_dimensionless,
        state.injury_dimensionless,
        state.mannitol_mmol,
        state.allocatable_energy_atp_eq,
        state.injury_exposure_hours,
        *state.network_state.all_values(),
    )


def simulate_plant(
    state: PlantState,
    parameters: BiologyParameters,
    forcings: Iterable[RootZoneForcing],
    *,
    cursor: LedgerCursor,
) -> SimulationResult:
    """Simulate registered forcing intervals and require step-halving convergence."""

    initial = _canonical_state(state)
    params = _canonical_parameters(parameters)
    schedule = _forcing_tuple(forcings)
    if not isinstance(cursor, LedgerCursor):
        fail("LEDGER_CURSOR_REQUIRED", "cursor must be LedgerCursor", "cursor")
    coarse = _run_forcings(initial, params, schedule, cursor)
    half_step = _product(
        0.5,
        params.integrator_max_step_hours,
        field_path="step_halving.fine_step_hours",
    )
    fine_params = replace(params, integrator_max_step_hours=half_step)
    fine = _run_forcings(initial, fine_params, schedule, cursor)
    coarse_state = coarse[0]
    fine_state = fine[0]
    coarse_values = _state_coordinates(coarse_state)
    fine_values = _state_coordinates(fine_state)
    differences = tuple(
        abs(left - right) for left, right in zip(coarse_values, fine_values)
    )
    scaled = tuple(
        difference / max(abs(left), abs(right), 1e-30)
        for difference, left, right in zip(differences, coarse_values, fine_values)
    )
    maximum_absolute = max(differences, default=0.0)
    maximum_scaled = max(scaled, default=0.0)
    converged = (
        coarse_state.alive is fine_state.alive
        and all(
            difference
            <= params.step_halving_absolute_tolerance
            + params.step_halving_relative_tolerance * max(abs(left), abs(right))
            for difference, left, right in zip(
                differences, coarse_values, fine_values
            )
        )
    )
    convergence = StepHalvingConvergence(
        converged=converged,
        coarse_step_hours=params.integrator_max_step_hours,
        fine_step_hours=half_step,
        maximum_absolute_difference=maximum_absolute,
        maximum_scaled_difference=maximum_scaled,
        absolute_tolerance=params.step_halving_absolute_tolerance,
        relative_tolerance=params.step_halving_relative_tolerance,
    )
    if not converged:
        fail(
            "BIOLOGY_STEP_CONVERGENCE_FAILURE",
            "registered half-step trajectory exceeds convergence tolerances",
            "convergence",
            {
                "maximum_absolute_difference": maximum_absolute,
                "maximum_scaled_difference": maximum_scaled,
            },
        )
    label = compose_evidence_labels(
        coarse_state.evidence_label,
        *(interval.evidence_label for interval in coarse[2]),
    )
    return SimulationResult(
        state=coarse_state,
        states=coarse[1],
        intervals=coarse[2],
        ledger=coarse[3],
        next_cursor=coarse[4],
        substeps=coarse[5],
        convergence=convergence,
        evidence_label=label,
    )
