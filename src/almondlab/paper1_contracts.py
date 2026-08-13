"""Frozen Paper 1 registry, allocation, and synthetic-input contracts."""

from collections.abc import Mapping, Sequence
from dataclasses import fields, replace
from enum import StrEnum
from math import isclose, log
from pathlib import Path
from types import MappingProxyType
from typing import Annotated, Literal

import yaml
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    SkipValidation,
    field_serializer,
    model_serializer,
    model_validator,
)

from almondlab.biology_surrogate import BiologyParameters, PlantState, RootZoneForcing
from almondlab.contracts import CompartmentKind, ConservedEntity, EvidenceLabel
from almondlab.errors import AlmondLabError, fail, finite_float
from almondlab.evidence_policy import compose_evidence_labels
from almondlab.hydraulics import HydraulicDomain
from almondlab.mass_balance import CompartmentState, NetworkState
from almondlab.schemas import WaterChemistry


class _DuplicateYamlKeyError(yaml.YAMLError):
    def __init__(self, key: object, node: yaml.nodes.Node) -> None:
        super().__init__(f"duplicate YAML key: {key}")
        self.key = key
        self.line = node.start_mark.line + 1
        self.column = node.start_mark.column + 1


class _UniqueKeySafeLoader(yaml.SafeLoader):
    """Safe loader that checks explicit keys before resolving YAML merges."""

    def __init__(self, stream: object) -> None:
        super().__init__(stream)
        self._checked_mapping_nodes: set[int] = set()

    def _check_mapping(self, node: yaml.nodes.MappingNode) -> None:
        node_identity = id(node)
        if node_identity not in self._checked_mapping_nodes:
            seen: set[object] = set()
            for key_node, _ in node.value:
                if key_node.tag == "tag:yaml.org,2002:merge":
                    continue
                key = self.construct_object(key_node, deep=False)
                try:
                    duplicate = key in seen
                except TypeError as error:
                    raise yaml.constructor.ConstructorError(
                        "while constructing a mapping",
                        node.start_mark,
                        "found unhashable key",
                        key_node.start_mark,
                    ) from error
                if duplicate:
                    raise _DuplicateYamlKeyError(key, key_node)
                seen.add(key)
            self._checked_mapping_nodes.add(node_identity)

    def construct_mapping(
        self,
        node: yaml.nodes.MappingNode,
        deep: bool = False,
    ) -> dict[object, object]:
        self._check_mapping(node)
        return super().construct_mapping(node, deep=deep)

    def flatten_mapping(self, node: yaml.nodes.MappingNode) -> None:
        # SafeConstructor recursively flattens merge sources, so validate each
        # raw mapping node once before that mutation can obscure key provenance.
        self._check_mapping(node)
        super().flatten_mapping(node)


class StrictPaper1Model(BaseModel):
    """Immutable Paper 1 boundary model that rejects unregistered fields."""

    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)


class AnalysisPopulation(StrEnum):
    COMPOSITE_ROOT = "composite_root"
    STABLE_EVENT = "stable_event"


class ScientificLabel(StrEnum):
    INCONCLUSIVE = "inconclusive"
    PROVISIONAL_LEADER = "provisional_leader"
    CO_LEADING = "co-leading"
    NOT_EVALUABLE = "not_evaluable"


class CandidateState(StrEnum):
    SCREENED_OUT = "screened_out"
    DISCOVERY_ELIGIBLE = "discovery_eligible"
    CONFIRMATION_PASSED = "confirmation_passed"
    FULLY_ADVANCEABLE = "fully_advanceable"


class H3Rule(StrictPaper1Model):
    endpoint: str = Field(min_length=1)
    unit: str = Field(min_length=1)
    scale: Literal["log_ratio", "difference"]
    direction: Literal["ge", "le"]
    margin: float
    min_probability: float = Field(default=0.90, ge=0.0, le=1.0)


FROZEN_CANDIDATE_IDENTITIES: dict[str, dict[str, object]] = {
    "C1": {
        "construct_name": "PyKPA1",
        "donor_species": "Pyropia yezoensis (Neopyropia yezoensis)",
        "sequence_accessions": ("AJ972674",),
        "sequence_status": "verified",
        "evidence_tier": "E2",
        "primary_parameter_id": "na_efflux_vmax_multiplier",
        "gates": {"sequence_build": "required", "directional_assay": "required"},
        "h3": (
            "root_surface_outward_na_flux_per_root_dry_mass",
            "umol Na g_root_dry_mass^-1 h^-1",
            "log_ratio",
            "ge",
            log(1.20),
            0.90,
        ),
    },
    "C2": {
        "construct_name": "PyAPX",
        "donor_species": "Pyropia yezoensis",
        "sequence_accessions": (),
        "sequence_status": "pending_audit",
        "evidence_tier": "E2",
        "primary_parameter_id": "ros_clearance_multiplier",
        "gates": {"sequence_build": "blocked", "directional_assay": "required"},
        "h3": (
            "root_h2o2_concentration_time_auc",
            "umol H2O2 g_root_fresh_mass^-1 h",
            "log_ratio",
            "le",
            log(0.80),
            0.90,
        ),
    },
    "C3": {
        "construct_name": "EsM1PDH1+EsM1Pase2",
        "donor_species": "Ectocarpus sp. Ec32",
        "sequence_accessions": ("Esi0017_0062", "Esi0100_0020"),
        "sequence_status": "verified",
        "evidence_tier": "E2",
        "primary_parameter_id": "mannitol_vmax_multiplier",
        "gates": {"sequence_build": "required", "directional_assay": "required"},
        "h3": (
            "root_mannitol_concentration_above_empty_vector",
            "nmol g_root_fresh_mass^-1",
            "difference",
            "ge",
            10.0,
            0.90,
        ),
    },
    "C4": {
        "construct_name": "SbSOS1",
        "donor_species": "Salicornia brachiata Roxb.",
        "sequence_accessions": ("EU879059",),
        "sequence_status": "verified",
        "evidence_tier": "E2",
        "primary_parameter_id": "na_efflux_vmax_multiplier",
        "gates": {
            "sequence_build": "required",
            "cortex_localization": "required",
            "directional_assay": "required",
        },
        "h3": (
            "root_surface_outward_na_flux_per_root_dry_mass",
            "umol Na g_root_dry_mass^-1 h^-1",
            "log_ratio",
            "ge",
            log(1.20),
            0.90,
        ),
    },
    "C5": {
        "construct_name": "PpHKT1",
        "donor_species": "Prunus persica 'Nemaguard'",
        "sequence_accessions": ("Prupe.1G067100",),
        "sequence_status": "verified",
        "evidence_tier": "E1",
        "primary_parameter_id": "xylem_na_retrieval_multiplier",
        "gates": {"sequence_build": "required", "directional_assay": "required"},
        "h3": (
            "xylem_sap_na_concentration_time_auc",
            "mmol Na L^-1 h",
            "log_ratio",
            "le",
            log(0.80),
            0.90,
        ),
    },
    "C6": {
        "construct_name": "PpSOS2_PpCIPK24",
        "donor_species": "Prunus persica 'Nemaguard'",
        "sequence_accessions": ("Prupe.7G244500.1", "XP_020424233.1"),
        "sequence_status": "verified",
        "evidence_tier": "E1",
        "primary_parameter_id": "sos_efflux_activation_multiplier",
        "gates": {"sequence_build": "required", "directional_assay": "required"},
        "h3": (
            "root_surface_outward_na_flux_per_root_dry_mass",
            "umol Na g_root_dry_mass^-1 h^-1",
            "log_ratio",
            "ge",
            log(1.20),
            0.90,
        ),
    },
}


class CandidateSpec(StrictPaper1Model):
    candidate_id: str = Field(pattern=r"^C[1-6]$")
    construct_name: str = Field(min_length=1)
    donor_species: str = Field(min_length=1)
    sequence_accessions: tuple[str, ...]
    sequence_status: Literal["verified", "pending_audit"]
    evidence_tier: Literal["E1", "E2"]
    evidence_label: Literal[EvidenceLabel.HYPOTHESIS_PRIOR]
    primary_parameter_id: str = Field(min_length=1)
    h3_rule: H3Rule
    gates: Mapping[str, Literal["required", "blocked"]]
    risk_warning: str = Field(min_length=1)

    @model_validator(mode="after")
    def require_frozen_v13_identity(self) -> "CandidateSpec":
        expected = FROZEN_CANDIDATE_IDENTITIES[self.candidate_id]
        actual = {
            "construct_name": self.construct_name,
            "donor_species": self.donor_species,
            "sequence_accessions": self.sequence_accessions,
            "sequence_status": self.sequence_status,
            "evidence_tier": self.evidence_tier,
            "primary_parameter_id": self.primary_parameter_id,
            "gates": self.gates,
        }
        mismatches = [name for name, value in actual.items() if value != expected[name]]
        expected_h3 = expected["h3"]
        actual_h3 = (
            self.h3_rule.endpoint,
            self.h3_rule.unit,
            self.h3_rule.scale,
            self.h3_rule.direction,
            self.h3_rule.margin,
            self.h3_rule.min_probability,
        )
        if actual_h3[:4] != expected_h3[:4] or any(
            not isclose(actual_value, expected_value, rel_tol=0.0, abs_tol=1e-12)
            for actual_value, expected_value in zip(actual_h3[4:], expected_h3[4:])
        ):
            mismatches.append("h3_rule")
        if mismatches:
            raise ValueError(
                f"candidate {self.candidate_id} does not match frozen v1.3 fields: "
                f"{sorted(mismatches)}"
            )
        object.__setattr__(self, "gates", MappingProxyType(dict(self.gates)))
        return self

    @field_serializer("gates")
    def serialize_gates(
        self, gates: Mapping[str, Literal["required", "blocked"]]
    ) -> dict[str, Literal["required", "blocked"]]:
        """Preserve the JSON contract while retaining a read-only runtime map."""

        return dict(gates)

    @property
    def h3(self) -> H3Rule:
        """Compatibility alias for the candidate's single registered H3 gate."""
        return self.h3_rule


class DecisionThresholds(StrictPaper1Model):
    h1_claim_log_ratio: float = log(1.20)
    h1_power_log_ratio: float = log(1.30)
    h1_min_probability: float = Field(default=0.90, ge=0.0, le=1.0)
    h2_control_ratio_min: float = Field(default=0.90, ge=0.0, le=1.0)
    h2_max_bad_probability: float = Field(default=0.10, ge=0.0, le=1.0)
    h3_min_probability: float = Field(default=0.90, ge=0.0, le=1.0)
    finalist_cap: int = Field(default=4, ge=1)
    tie_interval: float = Field(default=0.02, ge=0.0, le=1.0)
    probability_mcse_max: float = Field(default=0.005, gt=0.0, le=1.0)

    @model_validator(mode="after")
    def verify_frozen_values(self) -> "DecisionThresholds":
        expected = {
            "h1_claim_log_ratio": log(1.20),
            "h1_power_log_ratio": log(1.30),
            "h1_min_probability": 0.90,
            "h2_control_ratio_min": 0.90,
            "h2_max_bad_probability": 0.10,
            "h3_min_probability": 0.90,
            "finalist_cap": 4,
            "tie_interval": 0.02,
            "probability_mcse_max": 0.005,
        }
        changed = [
            name
            for name, target in expected.items()
            if not (
                getattr(self, name) == target
                if isinstance(target, int)
                else isclose(getattr(self, name), target, rel_tol=0.0, abs_tol=1e-12)
            )
        ]
        if changed:
            raise ValueError(f"Paper 1 decision thresholds are frozen: {changed}")
        return self

    @property
    def h1_claim_margin_log(self) -> float:
        return self.h1_claim_log_ratio

    @property
    def power_alternative_log(self) -> float:
        return self.h1_power_log_ratio

    @property
    def h2_ratio_min(self) -> float:
        return self.h2_control_ratio_min


class CandidateRegistry(StrictPaper1Model):
    schema_version: str = Field(min_length=1)
    thresholds: DecisionThresholds
    candidates: tuple[CandidateSpec, ...] = Field(min_length=6, max_length=6)

    @model_validator(mode="after")
    def require_exact_candidate_ids(self) -> "CandidateRegistry":
        if tuple(candidate.candidate_id for candidate in self.candidates) != tuple(
            f"C{number}" for number in range(1, 7)
        ):
            raise ValueError("candidate registry must contain C1 through C6 in order")
        return self


class WaterCondition(StrictPaper1Model):
    water_id: str = Field(min_length=1)
    chemistry: WaterChemistry
    evidence_label: Literal[EvidenceLabel.SYNTHETIC_ONLY, EvidenceLabel.HYPOTHESIS_PRIOR]


class Paper1DesignConfig(StrictPaper1Model):
    schema_version: str = Field(min_length=1)
    evidence_label: Literal[EvidenceLabel.SYNTHETIC_ONLY, EvidenceLabel.HYPOTHESIS_PRIOR]
    population: AnalysisPopulation
    full_allocation_groups: tuple[str, ...] = Field(min_length=9, max_length=9)
    water_conditions: tuple[WaterCondition, ...] = Field(min_length=2, max_length=2)
    runs: tuple[str, ...] = Field(min_length=2, max_length=2)
    reservoirs_per_water_run: int = Field(ge=4)
    independent_plants_per_group_reservoir: int = Field(ge=5)
    balanced_transformation_batches: tuple[str, ...] = Field(min_length=2)
    construct_level_unit: Literal["independently_transformed_plant"]
    water_treatment_unit: Literal["reservoir"]

    @model_validator(mode="after")
    def require_frozen_primary_design_identity(self) -> "Paper1DesignConfig":
        expected = {
            "schema_version": "1.3",
            "evidence_label": EvidenceLabel.SYNTHETIC_ONLY,
            "population": AnalysisPopulation.COMPOSITE_ROOT,
            "full_allocation_groups": (
                "C1",
                "C2",
                "C3",
                "C4",
                "C5",
                "C6",
                "empty_vector",
                "sham_transformation",
                "unmodified_parent",
            ),
            "water_ids": (
                "nonsaline_nutrient_matched_control",
                "pilot_selected_full_ion_marine_challenge",
            ),
            "water_evidence_labels": (
                EvidenceLabel.HYPOTHESIS_PRIOR,
                EvidenceLabel.HYPOTHESIS_PRIOR,
            ),
            "runs": ("discovery_run_1", "discovery_run_2"),
            "reservoirs_per_water_run": 4,
            "independent_plants_per_group_reservoir": 5,
            "balanced_transformation_batches": ("batch_a", "batch_b"),
            "construct_level_unit": "independently_transformed_plant",
            "water_treatment_unit": "reservoir",
        }
        actual = {
            "schema_version": self.schema_version,
            "evidence_label": self.evidence_label,
            "population": self.population,
            "full_allocation_groups": self.full_allocation_groups,
            "water_ids": tuple(water.water_id for water in self.water_conditions),
            "water_evidence_labels": tuple(
                water.evidence_label for water in self.water_conditions
            ),
            "runs": self.runs,
            "reservoirs_per_water_run": self.reservoirs_per_water_run,
            "independent_plants_per_group_reservoir": (
                self.independent_plants_per_group_reservoir
            ),
            "balanced_transformation_batches": self.balanced_transformation_batches,
            "construct_level_unit": self.construct_level_unit,
            "water_treatment_unit": self.water_treatment_unit,
        }
        mismatches = [name for name, value in actual.items() if value != expected[name]]
        if mismatches:
            raise ValueError(f"Paper 1 design identity is frozen: {sorted(mismatches)}")
        return self


REQUIRED_SYNTHETIC_SCENARIO_SECTIONS = frozenset(
    {"parameters", "initial_state", "forcing", "generator_parameters"}
)
REQUIRED_SYNTHETIC_SCENARIO_ROOT_KEYS = frozenset(
    {
        "biology_parameters",
        "initial_state",
        "forcing",
        "generator_parameters",
        "scenarios",
    }
)
REQUIRED_BIOLOGY_PARAMETER_KEYS = frozenset(
    field.name for field in fields(BiologyParameters)
)
REQUIRED_INITIAL_STATE_KEYS = frozenset(field.name for field in fields(PlantState))
REQUIRED_FORCING_KEYS = frozenset(field.name for field in fields(RootZoneForcing))
REQUIRED_GENERATOR_PARAMETER_KEYS = frozenset(
    {
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
)


def _scenario_invalid(
    message: str,
    field_path: str,
    *,
    cause: Exception | None = None,
) -> None:
    details = None
    if cause is not None:
        details = {"cause_type": type(cause).__name__}
        if isinstance(cause, AlmondLabError):
            details.update(
                {"cause_code": cause.code, "cause_field_path": cause.field_path}
            )
    fail("SYNTHETIC_SCENARIO_INVALID", message, field_path, details)


def _exact_scenario_keys(
    supplied: object,
    expected: frozenset[str],
    field_path: str,
) -> Mapping[str, object]:
    if not isinstance(supplied, Mapping):
        _scenario_invalid("section must be a mapping", field_path)
    names = set(supplied)
    if any(not isinstance(name, str) for name in names):
        _scenario_invalid("section keys must be strings", field_path)
    missing = sorted(expected - names)
    if missing:
        fail(
            "INCOMPLETE_SYNTHETIC_SCENARIO",
            "synthetic scenario omits registered inputs",
            field_path,
            {"missing": missing},
        )
    extra = sorted(names - expected)
    if extra:
        fail(
            "UNREGISTERED_SYNTHETIC_PARAMETER",
            "synthetic scenario contains unregistered inputs",
            field_path,
            {"extra": extra},
        )
    return supplied


def _evidence(value: object, field_path: str) -> EvidenceLabel:
    try:
        label = value if isinstance(value, EvidenceLabel) else EvidenceLabel(value)
    except (TypeError, ValueError) as error:
        _scenario_invalid("evidence label is invalid", field_path, cause=error)
    if label not in {EvidenceLabel.HYPOTHESIS_PRIOR, EvidenceLabel.SYNTHETIC_ONLY}:
        _scenario_invalid(
            "scenario evidence must be hypothesis_prior or synthetic_only",
            field_path,
        )
    return label


def _entity(value: object, field_path: str) -> ConservedEntity:
    try:
        return value if isinstance(value, ConservedEntity) else ConservedEntity(value)
    except (TypeError, ValueError) as error:
        _scenario_invalid("conserved entity is invalid", field_path, cause=error)


def _compartment_kind(value: object, field_path: str) -> CompartmentKind:
    try:
        return value if isinstance(value, CompartmentKind) else CompartmentKind(value)
    except (TypeError, ValueError) as error:
        _scenario_invalid("compartment kind is invalid", field_path, cause=error)


def _network_state(value: object, field_path: str) -> NetworkState:
    if isinstance(value, NetworkState):
        raw_compartments: object = value.compartments
        raw_entities: object = value.tracked_entities
        raw_label: object = value.evidence_label
    else:
        mapping = _exact_scenario_keys(
            value,
            frozenset({"compartments", "tracked_entities", "evidence_label"}),
            field_path,
        )
        raw_compartments = mapping["compartments"]
        raw_entities = mapping["tracked_entities"]
        raw_label = mapping["evidence_label"]
    if not isinstance(raw_compartments, Mapping) or not raw_compartments:
        _scenario_invalid("network compartments must be a nonempty mapping", f"{field_path}.compartments")
    compartments: dict[str, CompartmentState] = {}
    compartment_keys = frozenset(field.name for field in fields(CompartmentState))
    for raw_id, raw_compartment in raw_compartments.items():
        if not isinstance(raw_id, str):
            _scenario_invalid("compartment IDs must be strings", f"{field_path}.compartments")
        if isinstance(raw_compartment, CompartmentState):
            item = {
                field.name: getattr(raw_compartment, field.name)
                for field in fields(CompartmentState)
            }
        else:
            item = dict(
                _exact_scenario_keys(
                    raw_compartment,
                    compartment_keys,
                    f"{field_path}.compartments.{raw_id}",
                )
            )
        stocks = item["stocks"]
        if not isinstance(stocks, Mapping):
            _scenario_invalid("stocks must be a mapping", f"{field_path}.compartments.{raw_id}.stocks")
        typed_stocks: dict[ConservedEntity, object] = {}
        for raw_entity, amount in stocks.items():
            entity = _entity(
                raw_entity,
                f"{field_path}.compartments.{raw_id}.stocks",
            )
            typed_stocks[entity] = amount
        try:
            compartments[raw_id] = CompartmentState(
                compartment_id=item["compartment_id"],
                kind=_compartment_kind(
                    item["kind"], f"{field_path}.compartments.{raw_id}.kind"
                ),
                loop_id=item["loop_id"],
                volume_l=item["volume_l"],
                water_mass_kg=item["water_mass_kg"],
                empty_reference_density_kg_l=item[
                    "empty_reference_density_kg_l"
                ],
                stocks=typed_stocks,
                evidence_label=_evidence(
                    item["evidence_label"],
                    f"{field_path}.compartments.{raw_id}.evidence_label",
                ),
            )
        except AlmondLabError as error:
            _scenario_invalid(
                "network compartment is invalid",
                f"{field_path}.compartments.{raw_id}",
                cause=error,
            )
    if isinstance(raw_entities, (str, bytes, Mapping)) or not isinstance(
        raw_entities, (Sequence, set, frozenset)
    ):
        _scenario_invalid("tracked_entities must be a sequence", f"{field_path}.tracked_entities")
    tracked = frozenset(
        _entity(item, f"{field_path}.tracked_entities") for item in raw_entities
    )
    try:
        return NetworkState(
            compartments=compartments,
            tracked_entities=tracked,
            evidence_label=_evidence(raw_label, f"{field_path}.evidence_label"),
        )
    except AlmondLabError as error:
        _scenario_invalid("network state is invalid", field_path, cause=error)


def _biology_parameters(value: object) -> BiologyParameters:
    if isinstance(value, BiologyParameters):
        try:
            return replace(value)
        except AlmondLabError as error:
            _scenario_invalid("biology parameters are invalid", "parameters", cause=error)
    mapping = _exact_scenario_keys(
        value, REQUIRED_BIOLOGY_PARAMETER_KEYS, "parameters"
    )
    payload = dict(mapping)
    payload["evidence_label"] = _evidence(
        payload["evidence_label"], "parameters.evidence_label"
    )
    try:
        return BiologyParameters(**payload)
    except (AlmondLabError, TypeError, ValueError) as error:
        _scenario_invalid("biology parameters are invalid", "parameters", cause=error)


def _initial_state(value: object) -> PlantState:
    if isinstance(value, PlantState):
        try:
            return replace(value)
        except AlmondLabError as error:
            _scenario_invalid("initial plant state is invalid", "initial_state", cause=error)
    mapping = _exact_scenario_keys(value, REQUIRED_INITIAL_STATE_KEYS, "initial_state")
    payload = dict(mapping)
    payload["network_state"] = _network_state(
        payload["network_state"], "initial_state.network_state"
    )
    payload["evidence_label"] = _evidence(
        payload["evidence_label"], "initial_state.evidence_label"
    )
    try:
        return PlantState(**payload)
    except (AlmondLabError, TypeError, ValueError) as error:
        _scenario_invalid("initial plant state is invalid", "initial_state", cause=error)


def _hydraulic_domain(value: object) -> HydraulicDomain:
    if isinstance(value, HydraulicDomain):
        payload: object = value.model_dump(mode="python")
    else:
        payload = value
    try:
        return HydraulicDomain.model_validate(payload)
    except Exception as error:
        _scenario_invalid("hydraulic domain is invalid", "forcing.hydraulic_domain", cause=error)


def _forcing(value: object) -> RootZoneForcing:
    if isinstance(value, RootZoneForcing):
        try:
            return replace(value)
        except AlmondLabError as error:
            _scenario_invalid("root-zone forcing is invalid", "forcing", cause=error)
    mapping = _exact_scenario_keys(value, REQUIRED_FORCING_KEYS, "forcing")
    payload = dict(mapping)
    payload["evidence_label"] = _evidence(
        payload["evidence_label"], "forcing.evidence_label"
    )
    payload["hydraulic_domain"] = _hydraulic_domain(payload["hydraulic_domain"])
    try:
        return RootZoneForcing(**payload)
    except (AlmondLabError, TypeError, ValueError) as error:
        _scenario_invalid("root-zone forcing is invalid", "forcing", cause=error)


def _generator_parameters(value: object) -> Mapping[str, float]:
    mapping = _exact_scenario_keys(
        value, REQUIRED_GENERATOR_PARAMETER_KEYS, "generator_parameters"
    )
    copied: dict[str, float] = {}
    for name, raw_value in mapping.items():
        try:
            copied[name] = finite_float(
                raw_value,
                code="SYNTHETIC_SCENARIO_INVALID",
                field_path=f"generator_parameters.{name}",
                nonnegative=name != "missingness_intercept",
                positive=name == "duration_days",
            )
        except AlmondLabError:
            raise
    return MappingProxyType(copied)


class SyntheticScenarioConfig(StrictPaper1Model):
    """Every synthetic generator input, including typed biology state/forcing."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        allow_inf_nan=False,
        arbitrary_types_allowed=True,
        revalidate_instances="always",
    )

    scenario_id: str = Field(min_length=1)
    schema_version: str = Field(min_length=1)
    evidence_label: Literal[
        EvidenceLabel.SYNTHETIC_ONLY, EvidenceLabel.HYPOTHESIS_PRIOR
    ]
    parameters: Annotated[BiologyParameters, SkipValidation]
    initial_state: Annotated[PlantState, SkipValidation]
    forcing: Annotated[RootZoneForcing, SkipValidation]
    generator_parameters: Mapping[str, float]

    @model_validator(mode="before")
    @classmethod
    def validate_complete_scenario(cls, values: object) -> object:
        if isinstance(values, SyntheticScenarioConfig):
            supplied: dict[str, object] = {
                "scenario_id": values.scenario_id,
                "schema_version": values.schema_version,
                "evidence_label": values.evidence_label,
                "parameters": values.parameters,
                "initial_state": values.initial_state,
                "forcing": values.forcing,
                "generator_parameters": values.generator_parameters,
            }
        elif isinstance(values, Mapping):
            supplied = dict(values)
        else:
            _scenario_invalid("synthetic scenario must be a mapping", "scenario")
        missing = sorted(REQUIRED_SYNTHETIC_SCENARIO_SECTIONS - set(supplied))
        if missing:
            fail(
                "INCOMPLETE_SYNTHETIC_SCENARIO",
                "synthetic scenario omits registered sections",
                "scenario",
                {"missing": missing},
            )
        supplied["parameters"] = _biology_parameters(supplied["parameters"])
        supplied["initial_state"] = _initial_state(supplied["initial_state"])
        supplied["forcing"] = _forcing(supplied["forcing"])
        supplied["generator_parameters"] = _generator_parameters(
            supplied["generator_parameters"]
        )
        return supplied

    @model_validator(mode="after")
    def require_conservative_evidence(self) -> "SyntheticScenarioConfig":
        composed = compose_evidence_labels(
            self.parameters.evidence_label,
            self.initial_state.evidence_label,
            self.forcing.evidence_label,
        )
        if self.evidence_label is not composed:
            fail(
                "SYNTHETIC_SCENARIO_INVALID",
                "scenario evidence must equal its conservatively composed inputs",
                "evidence_label",
                {"expected": composed.value, "received": self.evidence_label.value},
            )
        object.__setattr__(
            self, "generator_parameters", MappingProxyType(dict(self.generator_parameters))
        )
        return self

    @model_serializer(mode="plain")
    def serialize_registered_inputs(self) -> dict[str, object]:
        """Emit plain JSON-compatible fields without exposing immutable proxies."""

        parameters = {
            field.name: (
                getattr(self.parameters, field.name).value
                if isinstance(getattr(self.parameters, field.name), EvidenceLabel)
                else getattr(self.parameters, field.name)
            )
            for field in fields(BiologyParameters)
        }
        compartments = {
            compartment_id: {
                "compartment_id": compartment.compartment_id,
                "kind": compartment.kind.value,
                "loop_id": compartment.loop_id,
                "volume_l": compartment.volume_l,
                "water_mass_kg": compartment.water_mass_kg,
                "empty_reference_density_kg_l": (
                    compartment.empty_reference_density_kg_l
                ),
                "stocks": {
                    entity.value: amount
                    for entity, amount in compartment.stocks.items()
                },
                "evidence_label": compartment.evidence_label.value,
            }
            for compartment_id, compartment in (
                self.initial_state.network_state.compartments.items()
            )
        }
        initial_state = {
            field.name: getattr(self.initial_state, field.name)
            for field in fields(PlantState)
            if field.name not in {"network_state", "evidence_label"}
        }
        initial_state.update(
            {
                "network_state": {
                    "compartments": compartments,
                    "tracked_entities": sorted(
                        entity.value
                        for entity in self.initial_state.network_state.tracked_entities
                    ),
                    "evidence_label": (
                        self.initial_state.network_state.evidence_label.value
                    ),
                },
                "evidence_label": self.initial_state.evidence_label.value,
            }
        )
        forcing = {
            field.name: (
                self.forcing.hydraulic_domain.model_dump(mode="json")
                if field.name == "hydraulic_domain"
                else getattr(self.forcing, field.name).value
                if isinstance(getattr(self.forcing, field.name), EvidenceLabel)
                else getattr(self.forcing, field.name)
            )
            for field in fields(RootZoneForcing)
        }
        return {
            "scenario_id": self.scenario_id,
            "schema_version": self.schema_version,
            "evidence_label": self.evidence_label.value,
            "parameters": parameters,
            "initial_state": initial_state,
            "forcing": forcing,
            "generator_parameters": dict(self.generator_parameters),
        }


def _load_yaml_mapping(
    path: str | Path,
    *,
    scenario_boundary: bool = False,
) -> dict[str, object]:
    try:
        payload = yaml.load(
            Path(path).read_text(encoding="utf-8"),
            Loader=_UniqueKeySafeLoader,
        )
    except _DuplicateYamlKeyError as error:
        if scenario_boundary:
            fail(
                "SYNTHETIC_SCENARIO_INVALID",
                "synthetic scenario YAML contains a duplicate explicit mapping key",
                "yaml",
                {
                    "duplicate_key": str(error.key),
                    "line": error.line,
                    "column": error.column,
                },
            )
        raise ValueError(f"duplicate YAML key: {error.key}") from error
    if not isinstance(payload, dict):
        raise ValueError(f"expected a mapping in {path}")
    return payload


def load_candidate_specs(path: str | Path) -> CandidateRegistry:
    """Load the complete ordered Paper 1 candidate registry."""
    return CandidateRegistry.model_validate(_load_yaml_mapping(path))


def load_candidates(path: str | Path) -> tuple[CandidateSpec, ...]:
    """Load candidate specifications without exposing registry implementation."""
    return load_candidate_specs(path).candidates


def load_thresholds(path: str | Path) -> DecisionThresholds:
    """Load frozen Paper 1 thresholds from a registry-shaped YAML file."""
    return load_candidate_specs(path).thresholds


def load_paper1_design(path: str | Path) -> Paper1DesignConfig:
    """Load the complete primary-population allocation design."""
    return Paper1DesignConfig.model_validate(_load_yaml_mapping(path))


def load_synthetic_scenarios(path: str | Path) -> tuple[SyntheticScenarioConfig, ...]:
    """Load labeled synthetic scenarios, failing closed on any hidden constant."""
    payload = _exact_scenario_keys(
        _load_yaml_mapping(path, scenario_boundary=True),
        REQUIRED_SYNTHETIC_SCENARIO_ROOT_KEYS,
        "root",
    )
    _exact_scenario_keys(
        payload["biology_parameters"],
        REQUIRED_BIOLOGY_PARAMETER_KEYS,
        "biology_parameters",
    )
    _biology_parameters(payload["biology_parameters"])
    _exact_scenario_keys(
        payload["initial_state"],
        REQUIRED_INITIAL_STATE_KEYS,
        "initial_state",
    )
    _initial_state(payload["initial_state"])
    _exact_scenario_keys(
        payload["forcing"],
        REQUIRED_FORCING_KEYS,
        "forcing",
    )
    _forcing(payload["forcing"])
    _exact_scenario_keys(
        payload["generator_parameters"],
        REQUIRED_GENERATOR_PARAMETER_KEYS,
        "generator_parameters",
    )
    _generator_parameters(payload["generator_parameters"])

    scenarios = payload["scenarios"]
    if not isinstance(scenarios, list) or not scenarios:
        _scenario_invalid(
            "synthetic scenario configuration requires a nonempty scenarios list",
            "scenarios",
        )
    for index, scenario in enumerate(scenarios):
        if not isinstance(scenario, Mapping):
            _scenario_invalid("synthetic scenario must be a mapping", f"scenarios.{index}")
    template_sections = {
        "biology_parameters": "parameters",
        "initial_state": "initial_state",
        "forcing": "forcing",
        "generator_parameters": "generator_parameters",
    }
    for template_name, section_name in template_sections.items():
        if not any(
            scenario.get(section_name) is payload[template_name]
            for scenario in scenarios
        ):
            _scenario_invalid(
                "registered root template must be consumed by a scenario alias",
                template_name,
            )
    return tuple(
        SyntheticScenarioConfig.model_validate(scenario) for scenario in scenarios
    )
