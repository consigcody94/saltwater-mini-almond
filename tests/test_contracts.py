from almondlab.contracts import ConservedEntity, DataOrigin, ECKind, EvidenceLabel, GateState
from almondlab.errors import AlmondLabError, fail


def test_public_enums_and_stable_error_code() -> None:
    assert EvidenceLabel.PHYSICS_CONSTRAINED.value == "physics_constrained"
    assert DataOrigin.SYNTHETIC.value == "synthetic"
    assert ECKind.ECW.value == "ECw"
    assert ConservedEntity.TOTAL_B.value == "total_b"
    assert GateState.NOT_EVALUABLE.value == "not_evaluable"
    try:
        fail("EC_TYPE_MISMATCH", "wrong EC kind", "water.ec_kind")
    except AlmondLabError as exc:
        assert exc.code == "EC_TYPE_MISMATCH"
        assert exc.field_path == "water.ec_kind"
    else:
        raise AssertionError("fail() did not raise")


def test_error_serializes_structured_fields() -> None:
    error = AlmondLabError(
        "EC_TYPE_MISMATCH",
        "wrong EC kind",
        "water.ec_kind",
        {"expected": "ECw", "received": "ECe"},
    )

    assert error.to_dict() == {
        "code": "EC_TYPE_MISMATCH",
        "message": "wrong EC kind",
        "field_path": "water.ec_kind",
        "details": {"expected": "ECw", "received": "ECe"},
    }
