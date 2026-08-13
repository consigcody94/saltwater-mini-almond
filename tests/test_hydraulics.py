from math import isclose

from almondlab.hydraulics import HydraulicInputs, hydraulic_uptake


def test_perfect_na_exclusion_keeps_osmotic_penalty() -> None:
    """An ion-specific factor cannot erase the bulk osmotic potential."""
    common = dict(
        temperature_k=298.15,
        water_density_kg_l=0.997,
        matric_mpa=-0.10,
        leaf_critical_mpa=-2.00,
        adjustment_mpa=0.0,
        root_conductance_l_day_mpa=0.50,
        potential_transpiration_l_day=1.00,
        specific_ion_factor=1.00,
    )
    fresh = hydraulic_uptake(HydraulicInputs(osmolality_osmol_kg=0.05, **common))
    saline = hydraulic_uptake(HydraulicInputs(osmolality_osmol_kg=0.40, **common))

    assert isclose(fresh.actual_l_day, 0.888212, abs_tol=1e-6)
    assert isclose(saline.actual_l_day, 0.455696, abs_tol=1e-6)
    assert isclose(saline.actual_l_day / fresh.actual_l_day, 0.513049, abs_tol=1e-6)
