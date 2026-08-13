"""Tracked Task 4 registration-artifact materializer.

This script creates no plant outcome and performs no mechanism calibration.  It
only expands the registered nominal forcing, operator/sample schedules, and
the exogenous fit/holdout climate panels described by the prospective
registration proposal.  Run with the repository's locked Python environment.
"""

from __future__ import annotations

import hashlib
from math import exp

from numpy import __version__ as numpy_version, ndarray
from numpy.random import Generator, PCG64, SeedSequence

from almondlab.provenance import canonical_json_bytes


SCHEMA_VERSION = "1.1.0"
ROOT_SEED = 420260813
WATER_IDS = (
    "nonsaline_nutrient_matched_control",
    "pilot_selected_full_ion_marine_challenge",
)
RECIPE_IDS = {
    WATER_IDS[0]: "paper1_base_nutrient_control_v1@1.0.0",
    WATER_IDS[1]: "paper1_base_plus_nacl40_challenge_v1@1.0.0",
}
HYDRAULIC_DOMAIN = {
    "model_id": "paper1-biology-v1",
    "version": "1.0.0",
    "purpose": "model_applicability",
    "osmolality_min": 0.0,
    "osmolality_max": 0.5,
    "temperature_k_min": 290.0,
    "temperature_k_max": 305.0,
    "permitted_evidence_label": "physics_constrained",
    "extrapolation_policy": "deny",
}


def _sha256(payload: object) -> str:
    return hashlib.sha256(canonical_json_bytes(payload)).hexdigest()


def _forcing(water_id: str, step_index: int) -> dict[str, object]:
    is_day = step_index % 2 == 0
    return {
        "measured_osmolality_osmol_kg": (
            0.02 if water_id == WATER_IDS[0] else 0.1
        ),
        "temperature_k": 297.15 if is_day else 293.15,
        "water_density_kg_l": 0.9973 if is_day else 0.9982,
        "matric_potential_mpa": -0.08 if is_day else -0.04,
        "leaf_critical_potential_mpa": -1.8,
        "apar_mol_h": 0.8 if is_day else 0.0,
        "temperature_factor": 0.85 if is_day else 0.65,
        "potential_transpiration_l_day": 0.8 if is_day else 0.15,
        "duration_hours": 12.0,
        "evidence_label": "synthetic_only",
        "hydraulic_domain": dict(HYDRAULIC_DOMAIN),
    }


def nominal_schedule_payload() -> dict[str, object]:
    records: list[dict[str, object]] = []
    for water_id in WATER_IDS:
        for step_index in range(168):
            records.append(
                {
                    "water_id": water_id,
                    "recipe_id": RECIPE_IDS[water_id],
                    "step_index": step_index,
                    "start_hour": float(12 * step_index),
                    "forcing": _forcing(water_id, step_index),
                }
            )
    return {
        "schema_version": SCHEMA_VERSION,
        "materialization_algorithm": "paper1_nominal_forcing_schedule_v2",
        "water_ids": list(WATER_IDS),
        "records": records,
        "evidence_label": "synthetic_only",
    }


def operator_times_payload() -> dict[str, object]:
    return {
        "schema_version": "1.0.0",
        "operator_event_times_days": [0.25 + index for index in range(84)],
    }


def sample_times_payload() -> dict[str, object]:
    return {
        "schema_version": SCHEMA_VERSION,
        "sample_timing": "before_same_day_operator_event_or_terminal_after_last_event",
        "reservoir_sample_times_days": [float(day) for day in range(0, 85, 14)],
        "sample_volume_l": 0.05,
        "evidence_label": "hypothesis_prior",
    }


def calibration_innovations(seed_sequence: SeedSequence) -> ndarray:
    """Draw the single registered 128-panel authority for one panel kind."""

    return Generator(PCG64(seed_sequence)).standard_normal((128, 4, 232))


def calibration_panel_payload(
    *,
    panel_kind: str,
    seed_sequence: SeedSequence,
    panel_size: int,
    innovations: ndarray,
) -> tuple[dict[str, object], tuple[tuple[float, float], ...]]:
    """Materialize one registered fixed-prefix calibration-panel artifact."""

    if panel_size not in (32, 64, 128):
        raise ValueError("panel_size must be one of 32, 64, or 128")
    if type(innovations) is not ndarray or innovations.shape != (128, 4, 232):
        raise ValueError("innovations must be the exact 128x4x232 authority")
    records: list[dict[str, object]] = []
    ranges = [[float("inf"), float("-inf")] for _ in range(4)]
    process = ((0.7, 0.35), (0.6, 0.10), (0.8, 0.006), (0.0, 0.08))

    for panel_index in range(panel_size):
        retained: list[list[float]] = []
        for variable_index, (phi, innovation_sd) in enumerate(process):
            anomaly = 0.0
            complete: list[float] = []
            for innovation in innovations[panel_index, variable_index]:
                anomaly = phi * anomaly + innovation_sd * float(innovation)
                complete.append(anomaly)
            retained.append(complete[64:])

        for water_id in WATER_IDS:
            for step_index in range(168):
                forcing = _forcing(water_id, step_index)
                temperature_k = float(forcing["temperature_k"]) + retained[0][step_index]
                apar_mol_h = float(forcing["apar_mol_h"]) * exp(
                    retained[1][step_index] - 0.5 * (0.10**2 / (1.0 - 0.60**2))
                )
                matric_potential_mpa = (
                    float(forcing["matric_potential_mpa"])
                    + retained[2][step_index]
                )
                potential_transpiration_l_day = float(
                    forcing["potential_transpiration_l_day"]
                ) * exp(retained[3][step_index] - 0.5 * 0.08**2)
                forcing.update(
                    {
                        "temperature_k": temperature_k,
                        "apar_mol_h": apar_mol_h,
                        "matric_potential_mpa": matric_potential_mpa,
                        "potential_transpiration_l_day": potential_transpiration_l_day,
                    }
                )
                for index, value in enumerate(
                    (
                        temperature_k,
                        apar_mol_h,
                        matric_potential_mpa,
                        potential_transpiration_l_day,
                    )
                ):
                    ranges[index][0] = min(ranges[index][0], value)
                    ranges[index][1] = max(ranges[index][1], value)
                records.append(
                    {
                        "panel_index": panel_index,
                        "water_id": water_id,
                        "recipe_id": RECIPE_IDS[water_id],
                        "step_index": step_index,
                        "start_hour": float(12 * step_index),
                        "forcing": forcing,
                    }
                )

    payload = {
        "schema_version": SCHEMA_VERSION,
        "panel_kind": panel_kind,
        "materialization_algorithm": "paper1_calibration_forcing_panel_v2",
        "root_seed": ROOT_SEED,
        "spawn_key": list(seed_sequence.spawn_key),
        "bit_generator": "PCG64",
        "numpy_version": "2.5.2",
        "panel_size": panel_size,
        "water_ids": list(WATER_IDS),
        "forcing_schema_version": "paper1_root_zone_forcing@1.0.0",
        "records": records,
        "evidence_label": "synthetic_only",
    }
    return payload, tuple((row[0], row[1]) for row in ranges)


def main() -> None:
    if numpy_version != "2.5.2":
        raise RuntimeError(f"NumPy 2.5.2 required, found {numpy_version}")
    calibration_family = SeedSequence(ROOT_SEED).spawn(12)[11]
    fit_seed, holdout_seed = calibration_family.spawn(2)
    fit_innovations = calibration_innovations(fit_seed)
    holdout_innovations = calibration_innovations(holdout_seed)
    print("nominal", _sha256(nominal_schedule_payload()))
    print("operator_times", _sha256(operator_times_payload()))
    print("sample_times", _sha256(sample_times_payload()))
    materialized: dict[tuple[str, int], dict[str, object]] = {}
    for panel_size in (32, 64, 128):
        fit, fit_ranges = calibration_panel_payload(
            panel_kind="fit",
            seed_sequence=fit_seed,
            panel_size=panel_size,
            innovations=fit_innovations,
        )
        holdout, holdout_ranges = calibration_panel_payload(
            panel_kind="holdout",
            seed_sequence=holdout_seed,
            panel_size=panel_size,
            innovations=holdout_innovations,
        )
        materialized[("fit", panel_size)] = fit
        materialized[("holdout", panel_size)] = holdout
        print(f"fit_{panel_size}", _sha256(fit), fit_ranges)
        print(f"holdout_{panel_size}", _sha256(holdout), holdout_ranges)
    for panel_kind in ("fit", "holdout"):
        records_32 = materialized[(panel_kind, 32)]["records"]
        records_64 = materialized[(panel_kind, 64)]["records"]
        records_128 = materialized[(panel_kind, 128)]["records"]
        assert isinstance(records_32, list)
        assert isinstance(records_64, list)
        assert isinstance(records_128, list)
        if records_32 != records_64[: len(records_32)]:
            raise RuntimeError(f"{panel_kind} 32-panel artifact is not a prefix")
        if records_64 != records_128[: len(records_64)]:
            raise RuntimeError(f"{panel_kind} 64-panel artifact is not a prefix")


if __name__ == "__main__":
    main()
