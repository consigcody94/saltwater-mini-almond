"""Physics-constrained osmotic and hydraulic uptake calculations."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite

from almondlab.errors import fail


GAS_CONSTANT_MPA_L_MOL_K = 0.008314462618


def _finite(value: float, field_path: str) -> float:
    converted = float(value)
    if not isfinite(converted):
        fail("HYDRAULIC_NONFINITE", "value must be finite", field_path)
    return converted


def osmotic_potential_mpa(
    osmolality_osmol_kg: float, temperature_k: float, density_kg_l: float
) -> float:
    """Return bulk osmotic potential from measured osmolality in MPa."""
    osmolality = _finite(osmolality_osmol_kg, "osmolality_osmol_kg")
    temperature = _finite(temperature_k, "temperature_k")
    density = _finite(density_kg_l, "density_kg_l")
    if osmolality < 0.0:
        fail("HYDRAULIC_INVALID_OSMOLALITY", "osmolality must be nonnegative", "osmolality_osmol_kg")
    if temperature <= 0.0:
        fail("HYDRAULIC_INVALID_TEMPERATURE", "temperature must be positive Kelvin", "temperature_k")
    if density <= 0.0:
        fail("HYDRAULIC_INVALID_DENSITY", "density must be positive", "density_kg_l")
    return -GAS_CONSTANT_MPA_L_MOL_K * temperature * density * osmolality


@dataclass(frozen=True)
class HydraulicInputs:
    """All explicitly unit-bearing inputs to the hydraulic uptake gate."""

    osmolality_osmol_kg: float
    temperature_k: float
    water_density_kg_l: float
    matric_mpa: float
    leaf_critical_mpa: float
    adjustment_mpa: float
    root_conductance_l_day_mpa: float
    potential_transpiration_l_day: float
    specific_ion_factor: float


@dataclass(frozen=True)
class HydraulicUptake:
    """Auditable hydraulic cap including every intermediate potential and flow."""

    osmotic_potential_mpa: float
    soil_potential_mpa: float
    leaf_limit_mpa: float
    hydraulic_capacity_l_day: float
    ion_limited_demand_l_day: float
    actual_l_day: float


def hydraulic_uptake(params: HydraulicInputs) -> HydraulicUptake:
    """Cap potential transpiration by the total-osmolality hydraulic limit."""
    values = {
        name: _finite(getattr(params, name), name)
        for name in (
            "matric_mpa",
            "leaf_critical_mpa",
            "adjustment_mpa",
            "root_conductance_l_day_mpa",
            "potential_transpiration_l_day",
            "specific_ion_factor",
        )
    }
    if values["root_conductance_l_day_mpa"] < 0.0:
        fail("HYDRAULIC_INVALID_CONDUCTANCE", "root conductance must be nonnegative", "root_conductance_l_day_mpa")
    if values["potential_transpiration_l_day"] < 0.0:
        fail("HYDRAULIC_INVALID_TRANSPIRATION", "potential transpiration must be nonnegative", "potential_transpiration_l_day")
    if not 0.0 <= values["specific_ion_factor"] <= 1.0:
        fail("HYDRAULIC_INVALID_ION_FACTOR", "specific ion factor must be in [0, 1]", "specific_ion_factor")

    osmotic = osmotic_potential_mpa(
        params.osmolality_osmol_kg, params.temperature_k, params.water_density_kg_l
    )
    soil = values["matric_mpa"] + osmotic
    leaf_limit = values["leaf_critical_mpa"] - values["adjustment_mpa"]
    hydraulic_capacity = max(
        0.0,
        values["root_conductance_l_day_mpa"] * (soil - leaf_limit),
    )
    ion_limited_demand = (
        values["potential_transpiration_l_day"] * values["specific_ion_factor"]
    )
    return HydraulicUptake(
        osmotic_potential_mpa=osmotic,
        soil_potential_mpa=soil,
        leaf_limit_mpa=leaf_limit,
        hydraulic_capacity_l_day=hydraulic_capacity,
        ion_limited_demand_l_day=ion_limited_demand,
        actual_l_day=min(ion_limited_demand, hydraulic_capacity),
    )
