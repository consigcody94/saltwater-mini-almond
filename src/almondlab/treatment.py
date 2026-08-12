"""Ion-specific reverse-osmosis split with explicit conserved stocks."""

from dataclasses import dataclass
from math import isfinite
from collections.abc import Mapping

from almondlab.contracts import ECKind
from almondlab.errors import fail


NEGATIVE_TOLERANCE = 1e-12
_EC_REJECTION_KEYS = {
    "ec",
    "ecw",
    "ec_ds_m",
    "pore_water_ec",
    "ece",
    *(kind.value.casefold() for kind in ECKind),
}


@dataclass(frozen=True)
class ROResult:
    """Water and entity stocks for an RO feed, permeate, and concentrate."""

    feed_volume_l: float
    permeate_volume_l: float
    concentrate_volume_l: float
    feed_stock_mmol: dict[str, float]
    permeate_stock_mmol: dict[str, float]
    concentrate_stock_mmol: dict[str, float]
    rejection: dict[str, float]


def _finite(value: float, code: str, field_path: str) -> float:
    converted = float(value)
    if not isfinite(converted):
        fail(code, "value must be finite", field_path)
    return converted


def ro_split(
    feed_volume_l: float,
    feed_stock_mmol: Mapping[str, float],
    recovery: float,
    rejection: Mapping[str, float],
) -> ROResult:
    """Split water and each tracked entity without an implicit loss or sink."""
    feed_volume = _finite(
        feed_volume_l,
        "RO_INVALID_FEED_VOLUME",
        "feed_volume_l",
    )
    if feed_volume <= 0.0:
        fail(
            "RO_INVALID_FEED_VOLUME",
            "feed volume must be positive",
            "feed_volume_l",
        )
    recovery_value = _finite(recovery, "RO_RECOVERY_OUT_OF_RANGE", "recovery")
    if not 0.0 < recovery_value < 1.0:
        fail(
            "RO_RECOVERY_OUT_OF_RANGE",
            "recovery must be strictly between zero and one",
            "recovery",
        )

    normalized_rejection_keys = {str(key).casefold() for key in rejection}
    if normalized_rejection_keys & _EC_REJECTION_KEYS:
        fail(
            "RO_EC_REJECTION_FORBIDDEN",
            "EC rejection cannot substitute for ion-specific rejection",
            "rejection",
        )

    feed = {str(entity): float(stock) for entity, stock in feed_stock_mmol.items()}
    rejection_values = {
        str(entity): float(value) for entity, value in rejection.items()
    }
    if set(feed) != set(rejection_values):
        fail(
            "RO_REJECTION_KEYS_MISMATCH",
            "every tracked entity requires exactly one rejection value",
            "rejection",
        )
    for entity, stock in feed.items():
        if not isfinite(stock) or stock < 0.0:
            fail(
                "RO_INVALID_FEED_STOCK",
                "feed stock must be finite and nonnegative",
                f"feed_stock_mmol.{entity}",
            )
    for entity, rejection_value in rejection_values.items():
        if not isfinite(rejection_value) or not 0.0 <= rejection_value <= 1.0:
            fail(
                "RO_REJECTION_OUT_OF_RANGE",
                "entity rejection must be between zero and one inclusive",
                f"rejection.{entity}",
            )

    permeate_volume = feed_volume * recovery_value
    concentrate_volume = feed_volume - permeate_volume
    permeate: dict[str, float] = {}
    concentrate: dict[str, float] = {}
    for entity, feed_stock in feed.items():
        feed_concentration = feed_stock / feed_volume
        permeate_concentration = (
            1.0 - rejection_values[entity]
        ) * feed_concentration
        permeate_stock = permeate_volume * permeate_concentration
        concentrate_stock = feed_stock - permeate_stock
        if permeate_stock < -NEGATIVE_TOLERANCE or concentrate_stock < -NEGATIVE_TOLERANCE:
            fail(
                "RO_NEGATIVE_RESULT",
                "RO calculation produced stock below numerical tolerance",
                f"result.{entity}",
            )
        permeate[entity] = max(0.0, permeate_stock)
        concentrate[entity] = max(0.0, concentrate_stock)

    return ROResult(
        feed_volume_l=feed_volume,
        permeate_volume_l=permeate_volume,
        concentrate_volume_l=concentrate_volume,
        feed_stock_mmol=dict(feed),
        permeate_stock_mmol=permeate,
        concentrate_stock_mmol=concentrate,
        rejection=dict(rejection_values),
    )
