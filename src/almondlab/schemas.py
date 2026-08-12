"""Strict boundary schemas for scientific inputs and records."""

import re
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from almondlab.contracts import DataOrigin, ECKind, EvidenceLabel


SHA256_PATTERN = re.compile(r"^[0-9a-fA-F]{64}$")


class StrictScientificModel(BaseModel):
    """Reject unknown, non-finite, and mutable top-level scientific inputs."""

    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)


class WaterChemistry(StrictScientificModel):
    """Registered water chemistry in canonical concentration units."""

    ec_kind: ECKind
    ec_ds_m: float = Field(ge=0)
    temperature_c: float
    measured_osmolality_osmol_kg: float = Field(ge=0)
    ph: float
    alkalinity_mmol_c_l: float
    na_mmol_l: float = Field(ge=0)
    cl_mmol_l: float = Field(ge=0)
    ca_mmol_l: float = Field(ge=0)
    mg_mmol_l: float = Field(ge=0)
    k_mmol_l: float = Field(ge=0)
    total_b_mmol_l: float = Field(ge=0)
    sulfate_mmol_l: float = Field(ge=0)
    bicarbonate_mmol_l: float = Field(ge=0)
    nitrate_mmol_l: float = Field(ge=0)
    phosphate_mmol_l: float = Field(ge=0)


class WaterBatch(StrictScientificModel):
    """A traceable batch of registered water chemistry."""

    water_batch_id: str = Field(min_length=1)
    chemistry: WaterChemistry
    data_origin: DataOrigin
    evidence_label: EvidenceLabel
    schema_version: str = Field(min_length=1)


class ModelDomain(StrictScientificModel):
    """The inclusive operating domain and evidence policy for a model."""

    model_id: str = Field(min_length=1)
    version: str = Field(min_length=1)
    permitted_label: EvidenceLabel
    ec_kind: ECKind = ECKind.ECW
    ec_ds_m_min: float
    ec_ds_m_max: float
    osmolality_min: float
    osmolality_max: float
    temperature_c_min: float
    temperature_c_max: float
    required_analytes: tuple[str, ...] = Field(min_length=1)
    allowed_chassis: tuple[str, ...] = Field(min_length=1)
    allowed_life_stages: tuple[str, ...] = Field(min_length=1)
    calibration_datasets: dict[str, str]
    extrapolation_policy: Literal["deny", "hypothesis_prior", "synthetic_only"]

    @model_validator(mode="after")
    def validate_ranges_and_datasets(self) -> "ModelDomain":
        for lower_name, upper_name in (
            ("ec_ds_m_min", "ec_ds_m_max"),
            ("osmolality_min", "osmolality_max"),
            ("temperature_c_min", "temperature_c_max"),
        ):
            if getattr(self, lower_name) > getattr(self, upper_name):
                raise ValueError(f"{lower_name} must be less than or equal to {upper_name}")

        malformed = [
            dataset_id
            for dataset_id, digest in self.calibration_datasets.items()
            if not SHA256_PATTERN.fullmatch(digest)
        ]
        if malformed:
            raise ValueError(f"calibration datasets have malformed SHA-256 hashes: {malformed}")
        if (
            self.permitted_label is EvidenceLabel.EMPIRICALLY_CALIBRATED
            and not self.calibration_datasets
        ):
            raise ValueError("empirically calibrated models require calibration datasets")
        return self


class ObservationRecord(StrictScientificModel):
    """A unit-bearing observation with independent provenance and evidence labels."""

    record_id: str = Field(min_length=1)
    observation_type: str = Field(min_length=1)
    observed_at: datetime
    value: float
    unit: str = Field(min_length=1)
    data_origin: DataOrigin
    evidence_label: EvidenceLabel
    schema_version: str = Field(min_length=1)
    water_batch_id: str | None = Field(default=None, min_length=1)
