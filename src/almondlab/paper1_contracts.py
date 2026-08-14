"""Frozen Paper 1 registry, allocation, and synthetic-input contracts."""

import hashlib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, fields, is_dataclass
from enum import Enum, StrEnum
from importlib import import_module
from math import fsum, isclose, isfinite, log
from pathlib import Path
from types import MappingProxyType
from typing import TYPE_CHECKING, Annotated, ClassVar, Literal

import yaml
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    SkipValidation,
    ValidationInfo,
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
from almondlab.chemistry import charge_balance_error
from almondlab.contracts import CompartmentKind, ConservedEntity, EvidenceLabel
from almondlab.domains import DomainRequest, DomainValidationResult, validate_domain
from almondlab.errors import AlmondLabError, fail, finite_float
from almondlab.evidence_policy import compose_evidence_labels
from almondlab.hydraulics import HydraulicDomain
from almondlab.mass_balance import CompartmentState, NetworkState
from almondlab.provenance import canonical_json_bytes
from almondlab.schemas import ModelDomain, WaterChemistry

if TYPE_CHECKING:
    from almondlab.design import (
        BaselineRoster,
        ConfirmationDesignConfig,
        PositionMap,
        RandomizationManifest,
    )


_MAPPING_PROXY_TYPE = type(MappingProxyType({}))
MAX_INTEROPERABLE_JSON_INTEGER = 2**53 - 1
TASK4_NUMPY_VERSION = "2.5.2"
TASK4_SCIPY_VERSION = "1.18.0"


def require_task4_scientific_runtime() -> None:
    """Require the exact prospective Task 4 numerical runtime."""

    for distribution, expected in (
        ("numpy", TASK4_NUMPY_VERSION),
        ("scipy", TASK4_SCIPY_VERSION),
    ):
        try:
            module = import_module(distribution)
            received = getattr(module, "__version__", None)
        except Exception as error:
            fail(
                "TASK4_RUNTIME_VERSION_MISMATCH",
                f"Task 4 requires {distribution} {expected}",
                f"{distribution}_version",
                {
                    "expected": expected,
                    "received": "unavailable",
                    "cause_type": type(error).__name__,
                },
            )
        if type(received) is not str or received != expected:
            fail(
                "TASK4_RUNTIME_VERSION_MISMATCH",
                f"Task 4 requires {distribution} {expected}",
                f"{distribution}_version",
                {
                    "expected": expected,
                    "received": (
                        received if type(received) is str else "invalid"
                    ),
                },
            )


class StrictPaper1Model(BaseModel):
    """Immutable Paper 1 boundary model that rejects unregistered fields."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        allow_inf_nan=False,
        revalidate_instances="always",
    )

    @model_validator(mode="before")
    @classmethod
    def reject_model_subclasses(cls, value: object) -> object:
        if isinstance(value, cls) and type(value) is not cls:
            raise ValueError(f"{cls.__name__} requires an exact model instance")
        if isinstance(value, Mapping):
            if type(value) not in (dict, _MAPPING_PROXY_TYPE):
                raise ValueError(f"{cls.__name__} requires a primitive mapping")
            if any(type(key) is not str for key in value):
                raise ValueError(f"{cls.__name__} requires primitive string keys")
        return value


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
REGISTERED_ENDPOINT_UNITS = MappingProxyType(
    {
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
)
REGISTERED_ION_ENDPOINT_IDS = REGISTERED_ENDPOINT_IDS[1:6]
REGISTERED_H3_ENDPOINT_IDS = REGISTERED_ENDPOINT_IDS[6:]
REGISTERED_CANDIDATE_IDS = tuple(f"C{number}" for number in range(1, 7))
REGISTERED_H3_ERROR_AUTHORITIES = MappingProxyType(
    {
        "C1": (
            "root_surface_outward_na_flux_per_root_dry_mass",
            "log_ratio",
            "umol Na g_root_dry_mass^-1 h^-1",
            "log-ratio",
        ),
        "C2": (
            "root_h2o2_concentration_time_auc",
            "log_ratio",
            "umol H2O2 g_root_fresh_mass^-1 h",
            "log-ratio",
        ),
        "C3": (
            "root_mannitol_concentration_above_empty_vector",
            "difference",
            "nmol g_root_fresh_mass^-1",
            "nmol g_root_fresh_mass^-1",
        ),
        "C4": (
            "root_surface_outward_na_flux_per_root_dry_mass",
            "log_ratio",
            "umol Na g_root_dry_mass^-1 h^-1",
            "log-ratio",
        ),
        "C5": (
            "xylem_sap_na_concentration_time_auc",
            "log_ratio",
            "mmol Na L^-1 h",
            "log-ratio",
        ),
        "C6": (
            "root_surface_outward_na_flux_per_root_dry_mass",
            "log_ratio",
            "umol Na g_root_dry_mass^-1 h^-1",
            "log-ratio",
        ),
    }
)


def _require_quantity_unit(
    value: RegisteredQuantity, expected: str, field_path: str
) -> None:
    if value.unit != expected:
        raise ValueError(f"{field_path} requires unit {expected!r}")


def _require_nonnegative_quantity(
    value: RegisteredQuantity, field_path: str
) -> None:
    if value.value < 0.0:
        raise ValueError(f"{field_path} must be nonnegative")


def _require_positive_quantity(value: RegisteredQuantity, field_path: str) -> None:
    if value.value <= 0.0:
        raise ValueError(f"{field_path} must be positive")


def _require_strictly_increasing_quantities(
    values: tuple[RegisteredQuantity, ...],
    *,
    field_path: str,
    unit: str,
) -> tuple[float, ...]:
    if not values:
        raise ValueError(f"{field_path} must be nonempty")
    for item in values:
        _require_quantity_unit(item, unit, field_path)
    plain = tuple(item.value for item in values)
    if any(right <= left for left, right in zip(plain, plain[1:])):
        raise ValueError(f"{field_path} must be strictly increasing")
    return plain


def _freeze_exact_map(
    value: Mapping[str, object], expected: tuple[str, ...], field_path: str
) -> Mapping[str, object]:
    _require_primitive_string_mapping(value, field_path)
    if tuple(value) != expected:
        raise ValueError(f"{field_path} must contain exact registered keys in order")
    return MappingProxyType(dict(value))


def _require_primitive_string_mapping(
    value: object, field_path: str
) -> Mapping[str, object]:
    if type(value) not in (dict, _MAPPING_PROXY_TYPE):
        raise ValueError(f"{field_path} must be a primitive mapping")
    if any(type(key) is not str for key in value):
        raise ValueError(f"{field_path} keys must be primitive strings")
    return value


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

    @model_validator(mode="after")
    def require_nonnegative_variances(self) -> "HierarchyGeneratorConfig":
        for name in self._quantity_units:
            _require_nonnegative_quantity(getattr(self, name), name)
        return self


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

    @model_validator(mode="after")
    def require_stationary_process(self) -> "ClimateGeneratorConfig":
        for name in (
            "temperature_ar1_phi",
            "apar_ar1_phi",
            "matric_potential_ar1_phi",
        ):
            if not -1.0 < getattr(self, name).value < 1.0:
                raise ValueError(f"{name} must be strictly between -1 and 1")
        for name in (
            "temperature_innovation_sd_k",
            "apar_log_innovation_sd",
            "matric_potential_innovation_sd_mpa",
            "potential_transpiration_log_innovation_sd",
        ):
            _require_nonnegative_quantity(getattr(self, name), name)
        if self.climate_initialization_burnin_steps.value <= 0:
            raise ValueError("climate burn-in count must be positive")
        return self


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

    @model_validator(mode="after")
    def require_measurement_scales(self) -> "ChemistryGeneratorConfig":
        for name in self._quantity_units:
            value = getattr(self, name)
            if name == "charge_balance_tolerance_percent":
                _require_positive_quantity(value, name)
            else:
                _require_nonnegative_quantity(value, name)
        return self


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
        for name in (
            "reservoir_initial_volume_l",
            "water_batch_volume_l",
            "irrigation_volume_l_per_plant_day",
            "sampling_volume_l_per_sample",
            "reservoir_min_volume_l",
            "reservoir_max_volume_l",
        ):
            _require_positive_quantity(getattr(self, name), name)
        _require_nonnegative_quantity(self.purge_volume_l_day, "purge_volume_l_day")
        fraction = self.drainage_return_fraction.value
        if not 0.0 <= fraction <= 1.0:
            raise ValueError("drainage_return_fraction must be in [0, 1]")
        minimum = self.reservoir_min_volume_l.value
        initial = self.reservoir_initial_volume_l.value
        maximum = self.reservoir_max_volume_l.value
        if not minimum <= initial <= maximum or minimum >= maximum:
            raise ValueError(
                "reservoir bounds must be ordered and contain the initial volume"
            )
        values = _require_strictly_increasing_quantities(
            self.operator_event_times_days,
            field_path="operator_event_times_days",
            unit="day",
        )
        if values != tuple(float(index) + 0.25 for index in range(84)):
            raise ValueError("operator event schedule must equal the registration")
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

    @model_validator(mode="after")
    def require_positive_links(self) -> "H3MeasurementLinksConfig":
        fraction = self.root_dry_matter_fraction.value
        if not 0.0 < fraction <= 1.0:
            raise ValueError("root dry matter fraction must be in (0, 1]")
        _require_positive_quantity(
            self.h2o2_umol_g_root_fresh_mass_inv_per_ros_dimensionless,
            "h2o2 measurement link",
        )
        return self


class H3ObservationErrorRecord(StrictPaper1Model):
    """One candidate-bound H3 measurement-error registration."""

    candidate_id: str
    endpoint_id: str
    analysis_scale: Literal["log_ratio", "difference"]
    endpoint_unit: str
    error_sd: RegisteredQuantity

    @model_validator(mode="after")
    def require_candidate_authority(self) -> "H3ObservationErrorRecord":
        if self.candidate_id not in REGISTERED_H3_ERROR_AUTHORITIES:
            raise ValueError("H3 error record requires candidate C1 through C6")
        expected = REGISTERED_H3_ERROR_AUTHORITIES[self.candidate_id]
        observed = (
            self.endpoint_id,
            self.analysis_scale,
            self.endpoint_unit,
            self.error_sd.unit,
        )
        if observed != expected:
            raise ValueError(
                "H3 error record must repeat the frozen candidate rule and scale"
            )
        if self.error_sd.value < 0.0:
            raise ValueError("H3 observation error SD must be nonnegative")
        return self


class ObservationGeneratorConfig(_RegisteredGeneratorSection):
    canopy_observation_error_sd: RegisteredQuantity
    ion_observation_error_sd: RegisteredQuantity
    h3_observation_error_by_endpoint: Mapping[str, H3ObservationErrorRecord]
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

    @field_validator(
        "h3_observation_error_by_endpoint",
        "h3_observation_times_days_by_endpoint",
        mode="before",
    )
    @classmethod
    def require_primitive_endpoint_maps(cls, value: object) -> object:
        return _require_primitive_string_mapping(value, "observation endpoint map")

    @model_validator(mode="after")
    def require_observation_maps(self) -> "ObservationGeneratorConfig":
        for name in (
            "canopy_observation_error_sd",
            "ion_observation_error_sd",
            "canopy_heteroscedastic_log_slope",
            "ion_heteroscedastic_log_slope",
        ):
            _require_nonnegative_quantity(getattr(self, name), name)
        errors = _freeze_exact_map(
            self.h3_observation_error_by_endpoint,
            REGISTERED_CANDIDATE_IDS,
            "h3_observation_error_by_endpoint",
        )
        for candidate_id, item in errors.items():
            if item.candidate_id != candidate_id:
                raise ValueError(
                    "H3 error map key must equal the repeated candidate ID"
                )
        schedules = _freeze_exact_map(
            self.h3_observation_times_days_by_endpoint,
            REGISTERED_H3_ENDPOINT_IDS,
            "h3_observation_times_days_by_endpoint",
        )
        for endpoint_id, schedule in schedules.items():
            if type(schedule) is not tuple or not schedule:
                raise ValueError(f"H3 schedule {endpoint_id} must be a nonempty tuple")
            observed = _require_strictly_increasing_quantities(
                schedule, field_path=endpoint_id, unit="day"
            )
            if observed != (84.0,):
                raise ValueError("H3 endpoint schedules must be terminal day 84")
        canopy_times = _require_strictly_increasing_quantities(
            self.canopy_observation_times_days,
            field_path="canopy_observation_times_days",
            unit="day",
        )
        if canopy_times != (
            0.0,
            3.0,
            7.0,
            14.0,
            21.0,
            28.0,
            35.0,
            42.0,
            49.0,
            56.0,
            63.0,
            70.0,
            77.0,
            84.0,
        ):
            raise ValueError("canopy observation schedule must equal registration")
        ion_times = _require_strictly_increasing_quantities(
            self.ion_observation_times_days,
            field_path="ion_observation_times_days",
            unit="day",
        )
        if ion_times != (0.0, 14.0, 28.0, 42.0, 56.0, 70.0, 84.0):
            raise ValueError("ion observation schedule must equal registration")
        object.__setattr__(self, "h3_observation_error_by_endpoint", errors)
        object.__setattr__(self, "h3_observation_times_days_by_endpoint", schedules)
        return self


class CensoringGeneratorConfig(StrictPaper1Model):
    lod_by_endpoint: Mapping[str, RegisteredQuantity | None]
    loq_by_endpoint: Mapping[str, RegisteredQuantity | None]
    lod_log_sd_by_endpoint: Mapping[str, RegisteredQuantity | None]
    loq_log_sd_by_endpoint: Mapping[str, RegisteredQuantity | None]

    @field_validator(
        "lod_by_endpoint",
        "loq_by_endpoint",
        "lod_log_sd_by_endpoint",
        "loq_log_sd_by_endpoint",
        mode="before",
    )
    @classmethod
    def require_primitive_endpoint_maps(cls, value: object) -> object:
        return _require_primitive_string_mapping(value, "censor endpoint map")

    @model_validator(mode="after")
    def require_endpoint_complete_maps(self) -> "CensoringGeneratorConfig":
        frozen_maps: dict[
            str, Mapping[str, RegisteredQuantity | None]
        ] = {}
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
                        _require_nonnegative_quantity(item, endpoint_id)
            else:
                for endpoint_id, item in frozen.items():
                    if item is not None:
                        _require_quantity_unit(
                            item, REGISTERED_ENDPOINT_UNITS[endpoint_id], endpoint_id
                        )
                        _require_nonnegative_quantity(item, endpoint_id)
            frozen_maps[name] = frozen
            object.__setattr__(self, name, frozen)
        for endpoint_id in REGISTERED_ENDPOINT_IDS:
            values = tuple(
                frozen_maps[name][endpoint_id]
                for name in (
                    "lod_by_endpoint",
                    "loq_by_endpoint",
                    "lod_log_sd_by_endpoint",
                    "loq_log_sd_by_endpoint",
                )
            )
            if any(item is None for item in values) and not all(
                item is None for item in values
            ):
                raise ValueError(
                    f"censor maps require aligned nullability for {endpoint_id}"
                )
            lod, loq, lod_log_sd, loq_log_sd = values
            if lod is not None and loq is not None and loq.value < lod.value:
                raise ValueError(f"LOQ must be greater than or equal to LOD for {endpoint_id}")
            if (
                lod_log_sd is not None
                and loq_log_sd is not None
                and lod_log_sd.value != loq_log_sd.value
            ):
                raise ValueError(
                    f"LOD and LOQ log SDs must match for {endpoint_id}"
                )
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

    @field_validator(
        "ion_drift_per_day_by_endpoint",
        "h3_drift_per_day_by_endpoint",
        "post_calibration_residual_sd_by_endpoint",
        mode="before",
    )
    @classmethod
    def require_primitive_endpoint_maps(cls, value: object) -> object:
        return _require_primitive_string_mapping(value, "drift endpoint map")

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
        for endpoint_id, item in self.ion_drift_per_day_by_endpoint.items():
            _require_quantity_unit(item, "log-ratio day^-1", endpoint_id)
        for endpoint_id, item in self.h3_drift_per_day_by_endpoint.items():
            expected = (
                "nmol g_root_fresh_mass^-1 day^-1"
                if endpoint_id
                == "root_mannitol_concentration_above_empty_vector"
                else "log-ratio day^-1"
            )
            _require_quantity_unit(item, expected, endpoint_id)
        for endpoint_id, item in self.post_calibration_residual_sd_by_endpoint.items():
            expected = (
                "nmol g_root_fresh_mass^-1"
                if endpoint_id
                == "root_mannitol_concentration_above_empty_vector"
                else "log-ratio"
            )
            _require_quantity_unit(item, expected, endpoint_id)
            _require_nonnegative_quantity(item, endpoint_id)
        _require_positive_quantity(
            self.calibration_interval_days, "calibration_interval_days"
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

    @model_validator(mode="after")
    def require_nonnegative_threshold_variation(self) -> "DeathGeneratorConfig":
        for name in self._quantity_units:
            _require_nonnegative_quantity(getattr(self, name), name)
        return self


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

    @field_validator(
        "observable_stress_proxy_center_by_field",
        "observable_stress_proxy_scale_by_field",
        mode="before",
    )
    @classmethod
    def require_primitive_proxy_maps(cls, value: object) -> object:
        return _require_primitive_string_mapping(value, "stress-proxy map")

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
        expected_units = MappingProxyType(
            {
                "challenge_water_indicator": "dimensionless",
                "scheduled_time_days": "day",
                "prior_observed_canopy_log_ratio": "log-ratio",
            }
        )
        for field_id in expected:
            for map_name in (
                "observable_stress_proxy_center_by_field",
                "observable_stress_proxy_scale_by_field",
            ):
                _require_quantity_unit(
                    getattr(self, map_name)[field_id],
                    expected_units[field_id],
                    f"{map_name}.{field_id}",
                )
            _require_positive_quantity(
                self.observable_stress_proxy_scale_by_field[field_id],
                f"observable_stress_proxy_scale_by_field.{field_id}",
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

    @model_validator(mode="after")
    def require_solver_domain(self) -> "CalibrationGeneratorConfig":
        for name in self._quantity_units:
            _require_positive_quantity(getattr(self, name), name)
        if self.max_iterations.value <= 0:
            raise ValueError("max_iterations must be positive")
        fit = self.fit_panel_size.value
        holdout = self.holdout_panel_size.value
        if fit != holdout or fit not in {32, 64, 128}:
            raise ValueError("fit/holdout panel counts must be equal and registered")
        return self


class GeneratorDesignConfig(_RegisteredGeneratorSection):
    duration_days: RegisteredQuantity
    confirmation_plants_per_group_reservoir: RegisteredCount

    _quantity_units = MappingProxyType({"duration_days": "day"})
    _count_fields = frozenset({"confirmation_plants_per_group_reservoir"})

    @model_validator(mode="after")
    def require_registered_design(self) -> "GeneratorDesignConfig":
        if self.duration_days.value != 84.0:
            raise ValueError("generator duration must be exactly 84 days")
        if self.confirmation_plants_per_group_reservoir.value not in {5, 6}:
            raise ValueError("confirmation cell size must be exactly 5 or 6")
        return self


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

    @model_validator(mode="after")
    def require_safe_composed_arithmetic(self) -> "SyntheticGeneratorConfig":
        loop = self.water_loop
        try:
            daily_makeup = (
                loop.irrigation_volume_l_per_plant_day.value
                * 45.0
                * (1.0 - loop.drainage_return_fraction.value)
                + loop.purge_volume_l_day.value
            )
            demand = fsum(
                (
                    loop.reservoir_initial_volume_l.value,
                    84.0 * daily_makeup,
                    6.0 * loop.sampling_volume_l_per_sample.value,
                )
            )
        except (OverflowError, ValueError):
            demand = float("inf")
        if not isfinite(daily_makeup) or not isfinite(demand):
            raise ValueError("water-loop arithmetic must remain finite")
        duration = self.design.duration_days.value
        drift_rates = (
            self.drift.canopy_drift_per_day,
            *self.drift.ion_drift_per_day_by_endpoint.values(),
            *self.drift.h3_drift_per_day_by_endpoint.values(),
        )
        if any(not isfinite(item.value * duration) for item in drift_rates):
            raise ValueError("drift arithmetic must remain finite over the design")
        return self

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


_REGISTERED_CHEMISTRY_NUMBER_FIELDS = (
    "ec_ds_m",
    "temperature_k",
    "measured_osmolality_osmol_kg",
    "ph",
    "alkalinity_mmol_c_l",
    "na_mmol_l",
    "cl_mmol_l",
    "ca_mmol_l",
    "mg_mmol_l",
    "k_mmol_l",
    "total_b_mmol_l",
    "sulfate_mmol_l",
    "bicarbonate_mmol_l",
    "nitrate_mmol_l",
    "phosphate_mmol_l",
)
_REGISTERED_ANALYTE_IDS = (
    "na",
    "cl",
    "ca",
    "mg",
    "k",
    "total_b",
    "sulfate",
    "bicarbonate",
    "nitrate",
    "phosphate",
)
_NONSTOICHIOMETRIC_TARGET_UNITS = MappingProxyType(
    {
        "ec_ds_m": "dS m^-1",
        "measured_osmolality_osmol_kg": "osmol kg^-1",
        "ph": "pH",
        "temperature_k": "K",
        "alkalinity_mmol_c_l": "mmol_c L^-1",
    }
)
_LEGACY_DESIGN_RAW_SHA256 = (
    "d402889dac8b4580b0d2f01e65b6caf750b8af65e0550fe6283c630109e465e0"
)
_LEGACY_ANCHOR_SHA256S = MappingProxyType(
    {
        REGISTERED_WATER_IDS[0]: (
            "a804553ff5d1e0c9938a10d14430d593cde2c5cbddd0a00c3e5460f884c61e1f"
        ),
        REGISTERED_WATER_IDS[1]: (
            "bef482128d45eff8a42593b9a19534f847858a265814edf627b8421d3e3b08a4"
        ),
    }
)
_LEGACY_SIGNED_CHARGE_ERRORS = MappingProxyType(
    {
        REGISTERED_WATER_IDS[0]: 23.167155425219942,
        REGISTERED_WATER_IDS[1]: 3.302286198137171,
    }
)
_LEGACY_CHEMISTRIES = MappingProxyType(
    {
        REGISTERED_WATER_IDS[0]: {
            "ec_kind": "ECw",
            "ec_ds_m": 0.7,
            "temperature_k": 298.15,
            "measured_osmolality_osmol_kg": 0.02,
            "ph": 7.2,
            "alkalinity_mmol_c_l": 2.1,
            "na_mmol_l": 5.0,
            "cl_mmol_l": 6.0,
            "ca_mmol_l": 4.0,
            "mg_mmol_l": 3.0,
            "k_mmol_l": 2.0,
            "total_b_mmol_l": 0.1,
            "sulfate_mmol_l": 2.0,
            "bicarbonate_mmol_l": 2.1,
            "nitrate_mmol_l": 1.0,
            "phosphate_mmol_l": 0.5,
        },
        REGISTERED_WATER_IDS[1]: {
            "ec_kind": "ECw",
            "ec_ds_m": 6.0,
            "temperature_k": 298.15,
            "measured_osmolality_osmol_kg": 0.15,
            "ph": 7.2,
            "alkalinity_mmol_c_l": 2.1,
            "na_mmol_l": 45.0,
            "cl_mmol_l": 50.0,
            "ca_mmol_l": 4.0,
            "mg_mmol_l": 3.0,
            "k_mmol_l": 2.0,
            "total_b_mmol_l": 0.1,
            "sulfate_mmol_l": 2.0,
            "bicarbonate_mmol_l": 2.1,
            "nitrate_mmol_l": 1.0,
            "phosphate_mmol_l": 0.5,
        },
    }
)
_ACTIVE_CHEMISTRIES = MappingProxyType(
    {
        REGISTERED_WATER_IDS[0]: {
            "ec_kind": "ECw",
            "ec_ds_m": 1.5,
            "temperature_k": 298.15,
            "measured_osmolality_osmol_kg": 0.02,
            "ph": 6.5,
            "alkalinity_mmol_c_l": 1.0,
            "na_mmol_l": 4.0,
            "cl_mmol_l": 4.0,
            "ca_mmol_l": 2.0,
            "mg_mmol_l": 1.0,
            "k_mmol_l": 2.0,
            "total_b_mmol_l": 0.05,
            "sulfate_mmol_l": 1.0,
            "bicarbonate_mmol_l": 0.75,
            "nitrate_mmol_l": 5.0,
            "phosphate_mmol_l": 0.25,
        },
        REGISTERED_WATER_IDS[1]: {
            "ec_kind": "ECw",
            "ec_ds_m": 6.0,
            "temperature_k": 298.15,
            "measured_osmolality_osmol_kg": 0.1,
            "ph": 6.5,
            "alkalinity_mmol_c_l": 1.0,
            "na_mmol_l": 44.0,
            "cl_mmol_l": 44.0,
            "ca_mmol_l": 2.0,
            "mg_mmol_l": 1.0,
            "k_mmol_l": 2.0,
            "total_b_mmol_l": 0.05,
            "sulfate_mmol_l": 1.0,
            "bicarbonate_mmol_l": 0.75,
            "nitrate_mmol_l": 5.0,
            "phosphate_mmol_l": 0.25,
        },
    }
)
_SYNTHETIC_BLANK_CHEMISTRY = MappingProxyType(
    {
        "ec_kind": "ECw",
        "ec_ds_m": 0.0,
        "temperature_k": 298.15,
        "measured_osmolality_osmol_kg": 0.0,
        "ph": 7.0,
        "alkalinity_mmol_c_l": 0.0,
        "na_mmol_l": 0.0,
        "cl_mmol_l": 0.0,
        "ca_mmol_l": 0.0,
        "mg_mmol_l": 0.0,
        "k_mmol_l": 0.0,
        "total_b_mmol_l": 0.0,
        "sulfate_mmol_l": 0.0,
        "bicarbonate_mmol_l": 0.0,
        "nitrate_mmol_l": 0.0,
        "phosphate_mmol_l": 0.0,
    }
)
_ACTIVE_RECIPE_IDS = MappingProxyType(
    {
        REGISTERED_WATER_IDS[0]: "paper1_base_nutrient_control_v1",
        REGISTERED_WATER_IDS[1]: "paper1_base_plus_nacl40_challenge_v1",
    }
)
_CONTROL_AMENDMENTS = (
    (
        "sodium_chloride",
        "NaCl",
        "anhydrous",
        4.0,
        58.44,
        233.76,
        (("na", 4.0), ("cl", 4.0)),
        0.0,
    ),
    (
        "calcium_nitrate_tetrahydrate",
        "Ca(NO3)2·4H2O",
        "tetrahydrate",
        2.0,
        236.15,
        472.3,
        (("ca", 2.0), ("nitrate", 4.0)),
        0.0,
    ),
    (
        "magnesium_sulfate_heptahydrate",
        "MgSO4·7H2O",
        "heptahydrate",
        1.0,
        246.48,
        246.48,
        (("mg", 1.0), ("sulfate", 1.0)),
        0.0,
    ),
    (
        "potassium_nitrate",
        "KNO3",
        "anhydrous",
        1.0,
        101.103,
        101.103,
        (("k", 1.0), ("nitrate", 1.0)),
        0.0,
    ),
    (
        "potassium_bicarbonate",
        "KHCO3",
        "anhydrous",
        0.75,
        100.115,
        75.08625,
        (("k", 0.75), ("bicarbonate", 0.75)),
        0.75,
    ),
    (
        "monobasic_potassium_phosphate",
        "KH2PO4",
        "anhydrous",
        0.25,
        136.086,
        34.0215,
        (("k", 0.25), ("phosphate", 0.25)),
        0.25,
    ),
    (
        "boric_acid",
        "H3BO3",
        "anhydrous",
        0.05,
        61.84,
        3.092,
        (("total_b", 0.05),),
        0.0,
    ),
)
_CHALLENGE_AMENDMENTS = (
    (
        "sodium_chloride_challenge_increment",
        "NaCl",
        "anhydrous",
        40.0,
        58.44,
        2337.6,
        (("na", 40.0), ("cl", 40.0)),
        0.0,
    ),
)


def _require_registered_text(value: object, field_path: str) -> str:
    if (
        type(value) is not str
        or not value
        or value != value.strip()
        or any(ord(character) < 32 for character in value)
    ):
        raise ValueError(f"{field_path} must be a trim-free nonempty string")
    return value


def _require_lowercase_sha256(value: object, field_path: str) -> str:
    text = _require_registered_text(value, field_path)
    if len(text) != 64 or any(character not in "0123456789abcdef" for character in text):
        raise ValueError(f"{field_path} must be a lowercase SHA-256 digest")
    return text


class RegisteredRecipeWaterChemistry(WaterChemistry):
    """Water chemistry whose registered numeric leaves must be Python floats."""

    @field_validator(*_REGISTERED_CHEMISTRY_NUMBER_FIELDS, mode="before")
    @classmethod
    def require_registered_float(cls, value: object) -> object:
        if type(value) is not float:
            raise ValueError("registered chemistry values must be primitive floats")
        return value


class HistoricalWaterRecipeAnchor(StrictPaper1Model):
    water_id: str
    source_field_path: str
    source_design_raw_sha256: str
    anchor_canonical_sha256: str
    signed_charge_error_percent: float
    status: Literal["superseded_unbalanced_hypothesis_anchor"]
    evidence_label: Literal[EvidenceLabel.HYPOTHESIS_PRIOR]
    chemistry: RegisteredRecipeWaterChemistry

    @field_validator("water_id", "source_field_path", mode="before")
    @classmethod
    def require_text(cls, value: object, info: object) -> object:
        return _require_registered_text(value, getattr(info, "field_name", "text"))

    @field_validator(
        "source_design_raw_sha256", "anchor_canonical_sha256", mode="before"
    )
    @classmethod
    def require_digest(cls, value: object, info: object) -> object:
        return _require_lowercase_sha256(value, getattr(info, "field_name", "sha256"))

    @field_validator("signed_charge_error_percent", mode="before")
    @classmethod
    def require_exact_error_float(cls, value: object) -> object:
        if type(value) is not float or not isfinite(value):
            raise ValueError("signed charge error must be a finite primitive float")
        return value


class WaterRecipeAmendment(StrictPaper1Model):
    reagent_id: str
    formula: str
    hydrate_state: str
    amount: RegisteredQuantity
    molecular_weight: RegisteredQuantity
    mass_per_final_litre: RegisteredQuantity
    stoichiometric_contributions_mmol_l: Mapping[str, RegisteredQuantity]
    alkalinity_contribution_mmol_c_l: RegisteredQuantity
    evidence_label: Literal[EvidenceLabel.HYPOTHESIS_PRIOR]

    @field_validator("reagent_id", "formula", "hydrate_state", mode="before")
    @classmethod
    def require_text(cls, value: object, info: object) -> object:
        return _require_registered_text(value, getattr(info, "field_name", "text"))

    @model_validator(mode="after")
    def require_units_arithmetic_and_frozen_contributions(self) -> "WaterRecipeAmendment":
        _require_quantity_unit(self.amount, "mmol L^-1", "amount")
        _require_quantity_unit(self.molecular_weight, "g mol^-1", "molecular_weight")
        _require_quantity_unit(
            self.mass_per_final_litre, "mg L^-1", "mass_per_final_litre"
        )
        _require_quantity_unit(
            self.alkalinity_contribution_mmol_c_l,
            "mmol_c L^-1",
            "alkalinity_contribution_mmol_c_l",
        )
        if self.amount.value <= 0.0 or self.molecular_weight.value <= 0.0:
            raise ValueError("amendment amount and molecular weight must be positive")
        if self.mass_per_final_litre.value <= 0.0:
            raise ValueError("amendment mass must be positive")
        if not isclose(
            self.mass_per_final_litre.value,
            self.amount.value * self.molecular_weight.value,
            rel_tol=0.0,
            abs_tol=1e-12,
        ):
            raise ValueError("amendment mass must equal amount times molecular weight")
        if type(self.stoichiometric_contributions_mmol_l) not in (
            dict,
            _MAPPING_PROXY_TYPE,
        ) or not self.stoichiometric_contributions_mmol_l:
            raise ValueError("stoichiometric contributions must be a nonempty mapping")
        if any(key not in _REGISTERED_ANALYTE_IDS for key in self.stoichiometric_contributions_mmol_l):
            raise ValueError("stoichiometric contribution contains an unknown analyte")
        for analyte_id, quantity in self.stoichiometric_contributions_mmol_l.items():
            _require_registered_text(analyte_id, "stoichiometric analyte")
            _require_quantity_unit(quantity, "mmol L^-1", analyte_id)
            if quantity.value < 0.0:
                raise ValueError("stoichiometric contributions must be nonnegative")
            if quantity.evidence_label is not EvidenceLabel.HYPOTHESIS_PRIOR:
                raise ValueError("stoichiometric contributions require hypothesis_prior")
        for quantity in (
            self.amount,
            self.molecular_weight,
            self.mass_per_final_litre,
            self.alkalinity_contribution_mmol_c_l,
        ):
            if quantity.evidence_label is not EvidenceLabel.HYPOTHESIS_PRIOR:
                raise ValueError("amendment quantities require hypothesis_prior")
        if self.alkalinity_contribution_mmol_c_l.value < 0.0:
            raise ValueError("alkalinity contribution must be nonnegative")
        object.__setattr__(
            self,
            "stoichiometric_contributions_mmol_l",
            MappingProxyType(dict(self.stoichiometric_contributions_mmol_l)),
        )
        return self

    @model_serializer(mode="plain")
    def serialize_amendment(self) -> dict[str, object]:
        return _registered_json_value(self)  # type: ignore[return-value]


class WaterRecipePreparation(StrictPaper1Model):
    preparation_basis: Literal["formula_resolved_synthetic_target"]
    physicalization_status: Literal[
        "blocked_pending_batch_specific_titration_revision"
    ]
    source_water_chemistry: RegisteredRecipeWaterChemistry
    amendments: tuple[WaterRecipeAmendment, ...] = Field(min_length=1)
    registered_nonstoichiometric_targets: Mapping[str, RegisteredQuantity]
    computed_target_chemistry: RegisteredRecipeWaterChemistry

    @model_validator(mode="after")
    def freeze_nonstoichiometric_targets(self) -> "WaterRecipePreparation":
        frozen = _freeze_exact_map(
            self.registered_nonstoichiometric_targets,
            tuple(_NONSTOICHIOMETRIC_TARGET_UNITS),
            "registered_nonstoichiometric_targets",
        )
        for field_name, expected_unit in _NONSTOICHIOMETRIC_TARGET_UNITS.items():
            quantity = frozen[field_name]
            if not isinstance(quantity, RegisteredQuantity):
                raise ValueError("nonstoichiometric targets must be quantities")
            _require_quantity_unit(quantity, expected_unit, field_name)
            if quantity.evidence_label is not EvidenceLabel.HYPOTHESIS_PRIOR:
                raise ValueError("nonstoichiometric targets require hypothesis_prior")
        object.__setattr__(self, "registered_nonstoichiometric_targets", frozen)
        return self

    @model_serializer(mode="plain")
    def serialize_preparation(self) -> dict[str, object]:
        return _registered_json_value(self)  # type: ignore[return-value]


class ActiveWaterRecipe(StrictPaper1Model):
    recipe_id: str
    revision: Literal["1.0.0"]
    water_id: str
    status: Literal["active"]
    supersedes_anchor_sha256: str
    preparation: WaterRecipePreparation
    chemistry: RegisteredRecipeWaterChemistry
    charge_convention_id: Literal["almondlab.chemistry.charge_balance_error@1"]
    charge_balance_tolerance_percent: RegisteredQuantity
    model_domain_id: Literal["core_v1"]
    model_domain_version: Literal["1.1.0"]
    evidence_label: Literal[EvidenceLabel.HYPOTHESIS_PRIOR]
    generated_batch_evidence_label: Literal[EvidenceLabel.SYNTHETIC_ONLY]

    @field_validator("recipe_id", "water_id", mode="before")
    @classmethod
    def require_text(cls, value: object, info: object) -> object:
        return _require_registered_text(value, getattr(info, "field_name", "text"))

    @field_validator("supersedes_anchor_sha256", mode="before")
    @classmethod
    def require_digest(cls, value: object) -> object:
        return _require_lowercase_sha256(value, "supersedes_anchor_sha256")

    @model_validator(mode="after")
    def require_tolerance_unit(self) -> "ActiveWaterRecipe":
        _require_quantity_unit(
            self.charge_balance_tolerance_percent,
            "percent",
            "charge_balance_tolerance_percent",
        )
        if (
            self.charge_balance_tolerance_percent.evidence_label
            is not EvidenceLabel.HYPOTHESIS_PRIOR
        ):
            raise ValueError("charge-balance tolerance requires hypothesis_prior")
        return self


class Paper1WaterRecipeRegistry(StrictPaper1Model):
    schema_version: Literal["1.0.0"]
    historical_anchors: tuple[HistoricalWaterRecipeAnchor, ...] = Field(
        min_length=2, max_length=2
    )
    active_recipes: tuple[ActiveWaterRecipe, ...] = Field(min_length=2, max_length=2)

    @model_validator(mode="after")
    def require_registered_authority(
        self, info: ValidationInfo
    ) -> "Paper1WaterRecipeRegistry":
        expected_tolerance = 1.0
        if info.context is not None:
            contextual = info.context.get(
                "registered_sensitivity_charge_balance_tolerance_percent"
            )
            if type(contextual) is float and contextual in {0.1, 0.5, 2.0}:
                expected_tolerance = contextual
        _validate_water_recipe_registry_authority(
            self,
            expected_charge_balance_tolerance_percent=expected_tolerance,
        )
        return self

    @model_serializer(mode="plain")
    def serialize_registry(self) -> dict[str, object]:
        return _registered_json_value(self)  # type: ignore[return-value]


def _chemistry_json(chemistry: WaterChemistry) -> dict[str, object]:
    return chemistry.model_dump(mode="json")


def _amendment_signature(
    amendment: WaterRecipeAmendment,
) -> tuple[object, ...]:
    return (
        amendment.reagent_id,
        amendment.formula,
        amendment.hydrate_state,
        amendment.amount.value,
        amendment.molecular_weight.value,
        amendment.mass_per_final_litre.value,
        tuple(
            (analyte_id, quantity.value)
            for analyte_id, quantity in amendment.stoichiometric_contributions_mmol_l.items()
        ),
        amendment.alkalinity_contribution_mmol_c_l.value,
    )


def _validate_water_recipe_registry_authority(
    registry: Paper1WaterRecipeRegistry,
    *,
    expected_charge_balance_tolerance_percent: float = 1.0,
) -> None:
    if tuple(anchor.water_id for anchor in registry.historical_anchors) != REGISTERED_WATER_IDS:
        raise ValueError("historical anchors must use the registered water order")
    if tuple(recipe.water_id for recipe in registry.active_recipes) != REGISTERED_WATER_IDS:
        raise ValueError("active recipes must use the registered water order")
    for index, anchor in enumerate(registry.historical_anchors):
        water_id = REGISTERED_WATER_IDS[index]
        expected_path = f"water_conditions[{index}].chemistry"
        if anchor.source_field_path != expected_path:
            raise ValueError("historical source field path is not registered")
        if anchor.source_design_raw_sha256 != _LEGACY_DESIGN_RAW_SHA256:
            raise ValueError("historical source design digest is not registered")
        if anchor.anchor_canonical_sha256 != _LEGACY_ANCHOR_SHA256S[water_id]:
            raise ValueError("historical anchor digest is not registered")
        if anchor.signed_charge_error_percent != _LEGACY_SIGNED_CHARGE_ERRORS[water_id]:
            raise ValueError("historical signed charge error is not registered")
        chemistry = _chemistry_json(anchor.chemistry)
        if chemistry != _LEGACY_CHEMISTRIES[water_id]:
            raise ValueError("historical chemistry is not the frozen anchor")
        # The lineage digest is over the complete superseded WaterCondition,
        # not the chemistry child alone.
        digest = hashlib.sha256(
            canonical_json_bytes(
                {
                    "water_id": water_id,
                    "chemistry": chemistry,
                    "evidence_label": EvidenceLabel.HYPOTHESIS_PRIOR.value,
                }
            )
        ).hexdigest()
        if digest != anchor.anchor_canonical_sha256:
            raise ValueError("historical chemistry does not reproduce its anchor digest")
        if charge_balance_error(anchor.chemistry) != anchor.signed_charge_error_percent:
            raise ValueError("historical charge error does not reproduce the public oracle")

    expected_amendments = (_CONTROL_AMENDMENTS, _CHALLENGE_AMENDMENTS)
    for index, recipe in enumerate(registry.active_recipes):
        water_id = REGISTERED_WATER_IDS[index]
        if recipe.recipe_id != _ACTIVE_RECIPE_IDS[water_id]:
            raise ValueError("active recipe ID is not registered")
        if recipe.supersedes_anchor_sha256 != _LEGACY_ANCHOR_SHA256S[water_id]:
            raise ValueError("active recipe lineage is detached from its anchor")
        expected_source = (
            _SYNTHETIC_BLANK_CHEMISTRY
            if index == 0
            else _ACTIVE_CHEMISTRIES[REGISTERED_WATER_IDS[0]]
        )
        if _chemistry_json(recipe.preparation.source_water_chemistry) != expected_source:
            raise ValueError("active recipe source chemistry is not registered")
        if tuple(_amendment_signature(row) for row in recipe.preparation.amendments) != expected_amendments[index]:
            raise ValueError("active recipe amendment authority drifted")
        expected_chemistry = _ACTIVE_CHEMISTRIES[water_id]
        computed = _chemistry_json(recipe.preparation.computed_target_chemistry)
        chemistry = _chemistry_json(recipe.chemistry)
        if computed != expected_chemistry or chemistry != expected_chemistry:
            raise ValueError("active recipe target chemistry drifted")
        if computed != chemistry:
            raise ValueError("serialized chemistry and computed target must be equal")
        for analyte_id in _REGISTERED_ANALYTE_IDS:
            source_value = getattr(
                recipe.preparation.source_water_chemistry,
                f"{analyte_id}_mmol_l",
            )
            contribution = fsum(
                row.stoichiometric_contributions_mmol_l[analyte_id].value
                for row in recipe.preparation.amendments
                if analyte_id in row.stoichiometric_contributions_mmol_l
            )
            if source_value + contribution != getattr(
                recipe.chemistry, f"{analyte_id}_mmol_l"
            ):
                raise ValueError("formula contributions do not reproduce target chemistry")
        alkalinity = recipe.preparation.source_water_chemistry.alkalinity_mmol_c_l + fsum(
            row.alkalinity_contribution_mmol_c_l.value
            for row in recipe.preparation.amendments
        )
        if alkalinity != recipe.chemistry.alkalinity_mmol_c_l:
            raise ValueError("formula alkalinity does not reproduce target chemistry")
        for field_name, expected_unit in _NONSTOICHIOMETRIC_TARGET_UNITS.items():
            quantity = recipe.preparation.registered_nonstoichiometric_targets[field_name]
            if quantity.value != getattr(recipe.chemistry, field_name):
                raise ValueError("nonstoichiometric target differs from active chemistry")
            if quantity.unit != expected_unit:
                raise ValueError("nonstoichiometric target unit drifted")
        error = charge_balance_error(recipe.chemistry)
        if error != 0.0 or abs(error) > recipe.charge_balance_tolerance_percent.value:
            raise ValueError("active chemistry fails the registered charge oracle")
        if (
            recipe.charge_balance_tolerance_percent.value
            != expected_charge_balance_tolerance_percent
        ):
            raise ValueError(
                "active charge-balance tolerance differs from its registered context"
            )


class Task4ConcentrationStopRule(StrictPaper1Model):
    rule_id: str
    analyte_ids: tuple[str, ...]
    compartment_kinds: tuple[str, ...]
    phase_ids: tuple[str, ...]
    maximum: RegisteredQuantity
    boundary: Literal["stop_above_equality_accepted"]
    evidence_label: Literal[EvidenceLabel.HYPOTHESIS_PRIOR]


class Task4PhysicalStopRule(StrictPaper1Model):
    rule_id: str
    quantity_id: str
    compartment_kinds: tuple[str, ...]
    phase_ids: tuple[str, ...]
    minimum: RegisteredQuantity | None
    maximum: RegisteredQuantity | None
    boundary: Literal[
        "stop_above_equality_accepted", "stop_outside_boundaries_accepted"
    ]
    applicability_key_fields: tuple[str, ...]
    aggregate_debit_preflight: bool
    evidence_label: Literal[EvidenceLabel.HYPOTHESIS_PRIOR]

    @field_validator("aggregate_debit_preflight", mode="before")
    @classmethod
    def require_exact_bool(cls, value: object) -> object:
        if type(value) is not bool:
            raise ValueError("aggregate_debit_preflight must be a primitive boolean")
        return value


_TASK4_CONCENTRATION_AUTHORITY = (
    "root_tissue_na_cl_k_concentration",
    ("na", "cl", "k"),
    ("root_apoplast", "root_symplast", "root_vacuole", "xylem", "shoot_tissue"),
    ("initialization", "state_transition", "terminal"),
    4.0,
    "mmol L^-1",
    "stop_above_equality_accepted",
)
_TASK4_OTHER_AUTHORITIES = (
    (
        "ecw",
        "ecw_ds_m",
        ("source_water", "irrigation_tank"),
        ("operational_sample",),
        None,
        (10.0, "dS m^-1"),
        "stop_above_equality_accepted",
        (),
        False,
    ),
    (
        "osmolality",
        "measured_osmolality_osmol_kg",
        ("mechanistic_water_forcing",),
        ("integration",),
        None,
        (0.4, "osmol kg^-1"),
        "stop_above_equality_accepted",
        (),
        False,
    ),
    (
        "loop_compartment_volume",
        "volume_l",
        (
            "treatment_feed",
            "treatment_product",
            "treatment_concentrate",
            "blend_tank",
            "irrigation_tank",
            "root_zone",
            "drainage",
            "condensate",
            "purge_holding",
        ),
        ("initialization", "state_transition", "terminal"),
        (0.1, "L"),
        (1000.0, "L"),
        "stop_outside_boundaries_accepted",
        ("loop_id", "compartment_id"),
        False,
    ),
    (
        "shared_source_batch_volume",
        "volume_l",
        ("shared_source_batch_inventory",),
        ("preflight", "initialization", "state_transition", "terminal"),
        (0.0, "L"),
        (5000.0, "L"),
        "stop_outside_boundaries_accepted",
        ("cohort_id", "water_batch_id"),
        True,
    ),
    (
        "injury",
        "injury",
        ("plant_state",),
        ("state_transition", "terminal"),
        None,
        (1.0, "dimensionless"),
        "stop_above_equality_accepted",
        ("plant_id",),
        False,
    ),
    (
        "containment_discharge",
        "unauthorized_discharge_volume_l",
        ("external_unauthorized_discharge_ledger",),
        ("initialization", "state_transition", "terminal"),
        None,
        (0.0, "L"),
        "stop_above_equality_accepted",
        ("ledger_category",),
        False,
    ),
)


def _quantity_signature(value: RegisteredQuantity | None) -> tuple[float, str] | None:
    if value is None:
        return None
    return (value.value, value.unit)


class Task4StopPolicy(StrictPaper1Model):
    schema_version: Literal["1.0.0"]
    policy_id: Literal["paper1_task4_stop_policy@1.0.0"]
    evidence_label: Literal[EvidenceLabel.HYPOTHESIS_PRIOR]
    absent_applicability: Literal["explicit_not_applicable"]
    concentration_rule: Task4ConcentrationStopRule
    other_rules: tuple[Task4PhysicalStopRule, ...] = Field(min_length=6, max_length=6)

    @model_validator(mode="after")
    def require_exact_authority(self) -> "Task4StopPolicy":
        rule = self.concentration_rule
        observed = (
            rule.rule_id,
            rule.analyte_ids,
            rule.compartment_kinds,
            rule.phase_ids,
            rule.maximum.value,
            rule.maximum.unit,
            rule.boundary,
        )
        if observed != _TASK4_CONCENTRATION_AUTHORITY:
            raise ValueError("Task 4 concentration applicability authority drifted")
        if rule.maximum.evidence_label is not EvidenceLabel.HYPOTHESIS_PRIOR:
            raise ValueError("Task 4 concentration maximum requires hypothesis_prior")
        observed_other = tuple(
            (
                item.rule_id,
                item.quantity_id,
                item.compartment_kinds,
                item.phase_ids,
                _quantity_signature(item.minimum),
                _quantity_signature(item.maximum),
                item.boundary,
                item.applicability_key_fields,
                item.aggregate_debit_preflight,
            )
            for item in self.other_rules
        )
        if observed_other != _TASK4_OTHER_AUTHORITIES:
            raise ValueError("Task 4 physical-stop authority drifted")
        for item in self.other_rules:
            for quantity in (item.minimum, item.maximum):
                if (
                    quantity is not None
                    and quantity.evidence_label is not EvidenceLabel.HYPOTHESIS_PRIOR
                ):
                    raise ValueError("Task 4 stop boundaries require hypothesis_prior")
        return self

    def resolve_concentration_rule(
        self,
        *,
        analyte_id: str,
        compartment_kind: str,
        phase_id: str,
    ) -> Task4ConcentrationStopRule | None:
        """Resolve an exact triple; absence is explicit non-applicability."""

        canonical = _canonical_task4_stop_policy(self)
        for value, name in (
            (analyte_id, "analyte_id"),
            (compartment_kind, "compartment_kind"),
            (phase_id, "phase_id"),
        ):
            try:
                _require_registered_text(value, name)
            except ValueError as error:
                fail(
                    "TASK4_STOP_LOOKUP_INVALID",
                    "stop-policy lookup identifiers must be exact strings",
                    name,
                    {"cause_type": type(error).__name__},
                )
        rule = canonical.concentration_rule
        if (
            analyte_id in rule.analyte_ids
            and compartment_kind in rule.compartment_kinds
            and phase_id in rule.phase_ids
        ):
            return rule
        return None


class SharedSourceLoopDemand(StrictPaper1Model):
    """One predeclared physical loop's expected debit from a shared batch."""

    cohort_id: str
    run_id: str
    water_id: str
    reservoir_id: str
    water_batch_id: str
    recipe_id: str
    recipe_revision: str
    chemistry_sha256: str
    expected_debit_l: float

    @field_validator(
        "cohort_id",
        "run_id",
        "water_id",
        "reservoir_id",
        "water_batch_id",
        "recipe_id",
        "recipe_revision",
        mode="before",
    )
    @classmethod
    def require_exact_ids(cls, value: object, info: object) -> object:
        return _require_registered_text(value, getattr(info, "field_name", "identifier"))

    @field_validator("chemistry_sha256", mode="before")
    @classmethod
    def require_chemistry_digest(cls, value: object) -> object:
        return _require_lowercase_sha256(value, "chemistry_sha256")

    @field_validator("expected_debit_l", mode="before")
    @classmethod
    def require_finite_debit(cls, value: object) -> object:
        if type(value) is not float or not isfinite(value) or value < 0.0:
            raise ValueError("expected debit must be a nonnegative finite primitive float")
        return value

    @model_validator(mode="after")
    def require_registered_recipe_identity(self) -> "SharedSourceLoopDemand":
        if self.water_id not in REGISTERED_WATER_IDS:
            raise ValueError("loop demand water_id is not registered")
        if self.recipe_id != _ACTIVE_RECIPE_IDS[self.water_id]:
            raise ValueError("loop demand recipe_id does not match its water_id")
        if self.recipe_revision != "1.0.0":
            raise ValueError("loop demand recipe revision is not registered")
        return self


class SharedSourceBatchCapacityAudit(StrictPaper1Model):
    cohort_id: str
    water_batch_id: str
    water_id: str
    recipe_id: str
    recipe_revision: str
    chemistry_sha256: str
    loop_count: int
    aggregate_expected_debit_l: float
    capacity_l: float
    remaining_capacity_l: float

    @field_validator("loop_count", mode="before")
    @classmethod
    def require_loop_count(cls, value: object) -> object:
        if type(value) is not int or value <= 0:
            raise ValueError("loop count must be a positive primitive integer")
        return value

    @field_validator(
        "aggregate_expected_debit_l", "capacity_l", "remaining_capacity_l", mode="before"
    )
    @classmethod
    def require_audit_float(cls, value: object) -> object:
        if type(value) is not float or not isfinite(value) or value < 0.0:
            raise ValueError("capacity audit values must be nonnegative finite floats")
        return value


def _canonical_task4_stop_policy(policy: object) -> Task4StopPolicy:
    if type(policy) is not Task4StopPolicy:
        fail(
            "TASK4_STOP_POLICY_INVALID",
            "stop policy must be a validated Task4StopPolicy",
            "policy",
            {"received_type": type(policy).__name__},
        )
    try:
        return Task4StopPolicy.model_validate(_registered_json_value(policy))
    except Exception as error:
        fail(
            "TASK4_STOP_POLICY_INVALID",
            "stop policy failed complete authority revalidation",
            "policy",
            {"cause_type": type(error).__name__},
        )


_TASK4_WATER_LOOP_AUTHORITY = (
    ("reservoir_initial_volume_l", 120.0, "L"),
    ("water_batch_volume_l", 5000.0, "L"),
    ("irrigation_volume_l_per_plant_day", 0.60, "L plant^-1 day^-1"),
    ("drainage_return_fraction", 0.70, "dimensionless"),
    ("purge_volume_l_day", 1.20, "L day^-1"),
    ("sampling_volume_l_per_sample", 0.05, "L sample^-1"),
    ("reservoir_min_volume_l", 80.0, "L"),
    ("reservoir_max_volume_l", 160.0, "L"),
)
_TASK4_DURATION_DAYS = 84
_TASK4_RESTORED_NONTERMINAL_SAMPLES = 6
_TASK4_DISCOVERY_GROUP_IDS = frozenset(
    {
        "C1",
        "C2",
        "C3",
        "C4",
        "C5",
        "C6",
        "empty_vector",
        "sham_transformation",
        "unmodified_parent",
    }
)
_TASK4_CONFIRMATION_CANDIDATE_IDS = frozenset(
    {"C1", "C2", "C3", "C4", "C5", "C6"}
)
_TASK3_DISCOVERY_ROOT_SEED = 20260812
# Task 4 prospectively migrated only the water chemistry in the active design;
# the registered physical Task 3 draw and its allocation identity are unchanged.
_TASK4_ACTIVE_DISCOVERY_CONFIG_SHA256 = (
    "f5911a6a63d7444575c2013d9737b9219ef21fb1f5c58dcc5fd633bcde38f5c9"
)
_TASK3_DISCOVERY_ALLOCATION_SHA256 = (
    "bd4cb366ac9c3144ab881af29615311839f1fc0a9a881645ba4995dcab7b7c3f"
)
_TASK3_DISCOVERY_INPUT_SHA256S = MappingProxyType(
    {
        "baseline_roster_canonical": (
            "f34dc944bf951fc8c2f752d981433482d475a4c4f3091e6d8d8f2e7d0df719d8"
        ),
        "position_map_canonical": (
            "fed49c40785388661b46a0ee5c174617e39230fac80171677cfdcca9b9d9cbea"
        ),
    }
)


def _canonical_task4_water_loop(
    water_loop: object,
    *,
    registered_sensitivity_binding: tuple[str, str, float] | None = None,
) -> WaterLoopGeneratorConfig:
    if type(water_loop) is not WaterLoopGeneratorConfig:
        fail(
            "WATER_BATCH_GENERATOR_INVALID",
            "shared source preflight requires an exact WaterLoopGeneratorConfig",
            "water_loop",
            {"received_type": type(water_loop).__name__},
        )
    try:
        checked = WaterLoopGeneratorConfig.model_validate(
            _registered_json_value(water_loop)
        )
    except Exception as error:
        fail(
            "WATER_BATCH_GENERATOR_INVALID",
            "water-loop authority failed complete reconstruction",
            "water_loop",
            {"cause_type": type(error).__name__},
        )
    expected_values = {
        name: value for name, value, _ in _TASK4_WATER_LOOP_AUTHORITY
    }
    if registered_sensitivity_binding is not None:
        name, value = _canonical_task4_capacity_sensitivity_binding(
            registered_sensitivity_binding
        )
        expected_values[name] = value
    observed = tuple(
        (
            name,
            getattr(checked, name).value,
            getattr(checked, name).unit,
            getattr(checked, name).evidence_label,
        )
        for name, _, _ in _TASK4_WATER_LOOP_AUTHORITY
    )
    expected = tuple(
        (name, expected_values[name], unit, EvidenceLabel.HYPOTHESIS_PRIOR)
        for name, _, unit in _TASK4_WATER_LOOP_AUTHORITY
    )
    observed_events = tuple(
        (item.value, item.unit, item.evidence_label)
        for item in checked.operator_event_times_days
    )
    expected_events = tuple(
        (float(index) + 0.25, "day", EvidenceLabel.HYPOTHESIS_PRIOR)
        for index in range(_TASK4_DURATION_DAYS)
    )
    if observed != expected or observed_events != expected_events:
        fail(
            "WATER_BATCH_GENERATOR_INVALID",
            "water-loop values differ from the registered Task 4 authority",
            "water_loop",
        )
    return checked


def _task3_position_payload(slot: object) -> dict[str, object]:
    return {
        "position_id": slot.position_id,
        "run_id": slot.run_id,
        "run_sequence_ordinal": slot.run_sequence_ordinal,
        "water_id": slot.water_id,
        "reservoir_id": slot.reservoir_id,
        "water_batch_id": slot.water_batch_id,
        "greenhouse_compartment_id": slot.greenhouse_compartment_id,
        "bench_id": slot.bench_id,
        "row": slot.row,
        "column": slot.column,
        "spatial_gradient_profile_id": slot.spatial_gradient_profile_id,
        "permitted_movement_schedule_ids": list(
            slot.permitted_movement_schedule_ids
        ),
        "cohort_id": slot.cohort_id,
    }


def _canonical_task3_capacity_authorities(
    config: object,
    baseline_roster: object,
    position_map: object,
    manifest: object,
) -> tuple["PositionMap", "RandomizationManifest"]:
    # design imports this module, so these runtime-only imports must remain local.
    from almondlab.design import (
        ConfirmationDesignConfig,
        cohort_identity_set,
        randomize,
        revalidate_baseline_roster,
        revalidate_confirmation_design,
        revalidate_position_map,
        revalidate_randomization_manifest,
    )

    discovery_config = type(config) is Paper1DesignConfig
    if discovery_config:
        try:
            checked_config = Paper1DesignConfig.model_validate(
                _registered_json_value(config)
            )
        except Exception as error:
            fail(
                "WATER_BATCH_AUTHORITY_INVALID",
                "discovery design failed complete authority revalidation",
                "config",
                {"cause_type": type(error).__name__},
            )
    elif type(config) is ConfirmationDesignConfig:
        checked_config = revalidate_confirmation_design(config)
    else:
        fail(
            "WATER_BATCH_AUTHORITY_INVALID",
            "capacity preflight requires an exact Task 3 design config",
            "config",
            {"received_type": type(config).__name__},
        )
    checked_roster = revalidate_baseline_roster(baseline_roster)
    checked_map = revalidate_position_map(position_map)
    checked_manifest = revalidate_randomization_manifest(manifest)
    cohort_identity_set(
        checked_manifest,
        baseline_roster=checked_roster,
        position_map=checked_map,
    )
    regenerated_manifest = randomize(
        checked_config,
        checked_manifest.root_seed,
        position_map=checked_map,
        baseline_roster=checked_roster,
    )
    if (
        regenerated_manifest.canonical_json_bytes()
        != checked_manifest.canonical_json_bytes()
    ):
        fail(
            "WATER_BATCH_AUTHORITY_INVALID",
            "manifest is not the exact canonical Task 3 allocation for its inputs",
            "manifest",
        )
    if discovery_config:
        if (
            checked_manifest.root_seed != _TASK3_DISCOVERY_ROOT_SEED
            or checked_manifest.config_sha256
            != _TASK4_ACTIVE_DISCOVERY_CONFIG_SHA256
            or checked_manifest.allocation_sha256
            != _TASK3_DISCOVERY_ALLOCATION_SHA256
            or dict(checked_manifest.input_sha256s)
            != dict(_TASK3_DISCOVERY_INPUT_SHA256S)
        ):
            fail(
                "WATER_BATCH_AUTHORITY_INVALID",
                "discovery inputs differ from the approved Task 3 registration",
                "manifest.input_sha256s",
            )
    position_payload = [
        _task3_position_payload(slot)
        for slot in sorted(checked_map.slots, key=lambda item: item.position_id)
    ]
    position_sha256 = hashlib.sha256(
        canonical_json_bytes(position_payload)
    ).hexdigest()
    if (
        checked_manifest.input_sha256s.get("position_map_canonical")
        != position_sha256
    ):
        fail(
            "WATER_BATCH_AUTHORITY_INVALID",
            "manifest does not name the supplied canonical position map",
            "manifest.input_sha256s.position_map_canonical",
        )
    slots_by_position = {slot.position_id: slot for slot in checked_map.slots}
    records_by_position = {
        record.position_id: record for record in checked_manifest.records
    }
    if (
        len(slots_by_position) != len(checked_map.slots)
        or len(records_by_position) != len(checked_manifest.records)
        or len(checked_map.slots) != len(checked_manifest.records)
        or set(slots_by_position) != set(records_by_position)
    ):
        fail(
            "WATER_BATCH_AUTHORITY_INVALID",
            "position map and manifest must have identical exhaustive membership",
            "position_map.slots",
            {
                "position_count": len(checked_map.slots),
                "manifest_count": len(checked_manifest.records),
            },
        )
    for field_name in ("allocation_id", "plant_id", "blinded_treatment_code"):
        values = tuple(
            getattr(record, field_name) for record in checked_manifest.records
        )
        if len(set(values)) != len(values):
            fail(
                "WATER_BATCH_AUTHORITY_INVALID",
                "manifest must allocate each Task 3 physical identity exactly once",
                f"manifest.records.{field_name}",
            )
    for position_id in sorted(slots_by_position):
        slot = slots_by_position[position_id]
        record = records_by_position[position_id]
        if (
            record.population is not AnalysisPopulation.COMPOSITE_ROOT
            or record.evidence_label is not EvidenceLabel.SYNTHETIC_ONLY
        ):
            fail(
                "WATER_BATCH_AUTHORITY_INVALID",
                "Task 3 capacity authority must remain composite-root synthetic allocation",
                "manifest.records",
                {"position_id": position_id},
            )
        observed = (
            record.run_id,
            record.run_sequence_ordinal,
            record.water_id,
            record.reservoir_id,
            record.water_batch_id,
            record.greenhouse_compartment_id,
            record.bench_id,
            record.row,
            record.column,
            record.spatial_gradient_profile_id,
            record.cohort_id,
        )
        expected = (
            slot.run_id,
            slot.run_sequence_ordinal,
            slot.water_id,
            slot.reservoir_id,
            slot.water_batch_id,
            slot.greenhouse_compartment_id,
            slot.bench_id,
            slot.row,
            slot.column,
            slot.spatial_gradient_profile_id,
            slot.cohort_id,
        )
        if (
            observed != expected
            or record.movement_schedule_id
            not in slot.permitted_movement_schedule_ids
        ):
            fail(
                "WATER_BATCH_AUTHORITY_INVALID",
                "manifest relabels a registered physical Task 3 position",
                "manifest.records",
                {"position_id": position_id},
            )
    return checked_map, checked_manifest


def _task4_expected_loop_debit(
    water_loop: WaterLoopGeneratorConfig,
    plant_count: int,
) -> float:
    try:
        daily_net_makeup = fsum(
            (
                water_loop.irrigation_volume_l_per_plant_day.value
                * float(plant_count)
                * (1.0 - water_loop.drainage_return_fraction.value),
                water_loop.purge_volume_l_day.value,
            )
        )
        expected_debit = fsum(
            (
                water_loop.reservoir_initial_volume_l.value,
                float(_TASK4_DURATION_DAYS) * daily_net_makeup,
                float(_TASK4_RESTORED_NONTERMINAL_SAMPLES)
                * water_loop.sampling_volume_l_per_sample.value,
            )
        )
    except (OverflowError, ValueError):
        expected_debit = float("inf")
    if not isfinite(expected_debit):
        fail(
            "WATER_BATCH_DEBIT_INVALID",
            "derived source debit is not finite",
            "manifest.records",
            {"plant_count": plant_count},
        )
    return float(expected_debit)


def preflight_shared_source_batch_capacity(
    policy: Task4StopPolicy,
    *,
    config: "Paper1DesignConfig | ConfirmationDesignConfig",
    baseline_roster: "BaselineRoster",
    position_map: "PositionMap",
    manifest: "RandomizationManifest",
    recipe_registry: Paper1WaterRecipeRegistry,
    water_loop: WaterLoopGeneratorConfig,
    registered_sensitivity_binding: tuple[str, str, float] | None = None,
) -> tuple[SharedSourceBatchCapacityAudit, ...]:
    """Derive exact Task 3 shared-batch debits before RNG, output, or execution."""

    canonical_policy = _canonical_task4_stop_policy(policy)
    _, canonical_manifest = _canonical_task3_capacity_authorities(
        config,
        baseline_roster,
        position_map,
        manifest,
    )
    canonical_registry = _canonical_water_recipe_registry(recipe_registry)
    canonical_loop = _canonical_task4_water_loop(
        water_loop,
        registered_sensitivity_binding=registered_sensitivity_binding,
    )
    cohort_ids = {record.cohort_id for record in canonical_manifest.records}
    if len(cohort_ids) != 1 or not cohort_ids <= {"discovery", "confirmation"}:
        fail(
            "WATER_BATCH_AUTHORITY_INVALID",
            "one preflight must contain exactly one registered Task 3 cohort",
            "manifest.records.cohort_id",
        )
    cohort_id = next(iter(cohort_ids))
    if cohort_id == "confirmation":
        fail(
            "WATER_BATCH_CONFIRMATION_AUTHORITY_UNAVAILABLE",
            "confirmation capacity preflight requires a registered CohortDesignBundle",
            "config",
            {
                "required_authority": "task4_registered_confirmation_cohort_bundle",
            },
        )
    loop_records: dict[tuple[str, str, str, str], list[object]] = {}
    for record in canonical_manifest.records:
        loop_key = (
            record.cohort_id,
            record.run_id,
            record.water_id,
            record.reservoir_id,
        )
        loop_records.setdefault(loop_key, []).append(record)
    expected_loop_count = 16 if cohort_id == "discovery" else 12
    expected_batch_count = 4 if cohort_id == "discovery" else 2
    expected_loops_per_batch = 4 if cohort_id == "discovery" else 6
    if len(loop_records) != expected_loop_count:
        fail(
            "WATER_BATCH_AUTHORITY_INVALID",
            "manifest omits or adds a registered physical Task 3 loop",
            "manifest.records",
            {
                "cohort_id": cohort_id,
                "expected_loop_count": expected_loop_count,
                "received_loop_count": len(loop_records),
            },
        )
    batch_loops: dict[
        tuple[str, str],
        list[tuple[tuple[str, str, str, str], int, str]],
    ] = {}
    cohort_group_ids: frozenset[str] | None = None
    cohort_cell_size: int | None = None
    for loop_key in sorted(loop_records):
        records = loop_records[loop_key]
        batch_ids = {record.water_batch_id for record in records}
        if len(batch_ids) != 1:
            fail(
                "WATER_BATCH_AUTHORITY_INVALID",
                "one physical loop has more than one water-batch identity",
                "manifest.records.water_batch_id",
                {"loop_key": loop_key},
            )
        group_counts: dict[str, int] = {}
        for record in records:
            group_counts[record.group_id] = group_counts.get(record.group_id, 0) + 1
        group_ids = frozenset(group_counts)
        cell_sizes = set(group_counts.values())
        if cohort_id == "discovery":
            valid_group_shape = (
                group_ids == _TASK4_DISCOVERY_GROUP_IDS and cell_sizes == {5}
            )
        else:
            candidate_ids = group_ids - {"empty_vector"}
            valid_group_shape = (
                "empty_vector" in group_ids
                and 1 <= len(candidate_ids) <= 4
                and candidate_ids <= _TASK4_CONFIRMATION_CANDIDATE_IDS
                and cell_sizes <= {5, 6}
                and len(cell_sizes) == 1
            )
        if not valid_group_shape:
            fail(
                "WATER_BATCH_AUTHORITY_INVALID",
                "physical loop groups or cell size differ from the registered Task 3 design",
                "manifest.records",
                {
                    "loop_key": loop_key,
                    "group_ids": sorted(group_ids),
                    "cell_sizes": sorted(cell_sizes),
                },
            )
        cell_size = next(iter(cell_sizes))
        if cohort_group_ids is None:
            cohort_group_ids = group_ids
            cohort_cell_size = cell_size
        elif group_ids != cohort_group_ids or cell_size != cohort_cell_size:
            fail(
                "WATER_BATCH_AUTHORITY_INVALID",
                "all Task 3 loops in one cohort must use the same groups and cell size",
                "manifest.records",
                {"loop_key": loop_key},
            )
        plant_count = len(records)
        water_id = loop_key[2]
        if water_id not in REGISTERED_WATER_IDS:
            fail(
                "WATER_BATCH_IDENTITY_MISMATCH",
                "physical loop names an unregistered water identity",
                "manifest.records.water_id",
                {"water_id": water_id},
            )
        water_batch_id = next(iter(batch_ids))
        batch_loops.setdefault((cohort_id, water_batch_id), []).append(
            (loop_key, plant_count, water_id)
        )
    if len(batch_loops) != expected_batch_count:
        fail(
            "WATER_BATCH_AUTHORITY_INVALID",
            "Task 3 shared water-batch identities were split, added, or omitted",
            "manifest.records.water_batch_id",
            {
                "cohort_id": cohort_id,
                "expected_batch_count": expected_batch_count,
                "received_batch_count": len(batch_loops),
            },
        )
    capacity_rule = next(
        item
        for item in canonical_policy.other_rules
        if item.rule_id == "shared_source_batch_volume"
    )
    if capacity_rule.maximum is None:
        raise AssertionError("registered capacity rule requires maximum")
    capacity = capacity_rule.maximum.value
    if canonical_loop.water_batch_volume_l.value != capacity:
        fail(
            "WATER_BATCH_GENERATOR_INVALID",
            "water-loop and stop-policy source capacities differ",
            "water_loop.water_batch_volume_l",
        )
    recipes = {
        recipe.water_id: recipe for recipe in canonical_registry.active_recipes
    }
    audits: list[SharedSourceBatchCapacityAudit] = []
    for group_key in sorted(batch_loops):
        loops = sorted(batch_loops[group_key], key=lambda item: item[0])
        water_ids = {item[2] for item in loops}
        plant_counts = {item[1] for item in loops}
        run_ids = {item[0][1] for item in loops}
        if (
            len(loops) != expected_loops_per_batch
            or len(water_ids) != 1
            or len(plant_counts) != 1
            or (cohort_id == "discovery" and len(run_ids) != 1)
        ):
            fail(
                "WATER_BATCH_IDENTITY_MISMATCH",
                "one shared water batch has conflicting or incomplete Task 3 loops",
                "manifest.records.water_batch_id",
                {"cohort_id": group_key[0], "water_batch_id": group_key[1]},
            )
        water_id = next(iter(water_ids))
        recipe = recipes[water_id]
        chemistry_sha256 = hashlib.sha256(
            canonical_json_bytes(_chemistry_json(recipe.chemistry))
        ).hexdigest()
        try:
            aggregate = fsum(
                _task4_expected_loop_debit(canonical_loop, plant_count)
                for _, plant_count, _ in loops
            )
        except OverflowError:
            aggregate = float("inf")
        if not isfinite(aggregate) or aggregate > capacity:
            fail(
                "WATER_BATCH_CAPACITY_EXCEEDED",
                "aggregate expected debit exceeds the shared 5,000-L source inventory",
                "manifest.records",
                {
                    "cohort_id": group_key[0],
                    "water_batch_id": group_key[1],
                    "aggregate_expected_debit_l": aggregate,
                    "capacity_l": capacity,
                },
            )
        audits.append(
            SharedSourceBatchCapacityAudit(
                cohort_id=group_key[0],
                water_batch_id=group_key[1],
                water_id=water_id,
                recipe_id=recipe.recipe_id,
                recipe_revision=recipe.revision,
                chemistry_sha256=chemistry_sha256,
                loop_count=len(loops),
                aggregate_expected_debit_l=float(aggregate),
                capacity_l=float(capacity),
                remaining_capacity_l=float(capacity - aggregate),
            )
        )
    return tuple(audits)


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
    if type(supplied) not in (dict, _MAPPING_PROXY_TYPE):
        _scenario_invalid("section must be a primitive mapping", field_path)
    names = set(supplied)
    if any(type(name) is not str for name in names):
        _scenario_invalid("section keys must be primitive strings", field_path)
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
    if type(value) not in (str, EvidenceLabel):
        _scenario_invalid("evidence label must be an exact string or enum", field_path)
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
    if type(value) not in (str, ConservedEntity):
        _scenario_invalid("conserved entity must be an exact string or enum", field_path)
    try:
        return value if isinstance(value, ConservedEntity) else ConservedEntity(value)
    except (TypeError, ValueError) as error:
        _scenario_invalid("conserved entity is invalid", field_path, cause=error)


def _compartment_kind(value: object, field_path: str) -> CompartmentKind:
    if type(value) not in (str, CompartmentKind):
        _scenario_invalid("compartment kind must be an exact string or enum", field_path)
    try:
        return value if isinstance(value, CompartmentKind) else CompartmentKind(value)
    except (TypeError, ValueError) as error:
        _scenario_invalid("compartment kind is invalid", field_path, cause=error)


def _network_state(value: object, field_path: str) -> NetworkState:
    if isinstance(value, NetworkState) and type(value) is not NetworkState:
        _scenario_invalid("network state must be exact", field_path)
    if type(value) is NetworkState:
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
    if (
        type(raw_compartments) not in (dict, _MAPPING_PROXY_TYPE)
        or not raw_compartments
    ):
        _scenario_invalid("network compartments must be a nonempty mapping", f"{field_path}.compartments")
    compartments: dict[str, CompartmentState] = {}
    compartment_keys = frozenset(field.name for field in fields(CompartmentState))
    for raw_id, raw_compartment in raw_compartments.items():
        if type(raw_id) is not str:
            _scenario_invalid("compartment IDs must be primitive strings", f"{field_path}.compartments")
        if isinstance(raw_compartment, CompartmentState) and type(
            raw_compartment
        ) is not CompartmentState:
            _scenario_invalid(
                "network compartment must be exact",
                f"{field_path}.compartments.{raw_id}",
            )
        if type(raw_compartment) is CompartmentState:
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
        if type(stocks) not in (dict, _MAPPING_PROXY_TYPE):
            _scenario_invalid("stocks must be a primitive mapping", f"{field_path}.compartments.{raw_id}.stocks")
        typed_stocks: dict[ConservedEntity, object] = {}
        for raw_entity, amount in stocks.items():
            if type(raw_entity) not in (str, ConservedEntity):
                _scenario_invalid(
                    "stock keys must be primitive strings or exact entities",
                    f"{field_path}.compartments.{raw_id}.stocks",
                )
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
    if type(raw_entities) not in (list, tuple, set, frozenset):
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
    if isinstance(value, BiologyParameters) and type(value) is not BiologyParameters:
        _scenario_invalid("biology parameters must be exact", "parameters")
    if type(value) is BiologyParameters:
        mapping: Mapping[str, object] = {
            field.name: getattr(value, field.name) for field in fields(BiologyParameters)
        }
    else:
        mapping = _exact_scenario_keys(
            value, REQUIRED_BIOLOGY_PARAMETER_KEYS, "parameters"
        )
    payload = dict(mapping)
    for field in fields(BiologyParameters):
        if field.name not in {"schema_version", "evidence_label"} and type(
            payload[field.name]
        ) is not float:
            _scenario_invalid(
                "biology numeric inputs must be primitive floats",
                f"parameters.{field.name}",
            )
    payload["evidence_label"] = _evidence(
        payload["evidence_label"], "parameters.evidence_label"
    )
    try:
        return BiologyParameters(**payload)
    except (AlmondLabError, TypeError, ValueError) as error:
        _scenario_invalid("biology parameters are invalid", "parameters", cause=error)


def _initial_state(value: object) -> PlantState:
    if isinstance(value, PlantState) and type(value) is not PlantState:
        _scenario_invalid("initial plant state must be exact", "initial_state")
    if type(value) is PlantState:
        mapping: Mapping[str, object] = {
            field.name: getattr(value, field.name) for field in fields(PlantState)
        }
    else:
        mapping = _exact_scenario_keys(
            value, REQUIRED_INITIAL_STATE_KEYS, "initial_state"
        )
    payload = dict(mapping)
    for field in fields(PlantState):
        if field.name in {
            "network_state",
            "evidence_label",
            "alive",
            "death_time_hours",
        }:
            continue
        if type(payload[field.name]) is not float:
            _scenario_invalid(
                "initial-state numeric inputs must be primitive floats",
                f"initial_state.{field.name}",
            )
    if type(payload["alive"]) is not bool:
        _scenario_invalid("alive must be a primitive boolean", "initial_state.alive")
    if payload["death_time_hours"] is not None and type(
        payload["death_time_hours"]
    ) is not float:
        _scenario_invalid(
            "death time must be null or a primitive float",
            "initial_state.death_time_hours",
        )
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
    if isinstance(value, HydraulicDomain) and type(value) is not HydraulicDomain:
        _scenario_invalid(
            "hydraulic domain must be exact", "forcing.hydraulic_domain"
        )
    if type(value) is HydraulicDomain:
        payload: object = value.model_dump(mode="python")
    else:
        payload = value
    try:
        return HydraulicDomain.model_validate(payload)
    except Exception as error:
        _scenario_invalid("hydraulic domain is invalid", "forcing.hydraulic_domain", cause=error)


def _forcing(value: object) -> RootZoneForcing:
    if isinstance(value, RootZoneForcing) and type(value) is not RootZoneForcing:
        _scenario_invalid("root-zone forcing must be exact", "forcing")
    if type(value) is RootZoneForcing:
        mapping: Mapping[str, object] = {
            field.name: getattr(value, field.name) for field in fields(RootZoneForcing)
        }
    else:
        mapping = _exact_scenario_keys(value, REQUIRED_FORCING_KEYS, "forcing")
    payload = dict(mapping)
    for field in fields(RootZoneForcing):
        if field.name in {"evidence_label", "hydraulic_domain"}:
            continue
        if type(payload[field.name]) is not float:
            _scenario_invalid(
                "forcing numeric inputs must be primitive floats",
                f"forcing.{field.name}",
            )
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
    if value is None or type(value) is str:
        return value
    if type(value) is float:
        if value != value or abs(value) == float("inf"):
            raise ValueError(f"{field_path} contains a nonfinite number")
        return value
    if type(value) in (int, bool):
        raise ValueError(f"{field_path} requires exact registered real values")
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

    @field_validator(
        "biology_parameter_overrides",
        "candidate_parameter_overrides_by_id",
        "post_onset_biology_parameter_overrides",
        "candidate_chassis_mechanism_modifiers",
        mode="before",
    )
    @classmethod
    def require_primitive_mechanism_maps(cls, value: object) -> object:
        return _require_primitive_string_mapping(value, "scenario mechanism map")

    @model_validator(mode="after")
    def freeze_registered_mechanism(self) -> "ScenarioMechanismConfig":
        if self.onset_time_days is not None:
            _require_quantity_unit(self.onset_time_days, "day", "onset_time_days")
            _require_positive_quantity(self.onset_time_days, "onset_time_days")
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

    @property
    def has_synthetic_semantics(self) -> bool:
        return bool(
            self.biology_parameter_overrides
            or self.candidate_parameter_overrides_by_id
            or self.onset_time_days is not None
            or self.post_onset_biology_parameter_overrides
            or self.chassis_id is not None
            or self.candidate_chassis_mechanism_modifiers
        )

    @model_serializer(mode="plain")
    def serialize_registered_mechanism(self) -> dict[str, object]:
        return _registered_json_value(self)  # type: ignore[return-value]


def _registered_registration_labels(value: object) -> tuple[EvidenceLabel, ...]:
    """Collect every nested unit-bearing registration label exactly once."""

    if type(value) in (RegisteredQuantity, RegisteredCount):
        return (value.evidence_label,)
    if isinstance(value, StrictPaper1Model):
        labels: list[EvidenceLabel] = []
        for name in type(value).model_fields:
            labels.extend(_registered_registration_labels(getattr(value, name)))
        return tuple(labels)
    if isinstance(value, Mapping):
        return tuple(
            label
            for item in value.values()
            for label in _registered_registration_labels(item)
        )
    if isinstance(value, (tuple, list)):
        return tuple(
            label
            for item in value
            for label in _registered_registration_labels(item)
        )
    return ()


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
            or any(type(key) is not str for key in value)
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
            *_registered_registration_labels(self.generator),
        ]
        if self.mechanism.onset_time_days is not None:
            labels.append(self.mechanism.onset_time_days.evidence_label)
        if self.mechanism.has_synthetic_semantics:
            labels.append(EvidenceLabel.SYNTHETIC_ONLY)
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
        expected_duration_hours = self.generator.design.duration_days.value * 24.0
        if not isfinite(expected_duration_hours):
            raise ValueError("scenario duration arithmetic must remain finite")
        for water_id, schedule in self.forcings_by_water_id.items():
            if len(schedule) != 168 or any(
                forcing.duration_hours != 12.0 for forcing in schedule
            ):
                raise ValueError(
                    f"forcing schedule {water_id} must contain exactly "
                    "168 registered 12-hour coordinates"
                )
            try:
                observed_duration_hours = fsum(
                    forcing.duration_hours for forcing in schedule
                )
            except (OverflowError, ValueError):
                observed_duration_hours = float("inf")
            if (
                not isfinite(observed_duration_hours)
                or observed_duration_hours != expected_duration_hours
            ):
                raise ValueError(
                    f"forcing schedule {water_id} must cover exactly "
                    f"{expected_duration_hours} hours"
                )
        return self

    @model_serializer(mode="plain")
    def serialize_registered_scenario(self) -> dict[str, object]:
        return _registered_json_value(self)  # type: ignore[return-value]


_TASK4_SENSITIVITY_SCENARIO_PREFIX = (
    "configs/synthetic_scenarios.yaml::anchor.generator."
)
_TASK4_SENSITIVITY_RECIPE_PREFIX = "configs/paper1_water_recipes.yaml::"
_TASK4_SENSITIVITY_SCENARIO_SELECTOR_PREFIX = (
    "configs/synthetic_scenarios.yaml::scenarios[scenario_id="
)


def _task4_sensitivity_authority() -> tuple[
    tuple[
        str,
        str,
        tuple[str, ...],
        tuple[int | float, ...],
        tuple[int | float, ...],
    ],
    ...,
]:
    """Return the immutable prospective 36-record sensitivity authority."""

    scenario = _TASK4_SENSITIVITY_SCENARIO_PREFIX
    recipe = _TASK4_SENSITIVITY_RECIPE_PREFIX
    selected = _TASK4_SENSITIVITY_SCENARIO_SELECTOR_PREFIX
    limits = (
        "root_zone_na_concentration",
        "root_zone_cl_concentration",
        "root_zone_k_concentration",
        "xylem_sap_na_concentration",
        "drainage_total_b_concentration",
        "root_surface_outward_na_flux_per_root_dry_mass",
        "root_h2o2_concentration_time_auc",
        "xylem_sap_na_concentration_time_auc",
    )
    endpoints = (
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

    def paths(*suffixes: str) -> tuple[str, ...]:
        return tuple(scenario + suffix for suffix in suffixes)

    return (
        (
            "S001_charge_tolerance",
            "percent",
            (
                scenario + "chemistry.charge_balance_tolerance_percent",
                recipe
                + "active_recipes[water_id=nonsaline_nutrient_matched_control]."
                "charge_balance_tolerance_percent",
                recipe
                + "active_recipes[water_id=pilot_selected_full_ion_marine_challenge]."
                "charge_balance_tolerance_percent",
            ),
            (0.1, 0.5, 2.0),
            (1.0, 1.0, 1.0),
        ),
        ("S002_temperature_phi", "dimensionless", paths("climate.temperature_ar1_phi"), (0.4, 0.9), (0.7,)),
        ("S003_apar_phi", "dimensionless", paths("climate.apar_ar1_phi"), (0.4, 0.9), (0.6,)),
        ("S004_matric_phi", "dimensionless", paths("climate.matric_potential_ar1_phi"), (0.4, 0.9), (0.8,)),
        ("S005_temperature_sd", "K", paths("climate.temperature_innovation_sd_k"), (0.175, 0.7), (0.35,)),
        ("S006_apar_sd", "log-ratio", paths("climate.apar_log_innovation_sd"), (0.05, 0.2), (0.1,)),
        ("S007_matric_sd", "MPa", paths("climate.matric_potential_innovation_sd_mpa"), (0.003, 0.012), (0.006,)),
        ("S008_transpiration_sd", "log-ratio", paths("climate.potential_transpiration_log_innovation_sd"), (0.04, 0.16), (0.08,)),
        ("S009_burnin", "count", paths("climate.climate_initialization_burnin_steps"), (32, 128), (64,)),
        ("S010_common_ion_sd", "log-ratio", paths("chemistry.common_ion_log_sd"), (0.015, 0.06), (0.03,)),
        ("S011_boron_sd", "log-ratio", paths("chemistry.boron_log_sd"), (0.04, 0.16), (0.08,)),
        (
            "S012_chemistry_measurement_sd",
            "multiplier",
            paths(
                "chemistry.ec_measurement_sd_ds_m",
                "chemistry.osmolality_measurement_sd_osmol_kg",
                "chemistry.ph_measurement_sd",
                "chemistry.temperature_measurement_sd_k",
            ),
            (0.5, 2.0),
            (0.05, 0.002, 0.03, 0.2),
        ),
        ("S013_initial_volume", "L", paths("water_loop.reservoir_initial_volume_l"), (100.0, 140.0), (120.0,)),
        ("S014_return_fraction", "dimensionless", paths("water_loop.drainage_return_fraction"), (0.5, 0.9), (0.7,)),
        ("S015_irrigation", "L plant^-1 day^-1", paths("water_loop.irrigation_volume_l_per_plant_day"), (0.4, 0.8), (0.6,)),
        ("S016_anchor_purge", "L day^-1", paths("water_loop.purge_volume_l_day"), (0.6, 2.4), (1.2,)),
        ("S017_sample_volume", "L sample^-1", paths("water_loop.sampling_volume_l_per_sample"), (0.025, 0.1), (0.05,)),
        ("S018_canopy_error", "log-ratio", paths("observation.canopy_observation_error_sd"), (0.025, 0.1), (0.05,)),
        ("S019_ion_error", "log-ratio", paths("observation.ion_observation_error_sd"), (0.02, 0.08), (0.04,)),
        (
            "S020_heteroscedasticity",
            "multiplier",
            paths(
                "observation.canopy_heteroscedastic_log_slope",
                "observation.ion_heteroscedastic_log_slope",
            ),
            (0.5, 2.0),
            (0.1, 0.08),
        ),
        (
            "S021_limits",
            "multiplier",
            tuple(
                scenario + f"censoring.{map_name}.{endpoint_id}"
                for map_name in ("lod_by_endpoint", "loq_by_endpoint")
                for endpoint_id in limits
            ),
            (0.5, 2.0),
            (
                0.01,
                0.01,
                0.01,
                0.005,
                0.0005,
                0.005,
                0.1,
                0.1,
                0.03,
                0.03,
                0.03,
                0.015,
                0.0015,
                0.015,
                0.3,
                0.3,
            ),
        ),
        (
            "S022_limit_variation",
            "log-ratio",
            tuple(
                scenario + f"censoring.{map_name}.{endpoint_id}"
                for map_name in (
                    "lod_log_sd_by_endpoint",
                    "loq_log_sd_by_endpoint",
                )
                for endpoint_id in limits
            ),
            (0.0, 0.025, 0.1),
            (0.05,) * 16,
        ),
        ("S023_calibration_interval", "day", paths("drift.calibration_interval_days"), (3.5, 14.0), (7.0,)),
        (
            "S024_drift_residuals",
            "multiplier",
            tuple(
                scenario
                + "drift.post_calibration_residual_sd_by_endpoint."
                + endpoint_id
                for endpoint_id in endpoints
            ),
            (0.5, 2.0),
            (0.005, 0.01, 0.01, 0.01, 0.01, 0.01, 0.01, 0.01, 0.25, 0.01),
        ),
        (
            "S025_death_heterogeneity",
            "log-ratio",
            paths(
                "death.biomass_death_threshold_log_sd",
                "death.injury_death_threshold_log_sd",
                "death.sustained_injury_duration_log_sd",
            ),
            (0.0, 0.05, 0.2, 0.3),
            (0.1, 0.1, 0.1),
        ),
        ("S026_missingness_intercept", "logit", paths("missingness.missingness_intercept"), (-4.0, -2.0), (-3.0,)),
        ("S027_mar_slope", "logit/SD", paths("missingness.missingness_stress_slope"), (0.0, 0.4, 0.8), (0.2,)),
        ("S028_mnar_delta", "logit/SD", paths("missingness.mnar_tipping_delta"), (-0.2, -0.1, 0.0, 0.2), (0.1,)),
        ("S029_parameter_xtol", "dimensionless", paths("calibration.parameter_xtol"), (1e-8, 1e-4), (1e-6,)),
        ("S030_parameter_rtol", "dimensionless", paths("calibration.parameter_rtol"), (1e-8, 1e-4), (1e-6,)),
        (
            "S031_panel_size",
            "count",
            paths("calibration.fit_panel_size", "calibration.holdout_panel_size"),
            (32, 128),
            (64, 64),
        ),
        ("S032_holdout_tolerance", "log-ratio", paths("calibration.holdout_tolerance_log_ratio"), (0.01, 0.05), (0.02,)),
        ("S033_confirmation_cell", "count", paths("design.confirmation_plants_per_group_reservoir"), (5,), (6,)),
        (
            "S034_chassis_modifier",
            "dimensionless",
            (
                selected
                + "chassis_interaction].mechanism."
                "candidate_chassis_mechanism_modifiers.C5."
                "xylem_na_retrieval_multiplier.factor",
            ),
            (0.6, 1.0),
            (0.8,),
        ),
        (
            "S035_delayed_onset",
            "day",
            (selected + "delayed_toxicity].mechanism.onset_time_days",),
            (28.0, 56.0),
            (42.0,),
        ),
        (
            "S036_insufficient_purge",
            "L day^-1",
            (
                selected
                + "insufficient_purge].generator.water_loop.purge_volume_l_day",
            ),
            (0.0, 0.3),
            (0.12,),
        ),
    )


_REGISTERED_TASK4_SENSITIVITY_AUTHORITY = _task4_sensitivity_authority()
_REGISTERED_TASK4_SENSITIVITY_BY_ID = MappingProxyType(
    {row[0]: row for row in _REGISTERED_TASK4_SENSITIVITY_AUTHORITY}
)


def _task4_capacity_sensitivity_bindings() -> Mapping[
    str,
    tuple[str, str, str | None, tuple[float, ...]],
]:
    """Derive the frozen capacity set from exact registered water-loop paths."""

    anchor_prefix = _TASK4_SENSITIVITY_SCENARIO_PREFIX + "water_loop."
    scenario_marker = "].generator.water_loop."
    water_loop_fields = frozenset(
        name for name, _, _ in _TASK4_WATER_LOOP_AUTHORITY
    )
    bindings: dict[
        str,
        tuple[str, str, str | None, tuple[float, ...]],
    ] = {}
    for sensitivity_id, _, paths, values, _ in (
        _REGISTERED_TASK4_SENSITIVITY_AUTHORITY
    ):
        if len(paths) != 1:
            continue
        path = paths[0]
        target_scenario_id: str | None
        if path.startswith(anchor_prefix):
            field_name = path[len(anchor_prefix) :]
            target_scenario_id = None
        elif path.startswith(_TASK4_SENSITIVITY_SCENARIO_SELECTOR_PREFIX):
            selector = path[len(_TASK4_SENSITIVITY_SCENARIO_SELECTOR_PREFIX) :]
            target_scenario_id, marker, field_name = selector.partition(
                scenario_marker
            )
            if not marker or not target_scenario_id:
                continue
        else:
            continue
        if field_name not in water_loop_fields:
            continue
        if any(type(value) is not float for value in values):
            raise AssertionError("water-loop sensitivity values must be floats")
        bindings[sensitivity_id] = (
            path,
            field_name,
            target_scenario_id,
            values,  # type: ignore[arg-type]
        )
    if tuple(bindings) != (
        "S013_initial_volume",
        "S014_return_fraction",
        "S015_irrigation",
        "S016_anchor_purge",
        "S017_sample_volume",
        "S036_insufficient_purge",
    ):
        raise AssertionError("registered water-loop sensitivity set changed")
    return MappingProxyType(bindings)


_TASK4_CAPACITY_SENSITIVITY_BINDINGS = _task4_capacity_sensitivity_bindings()


def _canonical_task4_capacity_sensitivity_binding(
    binding: object,
) -> tuple[str, float]:
    if (
        type(binding) is not tuple
        or len(binding) != 3
        or type(binding[0]) is not str
        or type(binding[1]) is not str
        or type(binding[2]) is not float
    ):
        fail(
            "WATER_BATCH_GENERATOR_INVALID",
            "capacity sensitivity binding must be an exact ID/path/value tuple",
            "registered_sensitivity_binding",
        )
    sensitivity_id, path, value = binding
    registered = _TASK4_CAPACITY_SENSITIVITY_BINDINGS.get(sensitivity_id)
    if registered is None:
        fail(
            "WATER_BATCH_GENERATOR_INVALID",
            "capacity sensitivity ID is not a registered water-loop sensitivity",
            "registered_sensitivity_binding",
        )
    registered_path, field_name, _, registered_values = registered
    if path != registered_path or not any(
        _same_registered_number(value, candidate)
        for candidate in registered_values
    ):
        fail(
            "WATER_BATCH_GENERATOR_INVALID",
            "capacity sensitivity path or value differs from the registration",
            "registered_sensitivity_binding",
        )
    return field_name, value


REGISTERED_TASK4_SCENARIO_REGISTRY_SHA256 = (
    "36033d8d58b65cc5647c0139ba4bebf92250cf9d8a7c08eba81f54b89ea10e51"
)
REGISTERED_TASK4_SCENARIO_MODEL_SHA256 = (
    "4229e855bcf783d994ce24f6dc98d1dc8eded92f5134f854880cb44204f6150a"
)


class SensitivityRecord(StrictPaper1Model):
    """One exact, prospective, one-at-a-time Task 4 sensitivity record."""

    sensitivity_id: str
    mode: Literal["one_at_a_time"]
    paths: tuple[str, ...]
    values: tuple[int | float, ...]
    unit: str
    anchor_value: tuple[int | float, ...]
    evidence_label: Literal[EvidenceLabel.HYPOTHESIS_PRIOR]

    @model_validator(mode="before")
    @classmethod
    def require_primitive_registration(cls, value: object) -> object:
        if type(value) not in (dict, _MAPPING_PROXY_TYPE):
            raise ValueError("sensitivity record requires a primitive mapping")
        required = tuple(cls.model_fields)
        if tuple(value) != required:
            raise ValueError("sensitivity record fields and order are frozen")
        sensitivity_id = value.get("sensitivity_id")
        mode = value.get("mode")
        unit = value.get("unit")
        evidence_label = value.get("evidence_label")
        paths = value.get("paths")
        values = value.get("values")
        anchors = value.get("anchor_value")
        if (
            type(sensitivity_id) is not str
            or sensitivity_id not in _REGISTERED_TASK4_SENSITIVITY_BY_ID
            or type(mode) is not str
            or mode != "one_at_a_time"
            or type(unit) is not str
            or type(evidence_label) not in (str, EvidenceLabel)
            or evidence_label != EvidenceLabel.HYPOTHESIS_PRIOR
            or type(paths) not in (list, tuple)
            or type(values) not in (list, tuple)
            or type(anchors) not in (list, tuple)
        ):
            raise ValueError("sensitivity registration has invalid primitive types")
        numeric_type = int if unit == "count" else float
        for collection in (values, anchors):
            if not collection or any(type(item) is not numeric_type for item in collection):
                raise ValueError("sensitivity numeric types must be exact")
            if numeric_type is int:
                if any(item < 0 or item > MAX_INTEROPERABLE_JSON_INTEGER for item in collection):
                    raise ValueError("sensitivity counts exceed the safe integer domain")
            elif any(not isfinite(item) for item in collection):
                raise ValueError("sensitivity values must be finite")
        if (
            not paths
            or any(
                type(path) is not str
                or not path
                or path != path.strip()
                or "::" not in path
                or "*" in path
                or "..." in path
                for path in paths
            )
            or len(set(paths)) != len(paths)
        ):
            raise ValueError("sensitivity paths must be unique literal document paths")
        return value

    @model_validator(mode="after")
    def require_exact_registered_record(self) -> "SensitivityRecord":
        expected = _REGISTERED_TASK4_SENSITIVITY_BY_ID[self.sensitivity_id]
        observed = (
            self.sensitivity_id,
            self.unit,
            self.paths,
            self.values,
            self.anchor_value,
        )
        if observed != expected:
            raise ValueError("sensitivity record differs from prospective authority")
        if len(self.anchor_value) != len(self.paths):
            raise ValueError("sensitivity anchors must align one-for-one with paths")
        return self


def _sensitivity_record_signature(record: SensitivityRecord) -> tuple[object, ...]:
    return (
        record.sensitivity_id,
        record.unit,
        record.paths,
        record.values,
        record.anchor_value,
    )


class SensitivityRegistry(StrictPaper1Model):
    """The complete prospective Task 4 sensitivity authority."""

    schema_version: Literal["1.0.0"]
    records: tuple[SensitivityRecord, ...]

    @model_validator(mode="after")
    def require_complete_authority(self) -> "SensitivityRegistry":
        observed = tuple(_sensitivity_record_signature(record) for record in self.records)
        if observed != _REGISTERED_TASK4_SENSITIVITY_AUTHORITY:
            raise ValueError("sensitivity registry must equal all 36 registered records")
        paths = tuple(path for record in self.records for path in record.paths)
        if len(paths) != 84 or len(set(paths)) != 84:
            raise ValueError("sensitivity registry must contain 84 unique literal paths")
        return self


class SyntheticScenarioRegistry(StrictPaper1Model):
    schema_version: Literal["1.4.0"]
    water_recipe_registry_sha256: str
    anchor: SyntheticScenarioConfig
    scenarios: tuple[SyntheticScenarioConfig, ...]
    sensitivities: tuple[SensitivityRecord, ...] = ()

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
        if any(
            item.evidence_label is not EvidenceLabel.SYNTHETIC_ONLY
            for item in self.all_scenarios
        ):
            raise ValueError("all ten Task 4 scenarios must be synthetic_only")
        anchor_inputs = tuple(
            canonical_json_bytes(_registered_json_value(value))
            for value in (
                self.anchor.parameters,
                self.anchor.initial_state,
                self.anchor.forcings_by_water_id,
            )
        )
        for scenario in self.scenarios:
            observed_inputs = tuple(
                canonical_json_bytes(_registered_json_value(value))
                for value in (
                    scenario.parameters,
                    scenario.initial_state,
                    scenario.forcings_by_water_id,
                )
            )
            if observed_inputs != anchor_inputs:
                raise ValueError(
                    "non-anchor scenario base biology, state, and forcings "
                    "must equal the anchor"
                )
            if (
                scenario.mechanism.onset_time_days is not None
                and scenario.mechanism.onset_time_days.value
                > scenario.generator.design.duration_days.value
            ):
                raise ValueError("scenario onset must fall within the design")
        if self.sensitivities:
            observed_sensitivities = tuple(
                _sensitivity_record_signature(record)
                for record in self.sensitivities
            )
            if observed_sensitivities != _REGISTERED_TASK4_SENSITIVITY_AUTHORITY:
                raise ValueError("scenario sensitivities differ from the registration")
        return self

    @property
    def all_scenarios(self) -> tuple[SyntheticScenarioConfig, ...]:
        return (self.anchor, *self.scenarios)

    @model_serializer(mode="plain")
    def serialize_registered_registry(self) -> dict[str, object]:
        return _registered_json_value(self)  # type: ignore[return-value]


@dataclass(frozen=True)
class AppliedSensitivity:
    """Detached, validated authority pair for one registered sensitivity run."""

    run_id: str
    sensitivity_id: str
    value_index: int
    selected_value: int | float
    scenario_registry: SyntheticScenarioRegistry
    recipe_registry: Paper1WaterRecipeRegistry
    applied_paths: tuple[str, ...]
    applied_values: tuple[int | float, ...]
    calibration_panel_sha256s: Mapping[str, str]
    capacity_audits: tuple[SharedSourceBatchCapacityAudit, ...]


_TASK4_SENSITIVITY_PANEL_SHA256S = MappingProxyType(
    {
        32: MappingProxyType(
            {
                "fit": "8b042b703b1c5148886182b344317986776fef8d68e795688741f74d54d790e3",
                "holdout": "80224dfe438556e8caa0ae561d79649acf465d8c09218bd429edb7d1bbc5f41a",
            }
        ),
        128: MappingProxyType(
            {
                "fit": "91b9c4d937b0417097f6e4b7272eff4efcf4a6dfdc23e76c73876a7e5ae02cc9",
                "holdout": "3df1fde7553bd5942a195e67eb7438f501e6ce6df3bd22f08397b623f5b97f11",
            }
        ),
    }
)


def _sensitivity_invalid(
    message: str,
    field_path: str = "registry",
    details: dict[str, object] | None = None,
) -> None:
    fail("SENSITIVITY_REGISTRY_INVALID", message, field_path, details)


def _canonical_sensitivity_registry(authority: object) -> SensitivityRegistry:
    if type(authority) is not SensitivityRegistry:
        _sensitivity_invalid(
            "sensitivity authority must be an exact SensitivityRegistry",
            details={"received_type": type(authority).__name__},
        )
    try:
        return SensitivityRegistry.model_validate(_registered_json_value(authority))
    except Exception as error:
        _sensitivity_invalid(
            "sensitivity authority failed complete reconstruction",
            details={"cause_type": type(error).__name__},
        )


def _canonical_sensitivity_scenarios(
    registry: object,
) -> SyntheticScenarioRegistry:
    if type(registry) is not SyntheticScenarioRegistry:
        _sensitivity_invalid(
            "scenario authority must be an exact SyntheticScenarioRegistry",
            "scenario_registry",
            {"received_type": type(registry).__name__},
        )
    try:
        checked = SyntheticScenarioRegistry.model_validate(
            _registered_json_value(registry)
        )
    except Exception as error:
        _sensitivity_invalid(
            "scenario authority failed complete reconstruction",
            "scenario_registry",
            {"cause_type": type(error).__name__},
        )
    if len(checked.sensitivities) != 36:
        _sensitivity_invalid(
            "scenario authority omits the complete sensitivity registry",
            "scenario_registry.sensitivities",
        )
    digest = hashlib.sha256(
        canonical_json_bytes(_registered_json_value(checked))
    ).hexdigest()
    if digest != REGISTERED_TASK4_SCENARIO_MODEL_SHA256:
        _sensitivity_invalid(
            "scenario authority differs from the canonical nominal registry",
            "scenario_registry",
            {"received_sha256": digest},
        )
    return checked


def _sensitivity_target(
    documents: Mapping[str, dict[str, object]], path: str
) -> tuple[dict[str, object], str]:
    try:
        document_id, expression = path.split("::", 1)
        current: object = documents[document_id]
        segments = expression.split(".")
        for segment in segments[:-1]:
            if "[" in segment:
                collection_id, selector = segment.split("[", 1)
                selector = selector.removesuffix("]")
                selector_field, selector_value = selector.split("=", 1)
                if type(current) is not dict:
                    raise TypeError("selector parent is not a mapping")
                collection = current[collection_id]
                if type(collection) is not list:
                    raise TypeError("selector target is not a list")
                matches = [
                    row
                    for row in collection
                    if type(row) is dict and row.get(selector_field) == selector_value
                ]
                if len(matches) != 1:
                    raise KeyError("selector does not identify exactly one row")
                current = matches[0]
            else:
                if type(current) is not dict:
                    raise TypeError("path parent is not a mapping")
                current = current[segment]
        if type(current) is not dict:
            raise TypeError("leaf parent is not a mapping")
        leaf = segments[-1]
        if leaf not in current:
            raise KeyError(leaf)
        target = current[leaf]
        if type(target) is dict and tuple(target) == (
            "value",
            "unit",
            "evidence_label",
        ):
            return target, "value"
        return current, leaf
    except (KeyError, TypeError, ValueError) as error:
        _sensitivity_invalid(
            "registered sensitivity path could not be resolved literally",
            path,
            {"cause_type": type(error).__name__},
        )


def _same_registered_number(left: object, right: int | float) -> bool:
    if type(left) is not type(right):
        return False
    if type(right) is float:
        return left.hex() == right.hex()  # type: ignore[union-attr]
    return left == right


def apply_registered_sensitivity(
    authority: SensitivityRegistry,
    *,
    scenario_registry: SyntheticScenarioRegistry,
    recipe_registry: Paper1WaterRecipeRegistry,
    selections: tuple[tuple[str, int], ...],
    occupied_run_ids: frozenset[str] = frozenset(),
    capacity_authorities: tuple[
        tuple[object, object, object, object], ...
    ] = (),
    stop_policy: Task4StopPolicy,
) -> AppliedSensitivity:
    """Apply exactly one registered scalar to its complete literal path bundle."""

    checked_authority = _canonical_sensitivity_registry(authority)
    checked_scenarios = _canonical_sensitivity_scenarios(scenario_registry)
    try:
        checked_recipes = _canonical_water_recipe_registry(recipe_registry)
    except AlmondLabError as error:
        _sensitivity_invalid(
            "recipe authority failed complete reconstruction",
            "recipe_registry",
            {"cause_code": error.code},
        )
    try:
        checked_policy = _canonical_task4_stop_policy(stop_policy)
    except AlmondLabError as error:
        _sensitivity_invalid(
            "stop authority failed complete reconstruction",
            "stop_policy",
            {"cause_code": error.code},
        )
    if (
        type(selections) is not tuple
        or len(selections) != 1
        or type(selections[0]) is not tuple
        or len(selections[0]) != 2
        or type(selections[0][0]) is not str
        or type(selections[0][1]) is not int
    ):
        _sensitivity_invalid(
            "one run must select exactly one registered ID and one value index",
            "selections",
        )
    sensitivity_id, value_index = selections[0]
    records = {
        record.sensitivity_id: record for record in checked_authority.records
    }
    if sensitivity_id not in records:
        _sensitivity_invalid("selected sensitivity ID is not registered", "selections")
    record = records[sensitivity_id]
    if value_index < 0 or value_index >= len(record.values):
        _sensitivity_invalid("selected sensitivity index is out of range", "selections")
    if type(occupied_run_ids) is not frozenset or any(
        type(run_id) is not str for run_id in occupied_run_ids
    ):
        _sensitivity_invalid("occupied run IDs must be an exact string frozenset", "occupied_run_ids")
    run_id = f"{sensitivity_id}__value_{value_index}"
    if run_id in occupied_run_ids:
        _sensitivity_invalid("derived sensitivity run ID already exists", "run_id")
    if type(capacity_authorities) is not tuple or any(
        type(item) is not tuple or len(item) != 4
        for item in capacity_authorities
    ):
        _sensitivity_invalid(
            "capacity authorities must be exact four-authority tuples",
            "capacity_authorities",
        )
    capacity_binding = _TASK4_CAPACITY_SENSITIVITY_BINDINGS.get(
        sensitivity_id
    )
    if capacity_binding is not None and not capacity_authorities:
        _sensitivity_invalid(
            "registered water-loop sensitivity requires capacity authority",
            "capacity_authorities",
        )

    scenario_payload = _registered_json_value(checked_scenarios)
    recipe_payload = _registered_json_value(checked_recipes)
    if type(scenario_payload) is not dict or type(recipe_payload) is not dict:
        raise AssertionError("registered sensitivity documents must serialize to maps")
    documents = {
        "configs/synthetic_scenarios.yaml": scenario_payload,
        "configs/paper1_water_recipes.yaml": recipe_payload,
    }

    # Revalidate every registered anchor, not merely the selected record, before
    # writing any detached output tree.
    for authority_record in checked_authority.records:
        for path, expected_anchor in zip(
            authority_record.paths, authority_record.anchor_value, strict=True
        ):
            container, key = _sensitivity_target(documents, path)
            if not _same_registered_number(container[key], expected_anchor):
                _sensitivity_invalid(
                    "current target differs bit-exactly from its registered anchor",
                    path,
                )

    selected_value = record.values[value_index]
    applied_values: list[int | float] = []
    for path, anchor in zip(record.paths, record.anchor_value, strict=True):
        replacement: int | float
        if record.unit == "multiplier":
            replacement = anchor * selected_value
            if type(anchor) is float:
                replacement = float(replacement)
        else:
            replacement = selected_value
        container, key = _sensitivity_target(documents, path)
        container[key] = replacement
        applied_values.append(replacement)

    try:
        applied_scenarios = SyntheticScenarioRegistry.model_validate(
            scenario_payload
        )
        recipe_context = None
        if sensitivity_id == "S001_charge_tolerance":
            recipe_context = {
                "registered_sensitivity_charge_balance_tolerance_percent": float(
                    selected_value
                )
            }
        applied_recipes = Paper1WaterRecipeRegistry.model_validate(
            recipe_payload,
            context=recipe_context,
        )
    except Exception as error:
        _sensitivity_invalid(
            "registered sensitivity produced an invalid detached authority",
            "application",
            {"cause_type": type(error).__name__},
        )

    capacity_audits: tuple[SharedSourceBatchCapacityAudit, ...] = ()
    if capacity_authorities:
        capacity_water_loop = applied_scenarios.anchor.generator.water_loop
        registered_capacity_binding = None
        if capacity_binding is not None:
            registered_path, _, target_scenario_id, registered_values = (
                capacity_binding
            )
            if record.paths != (registered_path,) or not any(
                _same_registered_number(selected_value, candidate)
                for candidate in registered_values
            ):
                _sensitivity_invalid(
                    "capacity sensitivity selection differs from its literal registration",
                    "selections",
                )
            if target_scenario_id is not None:
                targets = tuple(
                    scenario
                    for scenario in applied_scenarios.scenarios
                    if scenario.scenario_id.value == target_scenario_id
                )
                if len(targets) != 1:
                    _sensitivity_invalid(
                        "capacity sensitivity target scenario is unavailable",
                        registered_path,
                    )
                capacity_water_loop = targets[0].generator.water_loop
            registered_capacity_binding = (
                sensitivity_id,
                registered_path,
                float(selected_value),
            )
        for config, baseline_roster, position_map, manifest in capacity_authorities:
            capacity_audits += preflight_shared_source_batch_capacity(
                checked_policy,
                config=config,  # type: ignore[arg-type]
                baseline_roster=baseline_roster,  # type: ignore[arg-type]
                position_map=position_map,  # type: ignore[arg-type]
                manifest=manifest,  # type: ignore[arg-type]
                recipe_registry=checked_recipes,
                water_loop=capacity_water_loop,
                registered_sensitivity_binding=registered_capacity_binding,
            )

    panel_sha256s: Mapping[str, str] = MappingProxyType({})
    if sensitivity_id == "S031_panel_size":
        panel_sha256s = _TASK4_SENSITIVITY_PANEL_SHA256S[int(selected_value)]
    return AppliedSensitivity(
        run_id=run_id,
        sensitivity_id=sensitivity_id,
        value_index=value_index,
        selected_value=selected_value,
        scenario_registry=applied_scenarios,
        recipe_registry=applied_recipes,
        applied_paths=record.paths,
        applied_values=tuple(applied_values),
        calibration_panel_sha256s=panel_sha256s,
        capacity_audits=capacity_audits,
    )


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


REGISTERED_V13_SCENARIO_RAW_SHA256 = (
    "46286eb006fbfbaf13281dfe52d4c63c9dc00ff7b3ef0a8ee704146908f759cb"
)
REGISTERED_V13_SCENARIO_NORMALIZED_SHA256 = (
    "70138e7522ffb107285d7f1ba9d6e8a995bd44198a56f77f33c1c435f33eae63"
)
REGISTERED_V13_MIGRATION_ITEM_COUNT = 2021
REGISTERED_V13_MIGRATION_INVENTORY_SHA256 = (
    "e9c438aa08ea101c4f981187b221da8bf9df0273c4dcd8050f3d1661d040ac0c"
)


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
                    f"h3_observation_error_by_endpoint.{candidate}.error_sd"
                    for candidate in ("C1", "C2", "C4", "C5", "C6")
                ),
                (
                    "anchor.generator.observation."
                    "h3_observation_error_by_endpoint.C3.error_sd",
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
        scenario_prefix = f"scenarios[scenario_id={scenario_id}]"
        if suffix.startswith("parameters."):
            if (
                scenario_id == "chassis_interaction"
                and suffix == "parameters.root_conductance_l_day_mpa"
            ):
                return (
                    MigrationDisposition.RETIRED,
                    (),
                    (),
                    "Retire the explicitly withdrawn global conductance edit.",
                )
            return (
                MigrationDisposition.PRESERVED,
                (f"{scenario_prefix}.{suffix}",),
                (),
                "Preserve the expanded biology value in the detached scenario baseline.",
            )
        if suffix.startswith("initial_state."):
            return (
                MigrationDisposition.PRESERVED,
                (f"{scenario_prefix}.{suffix}",),
                (),
                "Preserve the expanded initial-state value in the detached scenario baseline.",
            )
        if suffix.startswith("forcing."):
            return (
                MigrationDisposition.RETIRED,
                (),
                (),
                "Retire the explicitly withdrawn one-water scenario forcing authority.",
            )
        if suffix.startswith("generator_parameters."):
            name = suffix.removeprefix("generator_parameters.")
            if name == "h3_observation_error_sd":
                return (
                    MigrationDisposition.SPLIT_REQUIRES_REGISTRATION,
                    tuple(
                        f"{scenario_prefix}.generator.observation."
                        f"h3_observation_error_by_endpoint.{candidate}.error_sd"
                        for candidate in ("C1", "C2", "C4", "C5", "C6")
                    ),
                    (
                        f"{scenario_prefix}.generator.observation."
                        "h3_observation_error_by_endpoint.C3.error_sd",
                    ),
                    "Split the expanded legacy H3 scalar by candidate endpoint.",
                )
            destination = _LEGACY_GENERATOR_DESTINATIONS.get(name)
            if destination is None:
                return (
                    MigrationDisposition.OWNER_REQUIRED,
                    (),
                    (source_path,),
                    "Require classification for an unknown expanded generator value.",
                )
            return (
                MigrationDisposition.RETYPED_WITH_UNIT,
                (destination.replace("anchor", scenario_prefix, 1),),
                (),
                "Retype the expanded generator scalar in the detached scenario.",
            )
        return (
            MigrationDisposition.OWNER_REQUIRED,
            (),
            (source_path,),
            "Require explicit classification for an unknown expanded scenario leaf.",
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
    return SyntheticScenarioRegistry.model_validate(_registered_json_value(registry))


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
        _registered_json_value(source)
    )
    inventory_sha256 = hashlib.sha256(
        canonical_json_bytes(_registered_json_value(checked_source))
    ).hexdigest()
    if (
        checked_source.source_raw_sha256 != REGISTERED_V13_SCENARIO_RAW_SHA256
        or checked_source.source_normalized_sha256
        != REGISTERED_V13_SCENARIO_NORMALIZED_SHA256
        or len(checked_source.items) != REGISTERED_V13_MIGRATION_ITEM_COUNT
        or inventory_sha256 != REGISTERED_V13_MIGRATION_INVENTORY_SHA256
    ):
        fail(
            "SCENARIO_MIGRATION_INVALID",
            "source inventory does not equal the pinned whole-archive authority",
            "source",
            {
                "item_count": len(checked_source.items),
                "inventory_sha256": inventory_sha256,
            },
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
                                    destination.rsplit("[", 1)[0],
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


TASK4_MAX_YAML_DEPTH = 64
TASK4_MAX_YAML_NODES = 175_000
TASK4_MAX_YAML_BYTES = 3_500_000


class YamlMergeKeyError(yaml.YAMLError):
    """A Task 4 authority attempted to use YAML merge semantics."""


class YamlAliasReferenceError(yaml.YAMLError):
    """A Task 4 authority attempted to use a YAML alias."""


class YamlAnchorDefinitionError(yaml.YAMLError):
    """A Task 4 authority attempted to define hidden YAML identity."""


class YamlResourceLimitError(yaml.YAMLError):
    """A Task 4 YAML stream exceeds its narrowly registered resource budget."""

    def __init__(self, resource: str, limit: int, observed: int) -> None:
        super().__init__(f"Task 4 YAML {resource} exceeds {limit}")
        self.resource = resource
        self.limit = limit
        self.observed = observed


def _task4_yaml_graph_has_cycle(root: yaml.nodes.Node) -> bool:
    active: set[int] = set()
    complete: set[int] = set()
    stack: list[tuple[yaml.nodes.Node, bool]] = [(root, False)]
    while stack:
        node, exiting = stack.pop()
        identity = id(node)
        if exiting:
            active.remove(identity)
            complete.add(identity)
            continue
        if identity in active:
            return True
        if identity in complete:
            continue
        active.add(identity)
        stack.append((node, True))
        if isinstance(node, yaml.nodes.MappingNode):
            children = tuple(
                child for pair in node.value for child in pair
            )
        elif isinstance(node, yaml.nodes.SequenceNode):
            children = tuple(node.value)
        else:
            children = ()
        for child in reversed(children):
            stack.append((child, False))
    return False


class _Task4SafeLoader(yaml.SafeLoader):
    """Alias-free loader with exact primitive string keys and duplicates denied."""

    def construct_mapping(
        self, node: yaml.nodes.MappingNode, deep: bool = False
    ) -> dict[str, object]:
        if not isinstance(node, yaml.nodes.MappingNode):
            raise yaml.constructor.ConstructorError(
                None,
                None,
                "expected a mapping node",
                node.start_mark,
            )
        mapping: dict[str, object] = {}
        for key_node, value_node in node.value:
            if (
                not isinstance(key_node, yaml.nodes.ScalarNode)
                or key_node.tag != "tag:yaml.org,2002:str"
            ):
                raise yaml.YAMLError("Task 4 YAML keys must be primitive strings")
            key = key_node.value
            if key in mapping:
                raise YamlDuplicateKeyError(key, key_node)
            mapping[key] = self.construct_object(value_node, deep=deep)
        return mapping


def _task4_strict_yaml_load(stream: str) -> object:
    """Load the explicit v1.4 authority under its separate 175k-node cap."""

    byte_count = len(stream.encode("utf-8"))
    if byte_count > TASK4_MAX_YAML_BYTES:
        raise YamlResourceLimitError(
            "bytes", TASK4_MAX_YAML_BYTES, byte_count
        )

    _, anchors, aliases, merges = _scan_task4_yaml_stream(stream)
    if merges:
        raise YamlMergeKeyError("Task 4 YAML merge keys are forbidden")
    if aliases:
        # The scanner has already bounded depth/nodes. Compose only the small
        # rejected graph so a cycle receives its stable specific error.
        root = yaml.compose(stream, Loader=yaml.SafeLoader)
        if root is not None and _task4_yaml_graph_has_cycle(root):
            raise YamlAliasCycleError(root)
        raise YamlAliasReferenceError("Task 4 YAML aliases are forbidden")
    if anchors:
        raise YamlAnchorDefinitionError("Task 4 YAML anchors are forbidden")
    return yaml.load(stream, Loader=_Task4SafeLoader)


def _scan_task4_yaml_stream(stream: str) -> tuple[tuple[yaml.Token, ...], int, int, int]:
    """Scan once under the Task 4 node/depth budget before composition."""

    depth = 0
    nodes = 0
    maximum_depth = 0
    anchors = 0
    aliases = 0
    merges = 0
    tokens: list[yaml.Token] = []
    start_tokens = (
        yaml.tokens.BlockMappingStartToken,
        yaml.tokens.BlockSequenceStartToken,
        yaml.tokens.FlowMappingStartToken,
        yaml.tokens.FlowSequenceStartToken,
    )
    end_tokens = (
        yaml.tokens.BlockEndToken,
        yaml.tokens.FlowMappingEndToken,
        yaml.tokens.FlowSequenceEndToken,
    )
    for token in yaml.scan(stream, Loader=yaml.SafeLoader):
        tokens.append(token)
        if isinstance(token, start_tokens):
            depth += 1
            maximum_depth = max(maximum_depth, depth)
            nodes += 1
        elif isinstance(token, end_tokens):
            depth -= 1
        elif isinstance(token, (yaml.tokens.ScalarToken, yaml.tokens.AliasToken)):
            nodes += 1
        anchors += int(isinstance(token, yaml.tokens.AnchorToken))
        aliases += int(isinstance(token, yaml.tokens.AliasToken))
        merges += int(
            isinstance(token, yaml.tokens.ScalarToken) and token.value == "<<"
        )
        if maximum_depth > TASK4_MAX_YAML_DEPTH:
            raise YamlResourceLimitError(
                "depth", TASK4_MAX_YAML_DEPTH, maximum_depth
            )
        if nodes > TASK4_MAX_YAML_NODES:
            raise YamlResourceLimitError(
                "nodes", TASK4_MAX_YAML_NODES, nodes
            )
    return tuple(tokens), anchors, aliases, merges


def _load_task4_yaml_mapping(path: str | Path) -> dict[str, object]:
    try:
        stream = _read_task4_yaml_stream(path)
        payload = _task4_strict_yaml_load(stream)
    except YamlDuplicateKeyError as error:
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
    except (
        OSError,
        TypeError,
        ValueError,
        UnicodeError,
        yaml.YAMLError,
        RecursionError,
        MemoryError,
    ) as error:
        _scenario_invalid(
            "synthetic scenario YAML could not be safely loaded",
            "yaml",
            cause=error,
        )
    if type(payload) is not dict:
        _scenario_invalid("synthetic scenario YAML must be a mapping", "yaml")
    return payload


def _read_task4_yaml_stream(path: str | Path) -> str:
    """Reject an oversized Task 4 authority before allocating or decoding it."""

    source = Path(path)
    try:
        observed_bytes = source.stat().st_size
    except OSError as error:
        _scenario_invalid(
            "synthetic scenario YAML could not be inspected",
            "yaml",
            cause=error,
        )
    if observed_bytes > TASK4_MAX_YAML_BYTES:
        _scenario_invalid(
            "synthetic scenario YAML exceeds its registered byte budget",
            "yaml",
            cause=YamlResourceLimitError(
                "bytes", TASK4_MAX_YAML_BYTES, observed_bytes
            ),
        )
    try:
        with source.open("rb") as handle:
            raw = handle.read(TASK4_MAX_YAML_BYTES + 1)
        if len(raw) > TASK4_MAX_YAML_BYTES:
            raise YamlResourceLimitError(
                "bytes", TASK4_MAX_YAML_BYTES, len(raw)
            )
        return raw.decode("utf-8")
    except (OSError, UnicodeError, YamlResourceLimitError) as error:
        _scenario_invalid(
            "synthetic scenario YAML could not be safely read",
            "yaml",
            cause=error,
        )


def _declared_scenario_schema_version(stream: str) -> str | None:
    """Read only an explicit root mapping key after bounded token scanning."""

    tokens, _, _, _ = _scan_task4_yaml_stream(stream)
    root_depth = 0
    root_mapping_started = False
    expecting_root_key = False
    pending_schema_value = False
    values: list[tuple[str, yaml.Token]] = []
    start_tokens = (
        yaml.tokens.BlockMappingStartToken,
        yaml.tokens.BlockSequenceStartToken,
        yaml.tokens.FlowMappingStartToken,
        yaml.tokens.FlowSequenceStartToken,
    )
    end_tokens = (
        yaml.tokens.BlockEndToken,
        yaml.tokens.FlowMappingEndToken,
        yaml.tokens.FlowSequenceEndToken,
    )
    for token in tokens:
        if isinstance(token, start_tokens):
            root_depth += 1
            if not root_mapping_started:
                root_mapping_started = isinstance(
                    token,
                    (yaml.tokens.BlockMappingStartToken, yaml.tokens.FlowMappingStartToken),
                )
            continue
        if isinstance(token, end_tokens):
            root_depth -= 1
            continue
        if not root_mapping_started or root_depth != 1:
            continue
        if isinstance(token, yaml.tokens.KeyToken):
            expecting_root_key = True
            pending_schema_value = False
            continue
        if expecting_root_key and isinstance(token, yaml.tokens.ScalarToken):
            pending_schema_value = token.value == "schema_version"
            expecting_root_key = False
            continue
        if pending_schema_value and isinstance(token, yaml.tokens.ValueToken):
            continue
        if pending_schema_value and isinstance(token, yaml.tokens.ScalarToken):
            values.append((token.value, token))
            pending_schema_value = False
    if len(values) > 1:
        duplicate = values[1][1]
        node = yaml.nodes.ScalarNode(
            "tag:yaml.org,2002:str",
            "schema_version",
            start_mark=duplicate.start_mark,
            end_mark=duplicate.end_mark,
        )
        raise YamlDuplicateKeyError("schema_version", node)
    return values[0][0] if values else None


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


def _canonical_water_recipe_registry(
    registry: object,
) -> Paper1WaterRecipeRegistry:
    if type(registry) is not Paper1WaterRecipeRegistry:
        fail(
            "PAPER1_WATER_RECIPE_INVALID",
            "recipe registry must be a validated Paper1WaterRecipeRegistry",
            "registry",
            {"received_type": type(registry).__name__},
        )
    try:
        return Paper1WaterRecipeRegistry.model_validate(_registered_json_value(registry))
    except Exception as error:
        fail(
            "PAPER1_WATER_RECIPE_INVALID",
            "recipe registry failed complete authority revalidation",
            "registry",
            {"cause_type": type(error).__name__},
        )


def _canonical_paper1_design(design: object) -> Paper1DesignConfig:
    if not isinstance(design, Paper1DesignConfig):
        fail(
            "PAPER1_WATER_RECIPE_INVALID",
            "design must be a validated Paper1DesignConfig",
            "design",
            {"received_type": type(design).__name__},
        )
    try:
        return Paper1DesignConfig.model_validate(_registered_json_value(design))
    except Exception as error:
        fail(
            "PAPER1_WATER_RECIPE_INVALID",
            "Paper 1 design failed complete revalidation",
            "design",
            {"cause_type": type(error).__name__},
        )


def _canonical_recipe_domain(domain: object) -> ModelDomain:
    if type(domain) is not ModelDomain:
        fail(
            "PAPER1_WATER_RECIPE_DOMAIN_INVALID",
            "recipe validation requires an exact ModelDomain",
            "domain",
            {"received_type": type(domain).__name__},
        )
    try:
        checked = ModelDomain.model_validate(_registered_json_value(domain))
    except Exception as error:
        fail(
            "PAPER1_WATER_RECIPE_DOMAIN_INVALID",
            "model domain failed complete revalidation",
            "domain",
            {"cause_type": type(error).__name__},
        )
    observed_requirements = tuple(
        (
            requirement.field_name,
            requirement.observation_kind,
            None if requirement.ec_kind is None else requirement.ec_kind.value,
        )
        for requirement in checked.required_chemistry_fields
    )
    expected_requirements = (
        ("ec_ds_m", "measured", "ECw"),
        ("ph", "measured", None),
        ("measured_osmolality_osmol_kg", "measured", None),
        ("alkalinity_mmol_c_l", "measured", None),
        ("temperature_k", "measured", None),
        ("sar", "computed", None),
    )
    observed = (
        checked.model_id,
        checked.version,
        checked.permitted_evidence_label,
        checked.ec_kind.value,
        checked.ec_ds_m_min,
        checked.ec_ds_m_max,
        checked.osmolality_min,
        checked.osmolality_max,
        checked.temperature_k_min,
        checked.temperature_k_max,
        observed_requirements,
        checked.required_analytes,
        checked.allowed_chassis,
        checked.allowed_life_stages,
        checked.calibration_datasets,
        checked.extrapolation_policy,
    )
    expected = (
        "core_v1",
        "1.1.0",
        EvidenceLabel.PHYSICS_CONSTRAINED,
        "ECw",
        0.7,
        15.0,
        0.02,
        0.30,
        291.15,
        303.15,
        expected_requirements,
        _REGISTERED_ANALYTE_IDS,
        ("Vairo", "SYNTHETIC_VAIRO_B"),
        ("juvenile",),
        (),
        "deny",
    )
    if observed != expected:
        fail(
            "PAPER1_WATER_RECIPE_DOMAIN_INVALID",
            "core_v1 is not the registered Paper 1 v1.1.0 domain",
            "domain",
        )
    return checked


def validate_task4_domain_request(
    domain: ModelDomain,
    request: DomainRequest,
) -> DomainValidationResult:
    """Apply the registered Task 4 chassis ceiling before public domain use."""

    checked_domain = _canonical_recipe_domain(domain)
    if type(request) is not DomainRequest:
        fail(
            "TASK4_DOMAIN_REQUEST_INVALID",
            "Task 4 domain validation requires an exact DomainRequest",
            "request",
            {"received_type": type(request).__name__},
        )
    try:
        checked_request = DomainRequest.model_validate(
            _registered_json_value(request)
        )
    except Exception as error:
        fail(
            "TASK4_DOMAIN_REQUEST_INVALID",
            "Task 4 domain request failed complete reconstruction",
            "request",
            {"cause_type": type(error).__name__},
        )
    if (
        checked_request.chassis == "SYNTHETIC_VAIRO_B"
        and checked_request.requested_label is not EvidenceLabel.SYNTHETIC_ONLY
    ):
        fail(
            "TASK4_CHASSIS_EVIDENCE_INVALID",
            "the secondary synthetic chassis cannot support a stronger evidence tier",
            "request.requested_label",
            {
                "chassis": checked_request.chassis,
                "maximum_evidence_label": EvidenceLabel.SYNTHETIC_ONLY.value,
                "received": checked_request.requested_label.value,
            },
        )
    return validate_domain(checked_domain, checked_request)


def load_paper1_water_recipes(path: str | Path) -> Paper1WaterRecipeRegistry:
    """Load and independently revalidate the prospective recipe authority."""

    try:
        raw = _load_yaml_mapping(path)
        return Paper1WaterRecipeRegistry.model_validate(raw)
    except AlmondLabError:
        raise
    except Exception as error:
        fail(
            "PAPER1_WATER_RECIPE_INVALID",
            "Paper 1 water-recipe authority is invalid",
            "registry",
            {"cause_type": type(error).__name__},
        )


def load_task4_stop_policy(path: str | Path) -> Task4StopPolicy:
    """Load and independently revalidate the exact Task 4 stop authority."""

    try:
        raw = _load_yaml_mapping(path)
        return Task4StopPolicy.model_validate(raw)
    except AlmondLabError:
        raise
    except Exception as error:
        fail(
            "TASK4_STOP_POLICY_INVALID",
            "Task 4 physical-stop authority is invalid",
            "policy",
            {"cause_type": type(error).__name__},
        )


def migrate_paper1_design_water_recipes(
    design: Paper1DesignConfig,
    registry: Paper1WaterRecipeRegistry,
) -> Paper1DesignConfig:
    """Detach and replace only the two superseded design chemistry records."""

    checked_design = _canonical_paper1_design(design)
    checked_registry = _canonical_water_recipe_registry(registry)
    anchors = {
        anchor.water_id: anchor for anchor in checked_registry.historical_anchors
    }
    for water in checked_design.water_conditions:
        if _chemistry_json(water.chemistry) != _chemistry_json(
            anchors[water.water_id].chemistry
        ):
            fail(
                "PAPER1_WATER_RECIPE_MIGRATION_INVALID",
                "migration source is not the exact superseded chemistry anchor",
                f"water_conditions.{water.water_id}.chemistry",
            )
    payload = _registered_json_value(checked_design)
    if not isinstance(payload, dict):
        raise AssertionError("Paper1DesignConfig serialization must be a mapping")
    water_rows = payload["water_conditions"]
    if not isinstance(water_rows, list):
        raise AssertionError("Paper1DesignConfig water conditions must be a list")
    active = {
        recipe.water_id: recipe for recipe in checked_registry.active_recipes
    }
    for row in water_rows:
        if not isinstance(row, dict):
            raise AssertionError("Paper1DesignConfig water row must be a mapping")
        water_id = row["water_id"]
        row["chemistry"] = _chemistry_json(active[water_id].chemistry)
    try:
        return Paper1DesignConfig.model_validate(payload)
    except Exception as error:
        fail(
            "PAPER1_WATER_RECIPE_MIGRATION_INVALID",
            "detached chemistry migration failed design revalidation",
            "water_conditions",
            {"cause_type": type(error).__name__},
        )


def validate_active_paper1_water_recipes(
    registry: Paper1WaterRecipeRegistry,
    *,
    design: Paper1DesignConfig,
    domain: ModelDomain,
    physical_use: bool = False,
) -> tuple[ActiveWaterRecipe, ...]:
    """Validate active synthetic recipes against design and model authorities."""

    if type(physical_use) is not bool:
        fail(
            "PAPER1_WATER_RECIPE_INVALID",
            "physical_use must be a primitive boolean",
            "physical_use",
        )
    checked_registry = _canonical_water_recipe_registry(registry)
    checked_design = _canonical_paper1_design(design)
    checked_domain = _canonical_recipe_domain(domain)
    by_water = {
        recipe.water_id: recipe for recipe in checked_registry.active_recipes
    }
    if tuple(water.water_id for water in checked_design.water_conditions) != REGISTERED_WATER_IDS:
        fail(
            "PAPER1_WATER_RECIPE_INVALID",
            "design water order differs from the recipe authority",
            "design.water_conditions",
        )
    for water in checked_design.water_conditions:
        recipe = by_water[water.water_id]
        if _chemistry_json(water.chemistry) != _chemistry_json(recipe.chemistry):
            fail(
                "PAPER1_WATER_RECIPE_INVALID",
                "design chemistry differs from the active recipe",
                f"design.water_conditions.{water.water_id}.chemistry",
            )
        if water.evidence_label is not EvidenceLabel.HYPOTHESIS_PRIOR:
            fail(
                "PAPER1_WATER_RECIPE_INVALID",
                "design water chemistry must remain hypothesis_prior",
                f"design.water_conditions.{water.water_id}.evidence_label",
            )
        chemistry = recipe.chemistry
        if not (
            checked_domain.ec_ds_m_min
            <= chemistry.ec_ds_m
            <= checked_domain.ec_ds_m_max
            and checked_domain.osmolality_min
            <= chemistry.measured_osmolality_osmol_kg
            <= checked_domain.osmolality_max
            and checked_domain.temperature_k_min
            <= chemistry.temperature_k
            <= checked_domain.temperature_k_max
        ):
            fail(
                "PAPER1_WATER_RECIPE_DOMAIN_INVALID",
                "active recipe chemistry is outside core_v1",
                f"registry.active_recipes.{water.water_id}.chemistry",
            )
        if (
            recipe.model_domain_id != checked_domain.model_id
            or recipe.model_domain_version != checked_domain.version
        ):
            fail(
                "PAPER1_WATER_RECIPE_DOMAIN_INVALID",
                "active recipe names a different model-domain authority",
                f"registry.active_recipes.{water.water_id}.model_domain_id",
            )
    if physical_use:
        fail(
            "PHYSICAL_RECIPE_NOT_REGISTERED",
            "synthetic targets lack a batch-specific titration and final-volume revision",
            "registry.active_recipes.preparation.physicalization_status",
            {
                "required_status": (
                    "blocked_pending_batch_specific_titration_revision"
                )
            },
        )
    return checked_registry.active_recipes


def load_synthetic_scenarios(path: str | Path) -> SyntheticScenarioRegistry:
    """Load the active v1.4 registry; legacy documents require migration."""
    try:
        stream = _read_task4_yaml_stream(path)
        if (
            hashlib.sha256(stream.encode("utf-8")).hexdigest()
            == REGISTERED_V13_SCENARIO_RAW_SHA256
        ):
            fail(
                "SCENARIO_SCHEMA_MIGRATION_REQUIRED",
                "active generation accepts only the v1.4 scenario registry",
                "schema_version",
                {"received": "1.3.0"},
            )
        declared_version = _declared_scenario_schema_version(stream)
    except AlmondLabError:
        raise
    except YamlDuplicateKeyError as error:
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
    except yaml.YAMLError as error:
        _scenario_invalid(
            "synthetic scenario YAML could not be safely inspected",
            "yaml",
            cause=error,
        )
    if declared_version is None:
        # Validate alternate YAML syntax before reporting a missing/legacy
        # schema. This preserves explicit v1.3 migration precedence while
        # still rejecting a merge-only attempt to synthesize v1.4 authority.
        _load_task4_yaml_mapping(path)
    if declared_version != "1.4.0":
        fail(
            "SCENARIO_SCHEMA_MIGRATION_REQUIRED",
            "active generation accepts only the v1.4 scenario registry",
            "schema_version",
            {"received": declared_version or "1.3.0"},
        )
    raw = _load_task4_yaml_mapping(path)
    if raw.get("schema_version") != "1.4.0":
        fail(
            "SCENARIO_SCHEMA_MIGRATION_REQUIRED",
            "active generation accepts only the v1.4 scenario registry",
            "schema_version",
            {"received": raw.get("schema_version")},
        )
    try:
        registry = SyntheticScenarioRegistry.model_validate(raw)
    except Exception as error:
        _scenario_invalid("v1.4 scenario registry is invalid", "root", cause=error)
    if len(registry.sensitivities) != 36:
        _scenario_invalid(
            "v1.4 scenario registry omits the sensitivity authority",
            "sensitivities",
        )
    observed_sha256 = hashlib.sha256(canonical_json_bytes(raw)).hexdigest()
    if observed_sha256 != REGISTERED_TASK4_SCENARIO_REGISTRY_SHA256:
        _scenario_invalid(
            "v1.4 scenario registry differs from the canonical authority",
            "root",
        )
    return registry


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


# Public Paper 1 facade for the isolated, solver-free forcing contracts.
from almondlab.task4_forcing import (  # noqa: E402,F401
    CalibrationForcingPanel,
    CalibrationForcingPanelBundle,
    CalibrationForcingRecord,
    NominalForcingArtifact,
    NominalForcingRecord,
    revalidate_calibration_forcing_panel_bundle,
    revalidate_nominal_forcing_artifact,
)
