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
    gates: dict[str, Literal["required", "blocked"]]
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
        return self

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
        parameter_names = set(parameters) if isinstance(parameters, dict) else set()
        missing = sorted(REQUIRED_SYNTHETIC_SCENARIO_KEYS - parameter_names)
        if missing:
            fail(
                "INCOMPLETE_SYNTHETIC_SCENARIO",
                "synthetic scenario omits registered generator inputs",
                "parameters",
                {"missing": missing},
            )
        extra = sorted(parameter_names - REQUIRED_SYNTHETIC_SCENARIO_KEYS)
        if extra:
            fail(
                "UNREGISTERED_SYNTHETIC_PARAMETER",
                "synthetic scenario contains unregistered generator inputs",
                "parameters",
                {"extra": extra},
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
