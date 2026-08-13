"""Fail-closed provenance frames and protected dataframe joins.

The join boundary deliberately trusts row-level provenance columns rather than
``DataFrame.attrs``.  A synthetic row can therefore neither be relabelled by an
attribute nor hidden after an inspected chunk.  All validation completes before
``pandas.merge`` is called.
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping, Sequence
from types import MappingProxyType
from typing import Final, Literal, TypeAlias
import re

import pandas as pd

from almondlab.errors import fail


SourceType: TypeAlias = Literal[
    "synthetic", "measured", "empirical", "literature_derived"
]
Cardinality: TypeAlias = Literal["one_to_one", "one_to_many", "many_to_one"]
JoinHow: TypeAlias = Literal["inner", "left", "right", "outer"]

_SOURCE_NAMESPACES: Final[dict[str, tuple[str, str]]] = {
    "synthetic": ("SYN_", "synthetic"),
    "measured": ("OBS_", "empirical"),
    "empirical": ("EMP_", "empirical"),
    "literature_derived": ("LIT_", "empirical"),
}
_PROVENANCE_COLUMNS: Final[tuple[str, str]] = ("record_id", "source_type")
_INTERNAL_LEFT_ORDER: Final[str] = "__almondlab_left_order"
_INTERNAL_RIGHT_ORDER: Final[str] = "__almondlab_right_order"
_INTERNAL_COLUMNS: Final[frozenset[str]] = frozenset(
    {_INTERNAL_LEFT_ORDER, _INTERNAL_RIGHT_ORDER}
)
_SAFE_RECORD_ID = re.compile(r"^[A-Z][A-Z0-9]*(?:_[A-Z0-9]+)+$")

# One tuple per output row; each atom is (record_id, source_type).  Joined rows
# retain both sides, which makes a later join inspect the complete ancestry.
_LineageAtom: TypeAlias = tuple[str, str]
_RowLineage: TypeAlias = tuple[_LineageAtom, ...]


class ProvenanceFrame:
    """Immutable, defensive snapshot of a provenance-bearing table.

    ``to_pandas`` always returns a deep copy.  The constructor also snapshots
    the caller's input, so mutation in either direction cannot alter the stored
    table.  Joined frames keep row-aligned ancestry privately even though the
    visible provenance columns are suffixed to preserve both source records.
    """

    __slots__ = ("_frame", "_row_lineage", "_lineage")

    def __init__(self, frame: pd.DataFrame) -> None:
        snapshot, row_lineage, source_types = _inspect_dataframe(frame, "frame")
        self._frame = snapshot
        self._row_lineage = row_lineage
        self._lineage = MappingProxyType(
            {
                "operation": "snapshot",
                "record_id_column": "record_id",
                "source_type_column": "source_type",
                "record_ids": tuple(atom[0] for row in row_lineage for atom in row),
                "source_types": tuple(sorted(source_types)),
            }
        )

    @classmethod
    def _from_join(
        cls,
        frame: pd.DataFrame,
        row_lineage: tuple[_RowLineage, ...],
        lineage: Mapping[str, object],
    ) -> "ProvenanceFrame":
        instance = object.__new__(cls)
        instance._frame = frame.copy(deep=True)
        instance._frame.attrs.clear()
        instance._row_lineage = tuple(tuple(row) for row in row_lineage)
        instance._lineage = MappingProxyType(dict(lineage))
        return instance

    @property
    def lineage(self) -> MappingProxyType:
        """Return immutable operation-level lineage metadata."""
        return self._lineage

    @property
    def columns(self) -> pd.Index:
        return self._frame.columns.copy()

    @property
    def shape(self) -> tuple[int, int]:
        return self._frame.shape

    @property
    def empty(self) -> bool:
        return self._frame.empty

    @property
    def loc(self):  # type: ignore[no-untyped-def]
        """Expose a read-safe indexer backed by a defensive materialization."""
        return self.to_pandas().loc

    @property
    def iloc(self):  # type: ignore[no-untyped-def]
        """Expose a read-safe positional indexer on a defensive copy."""
        return self.to_pandas().iloc

    def to_pandas(self) -> pd.DataFrame:
        """Materialize a deep copy; no mutable internal frame is exposed."""
        materialized = self._frame.copy(deep=True)
        materialized.attrs.clear()
        materialized.attrs["almondlab_lineage"] = dict(self._lineage)
        return materialized

    def set_index(self, *args: object, **kwargs: object) -> pd.DataFrame:
        return self.to_pandas().set_index(*args, **kwargs)

    def __getitem__(self, key: object):  # type: ignore[no-untyped-def]
        value = self._frame.__getitem__(key)
        return value.copy(deep=True) if hasattr(value, "copy") else value

    def __len__(self) -> int:
        return len(self._frame)

    def __iter__(self) -> Iterator[str]:
        return iter(self._frame)

    def __repr__(self) -> str:
        return f"ProvenanceFrame({self._frame!r})"


def _copy_frame(value: object, side: str) -> tuple[pd.DataFrame, tuple[_RowLineage, ...]]:
    if isinstance(value, ProvenanceFrame):
        frame = value._frame.copy(deep=True)
        frame.attrs.clear()
        if len(frame) != len(value._row_lineage):
            fail(
                "PROVENANCE_FRAME_TAMPERED",
                "protected frame row count no longer matches its stored lineage",
                side,
            )
        operation = value._lineage.get("operation")
        if operation == "snapshot":
            checked, visible_lineage, _ = _inspect_dataframe(frame, side)
            if visible_lineage != value._row_lineage:
                fail(
                    "PROVENANCE_FRAME_TAMPERED",
                    "protected frame provenance differs from its stored lineage",
                    side,
                )
            frame = checked
        elif operation == "safe_join":
            _validate_join_snapshot(frame, value._row_lineage, value._lineage, side)
        else:
            fail(
                "PROVENANCE_FRAME_TAMPERED",
                "protected frame operation metadata is invalid",
                side,
            )
        return frame, value._row_lineage
    if not isinstance(value, pd.DataFrame):
        fail(
            "PROVENANCE_FRAME_INVALID",
            "join inputs must be pandas DataFrame or ProvenanceFrame instances",
            side,
        )
    frame, row_lineage, _ = _inspect_dataframe(value, side)
    return frame, row_lineage


def _validate_join_snapshot(
    frame: pd.DataFrame,
    row_lineage: tuple[_RowLineage, ...],
    lineage: Mapping[str, object],
    side: str,
) -> None:
    """Reconcile every visible joined provenance cell with private ancestry."""
    columns = list(frame.columns)
    if (
        frame.empty
        or any(not isinstance(column, str) for column in columns)
        or len(columns) != len(set(columns))
        or any(column in _INTERNAL_COLUMNS for column in columns)
    ):
        fail(
            "PROVENANCE_FRAME_TAMPERED",
            "protected join frame structure is invalid",
            side,
        )
    provenance_pairs: list[tuple[str, str]] = []
    for prefix in ("left", "right"):
        record_column = lineage.get(f"{prefix}_record_id_column")
        source_column = lineage.get(f"{prefix}_source_type_column")
        if (
            not isinstance(record_column, str)
            or not isinstance(source_column, str)
            or record_column not in frame.columns
            or source_column not in frame.columns
        ):
            fail(
                "PROVENANCE_FRAME_TAMPERED",
                "protected join provenance columns are missing",
                f"{side}.columns",
            )
        provenance_pairs.append((record_column, source_column))

    for position, expected_atoms in enumerate(row_lineage):
        visible_atoms: list[_LineageAtom] = []
        for record_column, source_column in provenance_pairs:
            record_id = frame.iloc[position][record_column]
            source_type = frame.iloc[position][source_column]
            record_missing = bool(pd.isna(record_id))
            source_missing = bool(pd.isna(source_type))
            if record_missing != source_missing:
                fail(
                    "PROVENANCE_FRAME_TAMPERED",
                    "joined provenance record/source nullness differs",
                    f"{side}[{position}]",
                )
            if record_missing:
                continue
            if not isinstance(source_type, str) or source_type not in _SOURCE_NAMESPACES:
                fail(
                    "PROVENANCE_FRAME_TAMPERED",
                    "joined provenance source type is invalid",
                    f"{side}[{position}].{source_column}",
                )
            required_prefix, _ = _SOURCE_NAMESPACES[source_type]
            if (
                not isinstance(record_id, str)
                or _SAFE_RECORD_ID.fullmatch(record_id) is None
                or not record_id.startswith(required_prefix)
            ):
                fail(
                    "PROVENANCE_FRAME_TAMPERED",
                    "joined provenance record ID is invalid",
                    f"{side}[{position}].{record_column}",
                )
            visible_atoms.append((record_id, source_type))
        if tuple(visible_atoms) != expected_atoms:
            fail(
                "PROVENANCE_FRAME_TAMPERED",
                "visible joined provenance differs from stored ancestry",
                f"{side}[{position}]",
            )


def _inspect_dataframe(
    frame: pd.DataFrame, side: str
) -> tuple[pd.DataFrame, tuple[_RowLineage, ...], frozenset[str]]:
    """Inspect every provenance cell and return a defensive snapshot."""
    if not isinstance(frame, pd.DataFrame):
        fail("PROVENANCE_FRAME_INVALID", "value must be a pandas DataFrame", side)
    snapshot = frame.copy(deep=True)
    snapshot.attrs.clear()  # attrs are caller-controlled and never authoritative.

    columns = list(snapshot.columns)
    if any(not isinstance(column, str) for column in columns):
        fail(
            "PROVENANCE_COLUMN_INVALID",
            "all dataframe column names must be strings",
            f"{side}.columns",
        )
    if len(columns) != len(set(columns)):
        fail(
            "PROVENANCE_COLUMN_DUPLICATE",
            "dataframe column names must be unique",
            f"{side}.columns",
        )
    missing = [column for column in _PROVENANCE_COLUMNS if column not in columns]
    if missing:
        fail(
            "PROVENANCE_COLUMNS_MISSING",
            "record_id and source_type are mandatory row-level provenance columns",
            f"{side}.columns",
            {"missing": missing},
        )
    if snapshot.empty:
        fail(
            "PROVENANCE_EMPTY",
            "an empty dataframe has no row-level provenance to validate",
            side,
        )

    row_lineage: list[_RowLineage] = []
    source_types: set[str] = set()
    families: set[str] = set()
    record_ids: list[str] = []
    for position, (record_id, source_type) in enumerate(
        zip(snapshot["record_id"].tolist(), snapshot["source_type"].tolist())
    ):
        if not isinstance(source_type, str) or source_type not in _SOURCE_NAMESPACES:
            fail(
                "PROVENANCE_SOURCE_TYPE_INVALID",
                "source_type must use a registered exact value",
                f"{side}.source_type[{position}]",
                {"received": repr(source_type)},
            )
        prefix, family = _SOURCE_NAMESPACES[source_type]
        if (
            not isinstance(record_id, str)
            or _SAFE_RECORD_ID.fullmatch(record_id) is None
            or not record_id.startswith(prefix)
        ):
            fail(
                "PROVENANCE_ID_INVALID",
                "record_id must be portable and match its source_type namespace",
                f"{side}.record_id[{position}]",
                {"source_type": source_type, "required_prefix": prefix},
            )
        record_ids.append(record_id)
        source_types.add(source_type)
        families.add(family)
        row_lineage.append(((record_id, source_type),))

    if len(record_ids) != len(set(record_ids)):
        fail(
            "PROVENANCE_ID_DUPLICATE",
            "record_id values must be unique within each input frame",
            f"{side}.record_id",
        )
    if families == {"synthetic", "empirical"}:
        fail(
            "SYNTHETIC_CONTAMINATION",
            "a single input frame contains both synthetic and empirical ancestry",
            side,
        )
    return snapshot, tuple(row_lineage), frozenset(source_types)


def _inspect_lineage(
    row_lineage: tuple[_RowLineage, ...], side: str
) -> tuple[frozenset[str], frozenset[str]]:
    source_types: set[str] = set()
    families: set[str] = set()
    for row_position, row in enumerate(row_lineage):
        if not row:
            fail(
                "PROVENANCE_LINEAGE_INVALID",
                "each row must retain at least one provenance atom",
                f"{side}.lineage[{row_position}]",
            )
        for atom_position, atom in enumerate(row):
            if not isinstance(atom, tuple) or len(atom) != 2:
                fail(
                    "PROVENANCE_LINEAGE_INVALID",
                    "lineage atoms must be record/source pairs",
                    f"{side}.lineage[{row_position}][{atom_position}]",
                )
            record_id, source_type = atom
            if source_type not in _SOURCE_NAMESPACES:
                fail(
                    "PROVENANCE_SOURCE_TYPE_INVALID",
                    "lineage source_type is not registered",
                    f"{side}.lineage[{row_position}][{atom_position}]",
                )
            prefix, family = _SOURCE_NAMESPACES[source_type]
            if (
                not isinstance(record_id, str)
                or _SAFE_RECORD_ID.fullmatch(record_id) is None
                or not record_id.startswith(prefix)
            ):
                fail(
                    "PROVENANCE_ID_INVALID",
                    "lineage record_id does not match its namespace",
                    f"{side}.lineage[{row_position}][{atom_position}]",
                )
            source_types.add(source_type)
            families.add(family)
    if families == {"synthetic", "empirical"}:
        fail(
            "SYNTHETIC_CONTAMINATION",
            "input lineage contains both synthetic and empirical ancestry",
            side,
        )
    return frozenset(source_types), frozenset(families)


def _validate_join_keys(
    left: pd.DataFrame, right: pd.DataFrame, on: object
) -> tuple[str, ...]:
    if (
        isinstance(on, (str, bytes))
        or not isinstance(on, Sequence)
        or len(on) == 0
        or any(not isinstance(key, str) or not key for key in on)
    ):
        fail(
            "JOIN_KEYS_INVALID",
            "on must be a nonempty list or tuple of nonempty string column names",
            "on",
        )
    keys = tuple(on)
    if len(keys) != len(set(keys)) or any(key in _PROVENANCE_COLUMNS for key in keys):
        fail(
            "JOIN_KEYS_INVALID",
            "join keys must be unique and cannot be provenance columns",
            "on",
        )
    for side, frame in (("left", left), ("right", right)):
        missing = [key for key in keys if key not in frame.columns]
        if missing:
            fail(
                "JOIN_KEY_MISSING",
                "every join key must exist in both inputs",
                f"{side}.columns",
                {"missing": missing},
            )
        if frame.loc[:, list(keys)].isna().any(axis=None):
            fail(
                "JOIN_KEY_NULL",
                "join keys cannot contain null values",
                f"{side}.{','.join(keys)}",
            )
    return keys


def _validate_cardinality(
    left: pd.DataFrame,
    right: pd.DataFrame,
    keys: tuple[str, ...],
    cardinality: object,
    validate: object,
) -> Cardinality:
    selected = cardinality
    if validate is not None:
        if cardinality != "one_to_one":
            fail(
                "JOIN_CARDINALITY_INVALID",
                "specify cardinality or validate, not both",
                "cardinality",
            )
        selected = validate
    if selected == "many_to_many":
        fail(
            "JOIN_MANY_TO_MANY_FORBIDDEN",
            "many-to-many joins are forbidden at the protected data boundary",
            "cardinality",
        )
    if not isinstance(selected, str) or selected not in {
        "one_to_one",
        "one_to_many",
        "many_to_one",
    }:
        fail(
            "JOIN_CARDINALITY_INVALID",
            "cardinality must be one_to_one, one_to_many, or many_to_one",
            "cardinality",
        )

    left_duplicate = bool(left.duplicated(subset=list(keys), keep=False).any())
    right_duplicate = bool(right.duplicated(subset=list(keys), keep=False).any())
    violates = (
        (selected == "one_to_one" and (left_duplicate or right_duplicate))
        or (selected == "one_to_many" and left_duplicate)
        or (selected == "many_to_one" and right_duplicate)
    )
    if violates:
        fail(
            "JOIN_CARDINALITY_VIOLATION",
            "duplicate join keys violate the declared cardinality",
            "cardinality",
            {
                "cardinality": selected,
                "left_has_duplicates": left_duplicate,
                "right_has_duplicates": right_duplicate,
            },
        )
    return selected  # type: ignore[return-value]


def _validate_columns_for_merge(
    left: pd.DataFrame, right: pd.DataFrame, keys: tuple[str, ...]
) -> None:
    left_columns = set(left.columns)
    right_columns = set(right.columns)
    reserved = _INTERNAL_COLUMNS | {
        "record_id_left",
        "record_id_right",
        "source_type_left",
        "source_type_right",
    }
    present_reserved = sorted((left_columns | right_columns) & reserved)
    if present_reserved:
        fail(
            "JOIN_COLUMN_COLLISION",
            "input columns collide with protected join output/internal columns",
            "columns",
            {"columns": present_reserved},
        )

    overlaps = (left_columns & right_columns) - set(keys)
    output_columns: list[str] = list(keys)
    for column in left.columns:
        if column not in keys:
            output_columns.append(f"{column}_left" if column in overlaps else column)
    for column in right.columns:
        if column not in keys:
            output_columns.append(f"{column}_right" if column in overlaps else column)
    if len(output_columns) != len(set(output_columns)):
        fail(
            "JOIN_COLUMN_COLLISION",
            "merge suffixes would create duplicate output columns",
            "columns",
        )


def safe_join(
    left: pd.DataFrame | ProvenanceFrame,
    right: pd.DataFrame | ProvenanceFrame,
    *,
    on: Sequence[str],
    how: JoinHow = "inner",
    cardinality: Cardinality = "one_to_one",
    validate: Cardinality | None = None,
) -> ProvenanceFrame:
    """Join same-origin data after complete, fail-closed provenance validation.

    There is intentionally no production override for mixed origins.  Both
    complete ancestry graphs are inspected before key/cardinality checks and
    before pandas is allowed to execute a merge.
    """

    left_frame, left_rows = _copy_frame(left, "left")
    right_frame, right_rows = _copy_frame(right, "right")
    left_source_types, left_families = _inspect_lineage(left_rows, "left")
    right_source_types, right_families = _inspect_lineage(right_rows, "right")
    if "synthetic" in left_families | right_families and "empirical" in (
        left_families | right_families
    ):
        fail(
            "SYNTHETIC_CONTAMINATION",
            "synthetic and empirical ancestry cannot enter the same join",
            "safe_join",
            {
                "left_source_types": sorted(left_source_types),
                "right_source_types": sorted(right_source_types),
            },
        )

    if not isinstance(how, str) or how not in {"inner", "left", "right", "outer"}:
        fail(
            "JOIN_HOW_INVALID",
            "how must be inner, left, right, or outer",
            "how",
        )
    keys = _validate_join_keys(left_frame, right_frame, on)
    checked_cardinality = _validate_cardinality(
        left_frame, right_frame, keys, cardinality, validate
    )
    _validate_columns_for_merge(left_frame, right_frame, keys)

    left_work = left_frame.copy(deep=True)
    right_work = right_frame.copy(deep=True)
    left_work[_INTERNAL_LEFT_ORDER] = range(len(left_work))
    right_work[_INTERNAL_RIGHT_ORDER] = range(len(right_work))
    result = pd.merge(
        left_work,
        right_work,
        how=how,
        on=list(keys),
        sort=False,
        suffixes=("_left", "_right"),
        validate=checked_cardinality,
    )

    if how == "right":
        sort_columns = [_INTERNAL_RIGHT_ORDER, _INTERNAL_LEFT_ORDER]
    else:
        # NaNs sort last, yielding left order followed by right-only outer rows.
        sort_columns = [_INTERNAL_LEFT_ORDER, _INTERNAL_RIGHT_ORDER]
    result = result.sort_values(sort_columns, kind="mergesort", na_position="last")

    output_lineage: list[_RowLineage] = []
    for left_position, right_position in zip(
        result[_INTERNAL_LEFT_ORDER].tolist(), result[_INTERNAL_RIGHT_ORDER].tolist()
    ):
        atoms: list[_LineageAtom] = []
        if not pd.isna(left_position):
            atoms.extend(left_rows[int(left_position)])
        if not pd.isna(right_position):
            atoms.extend(right_rows[int(right_position)])
        output_lineage.append(tuple(atoms))

    result = result.drop(columns=[_INTERNAL_LEFT_ORDER, _INTERNAL_RIGHT_ORDER])
    result = result.reset_index(drop=True)
    result.attrs.clear()
    lineage = {
        "operation": "safe_join",
        "join_keys": keys,
        "join_how": how,
        "cardinality": checked_cardinality,
        "left_record_id_column": "record_id_left",
        "left_source_type_column": "source_type_left",
        "right_record_id_column": "record_id_right",
        "right_source_type_column": "source_type_right",
        "left_source_types": tuple(sorted(left_source_types)),
        "right_source_types": tuple(sorted(right_source_types)),
        "row_count": len(result),
    }
    return ProvenanceFrame._from_join(result, tuple(output_lineage), lineage)


__all__ = ["ProvenanceFrame", "safe_join"]
