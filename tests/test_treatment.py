from math import isclose

import pytest
from hypothesis import given, strategies as st

from almondlab.errors import AlmondLabError
from almondlab.treatment import ro_split


def test_ro_hand_oracle_and_each_entity_conservation() -> None:
    result = ro_split(
        feed_volume_l=100.0,
        feed_stock_mmol={"na": 5000.0, "cl": 5000.0},
        recovery=0.60,
        rejection={"na": 0.95, "cl": 0.90},
    )

    assert result.permeate_volume_l == 60.0
    assert result.concentrate_volume_l == 40.0
    assert result.permeate_stock_mmol == pytest.approx({"na": 150.0, "cl": 300.0})
    assert result.concentrate_stock_mmol == pytest.approx({"na": 4850.0, "cl": 4700.0})
    for entity in ("na", "cl"):
        assert isclose(
            result.permeate_stock_mmol[entity]
            + result.concentrate_stock_mmol[entity],
            result.feed_stock_mmol[entity],
            rel_tol=1e-12,
        )


@given(
    feed_volume_l=st.floats(min_value=1e-3, max_value=1e6, allow_nan=False),
    feed_stock=st.floats(min_value=0.0, max_value=1e9, allow_nan=False),
    recovery=st.floats(min_value=1e-6, max_value=0.999999, allow_nan=False),
    rejection=st.floats(min_value=0.0, max_value=1.0, allow_nan=False),
)
def test_ro_property_conserves_water_and_entity(
    feed_volume_l: float,
    feed_stock: float,
    recovery: float,
    rejection: float,
) -> None:
    result = ro_split(
        feed_volume_l,
        {"na": feed_stock},
        recovery,
        {"na": rejection},
    )

    assert isclose(
        result.permeate_volume_l + result.concentrate_volume_l,
        feed_volume_l,
        rel_tol=1e-12,
    )
    assert isclose(
        result.permeate_stock_mmol["na"] + result.concentrate_stock_mmol["na"],
        feed_stock,
        rel_tol=1e-12,
        abs_tol=1e-12,
    )
    assert result.permeate_stock_mmol["na"] >= 0.0
    assert result.concentrate_stock_mmol["na"] >= -1e-12


@pytest.mark.parametrize("recovery", [0.0, 1.0, -0.1, 1.1])
def test_ro_refuses_nonphysical_recovery(recovery: float) -> None:
    with pytest.raises(AlmondLabError) as exc_info:
        ro_split(100.0, {"na": 5.0}, recovery, {"na": 0.9})

    assert exc_info.value.code == "RO_RECOVERY_OUT_OF_RANGE"


@pytest.mark.parametrize("rejection", [-0.01, 1.01])
def test_ro_refuses_nonphysical_ion_rejection(rejection: float) -> None:
    with pytest.raises(AlmondLabError) as exc_info:
        ro_split(100.0, {"na": 5.0}, 0.5, {"na": rejection})

    assert exc_info.value.code == "RO_REJECTION_OUT_OF_RANGE"


@pytest.mark.parametrize("ec_key", ["ec", "ECw", "ec_ds_m", "pore_water_EC", "ECe"])
def test_ro_refuses_ec_rejection_key(ec_key: str) -> None:
    with pytest.raises(AlmondLabError) as exc_info:
        ro_split(100.0, {"na": 5.0}, 0.5, {"na": 0.9, ec_key: 0.8})

    assert exc_info.value.code == "RO_EC_REJECTION_FORBIDDEN"


def test_ro_requires_one_rejection_for_every_tracked_entity() -> None:
    with pytest.raises(AlmondLabError) as exc_info:
        ro_split(
            100.0,
            {"na": 5.0, "cl": 5.0},
            0.5,
            {"na": 0.9},
        )

    assert exc_info.value.code == "RO_REJECTION_KEYS_MISMATCH"
