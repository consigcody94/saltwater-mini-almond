"""Frozen Paper 1 registry, allocation, and synthetic-input contracts."""

from enum import StrEnum
from math import isclose, log
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

from almondlab.contracts import EvidenceLabel
from almondlab.errors import fail
from almondlab.schemas import WaterChemistry


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
    gates: dict[str, Literal["required", "blocked"]]
    risk_warning: str = Field(min_length=1)

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
    def require_composite_root_design(self) -> "Paper1DesignConfig":
        if self.population is not AnalysisPopulation.COMPOSITE_ROOT:
            raise ValueError("Paper 1 primary design population must be composite_root")
        return self


REQUIRED_SYNTHETIC_SCENARIO_KEYS = frozenset(
    {
        "root_na_permeability",
        "root_cl_permeability",
        "root_k_permeability",
        "root_water_conductivity",
        "na_efflux_capacity",
        "hkt_retrieval_capacity",
        "mannitol_synthesis_capacity",
        "apx_capacity",
        "sos2_kinase_capacity",
        "na_influx_km",
        "mannitol_km",
        "mannitol_turnover_rate",
        "biomass_loss_rate",
        "senescence_rate",
        "atp_per_na_efflux",
        "carbon_cost_per_mannitol",
        "apx_energy_cost",
        "cipk_energy_cost",
        "biomass_conversion",
        "root_na_initial_stock",
        "root_cl_initial_stock",
        "root_k_initial_stock",
        "initial_biomass",
        "initial_canopy_area",
        "forcing_ecw_ds_m",
        "forcing_temperature_k",
        "forcing_osmolality_osmol_kg",
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


class SyntheticScenarioConfig(StrictPaper1Model):
    scenario_id: str = Field(min_length=1)
    schema_version: str = Field(default="1.0.0", min_length=1)
    evidence_label: Literal[EvidenceLabel.SYNTHETIC_ONLY, EvidenceLabel.HYPOTHESIS_PRIOR]
    parameters: dict[str, float] = Field(default_factory=dict)

    @model_validator(mode="before")
    @classmethod
    def reject_incomplete_scenario(cls, values: object) -> object:
        parameters = values.get("parameters", {}) if isinstance(values, dict) else {}
        missing = sorted(REQUIRED_SYNTHETIC_SCENARIO_KEYS - set(parameters))
        if missing:
            fail(
                "INCOMPLETE_SYNTHETIC_SCENARIO",
                "synthetic scenario omits registered generator inputs",
                "parameters",
                {"missing": missing},
            )
        return values


def _load_yaml_mapping(path: str | Path) -> dict[str, object]:
    payload = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
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
    payload = _load_yaml_mapping(path)
    scenarios = payload.get("scenarios")
    if not isinstance(scenarios, list):
        raise ValueError("synthetic scenario configuration requires a scenarios list")
    return tuple(SyntheticScenarioConfig.model_validate(scenario) for scenario in scenarios)
