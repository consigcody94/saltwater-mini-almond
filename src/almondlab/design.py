"""Restricted Paper 1 allocation, blinding, and experimental-unit audits.

This module validates experimental structure only.  It deliberately contains no
candidate ranking, phenotype, survival, or performance inference.
"""

from __future__ import annotations

import csv
import hashlib
import hmac
from collections import Counter, defaultdict
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
import os
from pathlib import Path
import secrets
import shutil
import tempfile
from types import MappingProxyType
from typing import Literal

import numpy as np
from pydantic import ValidationError
from scipy.optimize import Bounds, LinearConstraint, milp
import yaml
from yaml.events import (
    AliasEvent,
    CollectionEndEvent,
    CollectionStartEvent,
    MappingStartEvent,
    ScalarEvent,
    SequenceStartEvent,
)

from almondlab.contracts import EvidenceLabel
from almondlab.errors import AlmondLabError, fail
from almondlab.paper1_contracts import (
    AnalysisPopulation,
    Paper1DesignConfig,
    load_paper1_design,
)
from almondlab.provenance import canonical_json_bytes, sha256_bytes, sha256_file
from almondlab.verification import (
    VerificationRecord,
    capture_code_provenance,
    code_version_from_provenance,
    write_verification_record,
)


DESIGN_SCHEMA_VERSION = "1.0"
DESIGN_MODEL_VERSION = "paper1_composite_root_restricted_v1"
SEED_POOL_SIZE = 4
SEED_CHILD_NAMES = (
    "run_block_ordering",
    "reservoir_identity",
    "transformation_batch",
    "plant_identity",
    "position",
    "blind_code",
    "movement_schedule",
)
TRANSFORMED_GROUPS = frozenset(
    {"C1", "C2", "C3", "C4", "C5", "C6", "empty_vector"}
)
NONTRANSFORMED_GROUPS = frozenset({"sham_transformation", "unmodified_parent"})
REGISTERED_GROUPS = (
    "C1",
    "C2",
    "C3",
    "C4",
    "C5",
    "C6",
    "empty_vector",
    "sham_transformation",
    "unmodified_parent",
)
REGISTERED_BATCH_BLOCKS = ("batch_a", "batch_b")
REGISTERED_STRATA = ("lower_canopy", "upper_canopy")
REGISTERED_WATERS = (
    "nonsaline_nutrient_matched_control",
    "pilot_selected_full_ion_marine_challenge",
)
CANONICAL_WATER_IDENTITY_FIELDS = ("run_id", "water_id", "reservoir_id")
MAX_INTEROPERABLE_INTEGER = 9_007_199_254_740_991
BLINDED_MODEL_VERSION = "paper1_staff_opaque_projection_v1"
OPAQUE_CODE_LENGTH = 32
FIXTURE_MAX_DEPTH = 24
FIXTURE_MAX_NODES = 36_000
JOINT_SPATIAL_CACHE_MAXSIZE = 256
_JOINT_SPATIAL_CACHE_SCHEMA_VERSION = "joint-spatial-template-v1"
_SPATIAL_MAXIMUM_BOUNDS = MappingProxyType(
    {
        "row_group_count_difference": 1,
        "column_group_max_count": 1,
        "compartment_group_count_difference": 1,
        "row_stratum_count_difference": 1,
        "column_stratum_count_difference": 1,
        "compartment_stratum_count_difference": 1,
        "row_transformed_batch_count_difference": 1,
        "column_transformed_batch_count_difference": 1,
        "compartment_transformed_batch_count_difference": 1,
        "row_not_applicable_max_count": 2,
        "column_not_applicable_max_count": 2,
        "compartment_not_applicable_max_count": 10,
    }
)

_JointSpatialKey = tuple[
    tuple[tuple[str, str, str], ...],
    tuple[tuple[str, int, int, int, int], ...],
]
_JointSpatialTemplate = tuple[tuple[int, int], ...]


@dataclass(frozen=True, slots=True)
class _JointSpatialTemplateEntry:
    template: _JointSpatialTemplate
    integrity_digest: bytes = field(repr=False)


class _JointSpatialTemplateCache:
    """Process-private optimization cache with no scientific authority."""

    __slots__ = ("__entries", "__integrity_key")

    def __init__(self) -> None:
        self.__entries: dict[_JointSpatialKey, _JointSpatialTemplateEntry] = {}
        self.__integrity_key = secrets.token_bytes(32)

    def __repr__(self) -> str:
        return f"<_JointSpatialTemplateCache entries={len(self.__entries)}>"

    def __reduce_ex__(self, protocol: int) -> object:
        raise TypeError("joint spatial cache is process-private and non-serializable")

    def __len__(self) -> int:
        return len(self.__entries)

    def clear(self) -> None:
        self.__entries.clear()

    def discard(self, key: _JointSpatialKey) -> None:
        self.__entries.pop(key, None)

    def items(
        self,
    ) -> tuple[tuple[_JointSpatialKey, _JointSpatialTemplateEntry], ...]:
        return tuple(self.__entries.items())

    @staticmethod
    def _is_primitive_key(key: object) -> bool:
        return (
            type(key) is tuple
            and len(key) == 2
            and type(key[0]) is tuple
            and type(key[1]) is tuple
            and all(
                type(category) is tuple
                and len(category) == 3
                and all(type(item) is str for item in category)
                for category in key[0]
            )
            and all(
                type(geometry) is tuple
                and len(geometry) == 5
                and type(geometry[0]) is str
                and all(type(item) is int for item in geometry[1:])
                for geometry in key[1]
            )
        )

    @staticmethod
    def _is_primitive_template(template: object) -> bool:
        return type(template) is tuple and all(
            type(pair) is tuple
            and len(pair) == 2
            and all(type(index) is int for index in pair)
            for pair in template
        )

    def _digest(
        self, key: _JointSpatialKey, template: _JointSpatialTemplate
    ) -> bytes:
        payload = canonical_json_bytes(
            {
                "cache_schema_version": _JOINT_SPATIAL_CACHE_SCHEMA_VERSION,
                "key": key,
                "template": template,
            }
        )
        return hmac.new(self.__integrity_key, payload, hashlib.sha256).digest()

    def get(self, key: _JointSpatialKey) -> _JointSpatialTemplate | None:
        entry = self.__entries.get(key)
        if (
            type(entry) is not _JointSpatialTemplateEntry
            or not self._is_primitive_key(key)
            or not self._is_primitive_template(entry.template)
            or type(entry.integrity_digest) is not bytes
            or len(entry.integrity_digest) != hashlib.sha256().digest_size
        ):
            self.discard(key)
            return None
        expected = self._digest(key, entry.template)
        if not hmac.compare_digest(entry.integrity_digest, expected):
            self.discard(key)
            return None
        return entry.template

    def put(
        self, key: _JointSpatialKey, template: _JointSpatialTemplate
    ) -> None:
        if not self._is_primitive_key(key) or not self._is_primitive_template(
            template
        ):
            raise TypeError("joint spatial cache accepts only primitive templates")
        if key not in self.__entries and len(self.__entries) >= JOINT_SPATIAL_CACHE_MAXSIZE:
            self.__entries.pop(next(iter(self.__entries)))
        self.__entries[key] = _JointSpatialTemplateEntry(
            template=template,
            integrity_digest=self._digest(key, template),
        )


_JOINT_SPATIAL_TEMPLATE_CACHE = _JointSpatialTemplateCache()


class _BoundSpatialAssignmentInvalid(Exception):
    """Internal signal that a bound cached template failed the public oracle."""


def _required_text(value: object, *, code: str, field_path: str) -> str:
    if (
        type(value) is not str
        or not value
        or value != value.strip()
        or any(ord(character) < 32 for character in value)
    ):
        fail(code, "value must be a trim-free nonempty string", field_path)
    return value


def _optional_text(value: object, *, code: str, field_path: str) -> str | None:
    if value is None:
        return None
    return _required_text(value, code=code, field_path=field_path)


def _positive_int(value: object, *, code: str, field_path: str) -> int:
    if (
        type(value) is not int
        or value <= 0
        or value > MAX_INTEROPERABLE_INTEGER
    ):
        fail(code, "value must be a positive interoperable primitive integer", field_path)
    return value


def _nonnegative_int(value: object, *, code: str, field_path: str) -> int:
    if (
        type(value) is not int
        or value < 0
        or value > MAX_INTEROPERABLE_INTEGER
    ):
        fail(
            code,
            "value must be a nonnegative interoperable primitive integer",
            field_path,
        )
    return value


def _positive_float(value: object, *, code: str, field_path: str) -> float:
    if type(value) not in (int, float):
        fail(code, "value must be a finite positive primitive number", field_path)
    try:
        converted = float(value)
    except (OverflowError, TypeError, ValueError):
        fail(code, "value must be a finite positive primitive number", field_path)
    if not np.isfinite(converted) or converted <= 0:
        fail(code, "value must be a finite positive primitive number", field_path)
    return converted


def _exact_tuple(
    value: object,
    *,
    item_type: type,
    code: str,
    field_path: str,
) -> tuple[object, ...]:
    if type(value) is not tuple:
        fail(code, "value must be an immutable tuple", field_path)
    if any(type(item) is not item_type for item in value):
        fail(code, f"items must be {item_type.__name__} values", field_path)
    return value


def _freeze_string_map(
    value: Mapping[str, str], *, code: str, field_path: str
) -> Mapping[str, str]:
    if type(value) not in (dict, MappingProxyType) or any(
        type(name) is not str or type(digest) is not str
        for name, digest in value.items()
    ):
        fail(code, "value must be a string mapping", field_path)
    return MappingProxyType(dict(sorted(value.items())))


def _deep_freeze(value: object) -> object:
    if type(value) in (dict, MappingProxyType):
        return MappingProxyType(
            {key: _deep_freeze(item) for key, item in value.items()}
        )
    if isinstance(value, (list, tuple)):
        return tuple(_deep_freeze(item) for item in value)
    return value


def _json_record(record: "AllocationRecord") -> dict[str, object]:
    return {
        "allocation_id": record.allocation_id,
        "plant_id": record.plant_id,
        "population": record.population.value,
        "group_id": record.group_id,
        "water_id": record.water_id,
        "run_id": record.run_id,
        "run_sequence_ordinal": record.run_sequence_ordinal,
        "reservoir_id": record.reservoir_id,
        "transformation_batch_block": record.transformation_batch_block,
        "transformation_batch_id": record.transformation_batch_id,
        "transformation_event_id": record.transformation_event_id,
        "pretreatment_canopy": record.pretreatment_canopy,
        "baseline_canopy_stratum": record.baseline_canopy_stratum,
        "greenhouse_compartment_id": record.greenhouse_compartment_id,
        "water_batch_id": record.water_batch_id,
        "bench_id": record.bench_id,
        "row": record.row,
        "column": record.column,
        "position_id": record.position_id,
        "spatial_gradient_profile_id": record.spatial_gradient_profile_id,
        "movement_schedule_id": record.movement_schedule_id,
        "blinded_treatment_code": record.blinded_treatment_code,
        "cohort_id": record.cohort_id,
        "evidence_label": record.evidence_label.value,
    }


@dataclass(frozen=True, slots=True)
class BaselinePlant:
    """One physically eligible plant frozen before randomization."""

    plant_id: str
    group_id: str
    pretreatment_canopy: float
    baseline_canopy_stratum: str
    transformation_batch_block: str | None
    transformation_batch_id: str | None
    transformation_event_id: str | None
    cohort_id: str

    def __post_init__(self) -> None:
        code = "ROSTER_INVALID"
        for name in ("plant_id", "group_id", "baseline_canopy_stratum", "cohort_id"):
            object.__setattr__(
                self,
                name,
                _required_text(getattr(self, name), code=code, field_path=name),
            )
        canopy = _positive_float(
            self.pretreatment_canopy, code=code, field_path="pretreatment_canopy"
        )
        object.__setattr__(self, "pretreatment_canopy", canopy)
        for name in (
            "transformation_batch_block",
            "transformation_batch_id",
            "transformation_event_id",
        ):
            object.__setattr__(
                self,
                name,
                _optional_text(getattr(self, name), code=code, field_path=name),
            )
        if self.group_id not in set(REGISTERED_GROUPS):
            fail(code, "plant group is not registered", "group_id")
        if self.baseline_canopy_stratum not in REGISTERED_STRATA:
            fail(code, "baseline canopy stratum is not registered", "baseline_canopy_stratum")
        if self.group_id in TRANSFORMED_GROUPS:
            if self.transformation_batch_block not in REGISTERED_BATCH_BLOCKS:
                fail(code, "transformed plants require a registered batch block", "transformation_batch_block")
            if self.transformation_batch_id is None:
                fail(code, "transformed plants require a physical batch identity", "transformation_batch_id")
        elif any(
            value is not None
            for value in (
                self.transformation_batch_block,
                self.transformation_batch_id,
                self.transformation_event_id,
            )
        ):
            field_path = next(
                name
                for name in (
                    "transformation_batch_block",
                    "transformation_batch_id",
                    "transformation_event_id",
                )
                if getattr(self, name) is not None
            )
            fail(code, "nontransformed controls cannot have transformation identities", field_path)


@dataclass(frozen=True, slots=True)
class BaselineRoster:
    plants: tuple[BaselinePlant, ...]

    def __post_init__(self) -> None:
        plants = _exact_tuple(
            self.plants,
            item_type=BaselinePlant,
            code="ROSTER_INVALID",
            field_path="plants",
        )
        identifiers = tuple(plant.plant_id for plant in plants)
        if len(set(identifiers)) != len(identifiers):
            fail("ROSTER_INVALID", "plant IDs must be unique", "plants.plant_id")
        event_ids = tuple(
            plant.transformation_event_id
            for plant in plants
            if plant.transformation_event_id is not None
        )
        if len(set(event_ids)) != len(event_ids):
            fail(
                "ROSTER_INVALID",
                "non-null transformation event IDs must be unique",
                "plants.transformation_event_id",
            )


@dataclass(frozen=True, slots=True)
class PositionSlot:
    """One physical, run-qualified greenhouse position."""

    position_id: str
    run_id: str
    run_sequence_ordinal: int
    water_id: str
    reservoir_id: str
    water_batch_id: str
    greenhouse_compartment_id: str
    bench_id: str
    row: int
    column: int
    spatial_gradient_profile_id: str
    permitted_movement_schedule_ids: tuple[str, ...]
    cohort_id: str

    def __post_init__(self) -> None:
        code = "POSITION_MAP_INVALID"
        for name in (
            "position_id",
            "run_id",
            "water_id",
            "reservoir_id",
            "water_batch_id",
            "greenhouse_compartment_id",
            "bench_id",
            "spatial_gradient_profile_id",
            "cohort_id",
        ):
            object.__setattr__(
                self,
                name,
                _required_text(getattr(self, name), code=code, field_path=name),
            )
        object.__setattr__(self, "row", _positive_int(self.row, code=code, field_path="row"))
        object.__setattr__(
            self,
            "run_sequence_ordinal",
            _positive_int(
                self.run_sequence_ordinal,
                code=code,
                field_path="run_sequence_ordinal",
            ),
        )
        object.__setattr__(
            self, "column", _positive_int(self.column, code=code, field_path="column")
        )
        schedules = _exact_tuple(
            self.permitted_movement_schedule_ids,
            item_type=str,
            code=code,
            field_path="permitted_movement_schedule_ids",
        )
        if not schedules:
            fail(code, "at least one movement schedule is required", "permitted_movement_schedule_ids")
        checked = tuple(
            _required_text(item, code=code, field_path="permitted_movement_schedule_ids")
            for item in schedules
        )
        if len(set(checked)) != len(checked):
            fail(code, "movement schedule IDs must be unique", "permitted_movement_schedule_ids")
        object.__setattr__(self, "permitted_movement_schedule_ids", checked)


@dataclass(frozen=True, slots=True)
class PositionMap:
    slots: tuple[PositionSlot, ...]

    def __post_init__(self) -> None:
        slots = _exact_tuple(
            self.slots,
            item_type=PositionSlot,
            code="POSITION_MAP_INVALID",
            field_path="slots",
        )
        identities = tuple(slot.position_id for slot in slots)
        if len(set(identities)) != len(identities):
            fail("POSITION_MAP_INVALID", "position IDs must be unique", "slots.position_id")
        coordinates = tuple(
            (
                slot.run_id,
                slot.greenhouse_compartment_id,
                slot.bench_id,
                slot.row,
                slot.column,
            )
            for slot in slots
        )
        if len(set(coordinates)) != len(coordinates):
            fail("POSITION_MAP_INVALID", "physical row/column positions must be unique", "slots")
        run_ordinals: dict[str, int] = {}
        ordinal_runs: dict[int, str] = {}
        for slot in slots:
            previous_ordinal = run_ordinals.setdefault(
                slot.run_id, slot.run_sequence_ordinal
            )
            previous_run = ordinal_runs.setdefault(
                slot.run_sequence_ordinal, slot.run_id
            )
            if previous_ordinal != slot.run_sequence_ordinal or previous_run != slot.run_id:
                fail(
                    "POSITION_MAP_INVALID",
                    "run IDs and sequence ordinals must be one-to-one",
                    "slots.run_sequence_ordinal",
                )


@dataclass(frozen=True, slots=True)
class ConfirmationDesignConfig:
    """A selected, later-run confirmation design separate from discovery."""

    schema_version: str
    evidence_label: EvidenceLabel
    population: AnalysisPopulation
    selected_candidate_ids: tuple[str, ...]
    water_ids: tuple[str, ...]
    runs: tuple[str, ...]
    reservoirs_per_water: int
    independent_plants_per_group_reservoir: int
    balanced_transformation_batches: tuple[str, ...]
    construct_level_unit: Literal["independently_transformed_plant"]
    water_treatment_unit: Literal["reservoir"]
    discovery_max_run_sequence_ordinal: int

    def __post_init__(self) -> None:
        code = "CONFIRMATION_DESIGN_INVALID"
        if type(self.schema_version) is not str or self.schema_version != "1.0":
            fail(code, "confirmation schema version is frozen", "schema_version")
        if type(self.evidence_label) is not EvidenceLabel or self.evidence_label is not EvidenceLabel.SYNTHETIC_ONLY:
            fail(code, "confirmation evidence must be synthetic_only", "evidence_label")
        if type(self.population) is not AnalysisPopulation or self.population is not AnalysisPopulation.COMPOSITE_ROOT:
            fail(code, "confirmation population must be composite_root", "population")
        for name in (
            "selected_candidate_ids",
            "water_ids",
            "runs",
            "balanced_transformation_batches",
        ):
            values = _exact_tuple(
                getattr(self, name),
                item_type=str,
                code=code,
                field_path=name,
            )
            if any(
                _required_text(item, code=code, field_path=name) != item
                for item in values
            ) or len(set(values)) != len(values):
                fail(code, "confirmation IDs must be unique", name)
        registered_candidates = tuple(f"C{number}" for number in range(1, 7))
        if not 1 <= len(self.selected_candidate_ids) <= 4 or tuple(
            candidate
            for candidate in registered_candidates
            if candidate in self.selected_candidate_ids
        ) != self.selected_candidate_ids:
            fail(
                code,
                "confirmation requires one to four registered candidates in order",
                "selected_candidate_ids",
            )
        if self.water_ids != REGISTERED_WATERS:
            fail(code, "confirmation waters and order are frozen", "water_ids")
        if len(self.runs) < 2:
            fail(code, "confirmation requires at least two later runs", "runs")
        if type(self.reservoirs_per_water) is not int or self.reservoirs_per_water != 6:
            fail(code, "confirmation requires exactly six loops per water", "reservoirs_per_water")
        if type(self.independent_plants_per_group_reservoir) is not int or self.independent_plants_per_group_reservoir not in (5, 6):
            fail(
                code,
                "confirmation cell size must be the exact integer five or six",
                "independent_plants_per_group_reservoir",
            )
        if self.balanced_transformation_batches != REGISTERED_BATCH_BLOCKS:
            fail(code, "confirmation batch blocks are frozen", "balanced_transformation_batches")
        if type(self.construct_level_unit) is not str or self.construct_level_unit != "independently_transformed_plant":
            fail(code, "confirmation construct unit is frozen", "construct_level_unit")
        if type(self.water_treatment_unit) is not str or self.water_treatment_unit != "reservoir":
            fail(code, "confirmation water unit is frozen", "water_treatment_unit")
        _positive_int(
            self.discovery_max_run_sequence_ordinal,
            code=code,
            field_path="discovery_max_run_sequence_ordinal",
        )

    @property
    def full_allocation_groups(self) -> tuple[str, ...]:
        return self.selected_candidate_ids + ("empty_vector",)

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "evidence_label": self.evidence_label.value,
            "population": self.population.value,
            "selected_candidate_ids": list(self.selected_candidate_ids),
            "water_ids": list(self.water_ids),
            "runs": list(self.runs),
            "reservoirs_per_water": self.reservoirs_per_water,
            "independent_plants_per_group_reservoir": self.independent_plants_per_group_reservoir,
            "balanced_transformation_batches": list(self.balanced_transformation_batches),
            "construct_level_unit": self.construct_level_unit,
            "water_treatment_unit": self.water_treatment_unit,
            "discovery_max_run_sequence_ordinal": self.discovery_max_run_sequence_ordinal,
        }


@dataclass(frozen=True, slots=True)
class Task3SeedChild:
    name: str
    entropy: int
    spawn_key: tuple[int, ...]
    pool_size: int

    def __post_init__(self) -> None:
        if type(self.name) is not str or self.name not in SEED_CHILD_NAMES:
            fail("RANDOMIZATION_INVALID", "seed child name is not registered", "seed_tree")
        _nonnegative_int(
            self.entropy, code="RANDOMIZATION_INVALID", field_path="seed_tree"
        )
        _exact_tuple(
            self.spawn_key,
            item_type=int,
            code="RANDOMIZATION_INVALID",
            field_path="seed_tree",
        )
        expected_index = SEED_CHILD_NAMES.index(self.name)
        if (
            self.spawn_key != (expected_index,)
            or type(self.pool_size) is not int
            or self.pool_size != SEED_POOL_SIZE
        ):
            fail("RANDOMIZATION_INVALID", "seed child metadata is inconsistent", "seed_tree")

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "entropy": self.entropy,
            "spawn_key": list(self.spawn_key),
            "pool_size": self.pool_size,
        }


@dataclass(frozen=True, slots=True)
class Task3SeedTree:
    """Task 3 seed metadata whose child sequence preserves literal spawn order."""

    entropy: int
    spawn_key: tuple[int, ...]
    pool_size: int
    children: tuple[Task3SeedChild, ...]

    def __post_init__(self) -> None:
        _nonnegative_int(
            self.entropy, code="RANDOMIZATION_INVALID", field_path="seed_tree"
        )
        if type(self.spawn_key) is not tuple or self.spawn_key != ():
            fail("RANDOMIZATION_INVALID", "root spawn key must be empty", "seed_tree")
        if type(self.pool_size) is not int or self.pool_size != SEED_POOL_SIZE:
            fail("RANDOMIZATION_INVALID", "root seed pool size is inconsistent", "seed_tree")
        _exact_tuple(
            self.children,
            item_type=Task3SeedChild,
            code="RANDOMIZATION_INVALID",
            field_path="seed_tree",
        )
        if tuple(child.name for child in self.children) != SEED_CHILD_NAMES:
            fail("RANDOMIZATION_INVALID", "seed children are not in literal order", "seed_tree")
        for child in self.children:
            child.__post_init__()
        if any(child.entropy != self.entropy for child in self.children):
            fail("RANDOMIZATION_INVALID", "seed entropy is inconsistent", "seed_tree")

    def to_dict(self) -> dict[str, object]:
        return {
            "algorithm": "numpy.random.SeedSequence+PCG64",
            "entropy": self.entropy,
            "spawn_key": list(self.spawn_key),
            "pool_size": self.pool_size,
            "children": [child.to_dict() for child in self.children],
        }


@dataclass(frozen=True, slots=True)
class AllocationRecord:
    allocation_id: str
    plant_id: str
    population: AnalysisPopulation
    group_id: str
    water_id: str
    run_id: str
    run_sequence_ordinal: int
    reservoir_id: str
    transformation_batch_block: str | None
    transformation_batch_id: str | None
    transformation_event_id: str | None
    pretreatment_canopy: float
    baseline_canopy_stratum: str
    greenhouse_compartment_id: str
    water_batch_id: str
    bench_id: str
    row: int
    column: int
    position_id: str
    spatial_gradient_profile_id: str
    movement_schedule_id: str
    blinded_treatment_code: str
    cohort_id: str
    evidence_label: EvidenceLabel

    def __post_init__(self) -> None:
        code = "ALLOCATION_RECORD_INVALID"
        for name in (
            "allocation_id",
            "plant_id",
            "group_id",
            "water_id",
            "run_id",
            "reservoir_id",
            "baseline_canopy_stratum",
            "greenhouse_compartment_id",
            "water_batch_id",
            "bench_id",
            "position_id",
            "spatial_gradient_profile_id",
            "movement_schedule_id",
            "blinded_treatment_code",
            "cohort_id",
        ):
            object.__setattr__(
                self,
                name,
                _required_text(getattr(self, name), code=code, field_path=name),
            )
        if type(self.population) is not AnalysisPopulation:
            fail(code, "population must be an AnalysisPopulation", "population")
        if type(self.evidence_label) is not EvidenceLabel:
            fail(code, "evidence label must be an EvidenceLabel", "evidence_label")
        if self.baseline_canopy_stratum not in REGISTERED_STRATA:
            fail(
                code,
                "allocation baseline canopy stratum is not registered",
                "baseline_canopy_stratum",
            )
        object.__setattr__(
            self,
            "pretreatment_canopy",
            _positive_float(
                self.pretreatment_canopy,
                code=code,
                field_path="pretreatment_canopy",
            ),
        )
        object.__setattr__(
            self,
            "run_sequence_ordinal",
            _positive_int(
                self.run_sequence_ordinal,
                code=code,
                field_path="run_sequence_ordinal",
            ),
        )
        object.__setattr__(self, "row", _positive_int(self.row, code=code, field_path="row"))
        object.__setattr__(
            self, "column", _positive_int(self.column, code=code, field_path="column")
        )
        for name in (
            "transformation_batch_block",
            "transformation_batch_id",
            "transformation_event_id",
        ):
            object.__setattr__(
                self,
                name,
                _optional_text(getattr(self, name), code=code, field_path=name),
            )
        if self.group_id in TRANSFORMED_GROUPS:
            if self.transformation_batch_block not in REGISTERED_BATCH_BLOCKS:
                fail(code, "transformed allocation requires a batch block", "transformation_batch_block")
            if self.transformation_batch_id is None:
                fail(code, "transformed allocation requires a physical batch", "transformation_batch_id")
        elif self.group_id in NONTRANSFORMED_GROUPS:
            if any(
                value is not None
                for value in (
                    self.transformation_batch_block,
                    self.transformation_batch_id,
                    self.transformation_event_id,
                )
            ):
                fail(code, "nontransformed allocation has a fictional event identity", "transformation_event_id")
        else:
            fail(code, "allocation group is not registered", "group_id")

    def to_dict(self) -> dict[str, object]:
        return _json_record(self)


@dataclass(frozen=True, slots=True)
class RandomizationManifest:
    schema_version: str
    model_version: str
    root_seed: int
    seed_tree: Task3SeedTree
    records: tuple[AllocationRecord, ...]
    config_sha256: str
    allocation_sha256: str
    input_sha256s: Mapping[str, str]
    evidence_label: EvidenceLabel

    def __post_init__(self) -> None:
        if self.schema_version != DESIGN_SCHEMA_VERSION or type(self.schema_version) is not str:
            fail("RANDOMIZATION_INVALID", "manifest schema version is frozen", "schema_version")
        if self.model_version != DESIGN_MODEL_VERSION or type(self.model_version) is not str:
            fail("RANDOMIZATION_INVALID", "manifest model version is frozen", "model_version")
        _nonnegative_int(
            self.root_seed, code="RANDOMIZATION_INVALID", field_path="root_seed"
        )
        if type(self.seed_tree) is not Task3SeedTree:
            fail("RANDOMIZATION_INVALID", "seed tree must be exact", "seed_tree")
        self.seed_tree.__post_init__()
        if self.seed_tree.entropy != self.root_seed:
            fail("RANDOMIZATION_INVALID", "seed tree entropy differs from root seed", "seed_tree")
        _exact_tuple(
            self.records,
            item_type=AllocationRecord,
            code="RANDOMIZATION_INVALID",
            field_path="records",
        )
        for record in self.records:
            record.__post_init__()
        if tuple(sorted(self.records, key=lambda record: record.allocation_id)) != self.records:
            fail("RANDOMIZATION_INVALID", "records must be allocation-ID ordered", "records")
        object.__setattr__(
            self,
            "input_sha256s",
            _freeze_string_map(
                self.input_sha256s,
                code="RANDOMIZATION_INVALID",
                field_path="input_sha256s",
            ),
        )
        expected_hash = sha256_bytes(
            canonical_json_bytes([record.to_dict() for record in self.records])
        )
        if self.allocation_sha256 != expected_hash:
            fail("RANDOMIZATION_INVALID", "allocation hash does not cover all records", "allocation_sha256")
        for name, digest in (
            ("config_sha256", self.config_sha256),
            ("allocation_sha256", self.allocation_sha256),
            *tuple(self.input_sha256s.items()),
        ):
            if len(digest) != 64 or any(character not in "0123456789abcdef" for character in digest):
                fail("RANDOMIZATION_INVALID", "hash must be lowercase SHA-256", name)
        if type(self.evidence_label) is not EvidenceLabel or self.evidence_label is not EvidenceLabel.SYNTHETIC_ONLY:
            fail("RANDOMIZATION_INVALID", "design evidence must be synthetic_only", "evidence_label")

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "model_version": self.model_version,
            "root_seed": self.root_seed,
            "seed_tree": self.seed_tree.to_dict(),
            "records": [record.to_dict() for record in self.records],
            "config_sha256": self.config_sha256,
            "allocation_sha256": self.allocation_sha256,
            "input_sha256s": dict(self.input_sha256s),
            "evidence_label": self.evidence_label.value,
        }

    def canonical_json_bytes(self) -> bytes:
        return canonical_json_bytes(self.to_dict())

    def canonical_json(self) -> str:
        return self.canonical_json_bytes().decode("utf-8")


@dataclass(frozen=True, slots=True)
class BlindingEscrowAuthority:
    """Private key material withheld with the manifest until unblinding."""

    secret_key: bytes = field(repr=False)

    def __post_init__(self) -> None:
        if (
            type(self.secret_key) is not bytes
            or len(self.secret_key) != 32
            or len(set(self.secret_key)) <= 1
        ):
            fail(
                "BLINDING_ESCROW_INVALID",
                "secret key must be exactly 32 primitive bytes",
                "secret_key",
            )


def generate_blinding_escrow_authority() -> BlindingEscrowAuthority:
    """Generate nondeterministic private key material for an escrow custodian."""

    while True:
        key = secrets.token_bytes(32)
        if len(set(key)) > 1:
            return BlindingEscrowAuthority(secret_key=key)


def _revalidate_blinding_escrow_authority(
    authority: BlindingEscrowAuthority,
) -> BlindingEscrowAuthority:
    if type(authority) is not BlindingEscrowAuthority:
        fail(
            "BLINDING_ESCROW_INVALID",
            "escrow authority must be exact",
            "escrow_authority",
        )
    return BlindingEscrowAuthority(secret_key=authority.secret_key)


@dataclass(frozen=True, slots=True)
class BlindedAllocationRecord:
    staff_allocation_code: str
    staff_specimen_code: str
    staff_location_code: str
    blinded_treatment_code: str

    def __post_init__(self) -> None:
        for name in self.__dataclass_fields__:
            value = _required_text(
                getattr(self, name),
                code="BLINDED_PROJECTION_INVALID",
                field_path=f"records.{name}",
            )
            if (
                not value.startswith("OPQ-")
                or len(value) != 4 + OPAQUE_CODE_LENGTH
                or any(character not in "0123456789ABCDEF" for character in value[4:])
            ):
                fail(
                    "BLINDED_PROJECTION_INVALID",
                    "staff code must be a code-owned opaque identifier",
                    f"records.{name}",
                )

    def to_dict(self) -> dict[str, object]:
        return {
            name: getattr(self, name)
            for name in self.__dataclass_fields__
        }


@dataclass(frozen=True, slots=True)
class BlindingEscrowRecord:
    """Private crosswalk row withheld from greenhouse staff until unblinding."""

    staff_allocation_code: str
    staff_specimen_code: str
    staff_location_code: str
    staff_treatment_code: str
    private_allocation_id: str
    private_plant_id: str
    private_position_id: str
    private_blinded_treatment_code: str

    def __post_init__(self) -> None:
        for name in self.__dataclass_fields__:
            value = _required_text(
                getattr(self, name),
                code="BLINDING_ESCROW_INVALID",
                field_path=f"crosswalk.{name}",
            )
            if name.startswith("staff_") and (
                not value.startswith("OPQ-")
                or len(value) != 4 + OPAQUE_CODE_LENGTH
                or any(
                    character not in "0123456789ABCDEF"
                    for character in value[4:]
                )
            ):
                fail(
                    "BLINDING_ESCROW_INVALID",
                    "crosswalk staff code is not opaque",
                    f"crosswalk.{name}",
                )


@dataclass(frozen=True, slots=True)
class BlindedProjection:
    schema_version: str
    model_version: str
    manifest_sha256: str
    records: tuple[BlindedAllocationRecord, ...]
    projection_sha256: str
    evidence_label: EvidenceLabel

    def __post_init__(self) -> None:
        code = "BLINDED_PROJECTION_INVALID"
        if type(self.schema_version) is not str or self.schema_version != DESIGN_SCHEMA_VERSION:
            fail(code, "blinded schema version is frozen", "schema_version")
        if type(self.model_version) is not str or self.model_version != BLINDED_MODEL_VERSION:
            fail(code, "blinded model version is frozen", "model_version")
        for name in ("manifest_sha256", "projection_sha256"):
            digest = getattr(self, name)
            if type(digest) is not str or len(digest) != 64 or any(
                character not in "0123456789abcdef" for character in digest
            ):
                fail(code, "hash must be lowercase SHA-256", name)
        rows = _exact_tuple(
            self.records,
            item_type=BlindedAllocationRecord,
            code=code,
            field_path="records",
        )
        for record in rows:
            record.__post_init__()
        for name in BlindedAllocationRecord.__dataclass_fields__:
            values = tuple(getattr(record, name) for record in rows)
            if len(set(values)) != len(values):
                fail(code, "opaque staff identifiers must be unique", f"records.{name}")
        expected_hash = sha256_bytes(
            canonical_json_bytes([record.to_dict() for record in rows])
        )
        if self.projection_sha256 != expected_hash:
            fail(code, "projection hash does not cover all public records", "projection_sha256")
        if type(self.evidence_label) is not EvidenceLabel or self.evidence_label is not EvidenceLabel.SYNTHETIC_ONLY:
            fail(code, "blinded evidence must be synthetic_only", "evidence_label")

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "model_version": self.model_version,
            "manifest_sha256": self.manifest_sha256,
            "records": [record.to_dict() for record in self.records],
            "projection_sha256": self.projection_sha256,
            "evidence_label": self.evidence_label.value,
        }

    def canonical_json_bytes(self) -> bytes:
        return canonical_json_bytes(self.to_dict())


def _opaque_digest(
    authority: BlindingEscrowAuthority,
    namespace: str,
    private_identity: str,
) -> str:
    digest = hmac.new(
        authority.secret_key,
        canonical_json_bytes(
            {"namespace": namespace, "private_identity": private_identity}
        ),
        hashlib.sha256,
    ).hexdigest()
    return digest


def _opaque_code(
    authority: BlindingEscrowAuthority,
    namespace: str,
    private_identity: str,
) -> str:
    return "OPQ-" + _opaque_digest(
        authority, namespace, private_identity
    )[:OPAQUE_CODE_LENGTH].upper()


def blinded_projection(
    manifest: RandomizationManifest,
    *,
    escrow_authority: BlindingEscrowAuthority,
) -> BlindedProjection:
    """Create staff rows; manifest, root seed, key, and crosswalk remain escrowed."""

    manifest = revalidate_randomization_manifest(manifest)
    authority = _revalidate_blinding_escrow_authority(escrow_authority)
    ranked_records = sorted(
        manifest.records,
        key=lambda record: (
            _opaque_digest(authority, "staff_order", record.allocation_id),
            record.allocation_id,
        ),
    )
    records = tuple(
        BlindedAllocationRecord(
            staff_allocation_code=_opaque_code(authority, "allocation", record.allocation_id),
            staff_specimen_code=_opaque_code(authority, "specimen", record.plant_id),
            staff_location_code=_opaque_code(authority, "location", record.position_id),
            blinded_treatment_code=_opaque_code(authority, "treatment", record.blinded_treatment_code),
        )
        for record in ranked_records
    )
    return BlindedProjection(
        schema_version=DESIGN_SCHEMA_VERSION,
        model_version=BLINDED_MODEL_VERSION,
        manifest_sha256=sha256_bytes(manifest.canonical_json_bytes()),
        records=records,
        projection_sha256=sha256_bytes(
            canonical_json_bytes([record.to_dict() for record in records])
        ),
        evidence_label=EvidenceLabel.SYNTHETIC_ONLY,
    )


def revalidate_blinded_projection(
    projection: BlindedProjection,
    *,
    manifest: RandomizationManifest,
    escrow_authority: BlindingEscrowAuthority,
) -> BlindedProjection:
    """Reconstruct the public projection and bind it to its private manifest authority."""

    if type(projection) is not BlindedProjection:
        fail("BLINDED_PROJECTION_INVALID", "projection must be exact", "projection")
    rows = _exact_tuple(
        projection.records,
        item_type=BlindedAllocationRecord,
        code="BLINDED_PROJECTION_INVALID",
        field_path="records",
    )
    rebuilt = BlindedProjection(
        schema_version=projection.schema_version,
        model_version=projection.model_version,
        manifest_sha256=projection.manifest_sha256,
        records=tuple(
            BlindedAllocationRecord(**record.to_dict()) for record in rows
        ),
        projection_sha256=projection.projection_sha256,
        evidence_label=projection.evidence_label,
    )
    expected = blinded_projection(
        revalidate_randomization_manifest(manifest),
        escrow_authority=_revalidate_blinding_escrow_authority(escrow_authority),
    )
    if rebuilt != expected:
        fail(
            "BLINDED_PROJECTION_INVALID",
            "projection is stale or does not match manifest authority",
            "projection",
        )
    return rebuilt


def blinding_escrow_crosswalk(
    manifest: RandomizationManifest,
    *,
    escrow_authority: BlindingEscrowAuthority,
) -> tuple[BlindingEscrowRecord, ...]:
    """Regenerate the private staff-allocation crosswalk for escrow custodians."""

    checked_manifest = revalidate_randomization_manifest(manifest)
    authority = _revalidate_blinding_escrow_authority(escrow_authority)
    ranked_records = sorted(
        checked_manifest.records,
        key=lambda record: (
            _opaque_digest(authority, "staff_order", record.allocation_id),
            record.allocation_id,
        ),
    )
    return tuple(
        BlindingEscrowRecord(
            staff_allocation_code=_opaque_code(
                authority, "allocation", record.allocation_id
            ),
            staff_specimen_code=_opaque_code(
                authority, "specimen", record.plant_id
            ),
            staff_location_code=_opaque_code(
                authority, "location", record.position_id
            ),
            staff_treatment_code=_opaque_code(
                authority, "treatment", record.blinded_treatment_code
            ),
            private_allocation_id=record.allocation_id,
            private_plant_id=record.plant_id,
            private_position_id=record.position_id,
            private_blinded_treatment_code=record.blinded_treatment_code,
        )
        for record in ranked_records
    )


@dataclass(frozen=True, slots=True)
class ExperimentalUnitSpec:
    population: AnalysisPopulation
    requested_water_unit: str = "reservoir"
    expected_groups: tuple[str, ...] = ()
    expected_water_ids: tuple[str, ...] = ()
    expected_run_ids: tuple[str, ...] = ()
    expected_reservoirs_per_water_run: int | None = None
    expected_reservoirs_per_water: int | None = None
    expected_plants_per_group_reservoir: int | None = None
    minimum_run_sequence_ordinal: int | None = None
    permitted_position_ids: tuple[str, ...] = ()
    position_slots: tuple[PositionSlot, ...] = ()

    def __post_init__(self) -> None:
        if type(self.population) is not AnalysisPopulation:
            fail("DESIGN_INPUT_INVALID", "population must be an AnalysisPopulation", "spec.population")
        _required_text(
            self.requested_water_unit,
            code="DESIGN_INPUT_INVALID",
            field_path="spec.requested_water_unit",
        )
        for name in ("expected_groups", "expected_water_ids", "expected_run_ids", "permitted_position_ids"):
            values = _exact_tuple(
                getattr(self, name),
                item_type=str,
                code="DESIGN_INPUT_INVALID",
                field_path=f"spec.{name}",
            )
            if len(set(values)) != len(values):
                fail("DESIGN_INPUT_INVALID", "expected IDs must be unique", f"spec.{name}")
        _exact_tuple(
            self.position_slots,
            item_type=PositionSlot,
            code="DESIGN_INPUT_INVALID",
            field_path="spec.position_slots",
        )
        if self.position_slots and tuple(
            sorted(slot.position_id for slot in self.position_slots)
        ) != tuple(sorted(self.permitted_position_ids)):
            fail(
                "DESIGN_INPUT_INVALID",
                "position slot identities must match permitted position IDs",
                "spec.position_slots",
            )
        for name in (
            "expected_reservoirs_per_water_run",
            "expected_reservoirs_per_water",
            "expected_plants_per_group_reservoir",
            "minimum_run_sequence_ordinal",
        ):
            value = getattr(self, name)
            if value is not None:
                _positive_int(value, code="DESIGN_INPUT_INVALID", field_path=f"spec.{name}")

    @classmethod
    def from_design(
        cls, config: Paper1DesignConfig, *, position_map: PositionMap
    ) -> "ExperimentalUnitSpec":
        checked = _revalidate_design(config)
        if type(position_map) is not PositionMap:
            fail("DESIGN_INPUT_INVALID", "position_map must be a PositionMap", "position_map")
        return cls(
            population=checked.population,
            expected_groups=checked.full_allocation_groups,
            expected_water_ids=tuple(water.water_id for water in checked.water_conditions),
            expected_run_ids=checked.runs,
            expected_reservoirs_per_water_run=checked.reservoirs_per_water_run,
            expected_plants_per_group_reservoir=checked.independent_plants_per_group_reservoir,
            permitted_position_ids=tuple(sorted(slot.position_id for slot in position_map.slots)),
            position_slots=tuple(
                sorted(position_map.slots, key=lambda slot: slot.position_id)
            ),
        )

    @classmethod
    def from_confirmation_design(
        cls, config: ConfirmationDesignConfig, *, position_map: PositionMap
    ) -> "ExperimentalUnitSpec":
        checked = revalidate_confirmation_design(config)
        checked_map = revalidate_position_map(position_map)
        return cls(
            population=checked.population,
            expected_groups=checked.full_allocation_groups,
            expected_water_ids=checked.water_ids,
            expected_run_ids=checked.runs,
            expected_reservoirs_per_water=checked.reservoirs_per_water,
            expected_plants_per_group_reservoir=checked.independent_plants_per_group_reservoir,
            minimum_run_sequence_ordinal=(
                checked.discovery_max_run_sequence_ordinal + 1
            ),
            permitted_position_ids=tuple(
                sorted(slot.position_id for slot in checked_map.slots)
            ),
            position_slots=tuple(
                sorted(checked_map.slots, key=lambda slot: slot.position_id)
            ),
        )


@dataclass(frozen=True, slots=True)
class CohortIdentitySet:
    cohort_id: str
    plant_ids: tuple[str, ...]
    transformation_batch_ids: tuple[str, ...]
    reservoir_ids: tuple[str, ...]
    water_batch_ids: tuple[str, ...]
    run_ids: tuple[str, ...]
    transformation_event_ids: tuple[str, ...] = ()
    run_sequence_ordinals: tuple[int, ...] = ()

    def __post_init__(self) -> None:
        _required_text(self.cohort_id, code="DESIGN_INPUT_INVALID", field_path="cohort_id")
        for name in (
            "plant_ids",
            "transformation_batch_ids",
            "reservoir_ids",
            "water_batch_ids",
            "run_ids",
            "transformation_event_ids",
        ):
            values = _exact_tuple(
                getattr(self, name),
                item_type=str,
                code="DESIGN_INPUT_INVALID",
                field_path=name,
            )
            checked = tuple(
                _required_text(item, code="DESIGN_INPUT_INVALID", field_path=name)
                for item in values
            )
            if len(set(checked)) != len(checked):
                fail("DESIGN_INPUT_INVALID", "cohort identities must be unique", name)
        ordinals = _exact_tuple(
            self.run_sequence_ordinals,
            item_type=int,
            code="DESIGN_INPUT_INVALID",
            field_path="run_sequence_ordinals",
        )
        if ordinals:
            if len(ordinals) != len(self.run_ids):
                fail(
                    "DESIGN_INPUT_INVALID",
                    "run IDs and ordinals must have equal length",
                    "run_sequence_ordinals",
                )
            for ordinal in ordinals:
                _positive_int(
                    ordinal,
                    code="DESIGN_INPUT_INVALID",
                    field_path="run_sequence_ordinals",
                )
            if len(set(ordinals)) != len(ordinals):
                fail(
                    "DESIGN_INPUT_INVALID",
                    "run ordinals must be unique",
                    "run_sequence_ordinals",
                )


def revalidate_cohort_identity_set(
    cohort: CohortIdentitySet,
) -> CohortIdentitySet:
    """Canonically reconstruct one exact cohort identity record."""

    if type(cohort) is not CohortIdentitySet:
        fail(
            "COHORT_IDENTITY_INVALID",
            "cohort must be an exact CohortIdentitySet",
            "cohort",
        )
    return CohortIdentitySet(
        cohort_id=cohort.cohort_id,
        plant_ids=tuple(cohort.plant_ids),
        transformation_batch_ids=tuple(cohort.transformation_batch_ids),
        reservoir_ids=tuple(cohort.reservoir_ids),
        water_batch_ids=tuple(cohort.water_batch_ids),
        run_ids=tuple(cohort.run_ids),
        transformation_event_ids=tuple(cohort.transformation_event_ids),
        run_sequence_ordinals=tuple(cohort.run_sequence_ordinals),
    )


@dataclass(frozen=True, slots=True)
class ObservationIdentityRecord:
    observation_id: str
    plant_id: str
    subsample_id: str
    technical_read_id: str
    timepoint_id: str

    def __post_init__(self) -> None:
        for name in self.__dataclass_fields__:
            _required_text(
                getattr(self, name),
                code="OBSERVATION_IDENTITY_INVALID",
                field_path=name,
            )


@dataclass(frozen=True, slots=True)
class ExperimentalUnitAudit:
    biological_n: int
    water_treatment_n: int
    observation_n: int
    counts: Mapping[str, object]
    checks: Mapping[str, bool]
    evidence_label: EvidenceLabel

    def __post_init__(self) -> None:
        for name in ("biological_n", "water_treatment_n", "observation_n"):
            value = getattr(self, name)
            if type(value) is not int or value < 0 or value > MAX_INTEROPERABLE_INTEGER:
                fail("EXPERIMENTAL_UNIT_INVALID", "audit counts must be exact nonnegative integers", name)
        if type(self.counts) not in (dict, MappingProxyType) or type(self.checks) not in (dict, MappingProxyType):
            fail("EXPERIMENTAL_UNIT_INVALID", "audit summaries must be exact mappings", "audit")
        if type(self.evidence_label) is not EvidenceLabel or self.evidence_label is not EvidenceLabel.SYNTHETIC_ONLY:
            fail("EXPERIMENTAL_UNIT_INVALID", "audit evidence must be synthetic_only", "evidence_label")
        object.__setattr__(self, "counts", _deep_freeze(self.counts))
        object.__setattr__(self, "checks", _deep_freeze(self.checks))


@dataclass(frozen=True, slots=True)
class RandomizationInputs:
    baseline_roster: BaselineRoster
    position_map: PositionMap
    consumed_anchors: tuple[str, ...]
    source_sha256s: Mapping[str, str]

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "source_sha256s",
            _freeze_string_map(
                self.source_sha256s,
                code="RANDOMIZATION_FIXTURE_INVALID",
                field_path="source_sha256s",
            ),
        )


class _UniqueKeyLoader(yaml.SafeLoader):
    pass


def _construct_unique_mapping(loader: _UniqueKeyLoader, node: yaml.MappingNode, deep: bool = False) -> dict[object, object]:
    mapping: dict[object, object] = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if type(key) is not str:
            raise ValueError("YAML mapping keys must be primitive strings")
        if key in mapping:
            raise ValueError(f"duplicate YAML key: {key}")
        mapping[key] = loader.construct_object(value_node, deep=deep)
    return mapping


_UniqueKeyLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
    _construct_unique_mapping,
)


def _preflight_fixture_yaml(text: str) -> None:
    """Reject graph features and resource-exhaustion inputs before construction."""

    node_count = 0
    depth = 0
    try:
        for event in yaml.parse(text, Loader=yaml.SafeLoader):
            if isinstance(event, AliasEvent) or getattr(event, "anchor", None) is not None:
                fail(
                    "RANDOMIZATION_FIXTURE_INVALID",
                    "YAML aliases and anchors are prohibited",
                    "fixture",
                )
            if isinstance(event, (ScalarEvent, SequenceStartEvent, MappingStartEvent)):
                node_count += 1
                if node_count > FIXTURE_MAX_NODES:
                    fail(
                        "RANDOMIZATION_FIXTURE_INVALID",
                        "YAML fixture exceeds the node budget",
                        "fixture",
                    )
            if isinstance(event, CollectionStartEvent):
                depth += 1
                if depth > FIXTURE_MAX_DEPTH:
                    fail(
                        "RANDOMIZATION_FIXTURE_INVALID",
                        "YAML fixture exceeds the nesting-depth budget",
                        "fixture",
                    )
            elif isinstance(event, CollectionEndEvent):
                depth -= 1
            tag = getattr(event, "tag", None)
            if tag is not None and not tag.startswith("tag:yaml.org,2002:"):
                fail(
                    "RANDOMIZATION_FIXTURE_INVALID",
                    "YAML fixture uses a prohibited tag",
                    "fixture",
                )
    except AlmondLabError:
        raise
    except (yaml.YAMLError, RecursionError, TypeError, ValueError, OverflowError) as error:
        fail(
            "RANDOMIZATION_FIXTURE_INVALID",
            "randomization fixture YAML is malformed",
            "fixture",
            {"cause_type": type(error).__name__},
        )


def _mapping_keys(
    value: object, expected: set[str], *, code: str, field_path: str
) -> Mapping[str, object]:
    if type(value) is not dict or any(type(key) is not str for key in value):
        fail(code, "value must be a string-keyed mapping", field_path)
    actual = set(value)
    if actual != expected:
        fail(
            code,
            "mapping keys do not match the frozen schema",
            field_path,
            {"missing": sorted(expected - actual), "extra": sorted(actual - expected)},
        )
    return value


_BASELINE_FIELDS = {
    "plant_id",
    "group_id",
    "pretreatment_canopy",
    "baseline_canopy_stratum",
    "transformation_batch_block",
    "transformation_batch_id",
    "transformation_event_id",
    "cohort_id",
}
_POSITION_FIELDS = {
    "position_id",
    "run_id",
    "run_sequence_ordinal",
    "water_id",
    "reservoir_id",
    "water_batch_id",
    "greenhouse_compartment_id",
    "bench_id",
    "row",
    "column",
    "spatial_gradient_profile_id",
    "permitted_movement_schedule_ids",
    "cohort_id",
}
_FIXTURE_ROOT_FIELDS = {
    "schema_version",
    "evidence_label",
    "cohort_id",
    "oracles",
    "baseline_roster",
    "position_map",
}
_FIXTURE_ORACLES = {
    "groups": 9,
    "runs": 2,
    "waters": 2,
    "reservoirs": 16,
    "plants_per_reservoir": 45,
    "plants_per_group_reservoir": 5,
    "plants_per_group": 80,
    "total_plants": 720,
}


def load_randomization_fixture(path: str | Path) -> RandomizationInputs:
    """Load the literal physical Paper 1 roster and greenhouse position map."""

    source = Path(path)
    try:
        raw = source.read_bytes()
        text = raw.decode("utf-8")
        _preflight_fixture_yaml(text)
        payload = yaml.load(text, Loader=_UniqueKeyLoader)
    except AlmondLabError:
        raise
    except (
        OSError,
        UnicodeError,
        yaml.YAMLError,
        RecursionError,
        TypeError,
        ValueError,
        OverflowError,
    ) as error:
        fail(
            "RANDOMIZATION_FIXTURE_INVALID",
            "randomization fixture could not be loaded",
            "fixture",
            {"cause_type": type(error).__name__},
        )
    root = _mapping_keys(
        payload,
        _FIXTURE_ROOT_FIELDS,
        code="RANDOMIZATION_FIXTURE_INVALID",
        field_path="root",
    )
    if root["schema_version"] != "1.0":
        fail("RANDOMIZATION_FIXTURE_INVALID", "fixture schema version is frozen", "schema_version")
    if root["evidence_label"] != EvidenceLabel.SYNTHETIC_ONLY.value:
        fail("RANDOMIZATION_FIXTURE_INVALID", "fixture evidence label is frozen", "evidence_label")
    if root["cohort_id"] != "discovery":
        fail("RANDOMIZATION_FIXTURE_INVALID", "fixture cohort is frozen", "cohort_id")
    oracle = _mapping_keys(
        root["oracles"],
        set(_FIXTURE_ORACLES),
        code="RANDOMIZATION_FIXTURE_INVALID",
        field_path="oracles",
    )
    if dict(oracle) != _FIXTURE_ORACLES:
        fail("RANDOMIZATION_FIXTURE_INVALID", "fixture count oracles are frozen", "oracles")
    raw_plants = root["baseline_roster"]
    raw_slots = root["position_map"]
    if type(raw_plants) is not list or type(raw_slots) is not list:
        fail("RANDOMIZATION_FIXTURE_INVALID", "roster and positions must be YAML lists", "root")
    plants: list[BaselinePlant] = []
    for index, item in enumerate(raw_plants):
        values = _mapping_keys(
            item,
            _BASELINE_FIELDS,
            code="RANDOMIZATION_FIXTURE_INVALID",
            field_path=f"baseline_roster.{index}",
        )
        plants.append(BaselinePlant(**dict(values)))  # type: ignore[arg-type]
    slots: list[PositionSlot] = []
    for index, item in enumerate(raw_slots):
        values = dict(
            _mapping_keys(
                item,
                _POSITION_FIELDS,
                code="RANDOMIZATION_FIXTURE_INVALID",
                field_path=f"position_map.{index}",
            )
        )
        schedules = values["permitted_movement_schedule_ids"]
        if type(schedules) is not list:
            fail(
                "RANDOMIZATION_FIXTURE_INVALID",
                "movement schedules must be a YAML list",
                f"position_map.{index}.permitted_movement_schedule_ids",
            )
        values["permitted_movement_schedule_ids"] = tuple(schedules)
        slots.append(PositionSlot(**values))  # type: ignore[arg-type]
    roster = BaselineRoster(tuple(plants))
    position_map = PositionMap(tuple(slots))
    if len(roster.plants) != _FIXTURE_ORACLES["total_plants"]:
        fail("RANDOMIZATION_FIXTURE_INVALID", "roster count does not match oracle", "baseline_roster")
    if len(position_map.slots) != _FIXTURE_ORACLES["total_plants"]:
        fail("RANDOMIZATION_FIXTURE_INVALID", "position count does not match oracle", "position_map")
    roster_marker = b"baseline_roster:\n"
    position_marker = b"position_map:\n"
    roster_start = raw.find(roster_marker)
    position_start = raw.find(position_marker)
    if roster_start < 0 or position_start <= roster_start:
        fail("RANDOMIZATION_FIXTURE_INVALID", "fixture section anchors are missing", "fixture")
    return RandomizationInputs(
        baseline_roster=roster,
        position_map=position_map,
        consumed_anchors=(
            "schema_version",
            "evidence_label",
            "cohort_id",
            "oracles",
            "baseline_roster",
            "position_map",
        ),
        source_sha256s={
            "paper1_small": sha256_bytes(raw),
            "baseline_roster_raw": sha256_bytes(raw[roster_start:position_start]),
            "position_map_raw": sha256_bytes(raw[position_start:]),
        },
    )


def _revalidate_design(config: Paper1DesignConfig) -> Paper1DesignConfig:
    if type(config) is not Paper1DesignConfig:
        fail("DESIGN_CONFIG_INVALID", "config must be a Paper1DesignConfig", "config")
    try:
        return Paper1DesignConfig.model_validate(config.model_dump(mode="python"))
    except (ValidationError, TypeError, ValueError) as error:
        fail(
            "DESIGN_CONFIG_INVALID",
            "Paper 1 design failed strict boundary revalidation",
            "config",
            {"cause_type": type(error).__name__},
        )


def revalidate_confirmation_design(
    config: ConfirmationDesignConfig,
) -> ConfirmationDesignConfig:
    """Canonically reconstruct an exact confirmation configuration."""

    if type(config) is not ConfirmationDesignConfig:
        fail(
            "CONFIRMATION_DESIGN_INVALID",
            "config must be an exact ConfirmationDesignConfig",
            "config",
        )
    return ConfirmationDesignConfig(
        schema_version=config.schema_version,
        evidence_label=config.evidence_label,
        population=config.population,
        selected_candidate_ids=tuple(config.selected_candidate_ids),
        water_ids=tuple(config.water_ids),
        runs=tuple(config.runs),
        reservoirs_per_water=config.reservoirs_per_water,
        independent_plants_per_group_reservoir=(
            config.independent_plants_per_group_reservoir
        ),
        balanced_transformation_batches=tuple(
            config.balanced_transformation_batches
        ),
        construct_level_unit=config.construct_level_unit,
        water_treatment_unit=config.water_treatment_unit,
        discovery_max_run_sequence_ordinal=(
            config.discovery_max_run_sequence_ordinal
        ),
    )


def _baseline_payload(plant: BaselinePlant) -> dict[str, object]:
    return {
        "plant_id": plant.plant_id,
        "group_id": plant.group_id,
        "pretreatment_canopy": plant.pretreatment_canopy,
        "baseline_canopy_stratum": plant.baseline_canopy_stratum,
        "transformation_batch_block": plant.transformation_batch_block,
        "transformation_batch_id": plant.transformation_batch_id,
        "transformation_event_id": plant.transformation_event_id,
        "cohort_id": plant.cohort_id,
    }


def _position_payload(slot: PositionSlot) -> dict[str, object]:
    return {
        "position_id": slot.position_id,
        "run_id": slot.run_id,
        "run_sequence_ordinal": slot.run_sequence_ordinal,
        "water_id": slot.water_id,
        "reservoir_id": slot.reservoir_id,
        "water_batch_id": slot.water_batch_id,
        "greenhouse_compartment_id": slot.greenhouse_compartment_id,
        "bench_id": slot.bench_id,
        "row": slot.row,
        "column": slot.column,
        "spatial_gradient_profile_id": slot.spatial_gradient_profile_id,
        "permitted_movement_schedule_ids": list(slot.permitted_movement_schedule_ids),
        "cohort_id": slot.cohort_id,
    }


def revalidate_baseline_roster(roster: BaselineRoster) -> BaselineRoster:
    """Reconstruct a roster and every plant through exact public boundaries."""

    if type(roster) is not BaselineRoster:
        fail("ROSTER_INVALID", "roster must be an exact BaselineRoster", "baseline_roster")
    plants = _exact_tuple(
        roster.plants,
        item_type=BaselinePlant,
        code="ROSTER_INVALID",
        field_path="plants",
    )
    return BaselineRoster(
        tuple(BaselinePlant(**_baseline_payload(plant)) for plant in plants)
    )


def revalidate_position_map(position_map: PositionMap) -> PositionMap:
    """Reconstruct a position map and every physical slot exactly."""

    if type(position_map) is not PositionMap:
        fail(
            "POSITION_MAP_INVALID",
            "position map must be an exact PositionMap",
            "position_map",
        )
    slots = _exact_tuple(
        position_map.slots,
        item_type=PositionSlot,
        code="POSITION_MAP_INVALID",
        field_path="slots",
    )
    return PositionMap(
        tuple(
            PositionSlot(
                **{
                    **_position_payload(slot),
                    "permitted_movement_schedule_ids": tuple(
                        slot.permitted_movement_schedule_ids
                    ),
                }
            )
            for slot in slots
        )
    )


def _reconstruct_allocation_record(record: AllocationRecord) -> AllocationRecord:
    if type(record) is not AllocationRecord:
        fail(
            "ALLOCATION_RECORD_INVALID",
            "record must be an exact AllocationRecord",
            "records",
        )
    values = record.to_dict()
    values["population"] = record.population
    values["evidence_label"] = record.evidence_label
    return AllocationRecord(**values)  # type: ignore[arg-type]


def revalidate_randomization_manifest(
    manifest: RandomizationManifest,
) -> RandomizationManifest:
    """Canonically reconstruct a complete manifest, seed tree, and records."""

    if type(manifest) is not RandomizationManifest:
        fail(
            "RANDOMIZATION_INVALID",
            "manifest must be an exact RandomizationManifest",
            "manifest",
        )
    tree = manifest.seed_tree
    if type(tree) is not Task3SeedTree:
        fail("RANDOMIZATION_INVALID", "seed tree must be exact", "seed_tree")
    children = _exact_tuple(
        tree.children,
        item_type=Task3SeedChild,
        code="RANDOMIZATION_INVALID",
        field_path="seed_tree",
    )
    rebuilt_tree = Task3SeedTree(
        entropy=tree.entropy,
        spawn_key=tuple(tree.spawn_key),
        pool_size=tree.pool_size,
        children=tuple(
            Task3SeedChild(
                name=child.name,
                entropy=child.entropy,
                spawn_key=tuple(child.spawn_key),
                pool_size=child.pool_size,
            )
            for child in children
        ),
    )
    records = _exact_tuple(
        manifest.records,
        item_type=AllocationRecord,
        code="RANDOMIZATION_INVALID",
        field_path="records",
    )
    return RandomizationManifest(
        schema_version=manifest.schema_version,
        model_version=manifest.model_version,
        root_seed=manifest.root_seed,
        seed_tree=rebuilt_tree,
        records=tuple(_reconstruct_allocation_record(record) for record in records),
        config_sha256=manifest.config_sha256,
        allocation_sha256=manifest.allocation_sha256,
        input_sha256s=dict(manifest.input_sha256s),
        evidence_label=manifest.evidence_label,
    )


DesignConfig = Paper1DesignConfig | ConfirmationDesignConfig


def _design_water_ids(config: DesignConfig) -> tuple[str, ...]:
    if type(config) is Paper1DesignConfig:
        return tuple(water.water_id for water in config.water_conditions)
    return config.water_ids


def _validate_randomization_inputs(
    config: DesignConfig,
    baseline_roster: BaselineRoster,
    position_map: PositionMap,
) -> tuple[
    dict[str, list[BaselinePlant]],
    dict[tuple[str, str, str], list[PositionSlot]],
]:
    water_ids = _design_water_ids(config)
    if type(config) is Paper1DesignConfig:
        expected_loop_count = (
            len(config.runs) * len(water_ids) * config.reservoirs_per_water_run
        )
    else:
        expected_loop_count = len(water_ids) * config.reservoirs_per_water
    expected_total = len(config.full_allocation_groups) * expected_loop_count * config.independent_plants_per_group_reservoir
    if len(baseline_roster.plants) != expected_total:
        fail("ROSTER_INVALID", "roster has wrong physical plant capacity", "baseline_roster.plants")
    if len(position_map.slots) != expected_total:
        fail("POSITION_MAP_INVALID", "position map has wrong physical capacity", "position_map.slots")
    plants_by_group: dict[str, list[BaselinePlant]] = defaultdict(list)
    for plant in baseline_roster.plants:
        plants_by_group[plant.group_id].append(plant)
    expected_per_group = (
        expected_loop_count * config.independent_plants_per_group_reservoir
    )
    if set(plants_by_group) != set(config.full_allocation_groups) or any(
        len(plants_by_group[group]) != expected_per_group
        for group in config.full_allocation_groups
    ):
        fail("ROSTER_INVALID", "roster group capacities do not match design", "baseline_roster.plants")
    physical_batch_owners: dict[str, tuple[str, str]] = {}
    for plant in baseline_roster.plants:
        if plant.transformation_batch_id is None:
            continue
        assert plant.transformation_batch_block is not None
        owner = (plant.group_id, plant.transformation_batch_block)
        previous = physical_batch_owners.setdefault(
            plant.transformation_batch_id, owner
        )
        if previous != owner:
            fail(
                "ROSTER_INVALID",
                "physical transformation batch IDs must be globally unique",
                "baseline_roster.plants.transformation_batch_id",
            )
    for group in config.full_allocation_groups:
        plants = plants_by_group[group]
        if len({plant.cohort_id for plant in plants}) != 1:
            fail("ROSTER_INVALID", "one allocation cannot mix cohort IDs", "baseline_roster.plants.cohort_id")
        expected_per_stratum = expected_per_group // 2
        strata = Counter(plant.baseline_canopy_stratum for plant in plants)
        if strata != Counter(
            {
                "lower_canopy": expected_per_stratum,
                "upper_canopy": expected_per_stratum,
            }
        ):
            fail("ROSTER_INVALID", "each group requires balanced physical canopy strata", "baseline_roster.plants.baseline_canopy_stratum")
        if group in TRANSFORMED_GROUPS:
            joint = Counter(
                (plant.transformation_batch_block, plant.baseline_canopy_stratum)
                for plant in plants
            )
            expected_joint = Counter(
                {
                    (block, stratum): expected_per_group // 4
                    for block in REGISTERED_BATCH_BLOCKS
                    for stratum in REGISTERED_STRATA
                }
            )
            if joint != expected_joint:
                fail("ROSTER_INVALID", "physical batch/stratum crossing lacks capacity", "baseline_roster.plants")
            batch_to_group_block = {
                (plant.transformation_batch_id, plant.transformation_batch_block)
                for plant in plants
            }
            if len(batch_to_group_block) != 2:
                fail("ROSTER_INVALID", "each transformed group requires two physical batches", "baseline_roster.plants.transformation_batch_id")
    expected_runs = set(config.runs)
    expected_waters = set(water_ids)
    cells: dict[tuple[str, str, str], list[PositionSlot]] = defaultdict(list)
    for slot in position_map.slots:
        if slot.run_id not in expected_runs or slot.water_id not in expected_waters:
            fail("POSITION_MAP_INVALID", "slot references an unregistered run or water", "position_map.slots")
        cells[(slot.run_id, slot.water_id, slot.reservoir_id)].append(slot)
    for slots in cells.values():
        if len({slot.water_batch_id for slot in slots}) != 1:
            fail(
                "POSITION_MAP_INVALID",
                "one reservoir loop cannot be relabeled by position",
                "position_map.slots.water_batch_id",
            )
    expected_slots_per_loop = (
        len(config.full_allocation_groups)
        * config.independent_plants_per_group_reservoir
    )
    if len(cells) != expected_loop_count or any(
        len(slots) != expected_slots_per_loop for slots in cells.values()
    ):
        fail("POSITION_MAP_INVALID", "position map loop capacity is wrong", "position_map.slots")
    if type(config) is Paper1DesignConfig:
        for run_id in config.runs:
            for water_id in water_ids:
                reservoirs = {key[2] for key in cells if key[:2] == (run_id, water_id)}
                if len(reservoirs) != config.reservoirs_per_water_run:
                    fail("POSITION_MAP_INVALID", "run/water reservoir capacity is wrong", "position_map.slots.reservoir_id")
    else:
        if {slot.run_id for slot in position_map.slots} != expected_runs:
            fail("POSITION_MAP_INVALID", "every confirmation run must own a loop", "position_map.slots.run_id")
        for water_id in water_ids:
            water_loops = {
                (slot.water_id, slot.reservoir_id)
                for slot in position_map.slots
                if slot.water_id == water_id
            }
            if len(water_loops) != config.reservoirs_per_water:
                fail("POSITION_MAP_INVALID", "confirmation requires six loops per water total", "position_map.slots.reservoir_id")
            if {
                slot.run_id
                for slot in position_map.slots
                if slot.water_id == water_id
            } != expected_runs:
                fail(
                    "POSITION_MAP_INVALID",
                    "every confirmation water must be represented in every later run",
                    "position_map.slots.run_id",
                )
        if min(slot.run_sequence_ordinal for slot in position_map.slots) <= config.discovery_max_run_sequence_ordinal:
            fail("POSITION_MAP_INVALID", "confirmation runs must be strictly later than discovery", "position_map.slots.run_sequence_ordinal")
    if len({slot.cohort_id for slot in position_map.slots}) != 1:
        fail("POSITION_MAP_INVALID", "one position map cannot mix cohort IDs", "position_map.slots.cohort_id")
    if {plant.cohort_id for plant in baseline_roster.plants} != {
        slot.cohort_id for slot in position_map.slots
    }:
        fail("DESIGN_INPUT_INVALID", "roster and position cohorts differ", "cohort_id")
    return plants_by_group, cells


def _validate_bound_spatial_assignments(
    assignments: Sequence[tuple[str, BaselinePlant, PositionSlot]],
    source_entries: Sequence[tuple[str, BaselinePlant]],
    source_slots: Sequence[PositionSlot],
    assigned_groups: Sequence[tuple[str, PositionSlot]],
    groups: tuple[str, ...],
) -> None:
    """Recompute the public spatial oracle independently after physical binding."""

    expected_entries = Counter(
        (
            allocation_id,
            plant.plant_id,
            plant.group_id,
            plant.baseline_canopy_stratum,
            plant.transformation_batch_block,
        )
        for allocation_id, plant in source_entries
    )
    observed_entries = Counter(
        (
            allocation_id,
            plant.plant_id,
            plant.group_id,
            plant.baseline_canopy_stratum,
            plant.transformation_batch_block,
        )
        for allocation_id, plant, _ in assignments
    )
    expected_positions = Counter(slot.position_id for slot in source_slots)
    observed_positions = Counter(slot.position_id for _, _, slot in assignments)
    slot_groups = {
        slot.position_id: group for group, slot in assigned_groups
    }
    if (
        len(assignments) != len(source_entries)
        or expected_entries != observed_entries
        or expected_positions != observed_positions
        or len(slot_groups) != len(assigned_groups)
        or any(
            slot_groups.get(slot.position_id) != plant.group_id
            for _, plant, slot in assignments
        )
        or any(
            plant.baseline_canopy_stratum not in REGISTERED_STRATA
            or (
                plant.group_id in TRANSFORMED_GROUPS
                and plant.transformation_batch_block
                not in REGISTERED_BATCH_BLOCKS
            )
            or (
                plant.group_id in NONTRANSFORMED_GROUPS
                and plant.transformation_batch_block is not None
            )
            for _, plant, _ in assignments
        )
    ):
        raise _BoundSpatialAssignmentInvalid

    row_blocks: dict[tuple[object, ...], list[BaselinePlant]] = defaultdict(list)
    column_blocks: dict[tuple[object, ...], list[BaselinePlant]] = defaultdict(list)
    compartment_blocks: dict[tuple[object, ...], list[BaselinePlant]] = defaultdict(list)
    for _, plant, slot in assignments:
        row_blocks[
            (slot.greenhouse_compartment_id, slot.bench_id, slot.row)
        ].append(plant)
        column_blocks[
            (slot.greenhouse_compartment_id, slot.bench_id, slot.column)
        ].append(plant)
        compartment_blocks[(slot.greenhouse_compartment_id,)].append(plant)

    def maximum_difference(
        blocks: Mapping[tuple[object, ...], list[BaselinePlant]],
        vocabulary: tuple[str, ...],
        value: Callable[[BaselinePlant], str | None],
        *,
        transformed_only: bool = False,
    ) -> int:
        differences: list[int] = []
        for block in blocks.values():
            counts = Counter(
                value(plant)
                for plant in block
                if not transformed_only or plant.group_id in TRANSFORMED_GROUPS
            )
            values = [counts[item] for item in vocabulary]
            differences.append(max(values) - min(values))
        return max(differences, default=0)

    def maximum_not_applicable(
        blocks: Mapping[tuple[object, ...], list[BaselinePlant]],
    ) -> int:
        return max(
            (
                sum(
                    plant.transformation_batch_block is None
                    for plant in block
                )
                for block in blocks.values()
            ),
            default=0,
        )

    maxima = {
        "row_group_count_difference": maximum_difference(
            row_blocks, groups, lambda plant: plant.group_id
        ),
        "column_group_max_count": max(
            (
                max(Counter(plant.group_id for plant in block).values())
                for block in column_blocks.values()
            ),
            default=0,
        ),
        "compartment_group_count_difference": maximum_difference(
            compartment_blocks, groups, lambda plant: plant.group_id
        ),
        "row_stratum_count_difference": maximum_difference(
            row_blocks,
            REGISTERED_STRATA,
            lambda plant: plant.baseline_canopy_stratum,
        ),
        "column_stratum_count_difference": maximum_difference(
            column_blocks,
            REGISTERED_STRATA,
            lambda plant: plant.baseline_canopy_stratum,
        ),
        "compartment_stratum_count_difference": maximum_difference(
            compartment_blocks,
            REGISTERED_STRATA,
            lambda plant: plant.baseline_canopy_stratum,
        ),
        "row_transformed_batch_count_difference": maximum_difference(
            row_blocks,
            REGISTERED_BATCH_BLOCKS,
            lambda plant: plant.transformation_batch_block,
            transformed_only=True,
        ),
        "column_transformed_batch_count_difference": maximum_difference(
            column_blocks,
            REGISTERED_BATCH_BLOCKS,
            lambda plant: plant.transformation_batch_block,
            transformed_only=True,
        ),
        "compartment_transformed_batch_count_difference": maximum_difference(
            compartment_blocks,
            REGISTERED_BATCH_BLOCKS,
            lambda plant: plant.transformation_batch_block,
            transformed_only=True,
        ),
        "row_not_applicable_max_count": maximum_not_applicable(row_blocks),
        "column_not_applicable_max_count": maximum_not_applicable(column_blocks),
        "compartment_not_applicable_max_count": maximum_not_applicable(
            compartment_blocks
        ),
    }
    if set(maxima) != set(_SPATIAL_MAXIMUM_BOUNDS) or any(
        maxima[name] > bound
        for name, bound in _SPATIAL_MAXIMUM_BOUNDS.items()
    ):
        raise _BoundSpatialAssignmentInvalid


def _spatially_restricted_assignments(
    entries: list[tuple[str, BaselinePlant]],
    slots: list[PositionSlot],
    groups: tuple[str, ...],
    priority: tuple[str, ...],
) -> list[tuple[str, BaselinePlant, PositionSlot]]:
    """Assign groups evenly within physical rows and at most once per column block."""

    entries_by_group: dict[str, list[tuple[str, BaselinePlant]]] = defaultdict(list)
    for entry in sorted(entries, key=lambda item: item[0]):
        entries_by_group[entry[1].group_id].append(entry)
    for group_entries in entries_by_group.values():
        group_entries.sort(
            key=lambda entry: (
                entry[1].baseline_canopy_stratum,
                entry[1].transformation_batch_block or "NA",
                entry[0],
            )
        )
    priority_index = {group: index for index, group in enumerate(priority)}
    remaining = {group: len(entries_by_group[group]) for group in groups}
    used_columns: dict[str, set[tuple[str, str, int]]] = {
        group: set() for group in groups
    }
    slots_by_row: dict[tuple[str, str, int], list[PositionSlot]] = defaultdict(list)
    for slot in sorted(
        slots,
        key=lambda item: (
            item.greenhouse_compartment_id,
            item.bench_id,
            item.row,
            item.column,
            item.position_id,
        ),
    ):
        slots_by_row[(slot.greenhouse_compartment_id, slot.bench_id, slot.row)].append(slot)

    assigned_groups: list[tuple[str, PositionSlot]] = []
    for row_key in sorted(slots_by_row):
        row_slots = slots_by_row[row_key]
        base = len(row_slots) // len(groups)
        row_counts = {
            group: min(base, remaining[group]) for group in groups
        }
        for group in groups:
            remaining[group] -= row_counts[group]
        for _ in range(len(row_slots) - sum(row_counts.values())):
            candidates = [group for group in groups if remaining[group] > 0]
            if not candidates:
                raise AssertionError("validated spatial capacities were exhausted")
            chosen = min(
                candidates,
                key=lambda group: (-remaining[group], priority_index[group]),
            )
            row_counts[chosen] += 1
            remaining[chosen] -= 1

        row_assignment: list[tuple[str, PositionSlot]] = []

        def assign_slot(index: int) -> bool:
            if index == len(row_slots):
                return True
            slot = row_slots[index]
            column_key = (
                slot.greenhouse_compartment_id,
                slot.bench_id,
                slot.column,
            )
            candidates = [
                group
                for group in groups
                if row_counts[group] > 0
                and column_key not in used_columns[group]
            ]
            candidates.sort(
                key=lambda group: (
                    -row_counts[group],
                    len(used_columns[group]),
                    priority_index[group],
                )
            )
            for group in candidates:
                row_counts[group] -= 1
                used_columns[group].add(column_key)
                row_assignment.append((group, slot))
                if assign_slot(index + 1):
                    return True
                row_assignment.pop()
                used_columns[group].remove(column_key)
                row_counts[group] += 1
            return False

        if not assign_slot(0):
            fail(
                "POSITION_MAP_INVALID",
                "physical row/column geometry cannot support registered spatial blocking",
                "position_map.slots",
            )
        assigned_groups.extend(row_assignment)
    if any(remaining.values()):
        raise AssertionError("validated group capacities were not spatially assigned")
    flat_entries = [
        entry for group in groups for entry in entries_by_group[group]
    ]
    allowed_pairs = [
        (entry_index, slot_index)
        for entry_index, (_, plant) in enumerate(flat_entries)
        for slot_index, (group, _) in enumerate(assigned_groups)
        if plant.group_id == group
    ]
    variable_index = {
        pair: index for index, pair in enumerate(allowed_pairs)
    }
    constraint_rows: list[np.ndarray] = []
    lower_bounds: list[float] = []
    upper_bounds: list[float] = []

    def add_constraint(
        variable_indices: list[int], lower: int, upper: int
    ) -> None:
        row = np.zeros(len(allowed_pairs), dtype=float)
        row[variable_indices] = 1.0
        constraint_rows.append(row)
        lower_bounds.append(float(lower))
        upper_bounds.append(float(upper))

    for entry_index in range(len(flat_entries)):
        add_constraint(
            [
                variable_index[pair]
                for pair in allowed_pairs
                if pair[0] == entry_index
            ],
            1,
            1,
        )
    for slot_index in range(len(assigned_groups)):
        add_constraint(
            [
                variable_index[pair]
                for pair in allowed_pairs
                if pair[1] == slot_index
            ],
            1,
            1,
        )

    block_slot_indices: list[list[int]] = []
    for key_function in (
        lambda slot: (
            slot.greenhouse_compartment_id,
            slot.bench_id,
            slot.row,
        ),
        lambda slot: (
            slot.greenhouse_compartment_id,
            slot.bench_id,
            slot.column,
        ),
        lambda slot: (slot.greenhouse_compartment_id,),
    ):
        by_block: dict[tuple[object, ...], list[int]] = defaultdict(list)
        for slot_index, (_, slot) in enumerate(assigned_groups):
            by_block[key_function(slot)].append(slot_index)
        block_slot_indices.extend(by_block.values())

    for slot_indices in block_slot_indices:
        slot_set = set(slot_indices)
        block_size = len(slot_indices)
        lower_indices = [
            variable_index[(entry_index, slot_index)]
            for entry_index, (_, plant) in enumerate(flat_entries)
            for slot_index in slot_indices
            if (entry_index, slot_index) in variable_index
            and plant.baseline_canopy_stratum == "lower_canopy"
        ]
        add_constraint(
            lower_indices,
            block_size // 2,
            (block_size + 1) // 2,
        )
        transformed_slot_count = sum(
            assigned_groups[slot_index][0] in TRANSFORMED_GROUPS
            for slot_index in slot_indices
        )
        if transformed_slot_count:
            batch_a_indices = [
                variable_index[(entry_index, slot_index)]
                for entry_index, (_, plant) in enumerate(flat_entries)
                for slot_index in slot_indices
                if (entry_index, slot_index) in variable_index
                and plant.transformation_batch_block == "batch_a"
            ]
            add_constraint(
                batch_a_indices,
                transformed_slot_count // 2,
                (transformed_slot_count + 1) // 2,
            )

    compartment_rank = {
        value: index
        for index, value in enumerate(
            sorted(
                {
                    slot.greenhouse_compartment_id
                    for _, slot in assigned_groups
                }
            )
        )
    }
    bench_rank = {
        value: index
        for index, value in enumerate(
            sorted({slot.bench_id for _, slot in assigned_groups})
        )
    }
    template_key = (
        tuple(
            (
                plant.group_id,
                plant.baseline_canopy_stratum,
                plant.transformation_batch_block or "NA",
            )
            for _, plant in flat_entries
        ),
        tuple(
            (
                group,
                compartment_rank[slot.greenhouse_compartment_id],
                bench_rank[slot.bench_id],
                slot.row,
                slot.column,
            )
            for group, slot in assigned_groups
        ),
    )
    def derive_template() -> _JointSpatialTemplate:
        objective = np.arange(len(allowed_pairs), dtype=float)
        result = milp(
            objective,
            integrality=np.ones(len(allowed_pairs), dtype=int),
            bounds=Bounds(0.0, 1.0),
            constraints=LinearConstraint(
                np.vstack(constraint_rows),
                np.asarray(lower_bounds),
                np.asarray(upper_bounds),
            ),
            options={"presolve": True},
        )
        if not result.success or result.x is None:
            fail(
                "POSITION_MAP_INVALID",
                "physical geometry cannot support joint group/stratum/batch blocking",
                "position_map.slots",
            )
        return tuple(
            allowed_pairs[index]
            for index, value in enumerate(result.x)
            if value > 0.5
        )

    chosen = _JOINT_SPATIAL_TEMPLATE_CACHE.get(template_key)
    from_cache = chosen is not None
    if chosen is None:
        chosen = derive_template()
        _JOINT_SPATIAL_TEMPLATE_CACHE.put(template_key, chosen)
        chosen = _JOINT_SPATIAL_TEMPLATE_CACHE.get(template_key)
        if chosen is None:
            fail(
                "POSITION_MAP_INVALID",
                "joint spatial template failed integrity sealing",
                "position_map.slots",
            )

    for recovery_attempt in range(2):
        try:
            assignments = [
                (*flat_entries[entry_index], assigned_groups[slot_index][1])
                for entry_index, slot_index in chosen
            ]
            _validate_bound_spatial_assignments(
                assignments,
                flat_entries,
                [slot for _, slot in assigned_groups],
                assigned_groups,
                groups,
            )
        except (IndexError, TypeError, _BoundSpatialAssignmentInvalid):
            if from_cache and recovery_attempt == 0:
                _JOINT_SPATIAL_TEMPLATE_CACHE.discard(template_key)
                chosen = derive_template()
                _JOINT_SPATIAL_TEMPLATE_CACHE.put(template_key, chosen)
                sealed = _JOINT_SPATIAL_TEMPLATE_CACHE.get(template_key)
                if sealed is None:
                    fail(
                        "POSITION_MAP_INVALID",
                        "joint spatial template failed integrity sealing",
                        "position_map.slots",
                    )
                chosen = sealed
                from_cache = False
                continue
            fail(
                "POSITION_MAP_INVALID",
                "joint spatial assignment failed independent post-binding audit",
                "position_map.slots",
            )
        return assignments
    raise RuntimeError("unreachable joint spatial recovery state")


def randomize(
    config: DesignConfig,
    root_seed: int,
    *,
    position_map: PositionMap,
    baseline_roster: BaselineRoster,
) -> RandomizationManifest:
    """Allocate only supplied physical plants to supplied physical slots."""

    if type(config) is Paper1DesignConfig:
        checked: DesignConfig = _revalidate_design(config)
    elif type(config) is ConfirmationDesignConfig:
        checked = revalidate_confirmation_design(config)
    else:
        fail("DESIGN_CONFIG_INVALID", "config type is not registered", "config")
    _nonnegative_int(root_seed, code="DESIGN_INPUT_INVALID", field_path="root_seed")
    checked_roster = revalidate_baseline_roster(baseline_roster)
    checked_map = revalidate_position_map(position_map)
    plants_by_group, cells = _validate_randomization_inputs(
        checked, checked_roster, checked_map
    )

    root = np.random.SeedSequence(root_seed, pool_size=SEED_POOL_SIZE)
    child_sequences = root.spawn(7)
    generators = tuple(np.random.Generator(np.random.PCG64(child)) for child in child_sequences)
    (
        run_rng,
        reservoir_rng,
        batch_rng,
        plant_rng,
        position_rng,
        blind_rng,
        movement_rng,
    ) = generators
    seed_tree = Task3SeedTree(
        entropy=root_seed,
        spawn_key=tuple(root.spawn_key),
        pool_size=root.pool_size,
        children=tuple(
            Task3SeedChild(
                name=name,
                entropy=root_seed,
                spawn_key=tuple(child.spawn_key),
                pool_size=child.pool_size,
            )
            for name, child in zip(SEED_CHILD_NAMES, child_sequences, strict=True)
        ),
    )

    run_order = list(checked.runs)
    run_rng.shuffle(run_order)
    water_order = _design_water_ids(checked)
    processing_cells: list[tuple[str, str, str]] = []
    for run_id in run_order:
        for water_id in water_order:
            reservoirs = sorted(key[2] for key in cells if key[:2] == (run_id, water_id))
            reservoir_rng.shuffle(reservoirs)
            processing_cells.extend((run_id, water_id, reservoir) for reservoir in reservoirs)
    loop_count = len(processing_cells)
    registered_cell_keys = sorted(cells)
    cell_index = {key: index for index, key in enumerate(registered_cell_keys)}
    group_index = {group: index for index, group in enumerate(checked.full_allocation_groups)}
    transformed_groups = tuple(
        group for group in checked.full_allocation_groups if group in TRANSFORMED_GROUPS
    )
    nontransformed_groups = tuple(
        group for group in checked.full_allocation_groups if group in NONTRANSFORMED_GROUPS
    )
    transformed_priority = list(transformed_groups)
    batch_rng.shuffle(transformed_priority)
    transformed_rank = {
        group: index for index, group in enumerate(transformed_priority)
    }
    nontransformed_priority = list(nontransformed_groups)
    batch_rng.shuffle(nontransformed_priority)
    nontransformed_rank = {
        group: index for index, group in enumerate(nontransformed_priority)
    }
    joint_offset_pattern = (0, 3, 1, 2)
    joint_common_offset = int(batch_rng.integers(0, 4))
    stratum_common_offset = int(batch_rng.integers(0, 2))

    provisional: dict[tuple[str, str, str], list[tuple[str, BaselinePlant]]] = defaultdict(list)
    for group in checked.full_allocation_groups:
        plants = sorted(plants_by_group[group], key=lambda item: item.plant_id)
        if group in TRANSFORMED_GROUPS:
            buckets: dict[tuple[str, str], list[BaselinePlant]] = {}
            for block in REGISTERED_BATCH_BLOCKS:
                for stratum in REGISTERED_STRATA:
                    bucket = [
                        plant
                        for plant in plants
                        if plant.transformation_batch_block == block
                        and plant.baseline_canopy_stratum == stratum
                    ]
                    plant_rng.shuffle(bucket)
                    buckets[(block, stratum)] = bucket
            joint_pairs = (
                ("batch_a", "lower_canopy"),
                ("batch_a", "upper_canopy"),
                ("batch_b", "lower_canopy"),
                ("batch_b", "upper_canopy"),
            )
            if checked.independent_plants_per_group_reservoir == 5:
                rank = transformed_rank[group]
                group_offset = joint_offset_pattern[rank % len(joint_offset_pattern)]
                extras: list[tuple[tuple[str, str], ...]] = [
                    (
                        joint_pairs[
                            (cell_rank % 4) ^ group_offset ^ joint_common_offset
                        ],
                    )
                    for cell_rank in range(loop_count)
                ]
            else:
                diagonals = (
                    (("batch_a", "lower_canopy"), ("batch_b", "upper_canopy")),
                    (("batch_a", "upper_canopy"), ("batch_b", "lower_canopy")),
                )
                extras = [
                    diagonal
                    for diagonal in diagonals
                    for _ in range(loop_count // 2)
                ]
            if len(extras) != loop_count:
                raise AssertionError("validated loop count must support exact balance")
            for cell, cell_extras in zip(processing_cells, extras, strict=True):
                selected: list[BaselinePlant] = []
                for pair in joint_pairs:
                    selected.append(buckets[pair].pop())
                for pair in cell_extras:
                    selected.append(buckets[pair].pop())
                plant_rng.shuffle(selected)
                for ordinal, plant in enumerate(selected, start=1):
                    allocation_id = (
                        f"A-{cell_index[cell] + 1:02d}-{group_index[group] + 1:02d}-{ordinal:02d}"
                    )
                    provisional[cell].append((allocation_id, plant))
        else:
            buckets_control = {
                stratum: [plant for plant in plants if plant.baseline_canopy_stratum == stratum]
                for stratum in REGISTERED_STRATA
            }
            for bucket in buckets_control.values():
                plant_rng.shuffle(bucket)
            control_rank = nontransformed_rank[group]
            excess_strata = [
                REGISTERED_STRATA[
                    (cell_rank + control_rank + stratum_common_offset) % 2
                ]
                for cell_rank in range(loop_count)
            ]
            for cell, excess in zip(processing_cells, excess_strata, strict=True):
                selected = [
                    buckets_control["lower_canopy"].pop(),
                    buckets_control["lower_canopy"].pop(),
                    buckets_control["upper_canopy"].pop(),
                    buckets_control["upper_canopy"].pop(),
                    buckets_control[excess].pop(),
                ]
                plant_rng.shuffle(selected)
                for ordinal, plant in enumerate(selected, start=1):
                    allocation_id = (
                        f"A-{cell_index[cell] + 1:02d}-{group_index[group] + 1:02d}-{ordinal:02d}"
                    )
                    provisional[cell].append((allocation_id, plant))

    spatial_priority_list = list(checked.full_allocation_groups)
    position_rng.shuffle(spatial_priority_list)
    spatial_priority = tuple(spatial_priority_list)
    assigned: list[tuple[str, BaselinePlant, PositionSlot, str]] = []
    for cell in registered_cell_keys:
        entries = sorted(provisional[cell], key=lambda item: item[0])
        slots = sorted(cells[cell], key=lambda item: item.position_id)
        spatial_assignments = _spatially_restricted_assignments(
            entries,
            slots,
            checked.full_allocation_groups,
            spatial_priority,
        )
        for allocation_id, plant, slot in spatial_assignments:
            schedule_index = int(
                movement_rng.integers(0, len(slot.permitted_movement_schedule_ids))
            )
            assigned.append(
                (
                    allocation_id,
                    plant,
                    slot,
                    slot.permitted_movement_schedule_ids[schedule_index],
                )
            )
    assigned.sort(key=lambda item: item[0])
    blind_numbers = blind_rng.permutation(np.arange(1, len(assigned) + 1))
    records = tuple(
        AllocationRecord(
            allocation_id=allocation_id,
            plant_id=plant.plant_id,
            population=checked.population,
            group_id=plant.group_id,
            water_id=slot.water_id,
            run_id=slot.run_id,
            run_sequence_ordinal=slot.run_sequence_ordinal,
            reservoir_id=slot.reservoir_id,
            transformation_batch_block=plant.transformation_batch_block,
            transformation_batch_id=plant.transformation_batch_id,
            transformation_event_id=plant.transformation_event_id,
            pretreatment_canopy=plant.pretreatment_canopy,
            baseline_canopy_stratum=plant.baseline_canopy_stratum,
            greenhouse_compartment_id=slot.greenhouse_compartment_id,
            water_batch_id=slot.water_batch_id,
            bench_id=slot.bench_id,
            row=slot.row,
            column=slot.column,
            position_id=slot.position_id,
            spatial_gradient_profile_id=slot.spatial_gradient_profile_id,
            movement_schedule_id=movement_schedule,
            blinded_treatment_code=f"BLD-{int(blind_number):04d}",
            cohort_id=plant.cohort_id,
            evidence_label=EvidenceLabel.SYNTHETIC_ONLY,
        )
        for (allocation_id, plant, slot, movement_schedule), blind_number in zip(
            assigned, blind_numbers, strict=True
        )
    )
    config_payload = (
        checked.model_dump(mode="json")
        if type(checked) is Paper1DesignConfig
        else checked.to_dict()
    )
    roster_payload = [
        _baseline_payload(plant)
        for plant in sorted(checked_roster.plants, key=lambda item: item.plant_id)
    ]
    position_payload = [
        _position_payload(slot)
        for slot in sorted(checked_map.slots, key=lambda item: item.position_id)
    ]
    allocation_hash = sha256_bytes(
        canonical_json_bytes([record.to_dict() for record in records])
    )
    return RandomizationManifest(
        schema_version=DESIGN_SCHEMA_VERSION,
        model_version=DESIGN_MODEL_VERSION,
        root_seed=root_seed,
        seed_tree=seed_tree,
        records=records,
        config_sha256=sha256_bytes(canonical_json_bytes(config_payload)),
        allocation_sha256=allocation_hash,
        input_sha256s={
            "baseline_roster_canonical": sha256_bytes(canonical_json_bytes(roster_payload)),
            "position_map_canonical": sha256_bytes(canonical_json_bytes(position_payload)),
        },
        evidence_label=EvidenceLabel.SYNTHETIC_ONLY,
    )


def _duplicates(values: Sequence[str]) -> list[str]:
    counts = Counter(values)
    return sorted(value for value, count in counts.items() if count > 1)


def _validate_cohort_disjointness(cohorts: tuple[CohortIdentitySet, ...]) -> None:
    if len({cohort.cohort_id for cohort in cohorts}) != len(cohorts):
        fail("COHORT_IDENTITY_REUSE", "cohort names must be unique", "cohorts.cohort_id")
    namespaces = (
        "plant_ids",
        "transformation_batch_ids",
        "reservoir_ids",
        "water_batch_ids",
        "run_ids",
        "transformation_event_ids",
    )
    for left_index, left in enumerate(cohorts):
        for right in cohorts[left_index + 1 :]:
            for namespace in namespaces:
                overlap = sorted(set(getattr(left, namespace)) & set(getattr(right, namespace)))
                if overlap:
                    fail(
                        "COHORT_IDENTITY_REUSE",
                        "discovery and confirmation physical identities must be disjoint",
                        f"cohorts.{namespace}",
                        {"namespace": namespace, "reused_ids": overlap},
                    )
    roles = tuple(cohort.cohort_id for cohort in cohorts)
    if roles == ("discovery", "confirmation"):
        discovery, confirmation = cohorts
        if not discovery.run_sequence_ordinals or not confirmation.run_sequence_ordinals:
            fail(
                "COHORT_IDENTITY_REUSE",
                "discovery and confirmation require explicit run sequence ordinals",
                "cohorts.run_sequence_ordinals",
            )
        if max(discovery.run_sequence_ordinals) >= min(
            confirmation.run_sequence_ordinals
        ):
            fail(
                "COHORT_IDENTITY_REUSE",
                "confirmation runs must occur strictly after discovery runs",
                "cohorts.run_sequence_ordinals",
                {
                    "discovery_max": max(discovery.run_sequence_ordinals),
                    "confirmation_min": min(confirmation.run_sequence_ordinals),
                },
            )


def cohort_identity_set(
    manifest: RandomizationManifest,
    *,
    baseline_roster: BaselineRoster,
    position_map: PositionMap,
) -> CohortIdentitySet:
    """Derive one exhaustive cohort identity set from canonical physical inputs."""

    checked_manifest = revalidate_randomization_manifest(manifest)
    checked_roster = revalidate_baseline_roster(baseline_roster)
    checked_map = revalidate_position_map(position_map)
    records = checked_manifest.records
    cohort_ids = {record.cohort_id for record in records}
    if len(cohort_ids) != 1:
        fail(
            "COHORT_IDENTITY_INVALID",
            "manifest must contain exactly one cohort",
            "manifest.records.cohort_id",
        )
    cohort_id = next(iter(cohort_ids))
    if {plant.cohort_id for plant in checked_roster.plants} != {cohort_id} or {
        slot.cohort_id for slot in checked_map.slots
    } != {cohort_id}:
        fail(
            "COHORT_IDENTITY_INVALID",
            "physical inputs and manifest cohort IDs differ",
            "cohort_id",
        )
    manifest_plants = {record.plant_id for record in records}
    roster_plants = {plant.plant_id for plant in checked_roster.plants}
    manifest_positions = {record.position_id for record in records}
    physical_positions = {slot.position_id for slot in checked_map.slots}
    if manifest_plants != roster_plants:
        fail(
            "COHORT_IDENTITY_INVALID",
            "manifest must allocate every roster plant exactly once",
            "plant_ids",
            {
                "unallocated": sorted(roster_plants - manifest_plants),
                "unknown": sorted(manifest_plants - roster_plants),
            },
        )
    if manifest_positions != physical_positions:
        fail(
            "COHORT_IDENTITY_INVALID",
            "manifest must allocate every physical position exactly once",
            "position_ids",
            {
                "unallocated": sorted(physical_positions - manifest_positions),
                "unknown": sorted(manifest_positions - physical_positions),
            },
        )
    roster_by_id = {plant.plant_id: plant for plant in checked_roster.plants}
    slots_by_id = {slot.position_id: slot for slot in checked_map.slots}
    for record in records:
        plant = roster_by_id[record.plant_id]
        slot = slots_by_id[record.position_id]
        if (
            record.group_id,
            record.transformation_batch_block,
            record.transformation_batch_id,
            record.transformation_event_id,
            record.pretreatment_canopy,
            record.baseline_canopy_stratum,
        ) != (
            plant.group_id,
            plant.transformation_batch_block,
            plant.transformation_batch_id,
            plant.transformation_event_id,
            plant.pretreatment_canopy,
            plant.baseline_canopy_stratum,
        ) or (
            record.run_id,
            record.run_sequence_ordinal,
            record.water_id,
            record.reservoir_id,
            record.water_batch_id,
            record.greenhouse_compartment_id,
            record.bench_id,
            record.row,
            record.column,
            record.spatial_gradient_profile_id,
        ) != (
            slot.run_id,
            slot.run_sequence_ordinal,
            slot.water_id,
            slot.reservoir_id,
            slot.water_batch_id,
            slot.greenhouse_compartment_id,
            slot.bench_id,
            slot.row,
            slot.column,
            slot.spatial_gradient_profile_id,
        ):
            fail(
                "COHORT_IDENTITY_INVALID",
                "manifest relabels a physical roster or position identity",
                "manifest.records",
            )
        if record.movement_schedule_id not in slot.permitted_movement_schedule_ids:
            fail(
                "COHORT_IDENTITY_INVALID",
                "manifest movement is not permitted by its physical slot",
                "manifest.records.movement_schedule_id",
            )
    run_pairs = sorted(
        {(record.run_sequence_ordinal, record.run_id) for record in records}
    )
    return CohortIdentitySet(
        cohort_id=cohort_id,
        plant_ids=tuple(sorted(manifest_plants)),
        transformation_batch_ids=tuple(
            sorted(
                {
                    record.transformation_batch_id
                    for record in records
                    if record.transformation_batch_id is not None
                }
            )
        ),
        reservoir_ids=tuple(sorted({record.reservoir_id for record in records})),
        water_batch_ids=tuple(sorted({record.water_batch_id for record in records})),
        run_ids=tuple(run_id for _, run_id in run_pairs),
        transformation_event_ids=tuple(
            sorted(
                {
                    record.transformation_event_id
                    for record in records
                    if record.transformation_event_id is not None
                }
            )
        ),
        run_sequence_ordinals=tuple(ordinal for ordinal, _ in run_pairs),
    )


def _cohort_identity_from_records(
    records: tuple[AllocationRecord, ...], cohort_id: str
) -> CohortIdentitySet:
    rows = tuple(record for record in records if record.cohort_id == cohort_id)
    run_pairs = sorted(
        {(record.run_sequence_ordinal, record.run_id) for record in rows}
    )
    return CohortIdentitySet(
        cohort_id=cohort_id,
        plant_ids=tuple(sorted({record.plant_id for record in rows})),
        transformation_batch_ids=tuple(
            sorted(
                {
                    record.transformation_batch_id
                    for record in rows
                    if record.transformation_batch_id is not None
                }
            )
        ),
        reservoir_ids=tuple(sorted({record.reservoir_id for record in rows})),
        water_batch_ids=tuple(sorted({record.water_batch_id for record in rows})),
        run_ids=tuple(run_id for _, run_id in run_pairs),
        transformation_event_ids=tuple(
            sorted(
                {
                    record.transformation_event_id
                    for record in rows
                    if record.transformation_event_id is not None
                }
            )
        ),
        run_sequence_ordinals=tuple(ordinal for ordinal, _ in run_pairs),
    )


def validate_cohort_separation(
    *,
    discovery_manifest: RandomizationManifest,
    discovery_roster: BaselineRoster,
    discovery_position_map: PositionMap,
    confirmation_manifest: RandomizationManifest,
    confirmation_roster: BaselineRoster,
    confirmation_position_map: PositionMap,
) -> tuple[CohortIdentitySet, CohortIdentitySet]:
    """Derive and audit exact discovery/confirmation physical identity sets."""

    discovery = cohort_identity_set(
        discovery_manifest,
        baseline_roster=discovery_roster,
        position_map=discovery_position_map,
    )
    confirmation = cohort_identity_set(
        confirmation_manifest,
        baseline_roster=confirmation_roster,
        position_map=confirmation_position_map,
    )
    if (discovery.cohort_id, confirmation.cohort_id) != (
        "discovery",
        "confirmation",
    ):
        fail(
            "COHORT_IDENTITY_INVALID",
            "cohort roles must be discovery then confirmation",
            "cohorts.cohort_id",
        )
    _validate_cohort_disjointness((discovery, confirmation))
    return discovery, confirmation


def _revalidate_experimental_unit_spec(
    spec: ExperimentalUnitSpec,
) -> ExperimentalUnitSpec:
    if type(spec) is not ExperimentalUnitSpec:
        fail("DESIGN_INPUT_INVALID", "spec must be exact", "spec")
    checked_slots = (
        revalidate_position_map(PositionMap(tuple(spec.position_slots))).slots
        if spec.position_slots
        else ()
    )
    return ExperimentalUnitSpec(
        population=spec.population,
        requested_water_unit=spec.requested_water_unit,
        expected_groups=tuple(spec.expected_groups),
        expected_water_ids=tuple(spec.expected_water_ids),
        expected_run_ids=tuple(spec.expected_run_ids),
        expected_reservoirs_per_water_run=spec.expected_reservoirs_per_water_run,
        expected_reservoirs_per_water=spec.expected_reservoirs_per_water,
        expected_plants_per_group_reservoir=spec.expected_plants_per_group_reservoir,
        minimum_run_sequence_ordinal=spec.minimum_run_sequence_ordinal,
        permitted_position_ids=tuple(spec.permitted_position_ids),
        position_slots=tuple(checked_slots),
    )


def _audit_spatial_blocks(
    rows: tuple[AllocationRecord, ...],
) -> Mapping[str, int]:
    """Independently derive literal group, stratum, batch, and N/A maxima."""

    groups = tuple(sorted({record.group_id for record in rows}))
    row_blocks: dict[tuple[object, ...], list[AllocationRecord]] = defaultdict(list)
    column_blocks: dict[tuple[object, ...], list[AllocationRecord]] = defaultdict(list)
    compartment_blocks: dict[tuple[object, ...], list[AllocationRecord]] = defaultdict(list)
    for record in rows:
        loop = (
            record.run_id,
            record.greenhouse_compartment_id,
            record.water_id,
            record.reservoir_id,
        )
        row_blocks[(*loop, record.bench_id, record.row)].append(record)
        column_blocks[(*loop, record.bench_id, record.column)].append(record)
        compartment_blocks[loop].append(record)

    def maximum_difference(
        blocks: Mapping[tuple[object, ...], list[AllocationRecord]],
        vocabulary: tuple[str, ...],
        value: Callable[[AllocationRecord], str | None],
        *,
        include: Callable[[AllocationRecord], bool] = lambda record: True,
    ) -> int:
        differences: list[int] = []
        for block in blocks.values():
            counts = Counter(value(record) for record in block if include(record))
            values = [counts[item] for item in vocabulary]
            differences.append(max(values) - min(values))
        return max(differences, default=0)

    def maximum_na_count(
        blocks: Mapping[tuple[object, ...], list[AllocationRecord]],
    ) -> int:
        return max(
            (
                sum(
                    record.transformation_batch_block is None
                    for record in block
                )
                for block in blocks.values()
            ),
            default=0,
        )

    transformed = lambda record: record.group_id in TRANSFORMED_GROUPS
    maxima = {
        "row_group_count_difference": maximum_difference(
            row_blocks, groups, lambda record: record.group_id
        ),
        "column_group_max_count": max(
            (
                max(Counter(record.group_id for record in block).values())
                for block in column_blocks.values()
            ),
            default=0,
        ),
        "compartment_group_count_difference": maximum_difference(
            compartment_blocks, groups, lambda record: record.group_id
        ),
        "row_stratum_count_difference": maximum_difference(
            row_blocks, REGISTERED_STRATA, lambda record: record.baseline_canopy_stratum
        ),
        "column_stratum_count_difference": maximum_difference(
            column_blocks, REGISTERED_STRATA, lambda record: record.baseline_canopy_stratum
        ),
        "compartment_stratum_count_difference": maximum_difference(
            compartment_blocks,
            REGISTERED_STRATA,
            lambda record: record.baseline_canopy_stratum,
        ),
        "row_transformed_batch_count_difference": maximum_difference(
            row_blocks,
            REGISTERED_BATCH_BLOCKS,
            lambda record: record.transformation_batch_block,
            include=transformed,
        ),
        "column_transformed_batch_count_difference": maximum_difference(
            column_blocks,
            REGISTERED_BATCH_BLOCKS,
            lambda record: record.transformation_batch_block,
            include=transformed,
        ),
        "compartment_transformed_batch_count_difference": maximum_difference(
            compartment_blocks,
            REGISTERED_BATCH_BLOCKS,
            lambda record: record.transformation_batch_block,
            include=transformed,
        ),
        "row_not_applicable_max_count": maximum_na_count(row_blocks),
        "column_not_applicable_max_count": maximum_na_count(column_blocks),
        "compartment_not_applicable_max_count": maximum_na_count(
            compartment_blocks
        ),
    }
    if (
        maxima["row_group_count_difference"]
        > _SPATIAL_MAXIMUM_BOUNDS["row_group_count_difference"]
        or maxima["column_group_max_count"]
        > _SPATIAL_MAXIMUM_BOUNDS["column_group_max_count"]
        or maxima["compartment_group_count_difference"]
        > _SPATIAL_MAXIMUM_BOUNDS["compartment_group_count_difference"]
    ):
        fail(
            "EXPERIMENTAL_UNIT_INVALID",
            "group allocation violates registered spatial blocking",
            "records.spatial_block",
        )
    if any(
        maxima[name] > _SPATIAL_MAXIMUM_BOUNDS[name]
        for name in (
            "row_stratum_count_difference",
            "column_stratum_count_difference",
            "compartment_stratum_count_difference",
        )
    ):
        fail(
            "EXPERIMENTAL_UNIT_INVALID",
            "canopy strata violate registered spatial blocking",
            "records.spatial_stratum_block",
        )
    if any(
        maxima[name] > _SPATIAL_MAXIMUM_BOUNDS[name]
        for name in (
            "row_transformed_batch_count_difference",
            "column_transformed_batch_count_difference",
            "compartment_transformed_batch_count_difference",
        )
    ):
        fail(
            "EXPERIMENTAL_UNIT_INVALID",
            "transformation batches violate registered spatial blocking",
            "records.spatial_batch_block",
        )
    return MappingProxyType(maxima)
def validate_experimental_units(
    records: tuple[AllocationRecord, ...],
    spec: ExperimentalUnitSpec,
    *,
    cohorts: tuple[CohortIdentitySet, ...] | None = None,
    observations: tuple[ObservationIdentityRecord, ...] = (),
) -> ExperimentalUnitAudit:
    """Independently derive biological and water replication from identities."""

    spec = _revalidate_experimental_unit_spec(spec)
    if spec.requested_water_unit != "reservoir":
        fail(
            "PSEUDOREPLICATION",
            "water treatment replication must use independent reservoirs",
            "spec.requested_water_unit",
            {
                "attempted_unit": spec.requested_water_unit,
                "canonical_unit": "reservoir",
                "canonical_identity_fields": list(CANONICAL_WATER_IDENTITY_FIELDS),
            },
        )
    input_rows = _exact_tuple(
        records,
        item_type=AllocationRecord,
        code="EXPERIMENTAL_UNIT_INVALID",
        field_path="records",
    )
    rows = tuple(_reconstruct_allocation_record(record) for record in input_rows)
    if not rows:
        fail("EXPERIMENTAL_UNIT_INVALID", "at least one allocation record is required", "records")
    observed_populations = {record.population for record in rows}
    if observed_populations != {spec.population}:
        fail(
            "MODEL_POPULATION_MISMATCH",
            "allocation population does not match requested unit model",
            "spec.population",
            {
                "requested": spec.population.value,
                "observed": sorted(population.value for population in observed_populations),
            },
        )
    unique_fields = (
        ("allocation_id", "records.allocation_id"),
        ("plant_id", "records.plant_id"),
        ("blinded_treatment_code", "records.blinded_treatment_code"),
        ("position_id", "records.position_id"),
    )
    for name, field_path in unique_fields:
        duplicates = _duplicates(tuple(getattr(record, name) for record in rows))
        if duplicates:
            fail(
                "EXPERIMENTAL_UNIT_INVALID",
                f"{name} values must be unique",
                field_path,
                {"duplicates": duplicates},
            )
    water_batches_by_loop: dict[tuple[str, str, str], set[str]] = defaultdict(set)
    for record in rows:
        water_batches_by_loop[
            (record.run_id, record.water_id, record.reservoir_id)
        ].add(record.water_batch_id)
    if any(len(batch_ids) != 1 for batch_ids in water_batches_by_loop.values()):
        fail(
            "EXPERIMENTAL_UNIT_INVALID",
            "one reservoir loop cannot be relabeled by plant",
            "records.water_batch_id",
        )
    if spec.permitted_position_ids:
        off_grid = sorted(
            {record.position_id for record in rows} - set(spec.permitted_position_ids)
        )
        if off_grid:
            fail(
                "EXPERIMENTAL_UNIT_INVALID",
                "allocation contains an off-grid physical position",
                "records.position_id",
                {"off_grid": off_grid},
            )
    if spec.position_slots:
        physical_slots = {slot.position_id: slot for slot in spec.position_slots}
        for record in rows:
            slot = physical_slots.get(record.position_id)
            if slot is None:
                fail(
                    "EXPERIMENTAL_UNIT_INVALID",
                    "allocation contains an off-grid physical position",
                    "records.position_id",
                )
            observed_position = (
                record.run_id,
                record.run_sequence_ordinal,
                record.water_id,
                record.reservoir_id,
                record.water_batch_id,
                record.greenhouse_compartment_id,
                record.bench_id,
                record.row,
                record.column,
                record.spatial_gradient_profile_id,
                record.cohort_id,
            )
            expected_position = (
                slot.run_id,
                slot.run_sequence_ordinal,
                slot.water_id,
                slot.reservoir_id,
                slot.water_batch_id,
                slot.greenhouse_compartment_id,
                slot.bench_id,
                slot.row,
                slot.column,
                slot.spatial_gradient_profile_id,
                slot.cohort_id,
            )
            if observed_position != expected_position or (
                record.movement_schedule_id
                not in slot.permitted_movement_schedule_ids
            ):
                fail(
                    "EXPERIMENTAL_UNIT_INVALID",
                    "allocation relabels a physical position or movement schedule",
                    "records.position_id",
                    {"position_id": record.position_id},
                )
    batch_identity: dict[str, tuple[str, str, str]] = {}
    for record in rows:
        if record.group_id in TRANSFORMED_GROUPS:
            assert record.transformation_batch_id is not None
            assert record.transformation_batch_block is not None
            identity = (
                record.group_id,
                record.transformation_batch_block,
                record.cohort_id,
            )
            previous = batch_identity.setdefault(record.transformation_batch_id, identity)
            if previous != identity:
                fail(
                    "EXPERIMENTAL_UNIT_INVALID",
                    "physical transformation batch was internally relabeled",
                    "records.transformation_batch_id",
                )
    groups_present = {record.group_id for record in rows}
    for group in groups_present & TRANSFORMED_GROUPS:
        blocks = {
            record.transformation_batch_block
            for record in rows
            if record.group_id == group
        }
        if len(blocks) < 2:
            fail(
                "EXPERIMENTAL_UNIT_INVALID",
                "transformed groups must cross at least two batch blocks",
                "records.transformation_batch_block",
            )
        global_block_counts = Counter(
            record.transformation_batch_block
            for record in rows
            if record.group_id == group
        )
        if max(global_block_counts.values()) - min(global_block_counts.values()) > 1:
            fail(
                "EXPERIMENTAL_UNIT_INVALID",
                "global transformation batch imbalance exceeds one",
                "records.transformation_batch_block",
            )
    cell_counts = Counter(
        (record.group_id, record.water_id, record.run_id, record.reservoir_id)
        for record in rows
    )
    if spec.expected_groups:
        if {record.group_id for record in rows} != set(spec.expected_groups):
            fail("EXPERIMENTAL_UNIT_INVALID", "allocation group set is wrong", "records.group_id")
        if {record.water_id for record in rows} != set(spec.expected_water_ids):
            fail("EXPERIMENTAL_UNIT_INVALID", "allocation water set is wrong", "records.water_id")
        if {record.run_id for record in rows} != set(spec.expected_run_ids):
            fail("EXPERIMENTAL_UNIT_INVALID", "allocation run set is wrong", "records.run_id")
        for water_id in spec.expected_water_ids:
            if {
                record.run_id for record in rows if record.water_id == water_id
            } != set(spec.expected_run_ids):
                fail(
                    "EXPERIMENTAL_UNIT_INVALID",
                    "every registered water must be represented in every run",
                    "records.run_id",
                )
        if spec.minimum_run_sequence_ordinal is not None and min(
            record.run_sequence_ordinal for record in rows
        ) < spec.minimum_run_sequence_ordinal:
            fail(
                "EXPERIMENTAL_UNIT_INVALID",
                "allocation run sequence is not later than discovery",
                "records.run_sequence_ordinal",
            )
        expected_cells: set[tuple[str, str, str, str]] = set()
        reservoirs_by_namespace: dict[tuple[str, str], set[str]] = defaultdict(set)
        for record in rows:
            reservoirs_by_namespace[(record.run_id, record.water_id)].add(record.reservoir_id)
        for run_id in spec.expected_run_ids:
            for water_id in spec.expected_water_ids:
                reservoirs = reservoirs_by_namespace[(run_id, water_id)]
                if (
                    spec.expected_reservoirs_per_water_run is not None
                    and len(reservoirs) != spec.expected_reservoirs_per_water_run
                ):
                    fail(
                        "EXPERIMENTAL_UNIT_INVALID",
                        "run/water reservoir count is incomplete",
                        "records.reservoir_id",
                    )
                expected_cells.update(
                    (group, water_id, run_id, reservoir)
                    for group in spec.expected_groups
                    for reservoir in reservoirs
                )
        if spec.expected_reservoirs_per_water is not None:
            for water_id in spec.expected_water_ids:
                loops = {
                    (record.water_id, record.reservoir_id)
                    for record in rows
                    if record.water_id == water_id
                }
                if len(loops) != spec.expected_reservoirs_per_water:
                    fail(
                        "EXPERIMENTAL_UNIT_INVALID",
                        "water reservoir count is incomplete",
                        "records.reservoir_id",
                    )
        if set(cell_counts) != expected_cells or any(
            count != spec.expected_plants_per_group_reservoir
            for count in cell_counts.values()
        ):
            fail(
                "EXPERIMENTAL_UNIT_INVALID",
                "allocation cells are missing, duplicated, or have wrong counts",
                "records",
            )
    for cell in cell_counts:
        cell_rows = [
            record
            for record in rows
            if (record.group_id, record.water_id, record.run_id, record.reservoir_id)
            == cell
        ]
        strata_counts = Counter(record.baseline_canopy_stratum for record in cell_rows)
        if set(strata_counts) != set(REGISTERED_STRATA) or (
            max(strata_counts.values()) - min(strata_counts.values()) > 1
        ):
            fail(
                "EXPERIMENTAL_UNIT_INVALID",
                "baseline stratum imbalance exceeds one",
                "records.baseline_canopy_stratum",
            )
        if cell[0] in TRANSFORMED_GROUPS:
            block_counts = Counter(
                record.transformation_batch_block for record in cell_rows
            )
            if set(block_counts) != set(REGISTERED_BATCH_BLOCKS) or (
                max(block_counts.values()) - min(block_counts.values()) > 1
            ):
                fail(
                    "EXPERIMENTAL_UNIT_INVALID",
                    "transformation batch imbalance exceeds one",
                    "records.transformation_batch_block",
                )
    spatial_balance_maxima = _audit_spatial_blocks(rows)
    if cohorts is not None:
        input_cohort_rows = _exact_tuple(
            cohorts,
            item_type=CohortIdentitySet,
            code="DESIGN_INPUT_INVALID",
            field_path="cohorts",
        )
        cohort_rows = tuple(
            revalidate_cohort_identity_set(cohort)
            for cohort in input_cohort_rows
        )
        _validate_cohort_disjointness(cohort_rows)  # type: ignore[arg-type]
        supplied_by_id = {cohort.cohort_id: cohort for cohort in cohort_rows}
        record_cohort_ids = {record.cohort_id for record in rows}
        if set(supplied_by_id) != record_cohort_ids:
            fail(
                "COHORT_IDENTITY_INVALID",
                "cohort sets must correspond exhaustively to allocation records",
                "cohorts",
                {
                    "record_cohorts": sorted(record_cohort_ids),
                    "supplied_cohorts": sorted(supplied_by_id),
                },
            )
        for cohort_id, supplied in supplied_by_id.items():
            derived = _cohort_identity_from_records(rows, cohort_id)
            if supplied != derived:
                fail(
                    "COHORT_IDENTITY_INVALID",
                    "caller cohort set omits or invents a physical identity",
                    f"cohorts.{cohort_id}",
                )
    input_observation_rows = _exact_tuple(
        observations,
        item_type=ObservationIdentityRecord,
        code="OBSERVATION_IDENTITY_INVALID",
        field_path="observations",
    )
    observation_rows = tuple(
        ObservationIdentityRecord(
            observation_id=item.observation_id,
            plant_id=item.plant_id,
            subsample_id=item.subsample_id,
            technical_read_id=item.technical_read_id,
            timepoint_id=item.timepoint_id,
        )
        for item in input_observation_rows
    )
    observation_ids = tuple(item.observation_id for item in observation_rows)
    if _duplicates(observation_ids):
        fail("OBSERVATION_IDENTITY_INVALID", "observation IDs must be unique", "observations.observation_id")
    unknown_plants = sorted(
        {item.plant_id for item in observation_rows}
        - {record.plant_id for record in rows}
    )
    if unknown_plants:
        fail(
            "OBSERVATION_IDENTITY_INVALID",
            "observation references an unallocated plant",
            "observations.plant_id",
            {"unknown": unknown_plants},
        )
    water_units = {
        (record.run_id, record.water_id, record.reservoir_id) for record in rows
    }
    biological_n = len({record.plant_id for record in rows})
    counts: dict[str, object] = {
        "biological_n": biological_n,
        "water_treatment_n": len(water_units),
        "allocation_n": len(rows),
        "observation_n": len(observation_rows),
        "group_counts": dict(sorted(Counter(record.group_id for record in rows).items())),
        "run_counts": dict(sorted(Counter(record.run_id for record in rows).items())),
        "water_counts": dict(sorted(Counter(record.water_id for record in rows).items())),
        "spatial_balance_maxima": spatial_balance_maxima,
    }
    return ExperimentalUnitAudit(
        biological_n=biological_n,
        water_treatment_n=len(water_units),
        observation_n=len(observation_rows),
        counts=counts,
        checks={
            "unique_allocation_ids": True,
            "unique_plant_ids": True,
            "unique_blind_codes": True,
            "unique_positions": True,
            "batch_crossing": True,
            "balance_within_one": True,
            "spatial_blocking": True,
            "spatial_group_balance": True,
            "spatial_stratum_balance": True,
            "spatial_batch_balance": True,
        },
        evidence_label=EvidenceLabel.SYNTHETIC_ONLY,
    )


def revalidate_experimental_unit_audit(
    audit: ExperimentalUnitAudit,
    *,
    records: tuple[AllocationRecord, ...],
    spec: ExperimentalUnitSpec,
) -> ExperimentalUnitAudit:
    """Recompute an audit and reject a forged or stale caller-supplied summary."""

    if type(audit) is not ExperimentalUnitAudit:
        fail(
            "EXPERIMENTAL_UNIT_INVALID",
            "audit must be an exact ExperimentalUnitAudit",
            "audit",
        )
    recomputed = validate_experimental_units(records, spec)
    if (
        audit.biological_n != recomputed.biological_n
        or audit.water_treatment_n != recomputed.water_treatment_n
        or audit.observation_n != recomputed.observation_n
        or canonical_json_bytes(dict(audit.counts))
        != canonical_json_bytes(dict(recomputed.counts))
        or canonical_json_bytes(dict(audit.checks))
        != canonical_json_bytes(dict(recomputed.checks))
        or audit.evidence_label is not recomputed.evidence_label
    ):
        fail(
            "EXPERIMENTAL_UNIT_INVALID",
            "audit does not match independent recomputation",
            "audit",
        )
    return recomputed


_CSV_FIELDS = (
    "allocation_id",
    "plant_id",
    "population",
    "group_id",
    "water_id",
    "run_id",
    "run_sequence_ordinal",
    "reservoir_id",
    "transformation_batch_block",
    "transformation_batch_id",
    "transformation_event_id",
    "pretreatment_canopy",
    "baseline_canopy_stratum",
    "greenhouse_compartment_id",
    "water_batch_id",
    "bench_id",
    "row",
    "column",
    "position_id",
    "spatial_gradient_profile_id",
    "movement_schedule_id",
    "blinded_treatment_code",
    "cohort_id",
    "evidence_label",
)


def load_shared_reservoir_records(path: str | Path) -> tuple[AllocationRecord, ...]:
    """Strictly load the literal acceptance-14 shared-loop trap fixture."""

    try:
        with Path(path).open("r", encoding="utf-8", newline="") as handle:
            rows = list(csv.reader(handle, strict=True))
    except (OSError, UnicodeError, csv.Error) as error:
        fail(
            "SHARED_RESERVOIR_FIXTURE_INVALID",
            "shared reservoir fixture could not be loaded",
            "csv",
            {"cause_type": type(error).__name__},
        )
    if not rows or tuple(rows[0]) != _CSV_FIELDS:
        fail("SHARED_RESERVOIR_FIXTURE_INVALID", "CSV header is not exact", "csv.header")
    if len(rows) != 5:
        fail("SHARED_RESERVOIR_FIXTURE_INVALID", "CSV must contain exactly four literal rows", "csv.rows")
    parsed: list[AllocationRecord] = []
    for index, row in enumerate(rows[1:], start=1):
        if len(row) != len(_CSV_FIELDS):
            fail("SHARED_RESERVOIR_FIXTURE_INVALID", "CSV row has excess or missing cells", f"csv.rows.{index}")
        if any(value == "" for value in row):
            fail("SHARED_RESERVOIR_FIXTURE_INVALID", "CSV cells cannot be empty", f"csv.rows.{index}")
        values = dict(zip(_CSV_FIELDS, row, strict=True))
        try:
            population = AnalysisPopulation(values.pop("population"))
            evidence_label = EvidenceLabel(values.pop("evidence_label"))
            canopy_text = values.pop("pretreatment_canopy")
            row_text = values.pop("row")
            column_text = values.pop("column")
            run_sequence_text = values.pop("run_sequence_ordinal")
            if not canopy_text.replace(".", "", 1).isdigit():
                raise ValueError("noncanonical canopy")
            if not row_text.isdigit() or not column_text.isdigit() or not run_sequence_text.isdigit():
                raise ValueError("noncanonical position integer")
            for name in (
                "transformation_batch_block",
                "transformation_batch_id",
                "transformation_event_id",
            ):
                values[name] = None if values[name] == "NA" else values[name]
            parsed.append(
                AllocationRecord(
                    **values,
                    population=population,
                    evidence_label=evidence_label,
                    pretreatment_canopy=float(canopy_text),
                    run_sequence_ordinal=int(run_sequence_text),
                    row=int(row_text),
                    column=int(column_text),
                )
            )
        except (ValueError, TypeError, AlmondLabError) as error:
            fail(
                "SHARED_RESERVOIR_FIXTURE_INVALID",
                "CSV row violates the allocation schema",
                f"csv.rows.{index}",
                {"cause_type": type(error).__name__},
            )
    return tuple(parsed)


def _acceptance_06(
    config: Paper1DesignConfig,
    inputs: RandomizationInputs,
    *,
    root_seed: int,
    config_path: Path,
    blinding_escrow_authority: BlindingEscrowAuthority,
) -> tuple[VerificationRecord, RandomizationManifest, BlindedProjection]:
    first = randomize(
        config,
        root_seed,
        position_map=inputs.position_map,
        baseline_roster=inputs.baseline_roster,
    )
    second = randomize(
        config,
        root_seed,
        position_map=inputs.position_map,
        baseline_roster=inputs.baseline_roster,
    )
    spec = ExperimentalUnitSpec.from_design(config, position_map=inputs.position_map)
    audit = validate_experimental_units(first.records, spec)
    cell_counts = Counter(
        (record.group_id, record.water_id, record.run_id, record.reservoir_id)
        for record in first.records
    )
    batch_differences: list[int] = []
    for cell in cell_counts:
        if cell[0] not in TRANSFORMED_GROUPS:
            continue
        counts = Counter(
            record.transformation_batch_block
            for record in first.records
            if (record.group_id, record.water_id, record.run_id, record.reservoir_id)
            == cell
        )
        batch_differences.append(max(counts.values()) - min(counts.values()))
    observed = {
        "record_count": len(first.records),
        "groups": len({record.group_id for record in first.records}),
        "runs": len({record.run_id for record in first.records}),
        "waters": len({record.water_id for record in first.records}),
        "water_treatment_n": audit.water_treatment_n,
        "plants_per_reservoir": min(
            Counter(
                (record.run_id, record.water_id, record.reservoir_id)
                for record in first.records
            ).values()
        ),
        "plants_per_group_reservoir": min(cell_counts.values()),
        "plants_per_group": min(Counter(record.group_id for record in first.records).values()),
        "plants_per_group_water": min(
            Counter((record.group_id, record.water_id) for record in first.records).values()
        ),
        "plants_per_water": min(Counter(record.water_id for record in first.records).values()),
        "plants_per_run": min(Counter(record.run_id for record in first.records).values()),
        "requiring_batch": sum(record.transformation_batch_id is not None for record in first.records),
        "batch_not_applicable": sum(record.transformation_batch_id is None for record in first.records),
        "unique_allocation_ids": len({record.allocation_id for record in first.records}),
        "unique_plant_ids": len({record.plant_id for record in first.records}),
        "unique_blind_codes": len({record.blinded_treatment_code for record in first.records}),
        "position_capacity": len({record.position_id for record in first.records}),
        "max_balance_difference": max(batch_differences),
        "child_seed_names": [child.name for child in first.seed_tree.children],
        "repeat_bytes_equal": first.canonical_json_bytes() == second.canonical_json_bytes(),
        "repeat_hash_equal": first.allocation_sha256 == second.allocation_sha256,
        "spatial_blocking": audit.checks["spatial_blocking"],
        "spatial_group_balance": audit.checks["spatial_group_balance"],
        "spatial_stratum_balance": audit.checks["spatial_stratum_balance"],
        "spatial_batch_balance": audit.checks["spatial_batch_balance"],
        "spatial_balance_maxima": dict(audit.counts["spatial_balance_maxima"]),
    }
    oracle = {
        "record_count": 720,
        "groups": 9,
        "runs": 2,
        "waters": 2,
        "water_treatment_n": 16,
        "plants_per_reservoir": 45,
        "plants_per_group_reservoir": 5,
        "plants_per_group": 80,
        "plants_per_group_water": 40,
        "plants_per_water": 360,
        "plants_per_run": 360,
        "requiring_batch": 560,
        "batch_not_applicable": 160,
        "unique_allocation_ids": 720,
        "unique_plant_ids": 720,
        "unique_blind_codes": 720,
        "position_capacity": 720,
        "max_balance_difference": 1,
        "child_seed_names": list(SEED_CHILD_NAMES),
        "repeat_bytes_equal": True,
        "repeat_hash_equal": True,
        "spatial_blocking": True,
        "spatial_group_balance": True,
        "spatial_stratum_balance": True,
        "spatial_batch_balance": True,
        "spatial_balance_maxima": {
            "row_group_count_difference": 0,
            "column_group_max_count": 1,
            "compartment_group_count_difference": 0,
            "row_stratum_count_difference": 1,
            "column_stratum_count_difference": 1,
            "compartment_stratum_count_difference": 1,
            "row_transformed_batch_count_difference": 1,
            "column_transformed_batch_count_difference": 1,
            "compartment_transformed_batch_count_difference": 1,
            "row_not_applicable_max_count": 2,
            "column_not_applicable_max_count": 2,
            "compartment_not_applicable_max_count": 10,
        },
    }
    manifest_payload = first.canonical_json_bytes() + b"\n"
    projection = blinded_projection(
        first, escrow_authority=blinding_escrow_authority
    )
    projection_payload = projection.canonical_json_bytes() + b"\n"
    provenance = capture_code_provenance()
    record = VerificationRecord(
        acceptance_test=6,
        fixture_sha256=inputs.source_sha256s["paper1_small"],
        fixture_sha256s={
            "primary": inputs.source_sha256s["paper1_small"],
            "baseline_roster_raw": inputs.source_sha256s["baseline_roster_raw"],
            "position_map_raw": inputs.source_sha256s["position_map_raw"],
            "experiment_paper1": sha256_file(config_path),
            "config_normalized": first.config_sha256,
        },
        auxiliary_artifacts_sha256s={
            "allocation_manifest.json": sha256_bytes(manifest_payload),
            "blinded_allocation.json": sha256_bytes(projection_payload),
        },
        observed_value=observed,
        oracle=oracle,
        tolerance=0,
        comparison="eq",
        code_version=code_version_from_provenance(provenance),
        code_provenance=provenance,
        evidence_label=EvidenceLabel.SYNTHETIC_ONLY,
    )
    record.validate()
    return record, first, projection


def _acceptance_14(trap_path: Path) -> VerificationRecord:
    records = load_shared_reservoir_records(trap_path)
    audit = validate_experimental_units(
        records, ExperimentalUnitSpec(population=AnalysisPopulation.COMPOSITE_ROOT)
    )
    try:
        validate_experimental_units(
            records,
            ExperimentalUnitSpec(
                population=AnalysisPopulation.COMPOSITE_ROOT,
                requested_water_unit="plant_id",
            ),
        )
    except AlmondLabError as error:
        attempted = error.to_dict()
    else:
        attempted = {"code": None, "field_path": None, "details": None}
    observed = {
        "water_treatment_n": audit.water_treatment_n,
        "biological_n": audit.biological_n,
        "attempted_code": attempted["code"],
        "attempted_field_path": attempted["field_path"],
        "attempted_details": attempted.get("details"),
    }
    oracle = {
        "water_treatment_n": 1,
        "biological_n": 4,
        "attempted_code": "PSEUDOREPLICATION",
        "attempted_field_path": "spec.requested_water_unit",
        "attempted_details": {
            "attempted_unit": "plant_id",
            "canonical_unit": "reservoir",
            "canonical_identity_fields": list(CANONICAL_WATER_IDENTITY_FIELDS),
        },
    }
    provenance = capture_code_provenance()
    record = VerificationRecord(
        acceptance_test=14,
        fixture_sha256=sha256_file(trap_path),
        fixture_sha256s={"primary": sha256_file(trap_path), "shared_reservoir_trap_raw": sha256_file(trap_path)},
        observed_value=observed,
        oracle=oracle,
        tolerance=0,
        comparison="eq",
        code_version=code_version_from_provenance(provenance),
        code_provenance=provenance,
        evidence_label=EvidenceLabel.SYNTHETIC_ONLY,
    )
    record.validate()
    return record


def publish_design_acceptance(
    run_directory: str | Path,
    *,
    config_path: str | Path,
    design_fixture_path: str | Path,
    trap_path: str | Path,
    blinding_escrow_authority: BlindingEscrowAuthority,
    root_seed: int = 20260812,
    failure_injector: Callable[[str], None] | None = None,
) -> tuple[VerificationRecord, VerificationRecord]:
    """Evaluate acceptance 6/14, then publish one fresh verification directory."""

    destination_root = Path(run_directory)
    if not destination_root.exists() or not destination_root.is_dir():
        fail("DESIGN_INPUT_INVALID", "run_directory must be an existing directory", "run_directory")
    destination = destination_root / "verification"
    if destination.exists():
        fail("ACCEPTANCE_PUBLICATION_FAILED", "verification destination already exists", "run_directory")
    config_source = Path(config_path)
    fixture_source = Path(design_fixture_path)
    trap_source = Path(trap_path)
    config = load_paper1_design(config_source)
    inputs = load_randomization_fixture(fixture_source)
    record_06, manifest, projection = _acceptance_06(
        config,
        inputs,
        root_seed=root_seed,
        config_path=config_source,
        blinding_escrow_authority=_revalidate_blinding_escrow_authority(
            blinding_escrow_authority
        ),
    )
    record_14 = _acceptance_14(trap_source)
    for record in (record_06, record_14):
        record.validate()
        if not record.passed:
            fail("ACCEPTANCE_PUBLICATION_FAILED", "acceptance oracle failed", f"test_{record.acceptance_test:02d}")
    manifest_payload = manifest.canonical_json_bytes() + b"\n"
    projection_payload = projection.canonical_json_bytes() + b"\n"
    staging = Path(tempfile.mkdtemp(prefix=".verification-", dir=destination_root))
    try:
        (staging / "allocation_manifest.json").write_bytes(manifest_payload)
        (staging / "blinded_allocation.json").write_bytes(projection_payload)
        write_verification_record(staging / "test_06.json", record_06)
        if failure_injector is not None:
            failure_injector("after_test_06")
        write_verification_record(staging / "test_14.json", record_14)
        if failure_injector is not None:
            failure_injector("before_publish")
        os.rename(staging, destination)
    except BaseException:
        if staging.exists():
            shutil.rmtree(staging)
        raise
    return record_06, record_14
