"""Canonical unit conversion helpers for AlmondLab."""

from pint import UnitRegistry


ureg = UnitRegistry(autoconvert_offset_to_baseunit=True)


def canonical_quantity(value: float, unit: str, target_unit: str) -> float:
    """Convert a scalar quantity to the requested canonical unit."""
    quantity = value * ureg(unit)
    return float(quantity.to(target_unit).magnitude)
