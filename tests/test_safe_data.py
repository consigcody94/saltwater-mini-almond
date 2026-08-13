from __future__ import annotations

from decimal import Decimal
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
    "former_reserved_name",
    [
        "record_id_left",
        "record_id_right",
        "source_type_left",
        "source_type_right",
        "__almondlab_left_order",
    ],
)
def test_former_provenance_and_internal_names_are_ordinary_user_columns(
    former_reserved_name: str,
) -> None:
    left = _measured(keys=[1])
    left[former_reserved_name] = "ordinary user value"

    joined = safe_join(left, _measured(keys=[1]), on=["key"])

    assert joined.to_pandas().loc[0, former_reserved_name] == "ordinary user value"


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
    assert set(materialized) == {"key", "right_value_left", "right_value_right"}
    assert joined.lineage["namespace"] == "almondlab.provenance.v1"
    assert joined.lineage["row_ancestry"] == (
        (("OBS_RIGHT_0", "measured"), ("OBS_RIGHT_1", "measured")),
        (("OBS_RIGHT_1", "measured"), ("OBS_RIGHT_0", "measured")),
    )
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


def test_arbitrarily_chained_joins_keep_ancestry_out_of_user_columns() -> None:
    first = safe_join(
        _measured(keys=[1]),
        pd.DataFrame(
            {
                "record_id": ["LIT_SECOND_1"],
                "source_type": ["literature_derived"],
                "key": [1],
                "second": ["two"],
                "record_id_left": ["ordinary user value"],
            }
        ),
        on=["key"],
    )
    second = safe_join(
        first,
        pd.DataFrame(
            {
                "record_id": ["EMP_THIRD_1"],
                "source_type": ["empirical"],
                "key": [1],
                "third": ["three"],
            }
        ),
        on=["key"],
    )
    third = safe_join(second, _measured(keys=[1]), on=["key"])

    assert third.to_pandas().loc[0, "record_id_left"] == "ordinary user value"
    assert len(third.lineage["row_ancestry"][0]) == 4
    assert third.lineage["row_ancestry"][0] == (
        ("OBS_RIGHT_0", "measured"),
        ("LIT_SECOND_1", "literature_derived"),
        ("EMP_THIRD_1", "empirical"),
        ("OBS_RIGHT_0", "measured"),
    )


def test_measured_and_literature_derived_are_one_intentional_empirical_family() -> None:
    literature = pd.DataFrame(
        {
            "record_id": ["LIT_SOURCE_1"],
            "source_type": ["literature_derived"],
            "key": [1],
            "citation": ["doi:10.1/example"],
        }
    )

    joined = safe_join(_measured(keys=[1]), literature, on=["key"])

    assert joined.lineage["origin_family"] == "empirical"
    assert joined.to_pandas().loc[0, "citation"] == "doi:10.1/example"


def test_nested_object_cells_are_deeply_detached_in_both_directions() -> None:
    nested = {"items": [1, {"leaf": [2, 3]}]}
    source = _measured(keys=[1])
    source["nested"] = [nested]
    protected = ProvenanceFrame(source)

    nested["items"][1]["leaf"].append(4)
    first = protected.to_pandas()
    first.loc[0, "nested"]["items"][1]["leaf"].append(5)
    second = protected.to_pandas()

    assert second.loc[0, "nested"] == {"items": [1, {"leaf": [2, 3]}]}


def test_nested_frozensets_preserve_type_and_remain_detached() -> None:
    source = _measured(keys=[1])
    source["nested"] = [{frozenset({"a", "b"}): (frozenset({1, 2}),)}]

    protected = ProvenanceFrame(source)
    materialized = protected.to_pandas().loc[0, "nested"]

    key = next(iter(materialized))
    assert type(key) is frozenset
    assert type(materialized[key][0]) is frozenset


def test_empty_chained_join_retains_ancestry_types_without_reserved_columns() -> None:
    literature = pd.DataFrame(
        {
            "record_id": ["LIT_NO_MATCH_2"],
            "source_type": ["literature_derived"],
            "key": [2],
            "literature_value": ["source"],
        }
    )
    empty = safe_join(_measured(keys=[1]), literature, on=["key"])

    chained = safe_join(empty, _measured(keys=[3]), on=["key"])

    assert chained.empty
    assert chained.lineage["source_types"] == (
        "literature_derived",
        "measured",
    )
    assert chained.lineage["origin_family"] == "empirical"


def test_private_state_assignment_is_blocked_and_content_tamper_is_sealed() -> None:
    protected = ProvenanceFrame(_measured(keys=[1]))

    with pytest.raises(AttributeError):
        protected._row_lineage = ()  # type: ignore[misc]
    protected._frame.loc[0, "key"] = 999  # type: ignore[attr-defined]

    with pytest.raises(AlmondLabError) as exc_info:
        protected.to_pandas()

    assert exc_info.value.code == "PROVENANCE_FRAME_TAMPERED"


def test_dataframe_subclass_is_rejected_without_invoking_caller_methods() -> None:
    calls: list[str] = []

    class HostileDataFrame(pd.DataFrame):
        def copy(self, *args: object, **kwargs: object) -> pd.DataFrame:
            calls.append("copy")
            raise AssertionError("caller-controlled method executed")

    hostile = HostileDataFrame(_measured(keys=[1]))

    with pytest.raises(AlmondLabError) as exc_info:
        ProvenanceFrame(hostile)

    assert exc_info.value.code == "PROVENANCE_FRAME_INVALID"
    assert calls == []


def test_string_subclasses_cannot_supply_provenance_identity() -> None:
    class StringSubclass(str):
        pass

    for column, value in (
        ("record_id", StringSubclass("OBS_RIGHT_0")),
        ("source_type", StringSubclass("measured")),
    ):
        frame = _measured(keys=[1])
        frame[column] = frame[column].astype(object)
        frame.at[0, column] = value

        with pytest.raises(AlmondLabError) as exc_info:
            ProvenanceFrame(frame)

        assert exc_info.value.code in {
            "PROVENANCE_ID_INVALID",
            "PROVENANCE_SOURCE_TYPE_INVALID",
        }


@pytest.mark.parametrize(
    ("left_key", "right_key"),
    [
        (True, 1),
        (1, True),
        (1, 1.0),
        (1.0, 1),
    ],
)
def test_join_keys_require_exact_non_boolean_kinds_before_merge(
    monkeypatch: pytest.MonkeyPatch, left_key: object, right_key: object
) -> None:
    calls: list[str] = []

    def forbidden_merge(*args: object, **kwargs: object) -> pd.DataFrame:
        calls.append("merge")
        raise AssertionError("merge ran before exact key validation")

    monkeypatch.setattr(pd, "merge", forbidden_merge)
    left = _measured(keys=[1])
    right = _measured(keys=[1])
    left["key"] = pd.Series([left_key], dtype=object)
    right["key"] = pd.Series([right_key], dtype=object)

    with pytest.raises(AlmondLabError) as exc_info:
        safe_join(left, right, on=["key"])

    assert exc_info.value.code == "JOIN_KEY_TYPE_MISMATCH"
    assert calls == []


def test_each_join_key_column_has_one_exact_kind() -> None:
    left = _measured(keys=[1, 2])
    left["key"] = pd.Series([1, 2.0], dtype=object)

    with pytest.raises(AlmondLabError) as exc_info:
        safe_join(left, _measured(keys=[1, 2]), on=["key"])

    assert exc_info.value.code == "JOIN_KEY_TYPE_MISMATCH"


def test_decimal_nan_key_is_rejected_before_merge(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []

    def forbidden_merge(*args: object, **kwargs: object) -> pd.DataFrame:
        calls.append("merge")
        raise AssertionError("merge ran before null key validation")

    monkeypatch.setattr(pd, "merge", forbidden_merge)
    left = _measured(keys=[1])
    right = _measured(keys=[1])
    left["key"] = pd.Series([Decimal("NaN")], dtype=object)
    right["key"] = pd.Series([Decimal("NaN")], dtype=object)

    with pytest.raises(AlmondLabError) as exc_info:
        safe_join(left, right, on=["key"])

    assert exc_info.value.code == "JOIN_KEY_NULL"
    assert calls == []
