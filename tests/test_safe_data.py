from __future__ import annotations

from types import MappingProxyType

import pandas as pd
import pytest

from almondlab.errors import AlmondLabError
from almondlab.safe_data import ProvenanceFrame, safe_join


def _synthetic(*, keys: list[int] | None = None) -> pd.DataFrame:
    keys = [2, 1] if keys is None else keys
    return pd.DataFrame(
        {
            "record_id": [f"SYN_LEFT_{number}" for number in range(len(keys))],
            "key": keys,
            "source_type": ["synthetic"] * len(keys),
            "left_value": [f"l{number}" for number in range(len(keys))],
        }
    )


def _measured(*, keys: list[int] | None = None) -> pd.DataFrame:
    keys = [1, 2] if keys is None else keys
    return pd.DataFrame(
        {
            "record_id": [f"OBS_RIGHT_{number}" for number in range(len(keys))],
            "key": keys,
            "source_type": ["measured"] * len(keys),
            "right_value": [f"r{number}" for number in range(len(keys))],
        }
    )


def test_synthetic_empirical_join_is_rejected() -> None:
    left = pd.DataFrame(
        {"record_id": ["SYN_1"], "key": [1], "source_type": ["synthetic"]}
    )
    right = pd.DataFrame(
        {"record_id": ["OBS_1"], "key": [1], "source_type": ["measured"]}
    )

    with pytest.raises(AlmondLabError, match="SYNTHETIC_CONTAMINATION") as exc_info:
        safe_join(left, right, on=["key"])

    assert exc_info.value.code == "SYNTHETIC_CONTAMINATION"


def test_every_row_is_inspected_before_merge_including_a_late_collision() -> None:
    left = _synthetic(keys=list(range(10_001)))
    right = _synthetic(keys=list(range(10_001)))
    right.loc[10_000, "record_id"] = "OBS_HIDDEN_AFTER_FIRST_CHUNK"
    right.loc[10_000, "source_type"] = "measured"

    with pytest.raises(AlmondLabError) as exc_info:
        safe_join(left, right, on=["key"])

    assert exc_info.value.code == "SYNTHETIC_CONTAMINATION"


@pytest.mark.parametrize(
    ("record_id", "source_type"),
    [
        ("SYN_SPOOF", "measured"),
        ("OBS_SPOOF", "synthetic"),
        ("EMP_SPOOF", "literature_derived"),
        ("LIT_SPOOF", "empirical"),
        ("../OBS_SPOOF", "measured"),
    ],
)
def test_record_id_namespace_cannot_spoof_source_type(
    record_id: str, source_type: str
) -> None:
    left = pd.DataFrame(
        {"record_id": [record_id], "key": [1], "source_type": [source_type]}
    )
    right = _measured(keys=[1])

    with pytest.raises(AlmondLabError) as exc_info:
        safe_join(left, right, on=["key"])

    assert exc_info.value.code in {"PROVENANCE_ID_INVALID", "SYNTHETIC_CONTAMINATION"}


def test_untrusted_attrs_cannot_launder_synthetic_rows() -> None:
    left = _synthetic(keys=[1])
    left.attrs.update(
        {
            "source_type": "measured",
            "data_origin": "empirical",
            "record_id_prefix": "OBS_",
        }
    )
    right = _measured(keys=[1])

    with pytest.raises(AlmondLabError) as exc_info:
        safe_join(left, right, on=["key"])

    assert exc_info.value.code == "SYNTHETIC_CONTAMINATION"


def test_renamed_provenance_columns_cannot_launder_origin() -> None:
    left = _synthetic(keys=[1]).rename(
        columns={"record_id": "left_record_id", "source_type": "left_source_type"}
    )

    with pytest.raises(AlmondLabError) as exc_info:
        safe_join(left, _measured(keys=[1]), on=["key"])

    assert exc_info.value.code == "PROVENANCE_COLUMNS_MISSING"


def test_unknown_or_mixed_source_types_are_rejected() -> None:
    unknown = _measured(keys=[1])
    unknown.loc[0, "source_type"] = "physicalish"
    with pytest.raises(AlmondLabError) as unknown_error:
        safe_join(unknown, _measured(keys=[1]), on=["key"])
    assert unknown_error.value.code == "PROVENANCE_SOURCE_TYPE_INVALID"

    mixed = pd.concat([_synthetic(keys=[1]), _measured(keys=[2])], ignore_index=True)
    with pytest.raises(AlmondLabError) as mixed_error:
        safe_join(mixed, _measured(keys=[1, 2]), on=["key"])
    assert mixed_error.value.code == "SYNTHETIC_CONTAMINATION"


def test_null_keys_fail_before_merge() -> None:
    left = _measured(keys=[1, 2])
    left.loc[1, "key"] = None

    with pytest.raises(AlmondLabError) as exc_info:
        safe_join(left, _measured(keys=[1, 2]), on=["key"])

    assert exc_info.value.code == "JOIN_KEY_NULL"


def test_duplicate_keys_fail_the_default_one_to_one_contract() -> None:
    left = _measured(keys=[1, 1])

    with pytest.raises(AlmondLabError) as exc_info:
        safe_join(left, _measured(keys=[1]), on=["key"])

    assert exc_info.value.code == "JOIN_CARDINALITY_VIOLATION"


def test_many_to_many_is_never_permitted() -> None:
    left = _measured(keys=[1, 1])
    right = _measured(keys=[1, 1])

    with pytest.raises(AlmondLabError) as exc_info:
        safe_join(left, right, on=["key"], cardinality="many_to_many")

    assert exc_info.value.code == "JOIN_MANY_TO_MANY_FORBIDDEN"


def test_declared_one_to_many_and_many_to_one_are_checked() -> None:
    one = _measured(keys=[1])
    many = _measured(keys=[1, 1])

    one_to_many = safe_join(one, many, on=["key"], cardinality="one_to_many")
    assert len(one_to_many) == 2

    many_to_one = safe_join(many, one, on=["key"], cardinality="many_to_one")
    assert len(many_to_one) == 2

    with pytest.raises(AlmondLabError, match="JOIN_CARDINALITY_VIOLATION"):
        safe_join(many, one, on=["key"], cardinality="one_to_many")


@pytest.mark.parametrize(
    "collision",
    [
        "record_id_left",
        "record_id_right",
        "source_type_left",
        "source_type_right",
        "__almondlab_left_order",
    ],
)
def test_suffix_and_internal_column_collisions_fail_closed(collision: str) -> None:
    left = _measured(keys=[1])
    left[collision] = "spoof"

    with pytest.raises(AlmondLabError) as exc_info:
        safe_join(left, _measured(keys=[1]), on=["key"])

    assert exc_info.value.code == "JOIN_COLUMN_COLLISION"


@pytest.mark.parametrize(
    "on",
    ["key", [], ["key", "key"], [True], True, None],
)
def test_join_key_api_rejects_coercive_or_ambiguous_objects(on: object) -> None:
    with pytest.raises(AlmondLabError, match="JOIN_KEYS_INVALID"):
        safe_join(_measured(keys=[1]), _measured(keys=[1]), on=on)  # type: ignore[arg-type]


def test_same_origin_join_is_deterministic_and_preserves_both_lineages() -> None:
    left = _measured(keys=[2, 1])
    right = _measured(keys=[1, 2])

    joined = safe_join(left, right, on=["key"])
    materialized = joined.to_pandas()

    assert isinstance(joined, ProvenanceFrame)
    assert materialized["key"].tolist() == [2, 1]
    assert materialized["record_id_left"].tolist() == ["OBS_RIGHT_0", "OBS_RIGHT_1"]
    assert materialized["record_id_right"].tolist() == ["OBS_RIGHT_1", "OBS_RIGHT_0"]
    assert "record_id" not in materialized
    assert "source_type" not in materialized
    assert joined.lineage["left_record_id_column"] == "record_id_left"
    assert joined.lineage["right_record_id_column"] == "record_id_right"
    assert isinstance(joined.lineage, MappingProxyType)


def test_provenance_frame_is_a_defensive_snapshot() -> None:
    source = _measured(keys=[1])
    protected = ProvenanceFrame(source)
    source.loc[0, "record_id"] = "OBS_MUTATED"
    first = protected.to_pandas()
    first.loc[0, "record_id"] = "OBS_CALLER_MUTATED"

    assert protected.to_pandas().loc[0, "record_id"] == "OBS_RIGHT_0"
    with pytest.raises(TypeError):
        protected.lineage["spoof"] = "value"  # type: ignore[index]


def test_protected_frame_internal_tampering_is_detected_before_merge() -> None:
    protected = ProvenanceFrame(_measured(keys=[1]))
    protected._frame.loc[0, "record_id"] = "SYN_LAUNDERED"  # type: ignore[attr-defined]
    protected._frame.loc[0, "source_type"] = "synthetic"  # type: ignore[attr-defined]

    with pytest.raises(AlmondLabError) as exc_info:
        safe_join(protected, _measured(keys=[1]), on=["key"])

    assert exc_info.value.code in {
        "PROVENANCE_FRAME_TAMPERED",
        "SYNTHETIC_CONTAMINATION",
    }


def test_join_exposes_no_mixed_origin_override() -> None:
    with pytest.raises(TypeError):
        safe_join(
            _synthetic(keys=[1]),
            _measured(keys=[1]),
            on=["key"],
            allow_mixed=True,
        )
