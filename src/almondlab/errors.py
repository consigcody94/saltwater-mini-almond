"""Structured AlmondLab errors and strict boundary conversion helpers."""

from math import isfinite
from numbers import Real
from typing import Never


class AlmondLabError(Exception):
    """An error with machine-readable, structured context."""

    def __init__(
        self,
        code: str,
        message: str,
        field_path: str,
        details: dict[str, object] | None = None,
    ) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message
        self.field_path = field_path
        self.details = details

    def to_dict(self) -> dict[str, object]:
        serialized: dict[str, object] = {
            "code": self.code,
            "message": self.message,
            "field_path": self.field_path,
        }
        if self.details is not None:
            serialized["details"] = self.details
        return serialized


def fail(
    code: str,
    message: str,
    field_path: str,
    details: dict[str, object] | None = None,
) -> Never:
    """Raise a structured AlmondLab error with stable fields."""
    raise AlmondLabError(code, message, field_path, details)


def finite_float(
    value: object,
    *,
    code: str,
    field_path: str,
    nonnegative: bool = False,
    positive: bool = False,
) -> float:
    """Return a finite float for a genuine real scalar or fail structurally.

    This is the shared numerical input boundary.  In particular, it deliberately
    refuses Python's otherwise-permissive conversions from booleans, strings, and
    arbitrary objects implementing ``__float__``.
    """

    if isinstance(value, bool) or not isinstance(value, Real):
        fail(code, "value must be a finite real number", field_path)
    try:
        converted = float(value)
    except Exception:
        fail(code, "value must be a finite real number", field_path)
    if not isfinite(converted):
        fail(code, "value must be a finite real number", field_path)
    if positive and converted <= 0.0:
        fail(code, "value must be greater than zero", field_path)
    if nonnegative and converted < 0.0:
        fail(code, "value must be nonnegative", field_path)
    return converted
