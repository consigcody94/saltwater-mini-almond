"""Strict boundary schemas for scientific inputs and records."""

from __future__ import annotations

import re
from datetime import datetime
from math import isfinite
from numbers import Real
from typing import Annotated, Literal

from pydantic import (
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    TypeAdapter,
    model_validator,
)

from almondlab.contracts import DataOrigin, ECKind, EvidenceLabel


SHA256_PATTERN = re.compile(r"^[0-9a-fA-F]{64}$")


def _normalize_finite_real(value: object) -> float:
    """Accept real numeric literals except booleans and normalize to float."""
    if isinstance(value, bool) or not isinstance(value, Real):
        raise ValueError("value must be a real number, not a boolean or string")
    try:
        converted = float(value)
    except (TypeError, ValueError, OverflowError) as error:
        raise ValueError("value must fit in a finite float") from error
    if not isfinite(converted):
        raise ValueError("value must be finite")
    return converted


FiniteFloat = Annotated[float, BeforeValidator(_normalize_finite_real)]
NonnegativeFiniteFloat = Annotated[FiniteFloat, Field(ge=0)]


class StrictScientificModel(BaseModel):
    """Reject unknown, non-finite, and mutable top-level scientific inputs."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        allow_inf_nan=False,
        revalidate_instances="always",
    )


class ProvenanceReference(StrictScientificModel):
    """An immutable identifier and content hash for one evidence source."""

    provenance_id: str = Field(min_length=1)
    sha256: str

    @model_validator(mode="after")
    def validate_digest(self) -> "ProvenanceReference":
        if not SHA256_PATTERN.fullmatch(self.sha256):
            raise ValueError("sha256 must be a 64-character hexadecimal digest")
        return self


class ChemistryFieldRequirement(StrictScientificModel):
    """Required observation semantics for a non-analyte chemistry field."""

    field_name: Literal[
        "ec_ds_m",
        "ph",
        "measured_osmolality_osmol_kg",
        "alkalinity_mmol_c_l",
        "temperature_k",
        "sar",
    ]
    observation_kind: Literal["measured", "computed"]
    ec_kind: ECKind | None = None

    @model_validator(mode="after")
    def validate_ec_semantics(self) -> "ChemistryFieldRequirement":
        if self.field_name == "ec_ds_m" and self.ec_kind is None:
            raise ValueError("ec_ds_m requirement must declare ec_kind")
        if self.field_name != "ec_ds_m" and self.ec_kind is not None:
            raise ValueError("ec_kind is only valid for ec_ds_m")
        return self


class ChemistryObservation(StrictScientificModel):
    """Actual field availability with value, method, label, and hashed provenance."""

    field_name: str = Field(min_length=1)
    value: FiniteFloat
    observation_kind: Literal["measured", "computed"]
    data_origin: DataOrigin
    evidence_label: EvidenceLabel
    provenance_id: str = Field(min_length=1)
    provenance_sha256: str
    ec_kind: ECKind | None = None

    @model_validator(mode="after")
    def validate_observation(self) -> "ChemistryObservation":
        if not SHA256_PATTERN.fullmatch(self.provenance_sha256):
            raise ValueError("provenance_sha256 must be a SHA-256 digest")
        if self.field_name == "ec_ds_m" and self.ec_kind is None:
            raise ValueError("ec_ds_m observation must declare ec_kind")
        if self.field_name != "ec_ds_m" and self.ec_kind is not None:
            raise ValueError("ec_kind is only valid for ec_ds_m")
        return self


class WaterChemistry(StrictScientificModel):
    """Registered water chemistry in canonical concentration units."""

    ec_kind: ECKind
    ec_ds_m: NonnegativeFiniteFloat
    temperature_k: NonnegativeFiniteFloat
    measured_osmolality_osmol_kg: NonnegativeFiniteFloat
    ph: FiniteFloat
    alkalinity_mmol_c_l: NonnegativeFiniteFloat
    na_mmol_l: NonnegativeFiniteFloat
    cl_mmol_l: NonnegativeFiniteFloat
    ca_mmol_l: NonnegativeFiniteFloat
    mg_mmol_l: NonnegativeFiniteFloat
    k_mmol_l: NonnegativeFiniteFloat
    total_b_mmol_l: NonnegativeFiniteFloat
    sulfate_mmol_l: NonnegativeFiniteFloat
    bicarbonate_mmol_l: NonnegativeFiniteFloat
    nitrate_mmol_l: NonnegativeFiniteFloat
    phosphate_mmol_l: NonnegativeFiniteFloat

    @classmethod
    def from_celsius(
        cls, *, temperature_c: object, **values: object
    ) -> "WaterChemistry":
        """Build canonical Kelvin chemistry from an explicit Celsius input."""
        if "temperature_k" in values:
            raise ValueError("temperature_k and temperature_c cannot both be provided")
        celsius = TypeAdapter(FiniteFloat).validate_python(temperature_c)
        return cls(**values, temperature_k=celsius + 273.15)


class WaterBatch(StrictScientificModel):
    """A traceable batch of registered water chemistry."""

    water_batch_id: str = Field(min_length=1)
    chemistry: WaterChemistry
    data_origin: DataOrigin
    evidence_label: EvidenceLabel
    schema_version: str = Field(min_length=1)


class ModelDomain(StrictScientificModel):
    """The inclusive operating domain and maximum permitted evidence claim."""

    model_id: str = Field(min_length=1)
    version: str = Field(min_length=1)
    permitted_evidence_label: EvidenceLabel
    ec_kind: ECKind = ECKind.ECW
    ec_ds_m_min: NonnegativeFiniteFloat
    ec_ds_m_max: NonnegativeFiniteFloat
    osmolality_min: NonnegativeFiniteFloat
    osmolality_max: NonnegativeFiniteFloat
    temperature_k_min: NonnegativeFiniteFloat
    temperature_k_max: NonnegativeFiniteFloat
    required_chemistry_fields: tuple[ChemistryFieldRequirement, ...] = Field(
        min_length=1
    )
    required_analytes: tuple[str, ...] = Field(min_length=1)
    allowed_chassis: tuple[str, ...] = Field(min_length=1)
    allowed_life_stages: tuple[str, ...] = Field(min_length=1)
    calibration_datasets: tuple[ProvenanceReference, ...]
    extrapolation_policy: Literal["deny", "hypothesis_prior", "synthetic_only"]

    @model_validator(mode="after")
    def validate_ranges_and_datasets(self) -> "ModelDomain":
        for lower_name, upper_name in (
            ("ec_ds_m_min", "ec_ds_m_max"),
            ("osmolality_min", "osmolality_max"),
            ("temperature_k_min", "temperature_k_max"),
        ):
            if getattr(self, lower_name) > getattr(self, upper_name):
                raise ValueError(f"{lower_name} must be less than or equal to {upper_name}")

        requirement_names = tuple(item.field_name for item in self.required_chemistry_fields)
        if len(set(requirement_names)) != len(requirement_names):
            raise ValueError("required chemistry fields must be unique")
        analyte_names = tuple(self.required_analytes)
        if len(set(analyte_names)) != len(analyte_names):
            raise ValueError("required analytes must be unique")
        dataset_ids = tuple(item.provenance_id for item in self.calibration_datasets)
        if len(set(dataset_ids)) != len(dataset_ids):
            raise ValueError("calibration dataset identifiers must be unique")
        is_conservation_core = (
            self.model_id == "core_v1"
            and self.permitted_evidence_label is EvidenceLabel.PHYSICS_CONSTRAINED
        )
        if not self.calibration_datasets and not is_conservation_core:
            raise ValueError("empty calibration datasets are reserved for core_v1")
        return self


class ObservationRecord(StrictScientificModel):
    """A unit-bearing observation with independent provenance and evidence labels."""

    record_id: str = Field(min_length=1)
    observation_type: str = Field(min_length=1)
    observed_at: datetime
    value: FiniteFloat
    unit: str = Field(min_length=1)
    data_origin: DataOrigin
    evidence_label: EvidenceLabel
    schema_version: str = Field(min_length=1)
    water_batch_id: str | None = Field(default=None, min_length=1)
