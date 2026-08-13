"""Prospective Task 4 scenario and sensitivity registration contracts."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import fields, is_dataclass
from enum import Enum
import hashlib
import json
from math import exp, floor, fsum, nextafter, sqrt
from pathlib import Path
from typing import Any

import pytest
import yaml

from pydantic import BaseModel, ValidationError

import almondlab.paper1_contracts as paper1_contracts
from almondlab.design import load_randomization_fixture, randomize
from almondlab.errors import AlmondLabError
from almondlab.paper1_contracts import (
    SyntheticScenarioRegistry,
    load_paper1_design,
    load_paper1_water_recipes,
    load_synthetic_scenarios,
    load_task4_stop_policy,
)
from almondlab.provenance import canonical_json_bytes


ROOT = Path(__file__).resolve().parents[1]
SCENARIO_PATH = ROOT / "configs" / "synthetic_scenarios.yaml"
LEGACY_PATH = ROOT / "configs" / "archive" / "synthetic_scenarios_v1_3.yaml"
RECIPE_PATH = ROOT / "configs" / "paper1_water_recipes.yaml"
DESIGN_PATH = ROOT / "configs" / "experiment_paper1.yaml"
STOP_POLICY_PATH = ROOT / "configs" / "paper1_task4_stop_policy.yaml"
TASK3_FIXTURE_PATH = ROOT / "tests" / "fixtures" / "paper1_small.yaml"

WATER_IDS = (
    "nonsaline_nutrient_matched_control",
    "pilot_selected_full_ion_marine_challenge",
)
RECIPE_IDS = {
    WATER_IDS[0]: "paper1_base_nutrient_control_v1@1.0.0",
    WATER_IDS[1]: "paper1_base_plus_nacl40_challenge_v1@1.0.0",
}
SCENARIO_IDS = (
    "perfect_control",
    "true_ion_exclusion",
    "root_na_accumulation",
    "marker_only",
    "nonsaline_penalty",
    "chassis_interaction",
    "delayed_toxicity",
    "sensor_drift_missingness",
    "insufficient_purge",
    "selection_bias_false_leader",
)
ENDPOINT_IDS = (
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
ION_ENDPOINT_IDS = ENDPOINT_IDS[1:6]
H3_ENDPOINT_IDS = ENDPOINT_IDS[6:]
LIMIT_ENDPOINT_IDS = ENDPOINT_IDS[1:8] + (ENDPOINT_IDS[9],)
H3_ERROR_AUTHORITIES = {
    "C1": (
        "root_surface_outward_na_flux_per_root_dry_mass",
        "log_ratio",
        "umol Na g_root_dry_mass^-1 h^-1",
        0.05,
        "log-ratio",
    ),
    "C2": (
        "root_h2o2_concentration_time_auc",
        "log_ratio",
        "umol H2O2 g_root_fresh_mass^-1 h",
        0.05,
        "log-ratio",
    ),
    "C3": (
        "root_mannitol_concentration_above_empty_vector",
        "difference",
        "nmol g_root_fresh_mass^-1",
        2.0,
        "nmol g_root_fresh_mass^-1",
    ),
    "C4": (
        "root_surface_outward_na_flux_per_root_dry_mass",
        "log_ratio",
        "umol Na g_root_dry_mass^-1 h^-1",
        0.05,
        "log-ratio",
    ),
    "C5": (
        "xylem_sap_na_concentration_time_auc",
        "log_ratio",
        "mmol Na L^-1 h",
        0.05,
        "log-ratio",
    ),
    "C6": (
        "root_surface_outward_na_flux_per_root_dry_mass",
        "log_ratio",
        "umol Na g_root_dry_mass^-1 h^-1",
        0.05,
        "log-ratio",
    ),
}

WATER_RECIPE_REGISTRY_SHA256 = (
    "8a902441d143017fddfddf5b174302187dd8da1d9a46f98af9a94d18e317b1bd"
)
NOMINAL_FORCING_SHA256 = (
    "329cb311b6a5915e1090a2e6b059857af9531bec3cbc26779d112eb9a5cbbc96"
)


def _rq(value: float, unit: str) -> dict[str, object]:
    return {
        "value": value,
        "unit": unit,
        "evidence_label": "hypothesis_prior",
    }


def _rc(value: int) -> dict[str, object]:
    return {
        "value": value,
        "unit": "count",
        "evidence_label": "hypothesis_prior",
    }


def _h3_error_records() -> dict[str, dict[str, object]]:
    return {
        candidate_id: {
            "candidate_id": candidate_id,
            "endpoint_id": authority[0],
            "analysis_scale": authority[1],
            "endpoint_unit": authority[2],
            "error_sd": _rq(authority[3], authority[4]),
        }
        for candidate_id, authority in H3_ERROR_AUTHORITIES.items()
    }


def _endpoint_quantity_map(
    values: dict[str, tuple[float, str] | None],
) -> dict[str, dict[str, object] | None]:
    return {
        endpoint_id: None if values[endpoint_id] is None else _rq(*values[endpoint_id])
        for endpoint_id in ENDPOINT_IDS
    }


def _expected_anchor_generator() -> dict[str, object]:
    lod_values = {
        "green_canopy_area": None,
        "root_zone_na_concentration": (0.01, "mmol Na L^-1"),
        "root_zone_cl_concentration": (0.01, "mmol Cl L^-1"),
        "root_zone_k_concentration": (0.01, "mmol K L^-1"),
        "xylem_sap_na_concentration": (0.005, "mmol Na L^-1"),
        "drainage_total_b_concentration": (0.0005, "mmol B L^-1"),
        "root_surface_outward_na_flux_per_root_dry_mass": (
            0.005,
            "umol Na g_root_dry_mass^-1 h^-1",
        ),
        "root_h2o2_concentration_time_auc": (
            0.1,
            "umol H2O2 g_root_fresh_mass^-1 h",
        ),
        "root_mannitol_concentration_above_empty_vector": None,
        "xylem_sap_na_concentration_time_auc": (0.1, "mmol Na L^-1 h"),
    }
    loq_values = {
        "green_canopy_area": None,
        "root_zone_na_concentration": (0.03, "mmol Na L^-1"),
        "root_zone_cl_concentration": (0.03, "mmol Cl L^-1"),
        "root_zone_k_concentration": (0.03, "mmol K L^-1"),
        "xylem_sap_na_concentration": (0.015, "mmol Na L^-1"),
        "drainage_total_b_concentration": (0.0015, "mmol B L^-1"),
        "root_surface_outward_na_flux_per_root_dry_mass": (
            0.015,
            "umol Na g_root_dry_mass^-1 h^-1",
        ),
        "root_h2o2_concentration_time_auc": (
            0.3,
            "umol H2O2 g_root_fresh_mass^-1 h",
        ),
        "root_mannitol_concentration_above_empty_vector": None,
        "xylem_sap_na_concentration_time_auc": (0.3, "mmol Na L^-1 h"),
    }
    log_sd_values = {
        endpoint_id: None
        if endpoint_id in {
            "green_canopy_area",
            "root_mannitol_concentration_above_empty_vector",
        }
        else (0.05, "log-ratio")
        for endpoint_id in ENDPOINT_IDS
    }
    return {
        "hierarchy": {
            "run_variance": _rq(0.02, "log-ratio^2"),
            "batch_variance": _rq(0.02, "log-ratio^2"),
            "reservoir_variance": _rq(0.04, "log-ratio^2"),
            "plant_variance": _rq(0.1, "log-ratio^2"),
        },
        "climate": {
            "temperature_ar1_phi": _rq(0.7, "dimensionless"),
            "temperature_innovation_sd_k": _rq(0.35, "K"),
            "apar_ar1_phi": _rq(0.6, "dimensionless"),
            "apar_log_innovation_sd": _rq(0.1, "log-ratio"),
            "matric_potential_ar1_phi": _rq(0.8, "dimensionless"),
            "matric_potential_innovation_sd_mpa": _rq(0.006, "MPa"),
            "potential_transpiration_log_innovation_sd": _rq(0.08, "log-ratio"),
            "climate_initialization_burnin_steps": _rc(64),
        },
        "chemistry": {
            "common_ion_log_sd": _rq(0.03, "log-ratio"),
            "boron_log_sd": _rq(0.08, "log-ratio"),
            "ec_measurement_sd_ds_m": _rq(0.05, "dS m^-1"),
            "osmolality_measurement_sd_osmol_kg": _rq(0.002, "osmol kg^-1"),
            "ph_measurement_sd": _rq(0.03, "pH"),
            "temperature_measurement_sd_k": _rq(0.2, "K"),
            "charge_balance_tolerance_percent": _rq(1.0, "percent"),
        },
        "water_loop": {
            "reservoir_initial_volume_l": _rq(120.0, "L"),
            "water_batch_volume_l": _rq(5000.0, "L"),
            "irrigation_volume_l_per_plant_day": _rq(
                0.6,
                "L plant^-1 day^-1",
            ),
            "drainage_return_fraction": _rq(0.7, "dimensionless"),
            "purge_volume_l_day": _rq(1.2, "L day^-1"),
            "sampling_volume_l_per_sample": _rq(0.05, "L sample^-1"),
            "reservoir_min_volume_l": _rq(80.0, "L"),
            "reservoir_max_volume_l": _rq(160.0, "L"),
            "operator_event_times_days": [
                _rq(float(index) + 0.25, "day") for index in range(84)
            ],
        },
        "observation": {
            "canopy_observation_error_sd": _rq(0.05, "log-ratio"),
            "ion_observation_error_sd": _rq(0.04, "log-ratio"),
            "h3_observation_error_by_endpoint": _h3_error_records(),
            "canopy_heteroscedastic_log_slope": _rq(0.1, "log/log"),
            "ion_heteroscedastic_log_slope": _rq(0.08, "log/log"),
            "canopy_observation_times_days": [
                _rq(float(day), "day")
                for day in (0, 3, 7, 14, 21, 28, 35, 42, 49, 56, 63, 70, 77, 84)
            ],
            "ion_observation_times_days": [
                _rq(float(day), "day") for day in (0, 14, 28, 42, 56, 70, 84)
            ],
            "h3_observation_times_days_by_endpoint": {
                endpoint_id: [_rq(84.0, "day")] for endpoint_id in H3_ENDPOINT_IDS
            },
            "h3_measurement_links": {
                "root_dry_matter_fraction": _rq(0.2, "dimensionless"),
                "h2o2_umol_g_root_fresh_mass_inv_per_ros_dimensionless": _rq(
                    1.0,
                    "umol H2O2 g_root_fresh_mass^-1 per ros_dimensionless",
                ),
            },
        },
        "censoring": {
            "lod_by_endpoint": _endpoint_quantity_map(lod_values),
            "loq_by_endpoint": _endpoint_quantity_map(loq_values),
            "lod_log_sd_by_endpoint": _endpoint_quantity_map(log_sd_values),
            "loq_log_sd_by_endpoint": _endpoint_quantity_map(log_sd_values),
        },
        "drift": {
            "canopy_drift_per_day": _rq(0.0, "log-ratio day^-1"),
            "ion_drift_per_day_by_endpoint": {
                endpoint_id: _rq(0.0, "log-ratio day^-1")
                for endpoint_id in ION_ENDPOINT_IDS
            },
            "h3_drift_per_day_by_endpoint": {
                "root_surface_outward_na_flux_per_root_dry_mass": _rq(
                    0.0,
                    "log-ratio day^-1",
                ),
                "root_h2o2_concentration_time_auc": _rq(
                    0.0,
                    "log-ratio day^-1",
                ),
                "root_mannitol_concentration_above_empty_vector": _rq(
                    0.0,
                    "nmol g_root_fresh_mass^-1 day^-1",
                ),
                "xylem_sap_na_concentration_time_auc": _rq(
                    0.0,
                    "log-ratio day^-1",
                ),
            },
            "calibration_interval_days": _rq(7.0, "day"),
            "calibration_phase_offset_days": _rq(0.0, "day"),
            "post_calibration_residual_sd_by_endpoint": {
                "green_canopy_area": _rq(0.005, "log-ratio"),
                **{
                    endpoint_id: _rq(0.01, "log-ratio")
                    for endpoint_id in ION_ENDPOINT_IDS
                },
                "root_surface_outward_na_flux_per_root_dry_mass": _rq(
                    0.01,
                    "log-ratio",
                ),
                "root_h2o2_concentration_time_auc": _rq(0.01, "log-ratio"),
                "root_mannitol_concentration_above_empty_vector": _rq(
                    0.25,
                    "nmol g_root_fresh_mass^-1",
                ),
                "xylem_sap_na_concentration_time_auc": _rq(0.01, "log-ratio"),
            },
        },
        "death": {
            "biomass_death_threshold_log_sd": _rq(0.1, "log-ratio"),
            "injury_death_threshold_log_sd": _rq(0.1, "log-ratio"),
            "sustained_injury_duration_log_sd": _rq(0.1, "log-ratio"),
        },
        "missingness": {
            "missingness_intercept": _rq(-3.0, "logit"),
            "missingness_stress_slope": _rq(
                0.2,
                "logit per standardized-proxy SD",
            ),
            "mnar_tipping_delta": _rq(
                0.1,
                "logit per standardized-endpoint SD",
            ),
            "observable_stress_proxy_fields": [
                "challenge_water_indicator",
                "scheduled_time_days",
                "prior_observed_canopy_log_ratio",
            ],
            "observable_stress_proxy_center_by_field": {
                "challenge_water_indicator": _rq(0.5, "dimensionless"),
                "scheduled_time_days": _rq(42.0, "day"),
                "prior_observed_canopy_log_ratio": _rq(0.0, "log-ratio"),
            },
            "observable_stress_proxy_scale_by_field": {
                "challenge_water_indicator": _rq(0.5, "dimensionless"),
                "scheduled_time_days": _rq(42.0, "day"),
                "prior_observed_canopy_log_ratio": _rq(0.25, "log-ratio"),
            },
            "mnar_endpoints": ["green_canopy_area", *H3_ENDPOINT_IDS],
        },
        "calibration": {
            "parameter_xtol": _rq(1.0e-6, "dimensionless"),
            "parameter_rtol": _rq(1.0e-6, "dimensionless"),
            "objective_residual_tolerance_log_ratio": _rq(
                1.0e-6,
                "log-ratio",
            ),
            "max_iterations": _rc(100),
            "fit_panel_size": _rc(64),
            "holdout_panel_size": _rc(64),
            "holdout_tolerance_log_ratio": _rq(0.02, "log-ratio"),
        },
        "design": {
            "duration_days": _rq(84.0, "day"),
            "confirmation_plants_per_group_reservoir": _rc(6),
        },
    }


def _raw_payload() -> dict[str, Any]:
    # Production's strict loader inherits SafeLoader's scalar resolver.  The
    # active document currently exceeds the general-purpose node budget, so
    # raw contract checks use that same resolver while public-boundary tests
    # exercise the complete strict loader and its resource policy.
    payload = yaml.safe_load(SCENARIO_PATH.read_text(encoding="utf-8"))
    assert type(payload) is dict
    return payload


def _assert_exact_primitive_types(
    actual: object,
    expected: object,
    path: str = "root",
) -> None:
    if isinstance(expected, dict):
        assert type(actual) is dict, path
        assert set(actual) == set(expected), path
        for key, value in expected.items():
            _assert_exact_primitive_types(
                actual[key],  # type: ignore[index]
                value,
                f"{path}.{key}",
            )
        return
    if isinstance(expected, list):
        assert type(actual) is list, path
        assert len(actual) == len(expected), path  # type: ignore[arg-type]
        for index, value in enumerate(expected):
            _assert_exact_primitive_types(
                actual[index],  # type: ignore[index]
                value,
                f"{path}[{index}]",
            )
        return
    assert type(actual) is type(expected), (
        path,
        type(actual).__name__,
        type(expected).__name__,
        actual,
    )


def _json_value(value: object) -> object:
    def normalize(item: object) -> object:
        if isinstance(item, BaseModel):
            return normalize(item.model_dump(mode="json"))
        if is_dataclass(item):
            return {
                field.name: normalize(getattr(item, field.name))
                for field in fields(item)
            }
        if isinstance(item, dict):
            return {str(key): normalize(child) for key, child in item.items()}
        if hasattr(item, "items"):
            return {
                str(key): normalize(child)
                for key, child in item.items()  # type: ignore[union-attr]
            }
        if isinstance(item, (set, frozenset)):
            return sorted(
                (normalize(child) for child in item),
                key=str,
            )
        if isinstance(item, (list, tuple)):
            return [normalize(child) for child in item]
        if isinstance(item, Enum):
            return item.value
        return item

    return json.loads(canonical_json_bytes(normalize(value)))


def _scenario_projection(payload: dict[str, Any]) -> SyntheticScenarioRegistry:
    return SyntheticScenarioRegistry.model_validate(
        {
            "schema_version": payload["schema_version"],
            "water_recipe_registry_sha256": payload["water_recipe_registry_sha256"],
            "anchor": payload["anchor"],
            "scenarios": payload["scenarios"],
            "sensitivities": payload["sensitivities"],
        }
    )


def _flatten_leaves(value: object, prefix: str = "") -> dict[str, object]:
    if isinstance(value, dict):
        leaves: dict[str, object] = {}
        for key, item in value.items():
            child = f"{prefix}.{key}" if prefix else str(key)
            leaves.update(_flatten_leaves(item, child))
        return leaves
    if isinstance(value, (list, tuple)):
        leaves = {}
        for index, item in enumerate(value):
            leaves.update(_flatten_leaves(item, f"{prefix}[{index}]"))
        return leaves
    return {prefix: value}


def _forcing_payload(step_index: int, water_id: str) -> dict[str, object]:
    is_day = step_index % 2 == 0
    return {
        "measured_osmolality_osmol_kg": 0.02 if water_id == WATER_IDS[0] else 0.1,
        "temperature_k": 297.15 if is_day else 293.15,
        "water_density_kg_l": 0.9973 if is_day else 0.9982,
        "matric_potential_mpa": -0.08 if is_day else -0.04,
        "leaf_critical_potential_mpa": -1.8,
        "apar_mol_h": 0.8 if is_day else 0.0,
        "temperature_factor": 0.85 if is_day else 0.65,
        "potential_transpiration_l_day": 0.8 if is_day else 0.15,
        "duration_hours": 12.0,
        "evidence_label": "synthetic_only",
        "hydraulic_domain": {
            "model_id": "paper1-biology-v1",
            "version": "1.0.0",
            "purpose": "model_applicability",
            "osmolality_min": 0.0,
            "osmolality_max": 0.5,
            "temperature_k_min": 290.0,
            "temperature_k_max": 305.0,
            "permitted_evidence_label": "physics_constrained",
            "extrapolation_policy": "deny",
        },
    }


def _nominal_forcing_artifact(registry: SyntheticScenarioRegistry) -> dict[str, object]:
    records = []
    for water_id in WATER_IDS:
        for step_index, forcing in enumerate(
            registry.anchor.forcings_by_water_id[water_id]
        ):
            records.append(
                {
                    "water_id": water_id,
                    "recipe_id": RECIPE_IDS[water_id],
                    "step_index": step_index,
                    "start_hour": float(12 * step_index),
                    "forcing": _json_value(forcing),
                }
            )
    return {
        "schema_version": "1.1.0",
        "materialization_algorithm": "paper1_nominal_forcing_schedule_v2",
        "water_ids": list(WATER_IDS),
        "records": records,
        "evidence_label": "synthetic_only",
    }


def test_active_loader_accepts_full_scenario_and_sensitivity_registry() -> None:
    """Catches a loader that cannot consume the complete active v1.4 authority."""

    registry = load_synthetic_scenarios(SCENARIO_PATH)
    assert tuple(scenario.scenario_id.value for scenario in registry.all_scenarios) == (
        SCENARIO_IDS
    )
    assert len(registry.sensitivities) == 36


def test_safe_loader_preserves_every_registered_primitive_type() -> None:
    """Catches exponent lexemes that PyYAML resolves as strings or int drift."""

    raw = _raw_payload()
    legacy = yaml.safe_load(LEGACY_PATH.read_text(encoding="utf-8"))
    _assert_exact_primitive_types(
        raw["anchor"]["parameters"],
        legacy["biology_parameters"],
        "anchor.parameters",
    )
    _assert_exact_primitive_types(
        raw["anchor"]["initial_state"],
        legacy["initial_state"],
        "anchor.initial_state",
    )
    _assert_exact_primitive_types(
        raw["anchor"]["generator"],
        _expected_anchor_generator(),
        "anchor.generator",
    )
    for scenario_index, scenario in enumerate(
        [raw["anchor"], *raw["scenarios"]]
    ):
        for water_id in WATER_IDS:
            for step_index, forcing in enumerate(
                scenario["forcings_by_water_id"][water_id]
            ):
                _assert_exact_primitive_types(
                    forcing,
                    _forcing_payload(step_index, water_id),
                    (
                        f"scenarios[{scenario_index}].forcings_by_water_id."
                        f"{water_id}[{step_index}]"
                    ),
                )
    _assert_exact_primitive_types(
        raw["sensitivities"],
        _expected_sensitivities(),
        "sensitivities",
    )


def test_v14_scenario_projection_has_exact_expanded_nominal_forcing_hash() -> None:
    """Catches an incomplete, reordered, aliased, or numerically changed schedule."""

    raw = _raw_payload()
    registry = _scenario_projection(raw)
    assert registry.schema_version == "1.4.0"
    assert registry.water_recipe_registry_sha256 == WATER_RECIPE_REGISTRY_SHA256
    assert tuple(scenario.scenario_id.value for scenario in registry.all_scenarios) == (
        SCENARIO_IDS
    )
    for scenario in registry.all_scenarios:
        assert tuple(scenario.forcings_by_water_id) == WATER_IDS
        for water_id in WATER_IDS:
            schedule = scenario.forcings_by_water_id[water_id]
            assert len(schedule) == 168
            assert fsum(forcing.duration_hours for forcing in schedule) == 2016.0
            for step_index, forcing in enumerate(schedule):
                assert _json_value(forcing) == _forcing_payload(
                    step_index,
                    water_id,
                )
    artifact = _nominal_forcing_artifact(registry)
    assert len(artifact["records"]) == 336
    assert hashlib.sha256(canonical_json_bytes(artifact)).hexdigest() == (
        NOMINAL_FORCING_SHA256
    )


def test_v14_document_uses_detached_expansion_not_yaml_alias_authority() -> None:
    """Catches shared YAML objects or omitted repeated scenario sections."""

    raw = _raw_payload()
    rows = [raw["anchor"], *raw["scenarios"]]
    assert len(rows) == 10
    for left, right in zip(rows, rows[1:]):
        assert left["parameters"] is not right["parameters"]
        assert left["initial_state"] is not right["initial_state"]
        assert left["generator"] is not right["generator"]
        assert left["forcings_by_water_id"] is not right["forcings_by_water_id"]
        for water_id in WATER_IDS:
            assert (
                left["forcings_by_water_id"][water_id]
                is not right["forcings_by_water_id"][water_id]
            )


def test_all_sixty_h3_error_records_are_exact_cross_bound_and_detached() -> None:
    """Catches bare SDs, candidate-rule drift, or shared expanded H3 records."""

    raw = _raw_payload()
    raw_rows = [raw["anchor"], *raw["scenarios"]]
    registry = _scenario_projection(raw)
    assert len(raw_rows) == len(registry.all_scenarios) == 10
    expected = _h3_error_records()
    raw_records: list[dict[str, object]] = []
    typed_records: list[object] = []
    raw_error_sds: list[dict[str, object]] = []
    typed_error_sds: list[object] = []

    for raw_row, scenario in zip(raw_rows, registry.all_scenarios, strict=True):
        observed_raw = raw_row["generator"]["observation"][
            "h3_observation_error_by_endpoint"
        ]
        observed_typed = scenario.generator.observation.h3_observation_error_by_endpoint
        assert observed_raw == expected
        assert tuple(observed_raw) == tuple(H3_ERROR_AUTHORITIES)
        assert tuple(observed_typed) == tuple(H3_ERROR_AUTHORITIES)
        for candidate_id, authority in H3_ERROR_AUTHORITIES.items():
            raw_record = observed_raw[candidate_id]
            typed_record = observed_typed[candidate_id]
            assert tuple(raw_record) == (
                "candidate_id",
                "endpoint_id",
                "analysis_scale",
                "endpoint_unit",
                "error_sd",
            )
            assert tuple(raw_record["error_sd"]) == (
                "value",
                "unit",
                "evidence_label",
            )
            assert (
                raw_record["candidate_id"],
                raw_record["endpoint_id"],
                raw_record["analysis_scale"],
                raw_record["endpoint_unit"],
                raw_record["error_sd"]["value"],
                raw_record["error_sd"]["unit"],
            ) == (candidate_id, *authority)
            assert _json_value(typed_record) == expected[candidate_id]
            raw_records.append(raw_record)
            typed_records.append(typed_record)
            raw_error_sds.append(raw_record["error_sd"])
            typed_error_sds.append(typed_record.error_sd)

    assert len(raw_records) == len(typed_records) == 60
    assert len({id(record) for record in raw_records}) == 60
    assert len({id(record) for record in typed_records}) == 60
    assert len({id(error_sd) for error_sd in raw_error_sds}) == 60
    assert len({id(error_sd) for error_sd in typed_error_sds}) == 60


def test_h3_error_record_raw_mutations_fail_at_projection_boundary() -> None:
    """Catches a projection that accepts a bare, forged, or weakly typed record."""

    raw = _raw_payload()
    errors = raw["anchor"]["generator"]["observation"][
        "h3_observation_error_by_endpoint"
    ]
    original = deepcopy(_h3_error_records()["C1"])
    mutations = (
        ("bare_quantity", _rq(0.05, "log-ratio")),
        ("candidate_id", {**original, "candidate_id": "C2"}),
        (
            "endpoint_id",
            {**original, "endpoint_id": "root_h2o2_concentration_time_auc"},
        ),
        ("analysis_scale", {**original, "analysis_scale": "difference"}),
        ("endpoint_unit", {**original, "endpoint_unit": "invented-unit"}),
        (
            "error_sd_unit",
            {**original, "error_sd": _rq(0.05, "nmol g_root_fresh_mass^-1")},
        ),
        (
            "integer_error_sd",
            {**original, "error_sd": {**original["error_sd"], "value": 1}},
        ),
        ("extra_key", {**original, "unregistered": "value"}),
    )
    for mutation_name, replacement in mutations:
        errors["C1"] = replacement
        with pytest.raises(ValidationError) as captured:
            _scenario_projection(raw)
        assert "h3_observation_error_by_endpoint" in str(captured.value), mutation_name
        errors["C1"] = deepcopy(original)


def test_anchor_generator_is_exact_and_all_scenario_inputs_are_conservative() -> None:
    """Catches a missing unit, wrong anchor, or generated input evidence inflation."""

    registry = _scenario_projection(_raw_payload())
    assert registry.anchor.generator.model_dump(mode="json") == (
        _expected_anchor_generator()
    )
    legacy = yaml.safe_load(LEGACY_PATH.read_text(encoding="utf-8"))
    for scenario in registry.all_scenarios:
        assert scenario.schema_version == "1.4.0"
        assert scenario.evidence_label.value == "synthetic_only"
        assert _json_value(scenario.parameters) == legacy[
            "biology_parameters"
        ]
        initial_state = _json_value(scenario.initial_state)
        assert isinstance(initial_state, dict)
        assert set(initial_state["network_state"]["tracked_entities"]) == set(
            legacy["initial_state"]["network_state"]["tracked_entities"]
        )
        initial_state["network_state"]["tracked_entities"] = legacy[
            "initial_state"
        ]["network_state"]["tracked_entities"]
        assert initial_state == legacy["initial_state"]


def test_scenario_whitelist_allows_only_exact_registered_leaf_differences() -> None:
    """Catches a retired forcing edit, direct outcome edit, or extra mechanism leaf."""

    registry = _scenario_projection(_raw_payload())
    anchor = registry.anchor.model_dump(mode="json")
    anchor.pop("scenario_id")
    anchor_leaves = _flatten_leaves(anchor)
    expected = {
        "perfect_control": set(),
        "true_ion_exclusion": {
            "mechanism.biology_parameter_overrides.root_na_permeability_l_cm2_h"
        },
        "root_na_accumulation": {
            "mechanism.biology_parameter_overrides.na_efflux_vmax_mmol_h"
        },
        "marker_only": {"mechanism.biology_parameter_overrides.ros_clearance_h_inv"},
        "nonsaline_penalty": {
            "mechanism.biology_parameter_overrides."
            "mannitol_carbon_cost_mmol_c_mmol_inv"
        },
        "chassis_interaction": {
            "mechanism.chassis_id",
            "mechanism.candidate_chassis_mechanism_modifiers.C5."
            "xylem_na_retrieval_multiplier.operation",
            "mechanism.candidate_chassis_mechanism_modifiers.C5."
            "xylem_na_retrieval_multiplier.factor",
        },
        "delayed_toxicity": {
            "mechanism.onset_time_days.value",
            "mechanism.onset_time_days.unit",
            "mechanism.onset_time_days.evidence_label",
            "mechanism.post_onset_biology_parameter_overrides.senescence_h_inv",
        },
        "sensor_drift_missingness": {
            "generator.observation.canopy_observation_error_sd.value",
            "generator.missingness.missingness_stress_slope.value",
            "generator.drift.calibration_interval_days.value",
            "generator.drift.calibration_phase_offset_days.value",
            "generator.drift.canopy_drift_per_day.value",
            *{
                f"generator.drift.ion_drift_per_day_by_endpoint.{endpoint_id}.value"
                for endpoint_id in ION_ENDPOINT_IDS
            },
            *{
                f"generator.drift.h3_drift_per_day_by_endpoint.{endpoint_id}.value"
                for endpoint_id in H3_ENDPOINT_IDS
            },
            *{
                "generator.drift.post_calibration_residual_sd_by_endpoint."
                f"{endpoint_id}.value"
                for endpoint_id in ENDPOINT_IDS
            },
        },
        "insufficient_purge": {"generator.water_loop.purge_volume_l_day.value"},
        "selection_bias_false_leader": {"generator.hierarchy.plant_variance.value"},
    }
    for scenario in registry.all_scenarios:
        payload = scenario.model_dump(mode="json")
        scenario_id = payload.pop("scenario_id")
        leaves = _flatten_leaves(payload)
        changed = {
            *{path for path in anchor_leaves if leaves.get(path) != anchor_leaves[path]},
            *{path for path in leaves if path not in anchor_leaves},
        }
        assert changed == expected[scenario_id]


def test_delayed_onset_and_b18_epoch_values_enforce_left_limit_and_nonzero_drift() -> None:
    """Catches day-42 retroactivity or a B18 reset coinciding with observations."""

    registry = _scenario_projection(_raw_payload())
    by_id = {scenario.scenario_id.value: scenario for scenario in registry.all_scenarios}
    delayed = by_id["delayed_toxicity"]
    assert delayed.mechanism.onset_time_days.model_dump(mode="json") == _rq(
        42.0,
        "day",
    )
    assert delayed.mechanism.post_onset_biology_parameter_overrides == {
        "senescence_h_inv": 0.06
    }
    b18 = by_id["sensor_drift_missingness"].generator
    assert b18.drift.calibration_interval_days.value == 14.0
    assert b18.drift.calibration_phase_offset_days.value == -7.0
    for scheduled_day in (0.0, 14.0, 28.0, 42.0, 56.0, 70.0, 84.0):
        interval = b18.drift.calibration_interval_days.value
        offset = b18.drift.calibration_phase_offset_days.value
        epoch_index = floor((scheduled_day - offset) / interval)
        elapsed = scheduled_day - (offset + epoch_index * interval)
        assert elapsed == 7.0


def test_hierarchy_values_are_variances_transformed_from_unit_normals_once() -> None:
    """Catches treating registered hierarchy variances as standard deviations."""

    hierarchy = _scenario_projection(_raw_payload()).anchor.generator.hierarchy
    z_values = (1.0, -1.0, 0.5, 2.0)
    variances = (
        hierarchy.run_variance.value,
        hierarchy.batch_variance.value,
        hierarchy.reservoir_variance.value,
        hierarchy.plant_variance.value,
    )
    effects = tuple(sqrt(variance) * z for variance, z in zip(variances, z_values))
    assert effects == pytest.approx(
        (sqrt(0.02), -sqrt(0.02), 0.1, 2.0 * sqrt(0.1)),
        rel=0.0,
        abs=1e-15,
    )
    assert exp(fsum(effects)) == pytest.approx(2.080182295694462, rel=1e-15)


def _document_paths(section: str, map_name: str, endpoints: tuple[str, ...]) -> list[str]:
    prefix = f"configs/synthetic_scenarios.yaml::anchor.generator.{section}.{map_name}"
    return [f"{prefix}.{endpoint_id}" for endpoint_id in endpoints]


def _expected_sensitivities() -> list[dict[str, object]]:
    scenario = "configs/synthetic_scenarios.yaml::"
    recipe = "configs/paper1_water_recipes.yaml::"
    anchor = f"{scenario}anchor.generator."
    limit_paths = [
        *_document_paths("censoring", "lod_by_endpoint", LIMIT_ENDPOINT_IDS),
        *_document_paths("censoring", "loq_by_endpoint", LIMIT_ENDPOINT_IDS),
    ]
    limit_variation_paths = [
        *_document_paths("censoring", "lod_log_sd_by_endpoint", LIMIT_ENDPOINT_IDS),
        *_document_paths("censoring", "loq_log_sd_by_endpoint", LIMIT_ENDPOINT_IDS),
    ]
    rows = [
        (
            "S001_charge_tolerance",
            [
                f"{anchor}chemistry.charge_balance_tolerance_percent",
                f"{recipe}active_recipes[water_id={WATER_IDS[0]}]."
                "charge_balance_tolerance_percent",
                f"{recipe}active_recipes[water_id={WATER_IDS[1]}]."
                "charge_balance_tolerance_percent",
            ],
            [0.1, 0.5, 2.0],
            "percent",
            [1.0, 1.0, 1.0],
        ),
        (
            "S002_temperature_phi",
            [f"{anchor}climate.temperature_ar1_phi"],
            [0.4, 0.9],
            "dimensionless",
            [0.7],
        ),
        (
            "S003_apar_phi",
            [f"{anchor}climate.apar_ar1_phi"],
            [0.4, 0.9],
            "dimensionless",
            [0.6],
        ),
        (
            "S004_matric_phi",
            [f"{anchor}climate.matric_potential_ar1_phi"],
            [0.4, 0.9],
            "dimensionless",
            [0.8],
        ),
        (
            "S005_temperature_sd",
            [f"{anchor}climate.temperature_innovation_sd_k"],
            [0.175, 0.7],
            "K",
            [0.35],
        ),
        (
            "S006_apar_sd",
            [f"{anchor}climate.apar_log_innovation_sd"],
            [0.05, 0.2],
            "log-ratio",
            [0.1],
        ),
        (
            "S007_matric_sd",
            [f"{anchor}climate.matric_potential_innovation_sd_mpa"],
            [0.003, 0.012],
            "MPa",
            [0.006],
        ),
        (
            "S008_transpiration_sd",
            [f"{anchor}climate.potential_transpiration_log_innovation_sd"],
            [0.04, 0.16],
            "log-ratio",
            [0.08],
        ),
        (
            "S009_burnin",
            [f"{anchor}climate.climate_initialization_burnin_steps"],
            [32, 128],
            "count",
            [64],
        ),
        (
            "S010_common_ion_sd",
            [f"{anchor}chemistry.common_ion_log_sd"],
            [0.015, 0.06],
            "log-ratio",
            [0.03],
        ),
        (
            "S011_boron_sd",
            [f"{anchor}chemistry.boron_log_sd"],
            [0.04, 0.16],
            "log-ratio",
            [0.08],
        ),
        (
            "S012_chemistry_measurement_sd",
            [
                f"{anchor}chemistry.ec_measurement_sd_ds_m",
                f"{anchor}chemistry.osmolality_measurement_sd_osmol_kg",
                f"{anchor}chemistry.ph_measurement_sd",
                f"{anchor}chemistry.temperature_measurement_sd_k",
            ],
            [0.5, 2.0],
            "multiplier",
            [0.05, 0.002, 0.03, 0.2],
        ),
        (
            "S013_initial_volume",
            [f"{anchor}water_loop.reservoir_initial_volume_l"],
            [100.0, 140.0],
            "L",
            [120.0],
        ),
        (
            "S014_return_fraction",
            [f"{anchor}water_loop.drainage_return_fraction"],
            [0.5, 0.9],
            "dimensionless",
            [0.7],
        ),
        (
            "S015_irrigation",
            [f"{anchor}water_loop.irrigation_volume_l_per_plant_day"],
            [0.4, 0.8],
            "L plant^-1 day^-1",
            [0.6],
        ),
        (
            "S016_anchor_purge",
            [f"{anchor}water_loop.purge_volume_l_day"],
            [0.6, 2.4],
            "L day^-1",
            [1.2],
        ),
        (
            "S017_sample_volume",
            [f"{anchor}water_loop.sampling_volume_l_per_sample"],
            [0.025, 0.1],
            "L sample^-1",
            [0.05],
        ),
        (
            "S018_canopy_error",
            [f"{anchor}observation.canopy_observation_error_sd"],
            [0.025, 0.1],
            "log-ratio",
            [0.05],
        ),
        (
            "S019_ion_error",
            [f"{anchor}observation.ion_observation_error_sd"],
            [0.02, 0.08],
            "log-ratio",
            [0.04],
        ),
        (
            "S020_heteroscedasticity",
            [
                f"{anchor}observation.canopy_heteroscedastic_log_slope",
                f"{anchor}observation.ion_heteroscedastic_log_slope",
            ],
            [0.5, 2.0],
            "multiplier",
            [0.1, 0.08],
        ),
        (
            "S021_limits",
            limit_paths,
            [0.5, 2.0],
            "multiplier",
            [
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
            ],
        ),
        (
            "S022_limit_variation",
            limit_variation_paths,
            [0.0, 0.025, 0.1],
            "log-ratio",
            [0.05] * 16,
        ),
        (
            "S023_calibration_interval",
            [f"{anchor}drift.calibration_interval_days"],
            [3.5, 14.0],
            "day",
            [7.0],
        ),
        (
            "S024_drift_residuals",
            _document_paths(
                "drift",
                "post_calibration_residual_sd_by_endpoint",
                ENDPOINT_IDS,
            ),
            [0.5, 2.0],
            "multiplier",
            [
                0.005,
                0.01,
                0.01,
                0.01,
                0.01,
                0.01,
                0.01,
                0.01,
                0.25,
                0.01,
            ],
        ),
        (
            "S025_death_heterogeneity",
            [
                f"{anchor}death.biomass_death_threshold_log_sd",
                f"{anchor}death.injury_death_threshold_log_sd",
                f"{anchor}death.sustained_injury_duration_log_sd",
            ],
            [0.0, 0.05, 0.2, 0.3],
            "log-ratio",
            [0.1, 0.1, 0.1],
        ),
        (
            "S026_missingness_intercept",
            [f"{anchor}missingness.missingness_intercept"],
            [-4.0, -2.0],
            "logit",
            [-3.0],
        ),
        (
            "S027_mar_slope",
            [f"{anchor}missingness.missingness_stress_slope"],
            [0.0, 0.4, 0.8],
            "logit/SD",
            [0.2],
        ),
        (
            "S028_mnar_delta",
            [f"{anchor}missingness.mnar_tipping_delta"],
            [-0.2, -0.1, 0.0, 0.2],
            "logit/SD",
            [0.1],
        ),
        (
            "S029_parameter_xtol",
            [f"{anchor}calibration.parameter_xtol"],
            [1.0e-8, 1.0e-4],
            "dimensionless",
            [1.0e-6],
        ),
        (
            "S030_parameter_rtol",
            [f"{anchor}calibration.parameter_rtol"],
            [1.0e-8, 1.0e-4],
            "dimensionless",
            [1.0e-6],
        ),
        (
            "S031_panel_size",
            [
                f"{anchor}calibration.fit_panel_size",
                f"{anchor}calibration.holdout_panel_size",
            ],
            [32, 128],
            "count",
            [64, 64],
        ),
        (
            "S032_holdout_tolerance",
            [f"{anchor}calibration.holdout_tolerance_log_ratio"],
            [0.01, 0.05],
            "log-ratio",
            [0.02],
        ),
        (
            "S033_confirmation_cell",
            [f"{anchor}design.confirmation_plants_per_group_reservoir"],
            [5],
            "count",
            [6],
        ),
        (
            "S034_chassis_modifier",
            [
                f"{scenario}scenarios[scenario_id=chassis_interaction].mechanism."
                "candidate_chassis_mechanism_modifiers.C5."
                "xylem_na_retrieval_multiplier.factor"
            ],
            [0.6, 1.0],
            "dimensionless",
            [0.8],
        ),
        (
            "S035_delayed_onset",
            [
                f"{scenario}scenarios[scenario_id=delayed_toxicity].mechanism."
                "onset_time_days"
            ],
            [28.0, 56.0],
            "day",
            [42.0],
        ),
        (
            "S036_insufficient_purge",
            [
                f"{scenario}scenarios[scenario_id=insufficient_purge].generator."
                "water_loop.purge_volume_l_day"
            ],
            [0.0, 0.3],
            "L day^-1",
            [0.12],
        ),
    ]
    return [
        {
            "sensitivity_id": sensitivity_id,
            "mode": "one_at_a_time",
            "paths": paths,
            "values": values,
            "unit": unit,
            "anchor_value": anchor_value,
            "evidence_label": "hypothesis_prior",
        }
        for sensitivity_id, paths, values, unit, anchor_value in rows
    ]


def test_sensitivity_registry_has_exact_ids_fields_paths_anchors_and_values() -> None:
    """Catches suffix pointers, wildcard expansion, bundles, or anchor drift."""

    sensitivities = _raw_payload()["sensitivities"]
    assert sensitivities == _expected_sensitivities()
    assert len(sensitivities) == 36
    assert len({row["sensitivity_id"] for row in sensitivities}) == 36
    assert all(
        tuple(row) == (
            "sensitivity_id",
            "mode",
            "paths",
            "values",
            "unit",
            "anchor_value",
            "evidence_label",
        )
        for row in sensitivities
    )
    all_paths = [path for row in sensitivities for path in row["paths"]]
    assert all(path.startswith("configs/") and "::" in path for path in all_paths)
    assert all("*" not in path and "..." not in path for path in all_paths)


def _source_batch_debit(
    *,
    initial_volume_l: float,
    return_fraction: float,
    plants_per_loop: int,
    loop_count: int,
) -> float:
    irrigation = 0.6 * plants_per_loop
    regular_makeup = irrigation * (1.0 - return_fraction) + 1.2
    restored_sample_volume = 6.0 * 0.05
    per_loop = initial_volume_l + 84.0 * regular_makeup + restored_sample_volume
    return float(loop_count) * per_loop


def test_s013_covers_v0_and_s014_registers_structural_capacity_failure() -> None:
    """Catches a fixed 120-L closure or silent capacity increase for S014."""

    sensitivities = {
        row["sensitivity_id"]: row for row in _raw_payload()["sensitivities"]
    }
    assert sensitivities["S013_initial_volume"]["values"] == [100.0, 140.0]
    assert sensitivities["S014_return_fraction"]["values"] == [0.5, 0.9]
    assert tuple(
        _source_batch_debit(
            initial_volume_l=value,
            return_fraction=0.7,
            plants_per_loop=45,
            loop_count=4,
        )
        for value in (100.0, 140.0)
    ) == (3526.0, 3686.0)
    assert tuple(
        _source_batch_debit(
            initial_volume_l=value,
            return_fraction=0.7,
            plants_per_loop=30,
            loop_count=6,
        )
        for value in (100.0, 140.0)
    ) == pytest.approx((3928.2, 4168.2), abs=1e-12)
    assert tuple(
        _source_batch_debit(
            initial_volume_l=value,
            return_fraction=0.7,
            plants_per_loop=25,
            loop_count=6,
        )
        for value in (100.0, 140.0)
    ) == pytest.approx((3474.6, 3714.6), abs=1e-12)
    overloaded = tuple(
        _source_batch_debit(
            initial_volume_l=120.0,
            return_fraction=0.5,
            plants_per_loop=plants,
            loop_count=loops,
        )
        for plants, loops in ((45, 4), (30, 6), (25, 6))
    )
    assert overloaded == pytest.approx((5420.4, 5862.6, 5106.6), abs=1e-12)
    assert all(debit > 5000.0 for debit in overloaded)


def _registered_sensitivity_authority() -> object:
    record_type = getattr(paper1_contracts, "SensitivityRecord")
    registry_type = getattr(paper1_contracts, "SensitivityRegistry")
    records = tuple(
        record_type.model_validate(row) for row in _raw_payload()["sensitivities"]
    )
    return registry_type.model_validate(
        {"schema_version": "1.0.0", "records": records}
    )


def _apply_sensitivity(
    authority: object,
    scenarios: SyntheticScenarioRegistry,
    recipes: object,
    selections: tuple[tuple[str, int], ...],
    *,
    occupied_run_ids: frozenset[str] = frozenset(),
    capacity_authorities: tuple[
        tuple[object, object, object, object], ...
    ] = (),
) -> object:
    return getattr(paper1_contracts, "apply_registered_sensitivity")(
        authority,
        scenario_registry=scenarios,
        recipe_registry=recipes,
        selections=selections,
        occupied_run_ids=occupied_run_ids,
        capacity_authorities=capacity_authorities,
        stop_policy=load_task4_stop_policy(STOP_POLICY_PATH),
    )


def _discovery_capacity_authorities() -> tuple[
    tuple[object, object, object, object], ...
]:
    inputs = load_randomization_fixture(TASK3_FIXTURE_PATH)
    design = load_paper1_design(DESIGN_PATH)
    manifest = randomize(
        design,
        20260812,
        position_map=inputs.position_map,
        baseline_roster=inputs.baseline_roster,
    )
    return (
        (
            design,
            inputs.baseline_roster,
            inputs.position_map,
            manifest,
        ),
    )


def _replaced_registry_record(
    authority: object,
    record_index: int,
    **updates: object,
) -> object:
    records = list(authority.records)  # type: ignore[attr-defined]
    records[record_index] = records[record_index].model_copy(update=updates)
    return authority.model_copy(update={"records": tuple(records)})  # type: ignore[attr-defined]


def test_public_sensitivity_models_preserve_exact_schema_types_and_84_paths() -> None:
    """Catches coercive models, omitted paths, duplicate pointers, or record drift."""

    authority = _registered_sensitivity_authority()
    record_type = getattr(paper1_contracts, "SensitivityRecord")
    registry_type = getattr(paper1_contracts, "SensitivityRegistry")
    assert type(authority) is registry_type
    assert len(authority.records) == 36
    assert all(type(record) is record_type for record in authority.records)
    assert [record.model_dump(mode="json") for record in authority.records] == (
        _expected_sensitivities()
    )
    paths = tuple(path for record in authority.records for path in record.paths)
    assert len(paths) == len(set(paths)) == 84
    for record in authority.records:
        numeric_type = int if record.unit == "count" else float
        assert all(type(value) is numeric_type for value in record.values)
        assert all(type(value) is numeric_type for value in record.anchor_value)


@pytest.mark.parametrize("hostile", (True, "0.4"))
def test_sensitivity_record_rejects_nonprimitive_or_wrong_numeric_types(
    hostile: object,
) -> None:
    """Catches bool/string coercion at the public registration boundary."""

    row = deepcopy(_expected_sensitivities()[1])
    row["values"][0] = hostile
    with pytest.raises(ValidationError):
        getattr(paper1_contracts, "SensitivityRecord").model_validate(row)


@pytest.mark.parametrize(
    ("field_name", "replacement"),
    (
        ("sensitivity_id", type("TextSubclass", (str,), {})('S002_temperature_phi')),
        ("mode", type("TextSubclass", (str,), {})("one_at_a_time")),
        ("unit", type("TextSubclass", (str,), {})("dimensionless")),
        ("evidence_label", type("TextSubclass", (str,), {})("hypothesis_prior")),
        (
            "paths",
            (
                type("TextSubclass", (str,), {})(
                    "configs/synthetic_scenarios.yaml::anchor.generator."
                    "climate.temperature_ar1_phi"
                ),
            ),
        ),
    ),
)
def test_sensitivity_record_rejects_text_subclasses(
    field_name: str,
    replacement: object,
) -> None:
    """Catches subclass-only state crossing the prospective text boundary."""

    row = deepcopy(_expected_sensitivities()[1])
    row[field_name] = replacement
    with pytest.raises(ValidationError):
        getattr(paper1_contracts, "SensitivityRecord").model_validate(row)


def test_sensitivity_registry_rejects_forged_nested_copies() -> None:
    """Catches Pydantic copy bypass at either sensitivity authority level."""

    authority = _registered_sensitivity_authority()
    forged_record = authority.records[0].model_copy(
        update={"mode": "not_one_at_a_time"}
    )
    forged = authority.model_copy(
        update={"records": (forged_record, *authority.records[1:])}
    )
    with pytest.raises(AlmondLabError) as captured:
        _apply_sensitivity(
            forged,
            _scenario_projection(_raw_payload()),
            load_paper1_water_recipes(RECIPE_PATH),
            (("S002_temperature_phi", 0),),
        )
    assert captured.value.code == "SENSITIVITY_REGISTRY_INVALID"


def test_public_loader_rejects_duplicate_merge_alias_and_cycle_syntax(
    tmp_path: Path,
) -> None:
    """Catches a scenario boundary that permits alternate YAML graph authority."""

    documents = (
        (
            "duplicate",
            'schema_version: "1.4.0"\nschema_version: "1.4.0"\n',
            None,
        ),
        (
            "merge",
            'base: &base {schema_version: "1.4.0"}\n<<: *base\n',
            "YamlMergeKeyError",
        ),
        (
            "alias",
            'schema_version: &version "1.4.0"\ncopy: *version\n',
            "YamlAliasReferenceError",
        ),
        (
            "cycle",
            'schema_version: "1.4.0"\ncycle: &cycle [*cycle]\n',
            "YamlAliasCycleError",
        ),
    )
    for name, contents, cause_type in documents:
        path = tmp_path / f"{name}.yaml"
        path.write_text(contents, encoding="utf-8", newline="\n")
        with pytest.raises(AlmondLabError) as captured:
            load_synthetic_scenarios(path)
        assert captured.value.code == "SYNTHETIC_SCENARIO_INVALID", name
        assert captured.value.field_path == "yaml", name
        assert captured.value.details is not None, name
        if cause_type is None:
            assert captured.value.details.get("duplicate_key") == "schema_version"
        else:
            assert captured.value.details.get("cause_type") == cause_type, name


def test_public_loader_rejects_anchor_only_and_task4_node_budget_overflow(
    tmp_path: Path,
) -> None:
    """Catches hidden YAML identity or widening Task 4 past 175,000 nodes."""

    anchor_path = tmp_path / "anchor.yaml"
    anchor_path.write_text(
        'schema_version: &version "1.4.0"\ncopy: "literal"\n',
        encoding="utf-8",
        newline="\n",
    )
    with pytest.raises(AlmondLabError) as anchor_error:
        load_synthetic_scenarios(anchor_path)
    assert anchor_error.value.code == "SYNTHETIC_SCENARIO_INVALID"
    assert anchor_error.value.field_path == "yaml"
    assert anchor_error.value.details is not None
    assert anchor_error.value.details.get("cause_type") == "YamlAnchorDefinitionError"

    oversized_path = tmp_path / "oversized.yaml"
    oversized_path.write_text(
        '{"schema_version":"1.4.0","padding":['
        + ",".join("0" for _ in range(175_001))
        + "]}\n",
        encoding="utf-8",
        newline="\n",
    )
    with pytest.raises(AlmondLabError) as budget_error:
        load_synthetic_scenarios(oversized_path)
    assert budget_error.value.code == "SYNTHETIC_SCENARIO_INVALID"
    assert budget_error.value.field_path == "yaml"
    assert budget_error.value.details is not None
    assert budget_error.value.details.get("cause_type") == "YamlResourceLimitError"


def test_public_loader_rejects_oversized_scalar_and_nested_schema_decoy(
    tmp_path: Path,
) -> None:
    """Catches byte-budget or non-root schema-version migration bypasses."""

    oversized_path = tmp_path / "oversized-scalar.yaml"
    oversized_path.write_text(
        'schema_version: "1.4.0"\npadding: "'
        + ("x" * 4_000_000)
        + '"\n',
        encoding="utf-8",
        newline="\n",
    )
    with pytest.raises(AlmondLabError) as oversized_error:
        load_synthetic_scenarios(oversized_path)
    assert oversized_error.value.code == "SYNTHETIC_SCENARIO_INVALID"
    assert oversized_error.value.field_path == "yaml"
    assert oversized_error.value.details is not None
    assert oversized_error.value.details.get("cause_type") == "YamlResourceLimitError"

    nested_path = tmp_path / "nested-schema-decoy.yaml"
    nested_path.write_text(
        'decoy:\n  schema_version: "1.4.0"\nschema_version: "1.3.0"\n',
        encoding="utf-8",
        newline="\n",
    )
    with pytest.raises(AlmondLabError) as nested_error:
        load_synthetic_scenarios(nested_path)
    assert nested_error.value.code == "SCENARIO_SCHEMA_MIGRATION_REQUIRED"
    assert nested_error.value.field_path == "schema_version"


def test_public_loader_rejects_oversized_file_before_read_text(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Catches allocating or decoding an oversized authority before stat rejection."""

    oversized_path = tmp_path / "oversized-pre-read.yaml"
    oversized_path.write_bytes(b"x" * 3_500_001)
    original = Path.read_text

    def guarded_read_text(self: Path, *args: object, **kwargs: object) -> str:
        if self == oversized_path:
            raise AssertionError("oversized Task 4 YAML was read before rejection")
        return original(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", guarded_read_text)
    with pytest.raises(AlmondLabError) as captured:
        load_synthetic_scenarios(oversized_path)
    assert captured.value.code == "SYNTHETIC_SCENARIO_INVALID"
    assert captured.value.field_path == "yaml"
    assert captured.value.details is not None
    assert captured.value.details.get("cause_type") == "YamlResourceLimitError"


def test_public_loader_bounds_read_when_file_grows_after_stat(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Catches a stat/read race allocating beyond the Task 4 byte budget."""

    path = tmp_path / "growing.yaml"
    path.write_bytes(b"schema_version: 1.4.0\n")
    original_open = Path.open

    class GrowingReader:
        def __enter__(self) -> "GrowingReader":
            return self

        def __exit__(self, *args: object) -> None:
            return None

        def read(self, size: int = -1) -> bytes:
            assert size == 3_500_001
            return b"x" * size

    def bounded_open(self: Path, *args: object, **kwargs: object) -> object:
        if self == path:
            return GrowingReader()
        return original_open(self, *args, **kwargs)

    monkeypatch.setattr(Path, "open", bounded_open)
    with pytest.raises(AlmondLabError) as captured:
        load_synthetic_scenarios(path)
    assert captured.value.code == "SYNTHETIC_SCENARIO_INVALID"
    assert captured.value.field_path == "yaml"
    assert captured.value.details is not None
    assert captured.value.details.get("cause_type") == "YamlResourceLimitError"


def test_schema_inspection_obeys_depth_budget_before_composition(tmp_path: Path) -> None:
    """Catches composing a deep graph before the strict Task 4 token budget."""

    path = tmp_path / "deep-decoy.yaml"
    nested = "value"
    for _ in range(65):
        nested = f"[{nested}]"
    path.write_text(
        f'schema_version: "1.4.0"\npadding: {nested}\n',
        encoding="utf-8",
        newline="\n",
    )
    with pytest.raises(AlmondLabError) as captured:
        load_synthetic_scenarios(path)
    assert captured.value.code == "SYNTHETIC_SCENARIO_INVALID"
    assert captured.value.field_path == "yaml"
    assert captured.value.details is not None
    assert captured.value.details.get("cause_type") == "YamlResourceLimitError"


def test_registered_absolute_and_multiplier_bundles_apply_atomically_detached() -> None:
    """Catches scalar-only application, multiplier replacement, or shared mutation."""

    authority = _registered_sensitivity_authority()
    scenarios = _scenario_projection(_raw_payload())
    recipes = load_paper1_water_recipes(RECIPE_PATH)
    absolute = _apply_sensitivity(
        authority,
        scenarios,
        recipes,
        (("S001_charge_tolerance", 0),),
    )
    assert scenarios.anchor.generator.chemistry.charge_balance_tolerance_percent.value == 1.0
    assert all(
        recipe.charge_balance_tolerance_percent.value == 1.0
        for recipe in recipes.active_recipes
    )
    assert absolute.scenario_registry is not scenarios
    assert absolute.recipe_registry is not recipes
    assert absolute.scenario_registry.anchor.generator is not scenarios.anchor.generator
    assert absolute.scenario_registry.anchor.generator.chemistry.charge_balance_tolerance_percent.value == 0.1
    assert all(
        recipe.charge_balance_tolerance_percent.value == 0.1
        for recipe in absolute.recipe_registry.active_recipes
    )
    assert absolute.applied_paths == authority.records[0].paths
    assert absolute.applied_values == (0.1, 0.1, 0.1)

    multiplier = _apply_sensitivity(
        authority,
        scenarios,
        recipes,
        (("S012_chemistry_measurement_sd", 1),),
    )
    chemistry = multiplier.scenario_registry.anchor.generator.chemistry
    assert (
        chemistry.ec_measurement_sd_ds_m.value,
        chemistry.osmolality_measurement_sd_osmol_kg.value,
        chemistry.ph_measurement_sd.value,
        chemistry.temperature_measurement_sd_k.value,
    ) == (0.1, 0.004, 0.06, 0.4)


def test_application_revalidates_all_paths_and_bit_exact_anchors_before_write() -> None:
    """Catches validating only the selected row or accepting near-equal anchors."""

    authority = _registered_sensitivity_authority()
    scenarios = _scenario_projection(_raw_payload())
    recipes = load_paper1_water_recipes(RECIPE_PATH)
    target_index = next(
        index
        for index, record in enumerate(authority.records)
        if record.sensitivity_id == "S036_insufficient_purge"
    )
    record = authority.records[target_index]
    forged = _replaced_registry_record(
        authority,
        target_index,
        anchor_value=(nextafter(record.anchor_value[0], float("inf")),),
    )
    before_scenarios = canonical_json_bytes(_json_value(scenarios))
    before_recipes = canonical_json_bytes(_json_value(recipes))
    with pytest.raises(AlmondLabError) as captured:
        _apply_sensitivity(
            forged,
            scenarios,
            recipes,
            (("S002_temperature_phi", 0),),
        )
    assert captured.value.code == "SENSITIVITY_REGISTRY_INVALID"
    assert canonical_json_bytes(_json_value(scenarios)) == before_scenarios
    assert canonical_json_bytes(_json_value(recipes)) == before_recipes


@pytest.mark.parametrize(
    "selections",
    (
        (),
        (("S002_temperature_phi", 0), ("S003_apar_phi", 0)),
        (("S002_temperature_phi", 0), ("S002_temperature_phi", 1)),
        (("not_registered", 0),),
        (("S002_temperature_phi", 99),),
    ),
)
def test_application_rejects_empty_two_id_two_value_and_unregistered_requests(
    selections: tuple[tuple[str, int], ...],
) -> None:
    """Catches Cartesian, duplicate-ID, out-of-range, or empty sensitivity runs."""

    with pytest.raises(AlmondLabError) as captured:
        _apply_sensitivity(
            _registered_sensitivity_authority(),
            _scenario_projection(_raw_payload()),
            load_paper1_water_recipes(RECIPE_PATH),
            selections,
        )
    assert captured.value.code == "SENSITIVITY_REGISTRY_INVALID"


@pytest.mark.parametrize("mutation", ("partial", "duplicate_id", "wildcard", "suffix"))
def test_application_rejects_partial_duplicate_and_nonliteral_registry_authority(
    mutation: str,
) -> None:
    """Catches forged model copies bypassing complete literal bundle authority."""

    authority = _registered_sensitivity_authority()
    if mutation == "partial":
        index = 11
        record = authority.records[index]
        forged = _replaced_registry_record(
            authority,
            index,
            paths=record.paths[:-1],
            anchor_value=record.anchor_value[:-1],
        )
    elif mutation == "duplicate_id":
        forged = _replaced_registry_record(
            authority,
            35,
            sensitivity_id=authority.records[0].sensitivity_id,
        )
    else:
        record = authority.records[35]
        bad_path = (
            "configs/synthetic_scenarios.yaml::scenarios[*].generator.water_loop."
            "purge_volume_l_day"
            if mutation == "wildcard"
            else "generator.water_loop.purge_volume_l_day"
        )
        forged = _replaced_registry_record(
            authority,
            35,
            paths=(bad_path,),
            anchor_value=record.anchor_value,
        )
    with pytest.raises(AlmondLabError) as captured:
        _apply_sensitivity(
            forged,
            _scenario_projection(_raw_payload()),
            load_paper1_water_recipes(RECIPE_PATH),
            (("S002_temperature_phi", 0),),
        )
    assert captured.value.code == "SENSITIVITY_REGISTRY_INVALID"


def test_run_id_is_derived_from_id_and_index_and_collision_is_rejected() -> None:
    """Catches caller-chosen or colliding sensitivity run identities."""

    authority = _registered_sensitivity_authority()
    scenarios = _scenario_projection(_raw_payload())
    recipes = load_paper1_water_recipes(RECIPE_PATH)
    first = _apply_sensitivity(
        authority,
        scenarios,
        recipes,
        (("S002_temperature_phi", 0),),
    )
    second = _apply_sensitivity(
        authority,
        scenarios,
        recipes,
        (("S002_temperature_phi", 1),),
    )
    assert type(first.run_id) is str and first.run_id
    assert first.run_id != second.run_id
    with pytest.raises(AlmondLabError) as captured:
        _apply_sensitivity(
            authority,
            scenarios,
            recipes,
            (("S002_temperature_phi", 0),),
            occupied_run_ids=frozenset({first.run_id}),
        )
    assert captured.value.code == "SENSITIVITY_REGISTRY_INVALID"


@pytest.mark.parametrize(
    ("value_index", "panel_size", "fit_sha256", "holdout_sha256"),
    (
        (
            0,
            32,
            "8b042b703b1c5148886182b344317986776fef8d68e795688741f74d54d790e3",
            "80224dfe438556e8caa0ae561d79649acf465d8c09218bd429edb7d1bbc5f41a",
        ),
        (
            1,
            128,
            "91b9c4d937b0417097f6e4b7272eff4efcf4a6dfdc23e76c73876a7e5ae02cc9",
            "3df1fde7553bd5942a195e67eb7438f501e6ce6df3bd22f08397b623f5b97f11",
        ),
    ),
)
def test_s031_pairs_panel_counts_with_exact_registered_fixed_prefix_hashes(
    value_index: int,
    panel_size: int,
    fit_sha256: str,
    holdout_sha256: str,
) -> None:
    """Catches one-sided panel changes or inferred/unregistered panel hashes."""

    applied = _apply_sensitivity(
        _registered_sensitivity_authority(),
        _scenario_projection(_raw_payload()),
        load_paper1_water_recipes(RECIPE_PATH),
        (("S031_panel_size", value_index),),
    )
    calibration = applied.scenario_registry.anchor.generator.calibration
    assert calibration.fit_panel_size.value == panel_size
    assert calibration.holdout_panel_size.value == panel_size
    assert applied.calibration_panel_sha256s == {
        "fit": fit_sha256,
        "holdout": holdout_sha256,
    }


@pytest.mark.parametrize(
    "sensitivity_id",
    (
        "S013_initial_volume",
        "S014_return_fraction",
        "S015_irrigation",
        "S016_anchor_purge",
        "S017_sample_volume",
        "S036_insufficient_purge",
    ),
)
def test_exact_water_loop_sensitivity_set_requires_capacity_authority(
    sensitivity_id: str,
) -> None:
    """Catches any registered water-loop run bypassing shared-batch preflight."""

    with pytest.raises(AlmondLabError) as captured:
        _apply_sensitivity(
            _registered_sensitivity_authority(),
            _scenario_projection(_raw_payload()),
            load_paper1_water_recipes(RECIPE_PATH),
            ((sensitivity_id, 0),),
        )
    assert captured.value.code == "SENSITIVITY_REGISTRY_INVALID"
    assert captured.value.field_path == "capacity_authorities"


def test_s033_confirmation_cell_remains_outside_discovery_capacity_ingress() -> None:
    """Catches broadening the six water-loop gates to confirmation design size."""

    applied = _apply_sensitivity(
        _registered_sensitivity_authority(),
        _scenario_projection(_raw_payload()),
        load_paper1_water_recipes(RECIPE_PATH),
        (("S033_confirmation_cell", 0),),
    )
    assert (
        applied.scenario_registry.anchor.generator.design
        .confirmation_plants_per_group_reservoir.value
        == 5
    )
    assert applied.capacity_audits == ()


@pytest.mark.parametrize(
    ("sensitivity_id", "value_index", "expected_debit_l"),
    (
        ("S013_initial_volume", 0, 3526.0),
        ("S015_irrigation", 0, 2698.8),
        ("S016_anchor_purge", 0, 3404.4),
        ("S017_sample_volume", 0, 3605.4),
        ("S036_insufficient_purge", 0, 3202.8),
        ("S036_insufficient_purge", 1, 3303.6),
    ),
)
def test_water_loop_sensitivity_preflight_binds_selected_id_path_and_value(
    sensitivity_id: str,
    value_index: int,
    expected_debit_l: float,
) -> None:
    """Catches field-only binding or preflighting S036 against the anchor loop."""

    applied = _apply_sensitivity(
        _registered_sensitivity_authority(),
        _scenario_projection(_raw_payload()),
        load_paper1_water_recipes(RECIPE_PATH),
        ((sensitivity_id, value_index),),
        capacity_authorities=_discovery_capacity_authorities(),
    )
    assert len(applied.capacity_audits) == 4
    assert tuple(
        sorted(
            {
                audit.aggregate_expected_debit_l
                for audit in applied.capacity_audits
            }
        )
    ) == pytest.approx((expected_debit_l,), abs=1e-12)
    assert applied.scenario_registry.anchor.generator.water_loop.purge_volume_l_day.value == (
        0.6 if sensitivity_id == "S016_anchor_purge" else 1.2
    )
    if sensitivity_id == "S036_insufficient_purge":
        scenario = next(
            item
            for item in applied.scenario_registry.scenarios
            if item.scenario_id.value == "insufficient_purge"
        )
        assert scenario.generator.water_loop.purge_volume_l_day.value == (
            0.0 if value_index == 0 else 0.3
        )


def test_s014_low_return_runs_real_shared_batch_preflight_and_structurally_fails() -> None:
    """Catches RNG/output proceeding after the registered 5,000-L capacity failure."""

    scenarios = _scenario_projection(_raw_payload())
    recipes = load_paper1_water_recipes(RECIPE_PATH)
    scenarios_before = canonical_json_bytes(_json_value(scenarios))
    recipes_before = canonical_json_bytes(_json_value(recipes))
    with pytest.raises(AlmondLabError) as captured:
        _apply_sensitivity(
            _registered_sensitivity_authority(),
            scenarios,
            recipes,
            (("S014_return_fraction", 0),),
            capacity_authorities=_discovery_capacity_authorities(),
        )
    assert captured.value.code == "WATER_BATCH_CAPACITY_EXCEEDED"
    assert captured.value.details is not None
    assert captured.value.details["aggregate_expected_debit_l"] == pytest.approx(
        5420.4,
        abs=1e-12,
    )
    assert captured.value.details["capacity_l"] == 5000.0
    assert canonical_json_bytes(_json_value(scenarios)) == scenarios_before
    assert canonical_json_bytes(_json_value(recipes)) == recipes_before
