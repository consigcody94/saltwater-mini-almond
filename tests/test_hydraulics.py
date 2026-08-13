from math import isclose

import pytest

from almondlab.errors import AlmondLabError
from almondlab.hydraulics import HydraulicDomain, HydraulicInputs, hydraulic_uptake


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


def _inputs(**updates: object) -> HydraulicInputs:
    values: dict[str, object] = {
        "osmolality_osmol_kg": 0.05,
        "temperature_k": 298.15,
        "water_density_kg_l": 0.997,
        "matric_mpa": -0.10,
        "leaf_critical_mpa": -2.00,
        "adjustment_mpa": 0.0,
        "root_conductance_l_day_mpa": 0.50,
        "potential_transpiration_l_day": 1.00,
        "specific_ion_factor": 1.00,
    }
    values.update(updates)
    return HydraulicInputs(**values)


@pytest.mark.parametrize(
    ("field", "value", "code"),
    [
        ("osmolality_osmol_kg", float("nan"), "HYDRAULIC_NONFINITE"),
        ("temperature_k", float("inf"), "HYDRAULIC_NONFINITE"),
        ("water_density_kg_l", float("-inf"), "HYDRAULIC_NONFINITE"),
        ("specific_ion_factor", 1.01, "HYDRAULIC_INVALID_ION_FACTOR"),
        ("osmolality_osmol_kg", "not-a-number", "HYDRAULIC_INVALID_NUMBER"),
        pytest.param(
            "osmolality_osmol_kg",
            10**10000,
            "HYDRAULIC_INVALID_NUMBER",
            id="overflowing-integer",
        ),
    ],
)
def test_hydraulic_gate_rejects_malformed_or_out_of_range_inputs(
    field: str, value: object, code: str
) -> None:
    with pytest.raises(AlmondLabError) as exc_info:
        hydraulic_uptake(_inputs(**{field: value}))

    assert exc_info.value.code == code


def test_adjustment_has_no_unregistered_global_bound() -> None:
    result = hydraulic_uptake(_inputs(adjustment_mpa=0.51))

    assert result.leaf_limit_mpa == pytest.approx(-2.51)


def test_hydraulic_gate_rejects_invalid_evidence_label_and_domain_violation() -> None:
    with pytest.raises(AlmondLabError) as label_error:
        hydraulic_uptake(_inputs(evidence_label="not-an-evidence-label"))
    assert label_error.value.code == "HYDRAULIC_INVALID_EVIDENCE_LABEL"

    domain = HydraulicDomain(
        osmolality_min=0.01,
        osmolality_max=0.10,
        temperature_k_min=290.0,
        temperature_k_max=305.0,
    )
    with pytest.raises(AlmondLabError) as domain_error:
        hydraulic_uptake(_inputs(osmolality_osmol_kg=0.11), domain=domain)
    assert domain_error.value.code == "HYDRAULIC_DOMAIN_VIOLATION"

    with pytest.raises(AlmondLabError) as malformed_domain_error:
        hydraulic_uptake(
            _inputs(osmolality_osmol_kg="not-a-number"),
            domain=domain,
        )
    assert malformed_domain_error.value.code == "HYDRAULIC_INVALID_NUMBER"
