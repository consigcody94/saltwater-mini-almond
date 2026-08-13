"""Fail-closed provenance frames and protected dataframe joins.

Row ancestry lives in an immutable AlmondLab namespace, not in mergeable user
columns.  Raw ``record_id``/``source_type`` cells are consumed into that
namespace before a join, so the returned frame can participate in arbitrarily
many later joins without suffix-reservation collisions.
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime, time
from decimal import Decimal
from hashlib import sha256
import json
from math import isnan
import re
from types import MappingProxyType
from typing import Final, Literal, TypeAlias

import numpy as np
import pandas as pd

from almondlab.errors import AlmondLabError, fail


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
_SAFE_RECORD_ID = re.compile(r"^[A-Z][A-Z0-9]*(?:_[A-Z0-9]+)+$")
_LINEAGE_NAMESPACE: Final[str] = "almondlab.provenance.v1"
_MAX_JOIN_ROWS: Final[int] = 10_000

_LineageAtom: TypeAlias = tuple[str, str]
_RowLineage: TypeAlias = tuple[_LineageAtom, ...]


@dataclass(frozen=True, slots=True)
class _FrozenList:
    items: tuple[object, ...]


@dataclass(frozen=True, slots=True)
class _FrozenTuple:
    items: tuple[object, ...]


@dataclass(frozen=True, slots=True)
class _FrozenDict:
    items: tuple[tuple[object, object], ...]


@dataclass(frozen=True, slots=True)
class _FrozenSet:
    items: frozenset[object]


@dataclass(frozen=True, slots=True)
class _FrozenFrozenset:
    items: frozenset[object]


_FROZEN_CONTAINER_TYPES: Final[tuple[type[object], ...]] = (
    _FrozenList,
    _FrozenTuple,
    _FrozenDict,
    _FrozenSet,
    _FrozenFrozenset,
)


def _jsonable(value: object) -> object:
    """Return a type-tagged, deterministic representation for the frame seal."""
    value_type = type(value)
    if value is None:
        return ["none"]
    if value is pd.NA:
        return ["pd.NA"]
    if value is pd.NaT:
        return ["pd.NaT"]
    if value_type is bool:
        return ["bool", value]
    if value_type is int:
        return ["int", str(value)]
    if value_type is float:
        if isnan(value):
            return ["float", "nan"]
        if value == float("inf"):
            return ["float", "inf"]
        if value == float("-inf"):
            return ["float", "-inf"]
        return ["float", value.hex()]
    if value_type is str:
        return ["str", value]
    if value_type is bytes:
        return ["bytes", value.hex()]
    if value_type is Decimal:
        return ["decimal", str(value)]
    if value_type is datetime:
        return ["datetime", value.isoformat()]
    if value_type is date:
        return ["date", value.isoformat()]
    if value_type is time:
        return ["time", value.isoformat()]
    if value_type is pd.Timestamp:
        return ["timestamp", value.isoformat()]
    if value_type is pd.Timedelta:
        return ["timedelta_ns", str(value.value)]
    if value_type is _FrozenList:
        return ["list", [_jsonable(item) for item in value.items]]
    if value_type is _FrozenTuple:
        return ["tuple", [_jsonable(item) for item in value.items]]
    if value_type is _FrozenDict:
        return [
            "dict",
            [[_jsonable(key), _jsonable(item)] for key, item in value.items],
        ]
    if value_type is _FrozenSet:
        items = [_jsonable(item) for item in value.items]
        items.sort(
            key=lambda item: json.dumps(
                item, ensure_ascii=False, separators=(",", ":")
            )
        )
        return ["set", items]
    if value_type is _FrozenFrozenset:
        items = [_jsonable(item) for item in value.items]
        items.sort(
            key=lambda item: json.dumps(
                item, ensure_ascii=False, separators=(",", ":")
            )
        )
        return ["frozenset", items]
    if value_type is tuple:
        return ["tuple", [_jsonable(item) for item in value]]
    if isinstance(value, Mapping):
        items = [(_jsonable(key), _jsonable(item)) for key, item in value.items()]
        items.sort(
            key=lambda pair: json.dumps(
                pair[0], ensure_ascii=False, separators=(",", ":")
            )
        )
        return ["mapping", [[key, item] for key, item in items]]
    fail(
        "PROVENANCE_FRAME_TAMPERED",
        "protected frame contains an unsupported value",
        "frame",
        {"type": f"{value_type.__module__}.{value_type.__qualname__}"},
    )


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(
        _jsonable(value),
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
    ).encode("utf-8")


def _freeze_value(value: object, field_path: str) -> object:
    """Copy primitives canonically and replace nested mutables with frozen forms."""
    value_type = type(value)
    if value is None or value is pd.NA or value is pd.NaT:
        return value
    if value_type in {
        bool,
        int,
        float,
        str,
        bytes,
        Decimal,
        datetime,
        date,
        time,
        pd.Timestamp,
        pd.Timedelta,
    }:
        return value
    if value_type in _FROZEN_CONTAINER_TYPES:
        return value
    if isinstance(value, np.generic):
        return _freeze_value(value.item(), field_path)
    if value_type is list:
        return _FrozenList(
            tuple(_freeze_value(item, f"{field_path}[]") for item in value)
        )
    if value_type is tuple:
        return _FrozenTuple(
            tuple(_freeze_value(item, f"{field_path}[]") for item in value)
        )
    if value_type is dict:
        frozen_items = tuple(
            (
                _freeze_value(key, f"{field_path}.key"),
                _freeze_value(item, f"{field_path}.value"),
            )
            for key, item in value.items()
        )
        try:
            return _FrozenDict(
                tuple(sorted(frozen_items, key=lambda pair: _canonical_bytes(pair[0])))
            )
        except (TypeError, ValueError) as exc:
            raise AlmondLabError(
                "PROVENANCE_CELL_INVALID",
                "mapping cells must have canonicalizable keys and values",
                field_path,
            ) from exc
    if value_type is set:
        try:
            return _FrozenSet(
                frozenset(_freeze_value(item, f"{field_path}[]") for item in value)
            )
        except TypeError as exc:
            raise AlmondLabError(
                "PROVENANCE_CELL_INVALID",
                "set cells must contain hashable canonical values",
                field_path,
            ) from exc
    if value_type is frozenset:
        try:
            return _FrozenFrozenset(
                frozenset(_freeze_value(item, f"{field_path}[]") for item in value)
            )
        except TypeError as exc:
            raise AlmondLabError(
                "PROVENANCE_CELL_INVALID",
                "frozenset cells must contain hashable canonical values",
                field_path,
            ) from exc
    fail(
        "PROVENANCE_CELL_INVALID",
        "dataframe cells must use supported primitive or nested container values",
        field_path,
        {"type": f"{value_type.__module__}.{value_type.__qualname__}"},
    )


def _thaw_value(value: object) -> object:
    value_type = type(value)
    if value_type is _FrozenList:
        return [_thaw_value(item) for item in value.items]
    if value_type is _FrozenTuple:
        return tuple(_thaw_value(item) for item in value.items)
    if value_type is _FrozenDict:
        return {_thaw_value(key): _thaw_value(item) for key, item in value.items}
    if value_type is _FrozenSet:
        return {_thaw_value(item) for item in value.items}
    if value_type is _FrozenFrozenset:
        return frozenset(_thaw_value(item) for item in value.items)
    return value


def _columns(frame: pd.DataFrame, side: str) -> tuple[str, ...]:
    received = list(frame.columns)
    if any(type(column) is not str for column in received):
        fail(
            "PROVENANCE_COLUMN_INVALID",
            "all dataframe column names must be exact strings",
            f"{side}.columns",
        )
    if len(received) != len(set(received)):
        fail(
            "PROVENANCE_COLUMN_DUPLICATE",
            "dataframe column names must be unique",
            f"{side}.columns",
        )
    return tuple(received)


def _values(frame: pd.DataFrame, column: str) -> list[object]:
    series = pd.DataFrame.__getitem__(frame, column)
    return pd.Series.tolist(series)


def _freeze_frame(frame: pd.DataFrame, side: str) -> pd.DataFrame:
    if type(frame) is not pd.DataFrame:
        fail(
            "PROVENANCE_FRAME_INVALID",
            "value must be an exact pandas DataFrame",
            side,
        )
    columns = _columns(frame, side)
    frozen_columns: dict[str, pd.Series] = {}
    for column in columns:
        frozen_columns[column] = pd.Series(
            [
                _freeze_value(value, f"{side}.{column}[{position}]")
                for position, value in enumerate(_values(frame, column))
            ],
            dtype=object,
        )
    snapshot = pd.DataFrame(frozen_columns, columns=list(columns))
    snapshot.attrs.clear()
    return snapshot


def _thaw_frame(frame: pd.DataFrame) -> pd.DataFrame:
    columns = tuple(frame.columns)
    materialized = pd.DataFrame(
        {
            column: pd.Series(
                [_thaw_value(value) for value in _values(frame, column)],
                dtype=object,
            )
            for column in columns
        },
        columns=list(columns),
    )
    materialized.attrs.clear()
    return materialized


def _clone_frozen_frame(frame: pd.DataFrame) -> pd.DataFrame:
    clone = pd.DataFrame.copy(frame, deep=True)
    clone.attrs.clear()
    return clone


def _frame_document(frame: pd.DataFrame) -> object:
    return {
        "columns": tuple(frame.columns),
        "rows": tuple(
            tuple(_values(frame, column)[row] for column in frame.columns)
            for row in range(len(frame))
        ),
    }


def _seal_for(
    frame: pd.DataFrame,
    row_lineage: tuple[_RowLineage, ...],
    lineage: Mapping[str, object],
) -> str:
    return sha256(
        _canonical_bytes(
            {
                "frame": _frame_document(frame),
                "row_lineage": row_lineage,
                "lineage": lineage,
            }
        )
    ).hexdigest()


def _lineage_metadata(
    *,
    operation: str,
    row_lineage: tuple[_RowLineage, ...],
    source_types: frozenset[str],
    origin_family: str,
    extra: Mapping[str, object] | None = None,
) -> MappingProxyType:
    metadata: dict[str, object] = {
        "namespace": _LINEAGE_NAMESPACE,
        "operation": operation,
        "origin_family": origin_family,
        "source_types": tuple(sorted(source_types)),
        "row_ancestry": row_lineage,
        "row_count": len(row_lineage),
    }
    if extra is not None:
        metadata.update(extra)
    return MappingProxyType(metadata)


class ProvenanceFrame:
    """Sealed defensive snapshot with immutable row-aligned ancestry."""

    __slots__ = ("_frame", "_row_lineage", "_lineage", "_seal")

    def __init__(self, frame: pd.DataFrame) -> None:
        snapshot, rows, source_types, families = _inspect_dataframe(frame, "frame")
        family = next(iter(families))
        lineage = _lineage_metadata(
            operation="snapshot",
            row_lineage=rows,
            source_types=source_types,
            origin_family=family,
        )
        object.__setattr__(self, "_frame", snapshot)
        object.__setattr__(self, "_row_lineage", rows)
        object.__setattr__(self, "_lineage", lineage)
        object.__setattr__(self, "_seal", _seal_for(snapshot, rows, lineage))

    def __setattr__(self, name: str, value: object) -> None:
        raise AttributeError("ProvenanceFrame is immutable")

    @classmethod
    def _from_join(
        cls,
        frame: pd.DataFrame,
        row_lineage: tuple[_RowLineage, ...],
        *,
        source_types: frozenset[str],
        origin_family: str,
        join_keys: tuple[str, ...],
        how: str,
        cardinality: str,
        suffixes: tuple[str, str],
        column_kinds: tuple[tuple[str, str], ...],
    ) -> "ProvenanceFrame":
        snapshot = _freeze_frame(frame, "joined_frame")
        lineage = _lineage_metadata(
            operation="safe_join",
            row_lineage=row_lineage,
            source_types=source_types,
            origin_family=origin_family,
            extra={
                "join_keys": join_keys,
                "join_how": how,
                "cardinality": cardinality,
                "column_suffixes": suffixes,
                "column_kinds": column_kinds,
            },
        )
        instance = object.__new__(cls)
        object.__setattr__(instance, "_frame", snapshot)
        object.__setattr__(instance, "_row_lineage", row_lineage)
        object.__setattr__(instance, "_lineage", lineage)
        object.__setattr__(instance, "_seal", _seal_for(snapshot, row_lineage, lineage))
        return instance

    def _assert_intact(self) -> None:
        try:
            valid = (
                type(self._frame) is pd.DataFrame
                and type(self._row_lineage) is tuple
                and isinstance(self._lineage, MappingProxyType)
                and self._seal == _seal_for(self._frame, self._row_lineage, self._lineage)
            )
        except Exception:
            valid = False
        if not valid:
            fail(
                "PROVENANCE_FRAME_TAMPERED",
                "protected frame content or ancestry differs from its seal",
                "frame",
            )

    @property
    def lineage(self) -> MappingProxyType:
        self._assert_intact()
        return self._lineage

    @property
    def columns(self) -> pd.Index:
        self._assert_intact()
        return self._frame.columns.copy()

    @property
    def shape(self) -> tuple[int, int]:
        self._assert_intact()
        return self._frame.shape

    @property
    def empty(self) -> bool:
        self._assert_intact()
        return self._frame.empty

    @property
    def loc(self):  # type: ignore[no-untyped-def]
        return self.to_pandas().loc

    @property
    def iloc(self):  # type: ignore[no-untyped-def]
        return self.to_pandas().iloc

    def to_pandas(self) -> pd.DataFrame:
        self._assert_intact()
        materialized = _thaw_frame(self._frame)
        materialized.attrs["almondlab_lineage"] = dict(self._lineage)
        return materialized

    def set_index(self, *args: object, **kwargs: object) -> pd.DataFrame:
        return self.to_pandas().set_index(*args, **kwargs)

    def __getitem__(self, key: object):  # type: ignore[no-untyped-def]
        return self.to_pandas().__getitem__(key)

    def __len__(self) -> int:
        self._assert_intact()
        return len(self._frame)

    def __iter__(self) -> Iterator[str]:
        self._assert_intact()
        return iter(self._frame)

    def __repr__(self) -> str:
        self._assert_intact()
        return f"ProvenanceFrame({self._frame!r})"


def _inspect_dataframe(
    frame: pd.DataFrame, side: str
) -> tuple[
    pd.DataFrame,
    tuple[_RowLineage, ...],
    frozenset[str],
    frozenset[str],
]:
    """Validate every raw provenance cell before making a canonical snapshot."""
    if type(frame) is not pd.DataFrame:
        fail(
            "PROVENANCE_FRAME_INVALID",
            "value must be an exact pandas DataFrame",
            side,
        )
    columns = _columns(frame, side)
    missing = [column for column in _PROVENANCE_COLUMNS if column not in columns]
    if missing:
        fail(
            "PROVENANCE_COLUMNS_MISSING",
            "record_id and source_type are mandatory row-level provenance columns",
            f"{side}.columns",
            {"missing": missing},
        )
    if len(frame) == 0:
        fail(
            "PROVENANCE_EMPTY",
            "an empty dataframe has no row-level provenance to validate",
            side,
        )

    record_values = _values(frame, "record_id")
    source_values = _values(frame, "source_type")
    row_lineage: list[_RowLineage] = []
    record_ids: list[str] = []
    source_types: set[str] = set()
    families: set[str] = set()
    for position, (record_id, source_type) in enumerate(
        zip(record_values, source_values, strict=True)
    ):
        if type(source_type) is not str or source_type not in _SOURCE_NAMESPACES:
            fail(
                "PROVENANCE_SOURCE_TYPE_INVALID",
                "source_type must use a registered exact string value",
                f"{side}.source_type[{position}]",
                {"received": repr(source_type)},
            )
        prefix, family = _SOURCE_NAMESPACES[source_type]
        if (
            type(record_id) is not str
            or _SAFE_RECORD_ID.fullmatch(record_id) is None
            or not record_id.startswith(prefix)
        ):
            fail(
                "PROVENANCE_ID_INVALID",
                "record_id must be an exact portable string matching its source namespace",
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
    return (
        _freeze_frame(frame, side),
        tuple(row_lineage),
        frozenset(source_types),
        frozenset(families),
    )


def _payload_without_provenance(frame: pd.DataFrame) -> pd.DataFrame:
    columns = [column for column in frame.columns if column not in _PROVENANCE_COLUMNS]
    payload = pd.DataFrame(
        {column: pd.Series(_values(frame, column), dtype=object) for column in columns},
        columns=columns,
    )
    payload.attrs.clear()
    return payload


def _inspect_lineage(
    row_lineage: tuple[_RowLineage, ...], side: str
) -> tuple[frozenset[str], frozenset[str]]:
    source_types: set[str] = set()
    families: set[str] = set()
    for row_position, row in enumerate(row_lineage):
        if type(row) is not tuple or not row:
            fail(
                "PROVENANCE_LINEAGE_INVALID",
                "each row must retain immutable provenance ancestry",
                f"{side}.lineage[{row_position}]",
            )
        for atom_position, atom in enumerate(row):
            if type(atom) is not tuple or len(atom) != 2:
                fail(
                    "PROVENANCE_LINEAGE_INVALID",
                    "lineage atoms must be exact record/source tuples",
                    f"{side}.lineage[{row_position}][{atom_position}]",
                )
            record_id, source_type = atom
            if type(source_type) is not str or source_type not in _SOURCE_NAMESPACES:
                fail(
                    "PROVENANCE_SOURCE_TYPE_INVALID",
                    "lineage source_type is not registered",
                    f"{side}.lineage[{row_position}][{atom_position}]",
                )
            prefix, family = _SOURCE_NAMESPACES[source_type]
            if (
                type(record_id) is not str
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


def _copy_frame(
    value: object, side: str
) -> tuple[
    pd.DataFrame,
    tuple[_RowLineage, ...],
    frozenset[str],
    frozenset[str],
    dict[str, str],
]:
    if type(value) is ProvenanceFrame:
        value._assert_intact()
        operation = value._lineage.get("operation")
        if operation not in {"snapshot", "safe_join"}:
            fail(
                "PROVENANCE_FRAME_TAMPERED",
                "protected frame operation metadata is invalid",
                side,
            )
        frame = _clone_frozen_frame(value._frame)
        if operation == "snapshot":
            frame = _payload_without_provenance(frame)
        observed_types, observed_families = _inspect_lineage(
            value._row_lineage, side
        )
        declared_types_value = value._lineage.get("source_types")
        declared_family = value._lineage.get("origin_family")
        if (
            type(declared_types_value) is not tuple
            or not declared_types_value
            or any(
                type(item) is not str or item not in _SOURCE_NAMESPACES
                for item in declared_types_value
            )
            or len(declared_types_value) != len(set(declared_types_value))
            or type(declared_family) is not str
        ):
            fail(
                "PROVENANCE_FRAME_TAMPERED",
                "protected frame source metadata is invalid",
                side,
            )
        declared_types = frozenset(declared_types_value)
        declared_families = frozenset(
            _SOURCE_NAMESPACES[item][1] for item in declared_types
        )
        if (
            len(declared_families) != 1
            or declared_family not in declared_families
            or (
                value._row_lineage
                and (
                    observed_types != declared_types
                    or observed_families != declared_families
                )
            )
        ):
            fail(
                "PROVENANCE_FRAME_TAMPERED",
                "protected frame ancestry differs from its source metadata",
                side,
            )
        if operation == "snapshot":
            column_kinds = _infer_column_kinds(frame)
        else:
            column_kinds = _parse_column_kinds(
                value._lineage.get("column_kinds"), frame, side
            )
        return (
            frame,
            value._row_lineage,
            declared_types,
            declared_families,
            column_kinds,
        )
    if type(value) is not pd.DataFrame:
        fail(
            "PROVENANCE_FRAME_INVALID",
            "join inputs must be exact pandas DataFrame or ProvenanceFrame instances",
            side,
        )
    snapshot, rows, source_types, families = _inspect_dataframe(value, side)
    payload = _payload_without_provenance(snapshot)
    return (
        payload,
        rows,
        source_types,
        families,
        _infer_column_kinds(payload),
    )


def _null_key(value: object) -> bool:
    if value is None or value is pd.NA or value is pd.NaT:
        return True
    if type(value) is float:
        return isnan(value)
    return type(value) is Decimal and value.is_nan()


_KEY_TYPES: Final[frozenset[type[object]]] = frozenset(
    {
        str,
        int,
        float,
        bytes,
        Decimal,
        date,
        datetime,
        pd.Timestamp,
        pd.Timedelta,
    }
)
_KEY_KIND_NAMES: Final[dict[type[object], str]] = {
    str: "builtins.str",
    int: "builtins.int",
    float: "builtins.float",
    bytes: "builtins.bytes",
    Decimal: "decimal.Decimal",
    date: "datetime.date",
    datetime: "datetime.datetime",
    pd.Timestamp: "pandas.Timestamp",
    pd.Timedelta: "pandas.Timedelta",
}
_KEY_NAME_TYPES: Final[dict[str, type[object]]] = {
    name: kind for kind, name in _KEY_KIND_NAMES.items()
}


def _infer_column_kinds(frame: pd.DataFrame) -> dict[str, str]:
    kinds: dict[str, str] = {}
    for column in frame.columns:
        values = _values(frame, column)
        if not values or any(_null_key(value) for value in values):
            continue
        exact_kinds = {type(value) for value in values}
        if len(exact_kinds) == 1:
            kind = next(iter(exact_kinds))
            if kind in _KEY_TYPES and kind is not bool:
                kinds[column] = _KEY_KIND_NAMES[kind]
    return kinds


def _parse_column_kinds(
    value: object, frame: pd.DataFrame, side: str
) -> dict[str, str]:
    if type(value) is not tuple:
        fail(
            "PROVENANCE_FRAME_TAMPERED",
            "protected joined frame lacks its sealed column-kind schema",
            side,
        )
    parsed: dict[str, str] = {}
    for position, item in enumerate(value):
        if (
            type(item) is not tuple
            or len(item) != 2
            or type(item[0]) is not str
            or type(item[1]) is not str
            or item[0] not in frame.columns
            or item[1] not in _KEY_NAME_TYPES
            or item[0] in parsed
        ):
            fail(
                "PROVENANCE_FRAME_TAMPERED",
                "protected joined frame column-kind schema is invalid",
                f"{side}.column_kinds[{position}]",
            )
        parsed[item[0]] = item[1]
    return parsed


def _validate_join_keys(
    left: pd.DataFrame,
    right: pd.DataFrame,
    on: object,
    left_hints: Mapping[str, str],
    right_hints: Mapping[str, str],
) -> tuple[tuple[str, ...], tuple[tuple[str, str], ...]]:
    if (
        type(on) not in {list, tuple}
        or len(on) == 0
        or any(type(key) is not str or not key for key in on)
    ):
        fail(
            "JOIN_KEYS_INVALID",
            "on must be a nonempty list or tuple of exact nonempty strings",
            "on",
        )
    keys = tuple(on)
    if len(keys) != len(set(keys)) or any(key in _PROVENANCE_COLUMNS for key in keys):
        fail(
            "JOIN_KEYS_INVALID",
            "join keys must be unique and cannot be provenance columns",
            "on",
        )
    schemas: dict[str, dict[str, type[object]]] = {"left": {}, "right": {}}
    for side, frame, hints in (
        ("left", left, left_hints),
        ("right", right, right_hints),
    ):
        missing = [key for key in keys if key not in frame.columns]
        if missing:
            fail(
                "JOIN_KEY_MISSING",
                "every join key must exist in both inputs",
                f"{side}.columns",
                {"missing": missing},
            )
        for key in keys:
            values = _values(frame, key)
            if any(_null_key(value) for value in values):
                fail(
                    "JOIN_KEY_NULL",
                    "join keys cannot contain null values",
                    f"{side}.{key}",
                )
            kinds = {type(value) for value in values}
            if not values:
                hinted_name = hints.get(key)
                kind = _KEY_NAME_TYPES.get(hinted_name or "")
            elif (
                bool in kinds
                or len(kinds) != 1
                or next(iter(kinds)) not in _KEY_TYPES
            ):
                kind = None
            else:
                kind = next(iter(kinds))
            if kind is None:
                fail(
                    "JOIN_KEY_TYPE_MISMATCH",
                    "each join-key column must use one registered exact non-boolean kind",
                    f"{side}.{key}",
                    {
                        "kinds": sorted(
                            f"{kind.__module__}.{kind.__qualname__}" for kind in kinds
                        )
                    },
                )
            schemas[side][key] = kind
    mismatched = [
        key for key in keys if schemas["left"][key] is not schemas["right"][key]
    ]
    if mismatched:
        fail(
            "JOIN_KEY_TYPE_MISMATCH",
            "left and right join-key kinds must match exactly",
            "on",
            {
                "columns": mismatched,
                "left": {
                    key: schemas["left"][key].__qualname__ for key in mismatched
                },
                "right": {
                    key: schemas["right"][key].__qualname__ for key in mismatched
                },
            },
        )
    return keys, tuple(
        (key, _KEY_KIND_NAMES[schemas["left"][key]]) for key in keys
    )


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
    if type(selected) is str and selected == "many_to_many":
        fail(
            "JOIN_MANY_TO_MANY_FORBIDDEN",
            "many-to-many joins are forbidden at the protected data boundary",
            "cardinality",
        )
    if type(selected) is not str or selected not in {
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


def _require_join_row_limit(
    observed_rows: int, *, field_path: str, stage: str
) -> None:
    if observed_rows > _MAX_JOIN_ROWS:
        fail(
            "JOIN_ROW_LIMIT_EXCEEDED",
            "protected joins allow at most 10,000 rows per input and result",
            field_path,
            {
                "maximum_rows": _MAX_JOIN_ROWS,
                "observed_rows": observed_rows,
                "stage": stage,
            },
        )


def _join_key_counts(
    frame: pd.DataFrame, keys: tuple[str, ...]
) -> dict[tuple[object, ...], int]:
    counts: dict[tuple[object, ...], int] = {}
    columns = [_values(frame, key) for key in keys]
    for key_values in zip(*columns, strict=True):
        counts[key_values] = counts.get(key_values, 0) + 1
    return counts


def _predicted_join_rows(
    left: pd.DataFrame,
    right: pd.DataFrame,
    keys: tuple[str, ...],
    how: str,
) -> int:
    """Return pandas-equivalent row multiplicity after exact key validation."""
    left_counts = _join_key_counts(left, keys)
    right_counts = _join_key_counts(right, keys)
    shared = left_counts.keys() & right_counts.keys()
    matched = sum(left_counts[key] * right_counts[key] for key in shared)
    left_only = sum(
        count for key, count in left_counts.items() if key not in right_counts
    )
    right_only = sum(
        count for key, count in right_counts.items() if key not in left_counts
    )
    if how == "inner":
        return matched
    if how == "left":
        return matched + left_only
    if how == "right":
        return matched + right_only
    return matched + left_only + right_only


def _plan_suffixes(
    left: pd.DataFrame, right: pd.DataFrame, keys: tuple[str, ...]
) -> tuple[str, str]:
    left_columns = tuple(left.columns)
    right_columns = tuple(right.columns)
    overlaps = (set(left_columns) & set(right_columns)) - set(keys)
    for generation in range(1, 10_001):
        suffixes = (
            "_left" if generation == 1 else f"_left{generation}",
            "_right" if generation == 1 else f"_right{generation}",
        )
        output = list(keys)
        output.extend(
            column + suffixes[0] if column in overlaps else column
            for column in left_columns
            if column not in keys
        )
        output.extend(
            column + suffixes[1] if column in overlaps else column
            for column in right_columns
            if column not in keys
        )
        if len(output) == len(set(output)):
            return suffixes
    fail(
        "JOIN_COLUMN_COLLISION",
        "no deterministic collision-free merge suffix namespace is available",
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
    """Join compatible ancestry with an inclusive 10,000-row input/output cap."""
    (
        left_frame,
        left_rows,
        left_types,
        left_families,
        left_kind_hints,
    ) = _copy_frame(left, "left")
    (
        right_frame,
        right_rows,
        right_types,
        right_families,
        right_kind_hints,
    ) = _copy_frame(right, "right")
    families = left_families | right_families
    if families == {"synthetic", "empirical"}:
        fail(
            "SYNTHETIC_CONTAMINATION",
            "synthetic and empirical ancestry cannot enter the same join",
            "safe_join",
            {
                "left_source_types": sorted(left_types),
                "right_source_types": sorted(right_types),
            },
        )
    _require_join_row_limit(len(left_frame), field_path="left", stage="input")
    _require_join_row_limit(len(right_frame), field_path="right", stage="input")
    if type(how) is not str or how not in {"inner", "left", "right", "outer"}:
        fail("JOIN_HOW_INVALID", "how must be inner, left, right, or outer", "how")
    keys, join_key_kinds = _validate_join_keys(
        left_frame,
        right_frame,
        on,
        left_kind_hints,
        right_kind_hints,
    )
    checked_cardinality = _validate_cardinality(
        left_frame, right_frame, keys, cardinality, validate
    )
    predicted_rows = _predicted_join_rows(left_frame, right_frame, keys, how)
    _require_join_row_limit(
        predicted_rows,
        field_path="result",
        stage="predicted_result",
    )
    suffixes = _plan_suffixes(left_frame, right_frame, keys)

    # Object sentinels cannot collide with exact-string user columns.  They are
    # introduced only after every validation and removed before sealing output.
    left_position_column = object()
    right_position_column = object()
    left_work = _clone_frozen_frame(left_frame)
    right_work = _clone_frozen_frame(right_frame)
    left_work[left_position_column] = list(range(len(left_work)))
    right_work[right_position_column] = list(range(len(right_work)))
    result = pd.merge(
        left_work,
        right_work,
        how=how,
        on=list(keys),
        sort=False,
        suffixes=suffixes,
        validate=checked_cardinality,
    )
    _require_join_row_limit(
        len(result),
        field_path="result",
        stage="materialized_result",
    )
    sort_columns = (
        [right_position_column, left_position_column]
        if how == "right"
        else [left_position_column, right_position_column]
    )
    result = result.sort_values(sort_columns, kind="mergesort", na_position="last")

    output_lineage: list[_RowLineage] = []
    for left_position, right_position in zip(
        result[left_position_column].tolist(),
        result[right_position_column].tolist(),
        strict=True,
    ):
        atoms: list[_LineageAtom] = []
        if not pd.isna(left_position):
            atoms.extend(left_rows[int(left_position)])
        if not pd.isna(right_position):
            atoms.extend(right_rows[int(right_position)])
        output_lineage.append(tuple(atoms))
    result = result.drop(columns=[left_position_column, right_position_column])
    result = result.reset_index(drop=True)
    result.attrs.clear()
    if len(result):
        column_kinds = tuple(_infer_column_kinds(result).items())
    else:
        joined_key_kinds = dict(join_key_kinds)
        overlaps = (set(left_frame.columns) & set(right_frame.columns)) - set(keys)
        derived: dict[str, str] = dict(joined_key_kinds)
        for column in left_frame.columns:
            if column in keys or column not in left_kind_hints:
                continue
            output_name = column + suffixes[0] if column in overlaps else column
            derived[output_name] = left_kind_hints[column]
        for column in right_frame.columns:
            if column in keys or column not in right_kind_hints:
                continue
            output_name = column + suffixes[1] if column in overlaps else column
            derived[output_name] = right_kind_hints[column]
        column_kinds = tuple(
            (column, derived[column]) for column in result.columns if column in derived
        )
    origin_family = next(iter(families))
    return ProvenanceFrame._from_join(
        result,
        tuple(output_lineage),
        source_types=left_types | right_types,
        origin_family=origin_family,
        join_keys=keys,
        how=how,
        cardinality=checked_cardinality,
        suffixes=suffixes,
        column_kinds=column_kinds,
    )


__all__ = ["ProvenanceFrame", "safe_join"]
