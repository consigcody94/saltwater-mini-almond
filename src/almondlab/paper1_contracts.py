"""Frozen Paper 1 registry, allocation, and synthetic-input contracts."""

import hashlib
from collections.abc import Mapping, Sequence
from dataclasses import fields, is_dataclass, replace
from enum import Enum, StrEnum
from math import isclose, log
from pathlib import Path
from types import MappingProxyType
from typing import Annotated, ClassVar, Literal

import yaml
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    SkipValidation,
    field_serializer,
    field_validator,
    model_serializer,
    model_validator,
)

from almondlab.biology_surrogate import (
    BiologyParameters,
    PlantState,
    RootZoneForcing,
    YamlAliasCycleError,
    YamlDuplicateKeyError,
    _strict_yaml_load,
)
from almondlab.contracts import CompartmentKind, ConservedEntity, EvidenceLabel
from almondlab.errors import AlmondLabError, fail, finite_float
from almondlab.evidence_policy import compose_evidence_labels
from almondlab.hydraulics import HydraulicDomain
from almondlab.mass_balance import CompartmentState, NetworkState
from almondlab.provenance import canonical_json_bytes
from almondlab.schemas import WaterChemistry


_MAPPING_PROXY_TYPE = type(MappingProxyType({}))
MAX_INTEROPERABLE_JSON_INTEGER = 2**53 - 1


class StrictPaper1Model(BaseModel):
    """Immutable Paper 1 boundary model that rejects unregistered fields."""

    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)


def _registered_json_value(value: object) -> object:
    """Detach immutable registered values into a canonical JSON-safe tree."""

    if isinstance(value, Enum):
        return value.value
    if isinstance(value, BaseModel):
        return {
            name: _registered_json_value(getattr(value, name))
            for name in type(value).model_fields
        }
    if is_dataclass(value) and not isinstance(value, type):
        return {
            field.name: _registered_json_value(getattr(value, field.name))
            for field in fields(value)
        }
    if isinstance(value, Mapping):
        return {
            str(key.value if isinstance(key, Enum) else key): _registered_json_value(
                item
            )
            for key, item in value.items()
        }
    if isinstance(value, (tuple, list)):
        return [_registered_json_value(item) for item in value]
    if isinstance(value, (set, frozenset)):
        plain = [_registered_json_value(item) for item in value]
        return sorted(plain, key=canonical_json_bytes)
    return value


class RegisteredQuantity(StrictPaper1Model):
    """One explicitly unit-bearing real-valued synthetic registration."""

    value: float
    unit: str
    evidence_label: Literal[
        EvidenceLabel.HYPOTHESIS_PRIOR,
        EvidenceLabel.SYNTHETIC_ONLY,
    ]

    @field_validator("value", mode="before")
    @classmethod
    def require_exact_float(cls, value: object) -> object:
        if type(value) is not float:
            raise ValueError("registered quantity values must be primitive floats")
        return value

    @field_validator("unit", mode="before")
    @classmethod
    def require_trimmed_unit(cls, value: object) -> object:
        if (
            type(value) is not str
            or not value
            or value != value.strip()
            or any(ord(character) < 32 for character in value)
        ):
            raise ValueError("registered quantity units must be trim-free strings")
        return value


class RegisteredCount(StrictPaper1Model):
    """One explicitly unit-bearing nonnegative integer registration."""

    value: int = Field(ge=0, le=MAX_INTEROPERABLE_JSON_INTEGER)
    unit: Literal["count"]
    evidence_label: Literal[
        EvidenceLabel.HYPOTHESIS_PRIOR,
        EvidenceLabel.SYNTHETIC_ONLY,
    ]

    @field_validator("value", mode="before")
    @classmethod
    def require_exact_integer(cls, value: object) -> object:
        if type(value) is not int:
            raise ValueError("registered counts must be primitive integers")
        return value


REGISTERED_WATER_IDS = (
    "nonsaline_nutrient_matched_control",
    "pilot_selected_full_ion_marine_challenge",
)
REGISTERED_ENDPOINT_IDS = (
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
REGISTERED_ION_ENDPOINT_IDS = REGISTERED_ENDPOINT_IDS[1:6]
REGISTERED_H3_ENDPOINT_IDS = REGISTERED_ENDPOINT_IDS[6:]
REGISTERED_CANDIDATE_IDS = tuple(f"C{number}" for number in range(1, 7))


def _require_quantity_unit(
    value: RegisteredQuantity, expected: str, field_path: str
) -> None:
    if value.unit != expected:
        raise ValueError(f"{field_path} requires unit {expected!r}")


def _freeze_exact_map(
    value: Mapping[str, object], expected: tuple[str, ...], field_path: str
) -> Mapping[str, object]:
    if type(value) not in (dict, _MAPPING_PROXY_TYPE):
        raise ValueError(f"{field_path} must be a primitive mapping")
    if tuple(value) != expected:
        raise ValueError(f"{field_path} must contain exact registered keys in order")
    return MappingProxyType(dict(value))


class _RegisteredGeneratorSection(StrictPaper1Model):
    _quantity_units: ClassVar[Mapping[str, str]] = MappingProxyType({})
    _count_fields: ClassVar[frozenset[str]] = frozenset()

    @model_validator(mode="after")
    def require_registered_units(self) -> "_RegisteredGeneratorSection":
        for name, unit in self._quantity_units.items():
            _require_quantity_unit(getattr(self, name), unit, name)
        for name in self._count_fields:
            if getattr(self, name).unit != "count":
                raise ValueError(f"{name} requires unit 'count'")
        return self

    @model_serializer(mode="plain")
    def serialize_registered_section(self) -> dict[str, object]:
        return _registered_json_value(self)  # type: ignore[return-value]


class HierarchyGeneratorConfig(_RegisteredGeneratorSection):
    run_variance: RegisteredQuantity
    batch_variance: RegisteredQuantity
    reservoir_variance: RegisteredQuantity
    plant_variance: RegisteredQuantity

    _quantity_units = MappingProxyType(
        {
            "run_variance": "log-ratio^2",
            "batch_variance": "log-ratio^2",
            "reservoir_variance": "log-ratio^2",
            "plant_variance": "log-ratio^2",
        }
    )


class ClimateGeneratorConfig(_RegisteredGeneratorSection):
    temperature_ar1_phi: RegisteredQuantity
    temperature_innovation_sd_k: RegisteredQuantity
    apar_ar1_phi: RegisteredQuantity
    apar_log_innovation_sd: RegisteredQuantity
    matric_potential_ar1_phi: RegisteredQuantity
    matric_potential_innovation_sd_mpa: RegisteredQuantity
    potential_transpiration_log_innovation_sd: RegisteredQuantity
    climate_initialization_burnin_steps: RegisteredCount

    _quantity_units = MappingProxyType(
        {
            "temperature_ar1_phi": "dimensionless",
            "temperature_innovation_sd_k": "K",
            "apar_ar1_phi": "dimensionless",
            "apar_log_innovation_sd": "log-ratio",
            "matric_potential_ar1_phi": "dimensionless",
            "matric_potential_innovation_sd_mpa": "MPa",
            "potential_transpiration_log_innovation_sd": "log-ratio",
        }
    )
    _count_fields = frozenset({"climate_initialization_burnin_steps"})


class ChemistryGeneratorConfig(_RegisteredGeneratorSection):
    common_ion_log_sd: RegisteredQuantity
    boron_log_sd: RegisteredQuantity
    ec_measurement_sd_ds_m: RegisteredQuantity
    osmolality_measurement_sd_osmol_kg: RegisteredQuantity
    ph_measurement_sd: RegisteredQuantity
    temperature_measurement_sd_k: RegisteredQuantity
    charge_balance_tolerance_percent: RegisteredQuantity

    _quantity_units = MappingProxyType(
        {
            "common_ion_log_sd": "log-ratio",
            "boron_log_sd": "log-ratio",
            "ec_measurement_sd_ds_m": "dS m^-1",
            "osmolality_measurement_sd_osmol_kg": "osmol kg^-1",
            "ph_measurement_sd": "pH",
            "temperature_measurement_sd_k": "K",
            "charge_balance_tolerance_percent": "percent",
        }
    )


class WaterLoopGeneratorConfig(_RegisteredGeneratorSection):
    reservoir_initial_volume_l: RegisteredQuantity
    water_batch_volume_l: RegisteredQuantity
    irrigation_volume_l_per_plant_day: RegisteredQuantity
    drainage_return_fraction: RegisteredQuantity
    purge_volume_l_day: RegisteredQuantity
    sampling_volume_l_per_sample: RegisteredQuantity
    reservoir_min_volume_l: RegisteredQuantity
    reservoir_max_volume_l: RegisteredQuantity
    operator_event_times_days: tuple[RegisteredQuantity, ...]

    _quantity_units = MappingProxyType(
        {
            "reservoir_initial_volume_l": "L",
            "water_batch_volume_l": "L",
            "irrigation_volume_l_per_plant_day": "L plant^-1 day^-1",
            "drainage_return_fraction": "dimensionless",
            "purge_volume_l_day": "L day^-1",
            "sampling_volume_l_per_sample": "L sample^-1",
            "reservoir_min_volume_l": "L",
            "reservoir_max_volume_l": "L",
        }
    )

    @model_validator(mode="after")
    def require_ordered_operator_schedule(self) -> "WaterLoopGeneratorConfig":
        if not self.operator_event_times_days:
            raise ValueError("operator event schedule must be nonempty")
        for item in self.operator_event_times_days:
            _require_quantity_unit(item, "day", "operator_event_times_days")
        values = tuple(item.value for item in self.operator_event_times_days)
        if any(right <= left for left, right in zip(values, values[1:])):
            raise ValueError("operator event schedule must be strictly increasing")
        return self


class H3MeasurementLinksConfig(_RegisteredGeneratorSection):
    root_dry_matter_fraction: RegisteredQuantity
    h2o2_umol_g_root_fresh_mass_inv_per_ros_dimensionless: RegisteredQuantity

    _quantity_units = MappingProxyType(
        {
            "root_dry_matter_fraction": "dimensionless",
            "h2o2_umol_g_root_fresh_mass_inv_per_ros_dimensionless": (
                "umol H2O2 g_root_fresh_mass^-1 per ros_dimensionless"
            ),
        }
    )


class ObservationGeneratorConfig(_RegisteredGeneratorSection):
    canopy_observation_error_sd: RegisteredQuantity
    ion_observation_error_sd: RegisteredQuantity
    h3_observation_error_by_endpoint: Mapping[str, RegisteredQuantity]
    canopy_heteroscedastic_log_slope: RegisteredQuantity
    ion_heteroscedastic_log_slope: RegisteredQuantity
    canopy_observation_times_days: tuple[RegisteredQuantity, ...]
    ion_observation_times_days: tuple[RegisteredQuantity, ...]
    h3_observation_times_days_by_endpoint: Mapping[
        str, tuple[RegisteredQuantity, ...]
    ]
    h3_measurement_links: H3MeasurementLinksConfig

    _quantity_units = MappingProxyType(
        {
            "canopy_observation_error_sd": "log-ratio",
            "ion_observation_error_sd": "log-ratio",
            "canopy_heteroscedastic_log_slope": "log/log",
            "ion_heteroscedastic_log_slope": "log/log",
        }
    )

    @model_validator(mode="after")
    def require_observation_maps(self) -> "ObservationGeneratorConfig":
        errors = _freeze_exact_map(
            self.h3_observation_error_by_endpoint,
            REGISTERED_CANDIDATE_IDS,
            "h3_observation_error_by_endpoint",
        )
        for candidate_id, item in errors.items():
            expected = (
                "nmol g_root_fresh_mass^-1"
                if candidate_id == "C3"
                else "log-ratio"
            )
            _require_quantity_unit(item, expected, f"h3.{candidate_id}")
        schedules = _freeze_exact_map(
            self.h3_observation_times_days_by_endpoint,
            REGISTERED_H3_ENDPOINT_IDS,
            "h3_observation_times_days_by_endpoint",
        )
        for endpoint_id, schedule in schedules.items():
            if type(schedule) is not tuple or not schedule:
                raise ValueError(f"H3 schedule {endpoint_id} must be a nonempty tuple")
            for item in schedule:
                _require_quantity_unit(item, "day", endpoint_id)
        for name in (
            "canopy_observation_times_days",
            "ion_observation_times_days",
        ):
            schedule = getattr(self, name)
            if not schedule:
                raise ValueError(f"{name} must be nonempty")
            for item in schedule:
                _require_quantity_unit(item, "day", name)
        object.__setattr__(self, "h3_observation_error_by_endpoint", errors)
        object.__setattr__(self, "h3_observation_times_days_by_endpoint", schedules)
        return self


class CensoringGeneratorConfig(StrictPaper1Model):
    lod_by_endpoint: Mapping[str, RegisteredQuantity | None]
    loq_by_endpoint: Mapping[str, RegisteredQuantity | None]
    lod_log_sd_by_endpoint: Mapping[str, RegisteredQuantity | None]
    loq_log_sd_by_endpoint: Mapping[str, RegisteredQuantity | None]

    @model_validator(mode="after")
    def require_endpoint_complete_maps(self) -> "CensoringGeneratorConfig":
        for name in (
            "lod_by_endpoint",
            "loq_by_endpoint",
            "lod_log_sd_by_endpoint",
            "loq_log_sd_by_endpoint",
        ):
            frozen = _freeze_exact_map(
                getattr(self, name), REGISTERED_ENDPOINT_IDS, name
            )
            if "log_sd" in name:
                for endpoint_id, item in frozen.items():
                    if item is not None:
                        _require_quantity_unit(item, "log-ratio", endpoint_id)
            object.__setattr__(self, name, frozen)
        return self

    @model_serializer(mode="plain")
    def serialize_registered_section(self) -> dict[str, object]:
        return _registered_json_value(self)  # type: ignore[return-value]


class DriftGeneratorConfig(_RegisteredGeneratorSection):
    canopy_drift_per_day: RegisteredQuantity
    ion_drift_per_day_by_endpoint: Mapping[str, RegisteredQuantity]
    h3_drift_per_day_by_endpoint: Mapping[str, RegisteredQuantity]
    calibration_interval_days: RegisteredQuantity
    calibration_phase_offset_days: RegisteredQuantity
    post_calibration_residual_sd_by_endpoint: Mapping[str, RegisteredQuantity]

    _quantity_units = MappingProxyType(
        {
            "canopy_drift_per_day": "log-ratio day^-1",
            "calibration_interval_days": "day",
            "calibration_phase_offset_days": "day",
        }
    )

    @model_validator(mode="after")
    def require_endpoint_complete_maps(self) -> "DriftGeneratorConfig":
        for name, keys in (
            ("ion_drift_per_day_by_endpoint", REGISTERED_ION_ENDPOINT_IDS),
            ("h3_drift_per_day_by_endpoint", REGISTERED_H3_ENDPOINT_IDS),
            ("post_calibration_residual_sd_by_endpoint", REGISTERED_ENDPOINT_IDS),
        ):
            object.__setattr__(
                self, name, _freeze_exact_map(getattr(self, name), keys, name)
            )
        return self


class DeathGeneratorConfig(_RegisteredGeneratorSection):
    biomass_death_threshold_log_sd: RegisteredQuantity
    injury_death_threshold_log_sd: RegisteredQuantity
    sustained_injury_duration_log_sd: RegisteredQuantity

    _quantity_units = MappingProxyType(
        {
            "biomass_death_threshold_log_sd": "log-ratio",
            "injury_death_threshold_log_sd": "log-ratio",
            "sustained_injury_duration_log_sd": "log-ratio",
        }
    )


class MissingnessGeneratorConfig(_RegisteredGeneratorSection):
    missingness_intercept: RegisteredQuantity
    missingness_stress_slope: RegisteredQuantity
    mnar_tipping_delta: RegisteredQuantity
    observable_stress_proxy_fields: tuple[str, ...]
    observable_stress_proxy_center_by_field: Mapping[str, RegisteredQuantity]
    observable_stress_proxy_scale_by_field: Mapping[str, RegisteredQuantity]
    mnar_endpoints: tuple[str, ...]

    _quantity_units = MappingProxyType(
        {
            "missingness_intercept": "logit",
            "missingness_stress_slope": "logit per standardized-proxy SD",
            "mnar_tipping_delta": "logit per standardized-endpoint SD",
        }
    )

    @model_validator(mode="after")
    def require_registered_proxy_maps(self) -> "MissingnessGeneratorConfig":
        expected = (
            "challenge_water_indicator",
            "scheduled_time_days",
            "prior_observed_canopy_log_ratio",
        )
        if self.observable_stress_proxy_fields != expected:
            raise ValueError("observable stress proxy fields are frozen")
        for name in (
            "observable_stress_proxy_center_by_field",
            "observable_stress_proxy_scale_by_field",
        ):
            object.__setattr__(
                self,
                name,
                _freeze_exact_map(getattr(self, name), expected, name),
            )
        if self.mnar_endpoints != (
            "green_canopy_area",
            *REGISTERED_H3_ENDPOINT_IDS,
        ):
            raise ValueError("MNAR endpoint set and order are frozen")
        return self


class CalibrationGeneratorConfig(_RegisteredGeneratorSection):
    parameter_xtol: RegisteredQuantity
    parameter_rtol: RegisteredQuantity
    objective_residual_tolerance_log_ratio: RegisteredQuantity
    max_iterations: RegisteredCount
    fit_panel_size: RegisteredCount
    holdout_panel_size: RegisteredCount
    holdout_tolerance_log_ratio: RegisteredQuantity

    _quantity_units = MappingProxyType(
        {
            "parameter_xtol": "dimensionless",
            "parameter_rtol": "dimensionless",
            "objective_residual_tolerance_log_ratio": "log-ratio",
            "holdout_tolerance_log_ratio": "log-ratio",
        }
    )
    _count_fields = frozenset(
        {"max_iterations", "fit_panel_size", "holdout_panel_size"}
    )


class GeneratorDesignConfig(_RegisteredGeneratorSection):
    duration_days: RegisteredQuantity
    confirmation_plants_per_group_reservoir: RegisteredCount

    _quantity_units = MappingProxyType({"duration_days": "day"})
    _count_fields = frozenset({"confirmation_plants_per_group_reservoir"})


class SyntheticGeneratorConfig(StrictPaper1Model):
    hierarchy: HierarchyGeneratorConfig
    climate: ClimateGeneratorConfig
    chemistry: ChemistryGeneratorConfig
    water_loop: WaterLoopGeneratorConfig
    observation: ObservationGeneratorConfig
    censoring: CensoringGeneratorConfig
    drift: DriftGeneratorConfig
    death: DeathGeneratorConfig
    missingness: MissingnessGeneratorConfig
    calibration: CalibrationGeneratorConfig
    design: GeneratorDesignConfig

    @model_serializer(mode="plain")
    def serialize_registered_generator(self) -> dict[str, object]:
        return _registered_json_value(self)  # type: ignore[return-value]


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
        "sequence_accessions": ("AJ972674.1", "CAI99405.1"),
        "sequence_status": "accession_verified",
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
        "sequence_accessions": ("AY282755.1",),
        "sequence_status": "accession_verified",
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
        "sequence_status": "crosswalk_pending",
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
        "sequence_accessions": ("EU879059.1", "ACJ63441.1"),
        "sequence_status": "accession_verified",
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
    sequence_status: Literal[
        "accession_verified", "crosswalk_pending", "verified", "pending_audit"
    ]
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

    @field_validator("water_id", mode="before")
    @classmethod
    def require_exact_water_id(cls, value: object) -> object:
        if (
            type(value) is not str
            or not value
            or value != value.strip()
            or any(ord(character) < 32 for character in value)
        ):
            raise ValueError("water_id must be a trim-free nonempty string")
        return value


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

    @field_validator(
        "reservoirs_per_water_run",
        "independent_plants_per_group_reservoir",
        mode="before",
    )
    @classmethod
    def require_exact_integer_counts(cls, value: object) -> object:
        if type(value) is not int:
            raise ValueError("allocation counts must be exact primitive integers")
        return value

    @field_validator(
        "full_allocation_groups",
        "runs",
        "balanced_transformation_batches",
        mode="before",
    )
    @classmethod
    def require_exact_unique_ids(cls, value: object) -> object:
        if type(value) not in (list, tuple):
            raise ValueError("design ID collections must be ordinary lists or tuples")
        items = tuple(value)
        if any(
            type(item) is not str
            or not item
            or item != item.strip()
            or any(ord(character) < 32 for character in item)
            for item in items
        ):
            raise ValueError("design IDs must be trim-free nonempty strings")
        if len(set(items)) != len(items):
            raise ValueError("design IDs must be unique")
        return items

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


class LegacySyntheticScenarioConfig(StrictPaper1Model):
    """Migration-only v1.3 scenario decoder; generation must never consume it."""

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
        if isinstance(values, LegacySyntheticScenarioConfig):
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
    def require_conservative_evidence(self) -> "LegacySyntheticScenarioConfig":
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


class SyntheticScenarioId(StrEnum):
    PERFECT_CONTROL = "perfect_control"
    TRUE_ION_EXCLUSION = "true_ion_exclusion"
    ROOT_NA_ACCUMULATION = "root_na_accumulation"
    MARKER_ONLY = "marker_only"
    NONSALINE_PENALTY = "nonsaline_penalty"
    CHASSIS_INTERACTION = "chassis_interaction"
    DELAYED_TOXICITY = "delayed_toxicity"
    SENSOR_DRIFT_MISSINGNESS = "sensor_drift_missingness"
    INSUFFICIENT_PURGE = "insufficient_purge"
    SELECTION_BIAS_FALSE_LEADER = "selection_bias_false_leader"


REGISTERED_SCENARIO_IDS = tuple(item.value for item in SyntheticScenarioId)


def _deep_freeze_registered_value(value: object, field_path: str) -> object:
    if value is None or type(value) in (str, int, float, bool):
        if type(value) is float and (value != value or abs(value) == float("inf")):
            raise ValueError(f"{field_path} contains a nonfinite number")
        return value
    if type(value) is list or type(value) is tuple:
        return tuple(
            _deep_freeze_registered_value(item, f"{field_path}[{index}]")
            for index, item in enumerate(value)
        )
    if type(value) in (dict, _MAPPING_PROXY_TYPE):
        frozen: dict[str, object] = {}
        for key, item in value.items():
            if type(key) is not str or not key or key != key.strip():
                raise ValueError(f"{field_path} keys must be trim-free strings")
            frozen[key] = _deep_freeze_registered_value(
                item, f"{field_path}.{key}"
            )
        return MappingProxyType(frozen)
    raise ValueError(f"{field_path} contains an unsupported value")


class ScenarioMechanismConfig(StrictPaper1Model):
    biology_parameter_overrides: Mapping[str, object]
    candidate_parameter_overrides_by_id: Mapping[str, object]
    onset_time_days: RegisteredQuantity | None
    post_onset_biology_parameter_overrides: Mapping[str, object]
    chassis_id: str | None
    candidate_chassis_mechanism_modifiers: Mapping[str, object]

    @model_validator(mode="after")
    def freeze_registered_mechanism(self) -> "ScenarioMechanismConfig":
        if self.onset_time_days is not None:
            _require_quantity_unit(self.onset_time_days, "day", "onset_time_days")
        if self.chassis_id is not None and (
            type(self.chassis_id) is not str
            or not self.chassis_id
            or self.chassis_id != self.chassis_id.strip()
        ):
            raise ValueError("chassis_id must be null or a trim-free string")
        for name in (
            "biology_parameter_overrides",
            "candidate_parameter_overrides_by_id",
            "post_onset_biology_parameter_overrides",
            "candidate_chassis_mechanism_modifiers",
        ):
            raw = getattr(self, name)
            if type(raw) not in (dict, _MAPPING_PROXY_TYPE):
                raise ValueError(f"{name} must be a primitive mapping")
            object.__setattr__(
                self, name, _deep_freeze_registered_value(raw, name)
            )
        return self

    @model_serializer(mode="plain")
    def serialize_registered_mechanism(self) -> dict[str, object]:
        return _registered_json_value(self)  # type: ignore[return-value]


class SyntheticScenarioConfig(StrictPaper1Model):
    """The only scenario shape accepted by Task 4 generation."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        allow_inf_nan=False,
        arbitrary_types_allowed=True,
        revalidate_instances="always",
    )

    scenario_id: SyntheticScenarioId
    schema_version: Literal["1.4.0"]
    evidence_label: Literal[
        EvidenceLabel.HYPOTHESIS_PRIOR,
        EvidenceLabel.SYNTHETIC_ONLY,
    ]
    parameters: Annotated[BiologyParameters, SkipValidation]
    initial_state: Annotated[PlantState, SkipValidation]
    forcings_by_water_id: Annotated[
        Mapping[str, tuple[RootZoneForcing, ...]], SkipValidation
    ]
    generator: SyntheticGeneratorConfig
    mechanism: ScenarioMechanismConfig

    @field_validator("parameters", mode="before")
    @classmethod
    def reconstruct_parameters(cls, value: object) -> BiologyParameters:
        return _biology_parameters(value)

    @field_validator("initial_state", mode="before")
    @classmethod
    def reconstruct_initial_state(cls, value: object) -> PlantState:
        return _initial_state(value)

    @field_validator("forcings_by_water_id", mode="before")
    @classmethod
    def reconstruct_water_forcings(
        cls, value: object
    ) -> Mapping[str, tuple[RootZoneForcing, ...]]:
        if (
            type(value) not in (dict, _MAPPING_PROXY_TYPE)
            or tuple(value) != REGISTERED_WATER_IDS
        ):
            raise ValueError("forcings_by_water_id requires exact registered waters")
        reconstructed: dict[str, tuple[RootZoneForcing, ...]] = {}
        for water_id, schedule in value.items():
            if type(schedule) not in (list, tuple) or not schedule:
                raise ValueError("each registered water requires a nonempty schedule")
            reconstructed[water_id] = tuple(_forcing(item) for item in schedule)
        return MappingProxyType(reconstructed)

    @model_validator(mode="after")
    def require_conservative_evidence(self) -> "SyntheticScenarioConfig":
        labels = [
            self.parameters.evidence_label,
            self.initial_state.evidence_label,
            *(
                forcing.evidence_label
                for schedule in self.forcings_by_water_id.values()
                for forcing in schedule
            ),
        ]
        expected = compose_evidence_labels(*labels)
        if self.evidence_label is not expected:
            raise ValueError(
                "scenario evidence must equal conservatively composed inputs"
            )
        object.__setattr__(
            self,
            "forcings_by_water_id",
            MappingProxyType(
                {
                    water_id: tuple(schedule)
                    for water_id, schedule in self.forcings_by_water_id.items()
                }
            ),
        )
        return self

    @model_serializer(mode="plain")
    def serialize_registered_scenario(self) -> dict[str, object]:
        return _registered_json_value(self)  # type: ignore[return-value]


class SyntheticScenarioRegistry(StrictPaper1Model):
    schema_version: Literal["1.4.0"]
    water_recipe_registry_sha256: str
    anchor: SyntheticScenarioConfig
    scenarios: tuple[SyntheticScenarioConfig, ...]

    @field_validator("water_recipe_registry_sha256", mode="before")
    @classmethod
    def require_sha256(cls, value: object) -> object:
        if (
            type(value) is not str
            or len(value) != 64
            or any(character not in "0123456789abcdef" for character in value)
        ):
            raise ValueError("water recipe registry hash must be lowercase SHA-256")
        return value

    @model_validator(mode="after")
    def require_exact_scenario_order(self) -> "SyntheticScenarioRegistry":
        observed = tuple(item.scenario_id.value for item in self.all_scenarios)
        if observed != REGISTERED_SCENARIO_IDS:
            raise ValueError("scenario registry must contain exact registered order")
        return self

    @property
    def all_scenarios(self) -> tuple[SyntheticScenarioConfig, ...]:
        return (self.anchor, *self.scenarios)

    @model_serializer(mode="plain")
    def serialize_registered_registry(self) -> dict[str, object]:
        return _registered_json_value(self)  # type: ignore[return-value]


class MigrationDisposition(StrEnum):
    PRESERVED = "preserved"
    RETYPED_WITH_UNIT = "retyped_with_unit"
    SPLIT_REQUIRES_REGISTRATION = "split_requires_registration"
    RETIRED = "retired"
    OWNER_REQUIRED = "owner_required"


class ScenarioMigrationItem(StrictPaper1Model):
    source_path: str | None
    source_canonical_json: str | None
    disposition: MigrationDisposition
    destination_paths: tuple[str, ...]
    owner_required_paths: tuple[str, ...]
    rationale: str


class ScenarioMigrationInventory(StrictPaper1Model):
    source_schema_version: Literal["1.3.0"]
    source_raw_sha256: str
    source_normalized_sha256: str
    items: tuple[ScenarioMigrationItem, ...]
    unclassified_source_paths: tuple[str, ...]
    multiply_classified_source_paths: tuple[str, ...]


def _iter_migration_leaves(
    value: object, prefix: str = ""
) -> tuple[tuple[str, object], ...]:
    leaves: list[tuple[str, object]] = []
    if isinstance(value, Mapping):
        for key, item in value.items():
            if type(key) is not str:
                raise ValueError("migration source keys must be strings")
            path = f"{prefix}.{key}" if prefix else key
            leaves.extend(_iter_migration_leaves(item, path))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            if prefix == "scenarios" and isinstance(item, Mapping):
                scenario_id = item.get("scenario_id")
                if type(scenario_id) is not str:
                    raise ValueError("each legacy scenario requires scenario_id")
                path = f"scenarios[scenario_id={scenario_id}]"
            else:
                path = f"{prefix}[{index}]"
            leaves.extend(_iter_migration_leaves(item, path))
    else:
        leaves.append((prefix, value))
    return tuple(leaves)


_LEGACY_GENERATOR_DESTINATIONS = MappingProxyType(
    {
        "run_variance": "anchor.generator.hierarchy.run_variance",
        "batch_variance": "anchor.generator.hierarchy.batch_variance",
        "reservoir_variance": "anchor.generator.hierarchy.reservoir_variance",
        "plant_variance": "anchor.generator.hierarchy.plant_variance",
        "canopy_observation_error_sd": (
            "anchor.generator.observation.canopy_observation_error_sd"
        ),
        "ion_observation_error_sd": (
            "anchor.generator.observation.ion_observation_error_sd"
        ),
        "missingness_intercept": (
            "anchor.generator.missingness.missingness_intercept"
        ),
        "missingness_stress_slope": (
            "anchor.generator.missingness.missingness_stress_slope"
        ),
        "mnar_tipping_delta": (
            "anchor.generator.missingness.mnar_tipping_delta"
        ),
        "duration_days": "anchor.generator.design.duration_days",
    }
)


_LEGACY_SCENARIO_OVERRIDE_DESTINATIONS = MappingProxyType(
    {
        (
            "true_ion_exclusion",
            "parameters.root_na_permeability_l_cm2_h",
        ): (
            "scenarios[scenario_id=true_ion_exclusion].mechanism."
            "biology_parameter_overrides.root_na_permeability_l_cm2_h"
        ),
        (
            "root_na_accumulation",
            "parameters.na_efflux_vmax_mmol_h",
        ): (
            "scenarios[scenario_id=root_na_accumulation].mechanism."
            "biology_parameter_overrides.na_efflux_vmax_mmol_h"
        ),
        ("marker_only", "parameters.ros_clearance_h_inv"): (
            "scenarios[scenario_id=marker_only].mechanism."
            "biology_parameter_overrides.ros_clearance_h_inv"
        ),
        (
            "nonsaline_penalty",
            "parameters.mannitol_carbon_cost_mmol_c_mmol_inv",
        ): (
            "scenarios[scenario_id=nonsaline_penalty].mechanism."
            "biology_parameter_overrides.mannitol_carbon_cost_mmol_c_mmol_inv"
        ),
        ("delayed_toxicity", "parameters.senescence_h_inv"): (
            "scenarios[scenario_id=delayed_toxicity].mechanism."
            "post_onset_biology_parameter_overrides.senescence_h_inv"
        ),
        (
            "sensor_drift_missingness",
            "generator_parameters.canopy_observation_error_sd",
        ): (
            "scenarios[scenario_id=sensor_drift_missingness].generator."
            "observation.canopy_observation_error_sd"
        ),
        (
            "sensor_drift_missingness",
            "generator_parameters.missingness_stress_slope",
        ): (
            "scenarios[scenario_id=sensor_drift_missingness].generator."
            "missingness.missingness_stress_slope"
        ),
        (
            "selection_bias_false_leader",
            "generator_parameters.plant_variance",
        ): (
            "scenarios[scenario_id=selection_bias_false_leader].generator."
            "hierarchy.plant_variance"
        ),
    }
)


def _classify_migration_leaf(
    source_path: str,
) -> tuple[MigrationDisposition, tuple[str, ...], tuple[str, ...], str]:
    if source_path.startswith("biology_parameters."):
        suffix = source_path.removeprefix("biology_parameters.")
        return (
            MigrationDisposition.PRESERVED,
            (f"anchor.parameters.{suffix}",),
            (),
            "Preserve the canonical biology anchor in the v1.4 anchor scenario.",
        )
    if source_path.startswith("initial_state."):
        suffix = source_path.removeprefix("initial_state.")
        return (
            MigrationDisposition.PRESERVED,
            (f"anchor.initial_state.{suffix}",),
            (),
            "Preserve the canonical initial-state anchor.",
        )
    if source_path.startswith("forcing."):
        return (
            MigrationDisposition.RETIRED,
            (),
            (),
            "Retire the one-water forcing in favor of registered two-water schedules.",
        )
    if source_path.startswith("generator_parameters."):
        name = source_path.removeprefix("generator_parameters.")
        if name == "h3_observation_error_sd":
            return (
                MigrationDisposition.SPLIT_REQUIRES_REGISTRATION,
                tuple(
                    "anchor.generator.observation."
                    f"h3_observation_error_by_endpoint.{candidate}"
                    for candidate in ("C1", "C2", "C4", "C5", "C6")
                ),
                (
                    "anchor.generator.observation."
                    "h3_observation_error_by_endpoint.C3",
                ),
                "Split the legacy scalar by candidate endpoint; C3 needs a native-unit value.",
            )
        return (
            MigrationDisposition.RETYPED_WITH_UNIT,
            (_LEGACY_GENERATOR_DESTINATIONS[name],),
            (),
            "Retype the legacy scalar as one explicit unit-bearing registration.",
        )
    if source_path.startswith("scenarios[scenario_id="):
        scenario_id, _, suffix = source_path.removeprefix(
            "scenarios[scenario_id="
        ).partition("].")
        destination = _LEGACY_SCENARIO_OVERRIDE_DESTINATIONS.get(
            (scenario_id, suffix)
        )
        if destination is not None:
            return (
                MigrationDisposition.RETYPED_WITH_UNIT,
                (destination,),
                (),
                "Retype the registered legacy scenario delta at its literal v1.4 path.",
            )
        if suffix in {"scenario_id", "schema_version", "evidence_label"}:
            return (
                MigrationDisposition.RETYPED_WITH_UNIT,
                (f"scenarios[scenario_id={scenario_id}].{suffix}",),
                (),
                "Retype scenario identity metadata in the v1.4 registry.",
            )
        return (
            MigrationDisposition.RETIRED,
            (),
            (),
            "Retire expanded YAML duplicates or a specifically withdrawn legacy scenario edit.",
        )
    return (
        MigrationDisposition.OWNER_REQUIRED,
        (),
        (source_path,),
        "Require an explicit owner classification for an unknown legacy path.",
    )


def inspect_v13_scenario_migration(
    path: str | Path,
) -> ScenarioMigrationInventory:
    """Inventory every legacy leaf without producing an active configuration."""

    source = Path(path)
    raw_bytes = source.read_bytes()
    try:
        payload = _load_yaml_mapping(source, scenario_boundary=True)
    except AlmondLabError:
        raise
    scenarios = payload.get("scenarios")
    if not isinstance(scenarios, list) or not scenarios or any(
        not isinstance(item, Mapping) or item.get("schema_version") != "1.3.0"
        for item in scenarios
    ):
        fail(
            "SCENARIO_MIGRATION_INVALID",
            "migration inspection requires an exact v1.3.0 source document",
            "schema_version",
        )
    leaves = _iter_migration_leaves(payload)
    items = tuple(
        ScenarioMigrationItem(
            source_path=source_path,
            source_canonical_json=canonical_json_bytes(value).decode("utf-8"),
            disposition=classification[0],
            destination_paths=classification[1],
            owner_required_paths=classification[2],
            rationale=classification[3],
        )
        for source_path, value in leaves
        for classification in (_classify_migration_leaf(source_path),)
    )
    paths = tuple(item.source_path for item in items if item.source_path is not None)
    duplicates = tuple(sorted(path for path in set(paths) if paths.count(path) > 1))
    unclassified = tuple(
        item.source_path
        for item in items
        if item.source_path is not None
        and item.disposition is MigrationDisposition.OWNER_REQUIRED
        and item.owner_required_paths == (item.source_path,)
    )
    return ScenarioMigrationInventory(
        source_schema_version="1.3.0",
        source_raw_sha256=hashlib.sha256(raw_bytes).hexdigest(),
        source_normalized_sha256=hashlib.sha256(
            canonical_json_bytes(payload)
        ).hexdigest(),
        items=items,
        unclassified_source_paths=unclassified,
        multiply_classified_source_paths=duplicates,
    )


class ScenarioMigrationRegistration(StrictPaper1Model):
    schema_version: Literal["1.0.0"]
    source_raw_sha256: Literal[
        "46286eb006fbfbaf13281dfe52d4c63c9dc00ff7b3ef0a8ee704146908f759cb"
    ]
    target_registry: SyntheticScenarioRegistry
    accepted_retired_source_paths: tuple[str, ...]
    evidence_label: Literal[EvidenceLabel.SYNTHETIC_ONLY]

    @field_validator("accepted_retired_source_paths", mode="before")
    @classmethod
    def require_exact_path_tuple(cls, value: object) -> object:
        if type(value) not in (list, tuple):
            raise ValueError("accepted retired paths must be a list or tuple")
        paths = tuple(value)
        if any(
            type(path) is not str or not path or path != path.strip()
            for path in paths
        ) or len(set(paths)) != len(paths):
            raise ValueError("accepted retired paths must be unique strings")
        return paths


def _mapping_value(mapping: Mapping[object, object], key: str) -> object:
    if key in mapping:
        return mapping[key]
    for candidate, value in mapping.items():
        if getattr(candidate, "value", None) == key:
            return value
    raise KeyError(key)


def _resolve_registry_path(
    registry: SyntheticScenarioRegistry, path: str
) -> object:
    if path.startswith("anchor."):
        current: object = registry.anchor
        remaining = path.removeprefix("anchor.")
    elif path.startswith("scenarios[scenario_id="):
        scenario_id, separator, remaining = path.removeprefix(
            "scenarios[scenario_id="
        ).partition("].")
        if not separator:
            raise KeyError(path)
        matches = tuple(
            scenario
            for scenario in registry.all_scenarios
            if scenario.scenario_id.value == scenario_id
        )
        if len(matches) != 1:
            raise KeyError(path)
        current = matches[0]
    else:
        raise KeyError(path)
    for component in remaining.split("."):
        index: int | None = None
        if component.endswith("]") and "[" in component:
            component, raw_index = component[:-1].rsplit("[", 1)
            index = int(raw_index)
        if isinstance(current, Mapping):
            current = _mapping_value(current, component)
        else:
            current = getattr(current, component)
        if index is not None:
            if isinstance(current, (set, frozenset)):
                ordered = tuple(
                    sorted(current, key=lambda item: str(getattr(item, "value", item)))
                )
            else:
                ordered = tuple(current)  # type: ignore[arg-type]
            current = ordered[index]
    return current


def _migration_comparable_value(value: object) -> object:
    if isinstance(value, (RegisteredQuantity, RegisteredCount)):
        return value.value
    if isinstance(value, StrEnum):
        return value.value
    return value


def _revalidate_scenario_registry(
    registry: SyntheticScenarioRegistry,
) -> SyntheticScenarioRegistry:
    if type(registry) is not SyntheticScenarioRegistry:
        fail(
            "SCENARIO_MIGRATION_INVALID",
            "target registry must be exact",
            "target_registry",
        )
    return SyntheticScenarioRegistry(
        schema_version=registry.schema_version,
        water_recipe_registry_sha256=registry.water_recipe_registry_sha256,
        anchor=SyntheticScenarioConfig.model_validate(registry.anchor),
        scenarios=tuple(
            SyntheticScenarioConfig.model_validate(scenario)
            for scenario in registry.scenarios
        ),
    )


def migrate_v13_scenario_document(
    source: ScenarioMigrationInventory,
    registration: ScenarioMigrationRegistration,
) -> SyntheticScenarioRegistry:
    """Apply one explicit, complete migration registration and detach it."""

    if type(source) is not ScenarioMigrationInventory:
        fail(
            "SCENARIO_MIGRATION_INVALID",
            "source inventory must be exact",
            "source",
        )
    if type(registration) is not ScenarioMigrationRegistration:
        fail(
            "SCENARIO_MIGRATION_INVALID",
            "migration registration must be exact",
            "registration",
        )
    checked_source = ScenarioMigrationInventory.model_validate(
        source.model_dump(mode="python")
    )
    checked_registration = ScenarioMigrationRegistration(
        schema_version=registration.schema_version,
        source_raw_sha256=registration.source_raw_sha256,
        target_registry=_revalidate_scenario_registry(registration.target_registry),
        accepted_retired_source_paths=tuple(
            registration.accepted_retired_source_paths
        ),
        evidence_label=registration.evidence_label,
    )
    if (
        checked_source.source_raw_sha256
        != checked_registration.source_raw_sha256
        or checked_source.unclassified_source_paths
        or checked_source.multiply_classified_source_paths
    ):
        fail(
            "SCENARIO_MIGRATION_INVALID",
            "source inventory is incomplete or does not match registration",
            "source",
        )
    expected_retired = tuple(
        item.source_path
        for item in checked_source.items
        if item.disposition is MigrationDisposition.RETIRED
        and item.source_path is not None
    )
    if checked_registration.accepted_retired_source_paths != expected_retired:
        fail(
            "SCENARIO_MIGRATION_INVALID",
            "accepted retirement list must equal the inventory exactly",
            "accepted_retired_source_paths",
        )
    registry = checked_registration.target_registry
    for item in checked_source.items:
        if item.disposition is MigrationDisposition.RETIRED:
            continue
        destinations = (*item.destination_paths, *item.owner_required_paths)
        for destination in destinations:
            try:
                received = _resolve_registry_path(registry, destination)
            except (AttributeError, KeyError) as error:
                fail(
                    "SCENARIO_MIGRATION_INVALID",
                    "migration target omits a classified destination",
                    destination,
                    {"source_path": item.source_path},
                )
            if (
                destination in item.destination_paths
                and item.source_canonical_json is not None
                and not destination.endswith(".schema_version")
                and not (
                    item.source_path is not None
                    and ".tracked_entities[" in item.source_path
                    and item.source_canonical_json
                    in {
                        canonical_json_bytes(
                            _migration_comparable_value(member)
                        ).decode("utf-8")
                        for member in (
                            getattr(
                                _resolve_registry_path(
                                    registry,
                                    destination.split("[")[0],
                                ),
                                "__iter__",
                            )()
                        )
                    }
                )
                and canonical_json_bytes(
                    _migration_comparable_value(received)
                ).decode("utf-8")
                != item.source_canonical_json
            ):
                fail(
                    "SCENARIO_MIGRATION_INVALID",
                    "migration target changed a preserved legacy value",
                    destination,
                    {"source_path": item.source_path},
                )
    return _revalidate_scenario_registry(registry)


def _load_yaml_mapping(
    path: str | Path,
    *,
    scenario_boundary: bool = False,
) -> dict[str, object]:
    try:
        payload = _strict_yaml_load(Path(path).read_text(encoding="utf-8"))
    except YamlDuplicateKeyError as error:
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
    except YamlAliasCycleError as error:
        if scenario_boundary:
            fail(
                "SYNTHETIC_SCENARIO_INVALID",
                "synthetic scenario YAML contains a cyclic alias graph",
                "yaml",
                {
                    "cause_type": type(error).__name__,
                    "line": error.line,
                    "column": error.column,
                },
            )
        raise ValueError("cyclic YAML alias graph") from error
    except (
        OSError,
        TypeError,
        ValueError,
        UnicodeError,
        yaml.YAMLError,
        RecursionError,
        MemoryError,
    ) as error:
        if scenario_boundary:
            _scenario_invalid(
                "synthetic scenario YAML could not be safely loaded",
                "yaml",
                cause=error,
            )
        raise ValueError(f"could not safely load YAML mapping from {path}") from error
    if not isinstance(payload, dict):
        if scenario_boundary:
            _scenario_invalid("synthetic scenario YAML must be a mapping", "yaml")
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


def load_synthetic_scenarios(path: str | Path) -> SyntheticScenarioRegistry:
    """Load the active v1.4 registry; legacy documents require migration."""
    raw = _load_yaml_mapping(path, scenario_boundary=True)
    if "schema_version" not in raw:
        fail(
            "SCENARIO_SCHEMA_MIGRATION_REQUIRED",
            "active generation accepts only the v1.4 scenario registry",
            "schema_version",
            {"received": "1.3.0"},
        )
    if raw.get("schema_version") != "1.4.0":
        fail(
            "SCENARIO_SCHEMA_MIGRATION_REQUIRED",
            "active generation accepts only the v1.4 scenario registry",
            "schema_version",
            {"received": raw.get("schema_version")},
        )
    try:
        return SyntheticScenarioRegistry.model_validate(raw)
    except Exception as error:
        _scenario_invalid("v1.4 scenario registry is invalid", "root", cause=error)


def _load_legacy_synthetic_scenarios(
    path: str | Path,
) -> tuple[LegacySyntheticScenarioConfig, ...]:
    """Decode v1.3 only for explicit migration inspection."""
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
        LegacySyntheticScenarioConfig.model_validate(scenario)
        for scenario in scenarios
    )
