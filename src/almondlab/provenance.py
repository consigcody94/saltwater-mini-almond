"""Deterministic run provenance and collision-safe artifact writes."""

from __future__ import annotations

import errno
import hashlib
import json
import math
import os
import re
import secrets
import stat
import subprocess
import sys
import tempfile
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
import platform
from types import MappingProxyType
from typing import Literal

import numpy as np


FILESYSTEM_CONFINEMENT_MODE = (
    "descriptor-relative-nofollow"
    if os.name != "nt"
    else "windows-reparse-identity-guarded"
)
FILESYSTEM_CONFINEMENT_LIMITATION = (
    None
    if os.name != "nt"
    else (
        "Python on Windows exposes neither dir_fd-relative creation nor O_NOFOLLOW; "
        "run operations reject reparse points and revalidate directory identities "
        "around each mutation, but a privileged concurrent reparse swap cannot be "
        "eliminated without a native handle-relative backend."
    )
)


class _FilesystemLinkRefused(OSError):
    pass


def canonical_json_bytes(value: object) -> bytes:
    """Encode a JSON value in its compact, key-sorted UTF-8 representation."""

    normalized = _strict_json_value(value)
    return json.dumps(
        normalized,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def _strict_json_value(value: object, field_path: str = "$") -> object:
    if isinstance(value, Mapping):
        if any(not isinstance(key, str) for key in value):
            raise TypeError(f"{field_path} mappings require string keys")
        return {
            key: _strict_json_value(item, f"{field_path}.{key}")
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [
            _strict_json_value(item, f"{field_path}[{index}]")
            for index, item in enumerate(value)
        ]
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError(f"{field_path} must contain only finite numbers")
    if value is None or isinstance(value, (str, bool, int, float)):
        return value
    raise TypeError(f"{field_path} is not a JSON value")


_JSON_SCHEMA_DRAFT_2020_12 = "https://json-schema.org/draft/2020-12/schema"
_SUPPORTED_SCHEMA_KEYWORDS = frozenset(
    {
        "$defs",
        "$id",
        "$ref",
        "$schema",
        "additionalProperties",
        "anyOf",
        "const",
        "enum",
        "format",
        "items",
        "maximum",
        "maxItems",
        "minimum",
        "minItems",
        "minLength",
        "oneOf",
        "pattern",
        "properties",
        "propertyNames",
        "required",
        "title",
        "type",
        "uniqueItems",
    }
)
_SUPPORTED_JSON_SCHEMA_TYPES = frozenset(
    {"array", "boolean", "integer", "null", "number", "object", "string"}
)


def check_json_schema_subset(schema: object) -> None:
    """Check the strict Draft 2020-12 subset used by the run manifest schema.

    This deliberately fails closed on unknown keywords.  It is a dependency-free
    runtime guard for the checked-in schema, not a general JSON Schema engine.
    Publication builds should additionally check the schema with an independent
    standards-conformant Draft 2020-12 implementation.
    """

    if not isinstance(schema, Mapping):
        raise ValueError("schema definition must be an object")
    if schema.get("$schema") != _JSON_SCHEMA_DRAFT_2020_12:
        raise ValueError("schema definition must declare Draft 2020-12")
    _check_json_schema_node(schema, schema, "$", is_root=True)


def validate_json_schema_subset(schema: object, instance: object) -> None:
    """Validate a JSON document against the checked-in schema keyword subset."""

    check_json_schema_subset(schema)
    if not isinstance(schema, Mapping):  # narrowed by check_json_schema_subset
        raise AssertionError("unreachable")
    _validate_json_schema_node(schema, instance, schema, "$")


def validate_run_manifest_document(schema: object, document: object) -> None:
    """Validate both schema constraints and derived run-manifest semantics."""

    validate_json_schema_subset(schema, document)
    if not isinstance(document, Mapping):  # narrowed by schema validation
        raise AssertionError("unreachable")

    root_seed = document["root_seed"]
    seed_tree = document["seed_tree"]
    if not isinstance(seed_tree, Mapping):
        raise AssertionError("unreachable")
    if seed_tree["root_seed"] != root_seed:
        raise ValueError("manifest root_seed must match seed_tree.root_seed")
    root = seed_tree["root"]
    if not isinstance(root, Mapping):
        raise AssertionError("unreachable")
    _validate_seed_node_document(
        root,
        expected_name="root",
        expected_entropy=root_seed,
        expected_spawn_key=(),
        expected_pool_size=root["pool_size"],
        field_path="seed_tree.root",
    )

    started_at = _parse_manifest_timestamp(document["started_at"], "started_at")
    ended_value = document["ended_at"]
    if ended_value is not None:
        ended_at = _parse_manifest_timestamp(ended_value, "ended_at")
        if ended_at < started_at:
            raise ValueError("manifest ended_at must not precede started_at")

    for mapping_name in ("config_hashes", "input_hashes", "artifact_hashes"):
        digest_mapping = document[mapping_name]
        if not isinstance(digest_mapping, Mapping):
            raise AssertionError("unreachable")
        for relative_path in digest_mapping:
            if _normalize_artifact_path(relative_path) != relative_path:
                raise ValueError(
                    f"manifest {mapping_name} keys must be portable paths"
                )
    artifact_hashes = document["artifact_hashes"]
    if "run_manifest.json" in artifact_hashes:
        raise ValueError("manifest cannot hash itself as an artifact")
    lockfile = document["lockfile"]
    if not isinstance(lockfile, Mapping):
        raise AssertionError("unreachable")
    lockfile_path = lockfile["path"]
    if _normalize_artifact_path(lockfile_path) != lockfile_path:
        raise ValueError("manifest lockfile.path must be a portable relative path")

    evidence_labels = document["evidence_labels"]
    if not isinstance(evidence_labels, list):
        raise AssertionError("unreachable")
    if evidence_labels != sorted(evidence_labels):
        raise ValueError("manifest evidence_labels must use canonical sorted order")

    base_payload = dict(document)
    recorded_manifest_hash = base_payload.pop("manifest_hash")
    recorded_science_hash = base_payload["canonical_science_hash"]
    manifest_hash = sha256_bytes(canonical_json_bytes(base_payload))
    if manifest_hash != recorded_manifest_hash:
        raise ValueError("manifest manifest_hash does not match its exact document")

    base_payload.pop("canonical_science_hash")
    for volatile_name in (
        "run_id",
        "started_at",
        "ended_at",
        "bayesian_raw_draws",
    ):
        base_payload.pop(volatile_name)
    git = dict(base_payload["git"])  # type: ignore[arg-type]
    git.pop("dirty")
    unavailable = git.get("unavailable")
    if isinstance(unavailable, list):
        git["unavailable"] = [name for name in unavailable if name != "dirty"]
    runtime = dict(base_payload["runtime"])  # type: ignore[arg-type]
    runtime.pop("interpreter_path")
    runtime.pop("os_text")
    base_payload["git"] = git
    base_payload["runtime"] = runtime
    science_hash = sha256_bytes(canonical_json_bytes(base_payload))
    if science_hash != recorded_science_hash:
        raise ValueError("manifest canonical_science_hash does not match its payload")


def _check_json_schema_node(
    node: object,
    root: Mapping[object, object],
    field_path: str,
    *,
    is_root: bool = False,
) -> None:
    if not isinstance(node, Mapping):
        raise ValueError(f"schema definition at {field_path} must be an object")
    if any(type(keyword) is not str for keyword in node):
        raise ValueError(f"schema definition at {field_path} requires string keywords")
    unsupported = sorted(set(node) - _SUPPORTED_SCHEMA_KEYWORDS)
    if unsupported:
        raise ValueError(
            f"unsupported schema keyword at {field_path}: {unsupported[0]}"
        )
    if "$schema" in node:
        if not is_root or node["$schema"] != _JSON_SCHEMA_DRAFT_2020_12:
            raise ValueError(f"schema definition at {field_path} has invalid $schema")
    for text_keyword in ("$id", "title"):
        if text_keyword in node and type(node[text_keyword]) is not str:
            raise ValueError(
                f"schema definition at {field_path}.{text_keyword} must be a string"
            )
    if "$ref" in node:
        reference = node["$ref"]
        if type(reference) is not str:
            raise ValueError(f"schema definition at {field_path} has a non-string $ref")
        _resolve_local_schema_ref(root, reference, field_path)
    if "type" in node:
        json_type = node["type"]
        if type(json_type) is not str or json_type not in _SUPPORTED_JSON_SCHEMA_TYPES:
            raise ValueError(f"schema definition at {field_path} has unsupported type")
    if "$defs" in node:
        definitions = node["$defs"]
        if not isinstance(definitions, Mapping) or any(
            type(name) is not str or not name for name in definitions
        ):
            raise ValueError(f"schema definition at {field_path} has invalid $defs")
        for name, definition in definitions.items():
            _check_json_schema_node(
                definition, root, f"{field_path}.$defs.{name}"
            )
    if "properties" in node:
        properties = node["properties"]
        if not isinstance(properties, Mapping) or any(
            type(name) is not str for name in properties
        ):
            raise ValueError(f"schema definition at {field_path} has invalid properties")
        for name, definition in properties.items():
            _check_json_schema_node(
                definition, root, f"{field_path}.properties.{name}"
            )
    if "propertyNames" in node:
        _check_json_schema_node(
            node["propertyNames"], root, f"{field_path}.propertyNames"
        )
    if "additionalProperties" in node:
        additional = node["additionalProperties"]
        if type(additional) is not bool:
            _check_json_schema_node(
                additional, root, f"{field_path}.additionalProperties"
            )
    if "required" in node:
        required = node["required"]
        if not isinstance(required, list) or any(
            type(name) is not str for name in required
        ):
            raise ValueError(f"schema definition at {field_path} has invalid required")
        if len(set(required)) != len(required):
            raise ValueError(f"schema definition at {field_path} repeats a required name")
    for composite in ("anyOf", "oneOf"):
        if composite in node:
            alternatives = node[composite]
            if not isinstance(alternatives, list) or not alternatives:
                raise ValueError(
                    f"schema definition at {field_path}.{composite} must be nonempty"
                )
            for index, alternative in enumerate(alternatives):
                _check_json_schema_node(
                    alternative, root, f"{field_path}.{composite}[{index}]"
                )
    if "items" in node:
        _check_json_schema_node(node["items"], root, f"{field_path}.items")
    if "enum" in node:
        enum = node["enum"]
        if not isinstance(enum, list) or not enum:
            raise ValueError(f"schema definition at {field_path}.enum must be nonempty")
        for value in enum:
            _assert_json_document_value(value, f"{field_path}.enum")
        if any(
            _json_values_equal(left, right)
            for index, left in enumerate(enum)
            for right in enum[index + 1 :]
        ):
            raise ValueError(f"schema definition at {field_path}.enum has duplicates")
    if "const" in node:
        _assert_json_document_value(node["const"], f"{field_path}.const")
    for integer_keyword in ("minItems", "maxItems", "minLength"):
        if integer_keyword in node and (
            type(node[integer_keyword]) is not int or node[integer_keyword] < 0
        ):
            raise ValueError(
                f"schema definition at {field_path}.{integer_keyword} must be nonnegative"
            )
    if (
        "minItems" in node
        and "maxItems" in node
        and node["minItems"] > node["maxItems"]
    ):
        raise ValueError(f"schema definition at {field_path} has inverted item bounds")
    if "uniqueItems" in node and type(node["uniqueItems"]) is not bool:
        raise ValueError(f"schema definition at {field_path}.uniqueItems must be boolean")
    if "pattern" in node:
        pattern = node["pattern"]
        if type(pattern) is not str:
            raise ValueError(f"schema definition at {field_path}.pattern must be a string")
        try:
            re.compile(pattern)
        except re.error as error:
            raise ValueError(
                f"schema definition at {field_path}.pattern is invalid"
            ) from error
    if "format" in node and node["format"] != "date-time":
        raise ValueError(f"schema definition at {field_path} has unsupported format")
    for numeric_keyword in ("minimum", "maximum"):
        if numeric_keyword in node:
            value = node[numeric_keyword]
            if type(value) not in (int, float) or (
                isinstance(value, float) and not math.isfinite(value)
            ):
                raise ValueError(
                    f"schema definition at {field_path}.{numeric_keyword} must be finite"
                )
    if (
        "minimum" in node
        and "maximum" in node
        and node["minimum"] > node["maximum"]
    ):
        raise ValueError(f"schema definition at {field_path} has inverted numeric bounds")


def _validate_json_schema_node(
    node: Mapping[object, object],
    instance: object,
    root: Mapping[object, object],
    field_path: str,
) -> None:
    if "$ref" in node:
        referenced = _resolve_local_schema_ref(root, node["$ref"], field_path)
        _validate_json_schema_node(referenced, instance, root, field_path)

    if "type" in node and not _json_schema_type_matches(node["type"], instance):
        _raise_schema_validation(field_path, f"expected type {node['type']}")
    if "const" in node and not _json_values_equal(instance, node["const"]):
        _raise_schema_validation(field_path, "does not match const")
    if "enum" in node and not any(
        _json_values_equal(instance, candidate)
        for candidate in node["enum"]  # type: ignore[union-attr]
    ):
        _raise_schema_validation(field_path, "is not a registered enum value")

    for composite, expected_matches in (("anyOf", None), ("oneOf", 1)):
        if composite not in node:
            continue
        match_count = 0
        for alternative in node[composite]:  # type: ignore[union-attr]
            try:
                _validate_json_schema_node(alternative, instance, root, field_path)
            except ValueError:
                continue
            match_count += 1
        if match_count == 0 or (
            expected_matches is not None and match_count != expected_matches
        ):
            _raise_schema_validation(
                field_path,
                "must match "
                f"{'exactly one' if expected_matches else 'at least one'} "
                f"{composite} branch",
            )

    if isinstance(instance, Mapping):
        if any(type(name) is not str for name in instance):
            _raise_schema_validation(field_path, "object keys must be strings")
        required = node.get("required", [])
        missing = [name for name in required if name not in instance]  # type: ignore[union-attr]
        if missing:
            _raise_schema_validation(field_path, f"missing required property {missing[0]}")
        properties = node.get("properties", {})
        if not isinstance(properties, Mapping):
            raise AssertionError("schema was not checked")
        for name, child_schema in properties.items():
            if name in instance:
                _validate_json_schema_node(
                    child_schema, instance[name], root, f"{field_path}.{name}"
                )
        if "propertyNames" in node:
            name_schema = node["propertyNames"]
            for name in instance:
                _validate_json_schema_node(
                    name_schema, name, root, f"{field_path}.<property-name>"
                )
        extras = set(instance) - set(properties)
        additional = node.get("additionalProperties", True)
        if additional is False and extras:
            _raise_schema_validation(
                field_path, f"unexpected property {sorted(extras)[0]}"
            )
        if isinstance(additional, Mapping):
            for name in extras:
                _validate_json_schema_node(
                    additional, instance[name], root, f"{field_path}.{name}"
                )

    if isinstance(instance, list):
        if "minItems" in node and len(instance) < node["minItems"]:
            _raise_schema_validation(field_path, "has too few items")
        if "maxItems" in node and len(instance) > node["maxItems"]:
            _raise_schema_validation(field_path, "has too many items")
        if node.get("uniqueItems") is True and any(
            _json_values_equal(left, right)
            for index, left in enumerate(instance)
            for right in instance[index + 1 :]
        ):
            _raise_schema_validation(field_path, "contains duplicate items")
        if "items" in node:
            for index, value in enumerate(instance):
                _validate_json_schema_node(
                    node["items"], value, root, f"{field_path}[{index}]"
                )

    if type(instance) is str:
        if "minLength" in node and len(instance) < node["minLength"]:
            _raise_schema_validation(field_path, "is shorter than minLength")
        if "pattern" in node and re.search(node["pattern"], instance) is None:
            _raise_schema_validation(field_path, "does not match pattern")
        if node.get("format") == "date-time":
            try:
                parsed = datetime.fromisoformat(instance.replace("Z", "+00:00"))
            except ValueError as error:
                raise ValueError(
                    f"schema validation failed at {field_path}: invalid date-time"
                ) from error
            if parsed.tzinfo is None:
                _raise_schema_validation(field_path, "date-time lacks an offset")

    if type(instance) in (int, float):
        if isinstance(instance, float) and not math.isfinite(instance):
            _raise_schema_validation(field_path, "number must be finite")
        if "minimum" in node and instance < node["minimum"]:
            _raise_schema_validation(field_path, "is below minimum")
        if "maximum" in node and instance > node["maximum"]:
            _raise_schema_validation(field_path, "is above maximum")


def _json_schema_type_matches(json_type: object, instance: object) -> bool:
    return {
        "array": type(instance) is list,
        "boolean": type(instance) is bool,
        "integer": type(instance) is int,
        "null": instance is None,
        "number": type(instance) in (int, float)
        and not (isinstance(instance, float) and not math.isfinite(instance)),
        "object": isinstance(instance, Mapping),
        "string": type(instance) is str,
    }[json_type]  # type: ignore[index]


def _json_values_equal(left: object, right: object) -> bool:
    if type(left) in (int, float) and type(right) in (int, float):
        return left == right
    if type(left) is not type(right):
        return False
    if isinstance(left, Mapping):
        return set(left) == set(right) and all(  # type: ignore[arg-type]
            _json_values_equal(left[key], right[key]) for key in left  # type: ignore[index]
        )
    if isinstance(left, list):
        return len(left) == len(right) and all(  # type: ignore[arg-type]
            _json_values_equal(a, b)
            for a, b in zip(left, right, strict=True)  # type: ignore[arg-type]
        )
    return left == right


def _assert_json_document_value(value: object, field_path: str) -> None:
    if isinstance(value, Mapping):
        if any(type(name) is not str for name in value):
            raise ValueError(f"schema definition at {field_path} has non-string keys")
        for name, child in value.items():
            _assert_json_document_value(child, f"{field_path}.{name}")
        return
    if isinstance(value, list):
        for index, child in enumerate(value):
            _assert_json_document_value(child, f"{field_path}[{index}]")
        return
    if value is None or type(value) in (str, bool, int):
        return
    if type(value) is float and math.isfinite(value):
        return
    raise ValueError(f"schema definition at {field_path} is not strict JSON")


def _resolve_local_schema_ref(
    root: Mapping[object, object], reference: object, field_path: str
) -> Mapping[object, object]:
    if type(reference) is not str or not reference.startswith("#/$defs/"):
        raise ValueError(
            f"schema definition at {field_path} uses a nonlocal or unsupported $ref"
        )
    current: object = root
    for encoded_component in reference[2:].split("/"):
        component = encoded_component.replace("~1", "/").replace("~0", "~")
        if not isinstance(current, Mapping) or component not in current:
            raise ValueError(
                f"schema definition at {field_path} has an unresolved $ref"
            )
        current = current[component]
    if not isinstance(current, Mapping):
        raise ValueError(f"schema definition at {field_path} has a non-schema $ref")
    return current


def _raise_schema_validation(field_path: str, message: str) -> None:
    raise ValueError(f"schema validation failed at {field_path}: {message}")


def _parse_manifest_timestamp(value: object, field_path: str) -> datetime:
    if type(value) is not str:
        raise ValueError(f"manifest {field_path} must be a timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError(f"manifest {field_path} is invalid") from error
    if parsed.tzinfo != timezone.utc:
        raise ValueError(f"manifest {field_path} must be UTC")
    return parsed


def _validate_seed_node_document(
    node: Mapping[object, object],
    *,
    expected_name: str,
    expected_entropy: object,
    expected_spawn_key: tuple[int, ...],
    expected_pool_size: object,
    field_path: str,
) -> None:
    if node["name"] != expected_name:
        raise ValueError(f"manifest {field_path}.name must match its child key")
    if node["entropy"] != expected_entropy:
        raise ValueError(f"manifest {field_path}.entropy must match root_seed")
    if tuple(node["spawn_key"]) != expected_spawn_key:  # type: ignore[arg-type]
        raise ValueError(f"manifest {field_path}.spawn_key is inconsistent")
    if node["pool_size"] != expected_pool_size:
        raise ValueError(f"manifest {field_path}.pool_size is inconsistent")
    children = node["children"]
    if not isinstance(children, Mapping):
        raise AssertionError("unreachable")
    if node["n_children_spawned"] != len(children):
        raise ValueError(
            f"manifest {field_path}.n_children_spawned must equal declared children"
        )
    sequence = np.random.SeedSequence(
        entropy=node["entropy"],
        spawn_key=tuple(node["spawn_key"]),  # type: ignore[arg-type]
        pool_size=node["pool_size"],
        n_children_spawned=node["n_children_spawned"],
    )
    expected_state = sequence.generate_state(4, dtype=np.uint32).tolist()
    if node["state"] != expected_state:
        raise ValueError(f"manifest {field_path}.state does not match SeedSequence")
    for index, child_name in enumerate(sorted(children)):
        child = children[child_name]
        if not isinstance(child, Mapping):
            raise AssertionError("unreachable")
        _validate_seed_node_document(
            child,
            expected_name=child_name,
            expected_entropy=expected_entropy,
            expected_spawn_key=(*expected_spawn_key, index),
            expected_pool_size=expected_pool_size,
            field_path=f"{field_path}.children.{child_name}",
        )


def sha256_bytes(payload: bytes) -> str:
    """Return the lowercase SHA-256 digest of an immutable byte payload."""

    return hashlib.sha256(payload).hexdigest()


def sha256_file(source: str | Path) -> str:
    """Return the SHA-256 digest of the exact bytes stored in one file."""

    digest = hashlib.sha256()
    with Path(source).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


class AtomicCommitUncertainError(OSError):
    """A destination changed atomically, but post-commit durability is uncertain."""

    committed = True

    def __init__(self, destination: str | Path) -> None:
        self.destination = Path(destination)
        super().__init__(
            f"atomic commit completed but durability is uncertain: {self.destination}"
        )


@dataclass(frozen=True, slots=True)
class FileProvenance:
    """Exact file identity or a stable reason that identity is unavailable."""

    path: str
    sha256: str | None
    size_bytes: int | None
    state: Literal["available", "unavailable"]
    unavailable_reason: str | None

    def __post_init__(self) -> None:
        if type(self.path) is not str or not self.path:
            raise ValueError("file provenance path must be a nonempty string")
        if _normalize_artifact_path(self.path) != self.path:
            raise ValueError("file provenance path must be a portable relative path")
        if self.state == "available":
            if not _is_sha256(self.sha256):
                raise ValueError("available file provenance requires an exact SHA-256")
            if type(self.size_bytes) is not int or self.size_bytes < 0:
                raise ValueError("available file provenance requires a byte size")
            if self.unavailable_reason is not None:
                raise ValueError("available file provenance cannot have an unavailable reason")
        elif self.state == "unavailable":
            if self.sha256 is not None or self.size_bytes is not None:
                raise ValueError("unavailable file provenance cannot contain invented values")
            if not isinstance(self.unavailable_reason, str) or not self.unavailable_reason:
                raise ValueError("unavailable file provenance requires a stable reason")
        else:
            raise ValueError("file provenance state must be available or unavailable")

    def to_dict(self) -> dict[str, object]:
        return {
            "path": self.path,
            "sha256": self.sha256,
            "size_bytes": self.size_bytes,
            "state": self.state,
            "unavailable_reason": self.unavailable_reason,
        }


@dataclass(frozen=True, slots=True)
class GitProvenance:
    """Exact Git HEAD and worktree status, with stable unavailable semantics."""

    commit_sha: str | None
    dirty: bool | None
    status_sha256: str | None
    state: Literal["available", "unavailable"]
    unavailable_reason: str | None
    unavailable: tuple[str, ...]

    def __post_init__(self) -> None:
        expected_unavailable = tuple(
            name
            for name, value in (
                ("commit_sha", self.commit_sha),
                ("dirty", self.dirty),
                ("status_sha256", self.status_sha256),
            )
            if value is None
        )
        if self.unavailable != expected_unavailable:
            raise ValueError("Git unavailable fields must exactly match null fields")
        if self.state == "available":
            if not _is_git_sha(self.commit_sha):
                raise ValueError("available Git provenance requires an exact commit SHA")
            if type(self.dirty) is not bool:
                raise ValueError("available Git provenance requires an exact dirty boolean")
            if not _is_sha256(self.status_sha256):
                raise ValueError("available Git provenance requires a status SHA-256")
            if self.unavailable or self.unavailable_reason is not None:
                raise ValueError("available Git provenance cannot contain unavailable state")
        elif self.state == "unavailable":
            if self.unavailable != ("commit_sha", "dirty", "status_sha256"):
                raise ValueError("unavailable Git provenance cannot contain partial values")
            if not isinstance(self.unavailable_reason, str) or not self.unavailable_reason:
                raise ValueError("unavailable Git provenance requires a stable reason")
        else:
            raise ValueError("Git provenance state must be available or unavailable")

    def to_dict(self) -> dict[str, object]:
        return {
            "commit_sha": self.commit_sha,
            "dirty": self.dirty,
            "status_sha256": self.status_sha256,
            "state": self.state,
            "unavailable_reason": self.unavailable_reason,
            "unavailable": list(self.unavailable),
        }


@dataclass(frozen=True, slots=True)
class RuntimeProvenance:
    """Exact interpreter/runtime fields, including explicitly volatile identity."""

    interpreter_path: str
    python_version: str
    python_implementation: str
    os_text: str

    def __post_init__(self) -> None:
        for name in (
            "interpreter_path",
            "python_version",
            "python_implementation",
            "os_text",
        ):
            value = getattr(self, name)
            if not isinstance(value, str) or not value:
                raise ValueError(f"runtime {name} must be a nonempty string")

    def to_dict(self) -> dict[str, str]:
        return {
            "interpreter_path": self.interpreter_path,
            "python_version": self.python_version,
            "python_implementation": self.python_implementation,
            "os_text": self.os_text,
        }


@dataclass(frozen=True, slots=True)
class RunManifest:
    """Immutable complete run identity with scientific and whole-record hashes."""

    run_id: str
    deterministic_demo_id: bool
    root_seed: int
    seed_tree: SeedTree
    started_at: datetime
    ended_at: datetime | None
    git: GitProvenance
    lockfile: FileProvenance
    config_hashes: Mapping[str, str]
    input_hashes: Mapping[str, str]
    artifact_hashes: Mapping[str, str]
    model_versions: Mapping[str, str]
    runtime: RuntimeProvenance
    evidence_labels: tuple[str, ...]
    bayesian_raw_draws: object
    schema_version: str = "1.0.0"

    def __post_init__(self) -> None:
        if not isinstance(self.run_id, str) or not re.fullmatch(
            r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}", self.run_id
        ):
            raise ValueError("run_id must be one safe path component")
        if type(self.deterministic_demo_id) is not bool:
            raise TypeError("deterministic_demo_id must be a boolean without coercion")
        if type(self.root_seed) is not int:
            raise TypeError("root_seed must be an integer without coercion")
        if self.root_seed < 0:
            raise ValueError("root_seed must be nonnegative")
        if not isinstance(self.seed_tree, SeedTree):
            raise TypeError("seed_tree must be a SeedTree")
        if self.seed_tree.root_seed != self.root_seed:
            raise ValueError("root_seed must match seed_tree.root_seed")
        started_at = _utc_datetime(self.started_at, "started_at")
        ended_at = (
            None if self.ended_at is None else _utc_datetime(self.ended_at, "ended_at")
        )
        if ended_at is not None and ended_at < started_at:
            raise ValueError("ended_at must not precede started_at")
        object.__setattr__(self, "started_at", started_at)
        object.__setattr__(self, "ended_at", ended_at)
        if not isinstance(self.git, GitProvenance):
            raise TypeError("git must be GitProvenance")
        if not isinstance(self.lockfile, FileProvenance):
            raise TypeError("lockfile must be FileProvenance")
        if not isinstance(self.runtime, RuntimeProvenance):
            raise TypeError("runtime must be RuntimeProvenance")
        object.__setattr__(
            self,
            "config_hashes",
            _freeze_digest_mapping(
                self.config_hashes, "config_hashes", portable_paths=True
            ),
        )
        object.__setattr__(
            self,
            "input_hashes",
            _freeze_digest_mapping(
                self.input_hashes, "input_hashes", portable_paths=True
            ),
        )
        object.__setattr__(
            self,
            "artifact_hashes",
            _freeze_digest_mapping(
                self.artifact_hashes, "artifact_hashes", portable_paths=True
            ),
        )
        if "run_manifest.json" in self.artifact_hashes:
            raise ValueError("run_manifest.json cannot hash itself as an artifact")
        object.__setattr__(
            self,
            "model_versions",
            _freeze_model_versions(self.model_versions),
        )
        if isinstance(self.evidence_labels, (str, bytes)) or not isinstance(
            self.evidence_labels, Sequence
        ):
            raise TypeError("evidence_labels must be a sequence of strings")
        labels = tuple(self.evidence_labels)
        allowed_labels = {
            "physics_constrained",
            "empirically_calibrated",
            "hypothesis_prior",
            "synthetic_only",
        }
        if any(type(label) is not str or label not in allowed_labels for label in labels):
            raise ValueError("evidence_labels must contain only registered labels")
        if len(set(labels)) != len(labels):
            raise ValueError("evidence_labels must not contain duplicates")
        object.__setattr__(self, "evidence_labels", tuple(sorted(labels)))
        object.__setattr__(
            self,
            "bayesian_raw_draws",
            _deep_freeze_json(self.bayesian_raw_draws, "bayesian_raw_draws"),
        )
        if type(self.schema_version) is not str or self.schema_version != "1.0.0":
            raise ValueError("schema_version must be exactly 1.0.0")

    def canonical_science_payload(self) -> dict[str, object]:
        """Return the manifest fields allowed to define deterministic science."""

        git = self.git.to_dict()
        git.pop("dirty")
        unavailable = git.get("unavailable")
        if isinstance(unavailable, list):
            git["unavailable"] = [name for name in unavailable if name != "dirty"]
        runtime = self.runtime.to_dict()
        runtime.pop("interpreter_path")
        runtime.pop("os_text")
        base = self._base_payload()
        for volatile_name in (
            "run_id",
            "started_at",
            "ended_at",
            "bayesian_raw_draws",
        ):
            base.pop(volatile_name)
        base["git"] = git
        base["runtime"] = runtime
        return base

    @property
    def canonical_science_hash(self) -> str:
        return sha256_bytes(canonical_json_bytes(self.canonical_science_payload()))

    @property
    def manifest_hash(self) -> str:
        payload = self._base_payload()
        payload["canonical_science_hash"] = self.canonical_science_hash
        return sha256_bytes(canonical_json_bytes(payload))

    def to_dict(self) -> dict[str, object]:
        """Return a detached JSON document including both derived hashes."""

        payload = self._base_payload()
        payload["canonical_science_hash"] = self.canonical_science_hash
        payload["manifest_hash"] = self.manifest_hash
        return payload

    def _base_payload(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "run_id": self.run_id,
            "deterministic_demo_id": self.deterministic_demo_id,
            "root_seed": self.root_seed,
            "seed_tree": self.seed_tree.to_dict(),
            "started_at": _format_utc(self.started_at),
            "ended_at": None if self.ended_at is None else _format_utc(self.ended_at),
            "git": self.git.to_dict(),
            "lockfile": self.lockfile.to_dict(),
            "config_hashes": dict(self.config_hashes),
            "input_hashes": dict(self.input_hashes),
            "artifact_hashes": dict(self.artifact_hashes),
            "model_versions": dict(self.model_versions),
            "runtime": self.runtime.to_dict(),
            "evidence_labels": list(self.evidence_labels),
            "bayesian_raw_draws": _thaw_json(self.bayesian_raw_draws),
        }


@dataclass(frozen=True, slots=True, init=False)
class RunDirectory:
    """One collision-created directory confined to a literal ``outputs/runs``."""

    runs_root: Path
    path: Path
    run_id: str
    deterministic_demo_id: bool
    _root_identity: tuple[int, int]
    _path_identity: tuple[int, int]

    def __init__(
        self,
        *,
        runs_root: Path,
        path: Path,
        run_id: str,
        deterministic_demo_id: bool,
    ) -> None:
        raise TypeError("RunDirectory instances must be claimed with RunDirectory.create")

    @classmethod
    def _from_claim(
        cls,
        *,
        runs_root: Path,
        path: Path,
        run_id: str,
        deterministic_demo_id: bool,
        root_identity: tuple[int, int],
        path_identity: tuple[int, int],
    ) -> "RunDirectory":
        instance = object.__new__(cls)
        object.__setattr__(instance, "runs_root", runs_root)
        object.__setattr__(instance, "path", path)
        object.__setattr__(instance, "run_id", run_id)
        object.__setattr__(
            instance, "deterministic_demo_id", deterministic_demo_id
        )
        object.__setattr__(instance, "_root_identity", root_identity)
        object.__setattr__(instance, "_path_identity", path_identity)
        instance._validate_claim()
        return instance

    def _validate_claim(self) -> None:
        root = Path(self.runs_root).absolute()
        path = Path(self.path).absolute()
        _validate_runs_root(root)
        _validate_run_id(self.run_id)
        if type(self.deterministic_demo_id) is not bool:
            raise TypeError("deterministic_demo_id must be a boolean without coercion")
        if path.parent != root or path.name != self.run_id:
            raise ValueError("RunDirectory path must remain directly inside outputs/runs")
        _assert_no_links(root)
        _assert_no_links(path)
        if not root.is_dir() or not path.is_dir():
            raise ValueError("RunDirectory paths must be existing directories")
        if _directory_identity(root) != self._root_identity:
            raise RuntimeError("outputs/runs directory identity was replaced")
        if _directory_identity(path) != self._path_identity:
            raise RuntimeError("run directory identity was replaced")
        object.__setattr__(self, "runs_root", root)
        object.__setattr__(self, "path", path)

    @classmethod
    def create(
        cls,
        runs_root: str | Path,
        *,
        config_sha256: str,
        root_seed: int,
        deterministic_run_id: str | None = None,
        timestamp: datetime | None = None,
    ) -> "RunDirectory":
        """Atomically claim a new run ID without following filesystem links.

        POSIX creation is descriptor-relative with no-follow traversal.  On
        Windows, Python lacks the equivalent directory-relative primitives, so
        reparse rejection and identity checks narrow (but cannot eliminate) a
        privileged concurrent parent-swap race; the limitation is exposed by
        ``FILESYSTEM_CONFINEMENT_LIMITATION``.
        """

        raw_root = Path(runs_root)
        _validate_runs_root(raw_root)
        root = raw_root.absolute()
        _assert_no_links(root)
        if not _is_sha256(config_sha256):
            raise ValueError("config_sha256 must be an exact lowercase SHA-256")
        if type(root_seed) is not int:
            raise TypeError("root_seed must be an integer without coercion")
        if root_seed < 0:
            raise ValueError("root_seed must be nonnegative")
        if deterministic_run_id is None:
            instant = datetime.now(timezone.utc) if timestamp is None else _utc_datetime(
                timestamp, "timestamp"
            )
            identity_digest = sha256_bytes(
                canonical_json_bytes(
                    {"config_sha256": config_sha256, "root_seed": root_seed}
                )
            )[:12]
            run_id = f"{instant.strftime('%Y%m%dT%H%M%S%fZ')}-{identity_digest}"
            deterministic_demo_id = False
        else:
            _validate_run_id(deterministic_run_id)
            run_id = deterministic_run_id
            deterministic_demo_id = True

        destination = root / run_id
        if os.name != "nt":
            root_descriptor = _open_directory_descriptor(root, create=True)
            staging_name = f".claim-{secrets.token_hex(16)}"
            path_identity: tuple[int, int] | None = None
            published = False
            try:
                root_identity = _require_path_matches_descriptor(
                    root, root_descriptor, None
                )
                os.mkdir(staging_name, mode=0o700, dir_fd=root_descriptor)
                flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
                flags |= getattr(os, "O_NOFOLLOW", 0) | getattr(
                    os, "O_CLOEXEC", 0
                )
                child_descriptor = os.open(
                    staging_name, flags, dir_fd=root_descriptor
                )
                try:
                    path_identity = _descriptor_identity(child_descriptor)
                    _require_path_matches_descriptor(
                        root, root_descriptor, root_identity
                    )
                    _rename_directory_noreplace(
                        root_descriptor, staging_name, run_id
                    )
                    published = True
                    if _directory_identity(destination) != path_identity:
                        raise RuntimeError("run directory identity was replaced")
                    return cls._from_claim(
                        runs_root=root,
                        path=destination,
                        run_id=run_id,
                        deterministic_demo_id=deterministic_demo_id,
                        root_identity=root_identity,
                        path_identity=path_identity,
                    )
                finally:
                    os.close(child_descriptor)
            except BaseException:
                if path_identity is not None:
                    _rmdir_name_if_identity(
                        root_descriptor,
                        run_id if published else staging_name,
                        path_identity,
                    )
                raise
            finally:
                os.close(root_descriptor)

        root.mkdir(parents=True, exist_ok=True)
        _assert_no_links(root)
        if not root.is_dir():
            raise ValueError("outputs/runs root must be a directory")
        root_identity = _directory_identity(root)
        if _path_is_link(destination):
            raise ValueError("run destination must not be a link or symlink")
        staging = root / f".claim-{secrets.token_hex(16)}"
        os.mkdir(staging)
        path_identity = _directory_identity(staging)
        published = False
        try:
            if _directory_identity(root) != root_identity:
                raise RuntimeError("outputs/runs directory identity was replaced")
            os.rename(staging, destination)
            published = True
            if _directory_identity(destination) != path_identity:
                raise RuntimeError("run directory identity was replaced")
            return cls._from_claim(
                runs_root=root,
                path=destination,
                run_id=run_id,
                deterministic_demo_id=deterministic_demo_id,
                root_identity=root_identity,
                path_identity=path_identity,
            )
        except BaseException:
            _rmdir_path_if_identity(
                destination if published else staging, path_identity
            )
            raise

    def artifact_path(self, relative_path: str | Path) -> Path:
        """Resolve a future artifact path while rejecting escape and link parents."""

        self._validate_claim()
        normalized = _normalize_artifact_path(relative_path)
        relative = Path(normalized)
        candidate = self.path / relative
        if candidate == self.path or self.path not in candidate.parents:
            raise ValueError("artifact path must remain inside the run directory")
        _assert_no_links(candidate)
        return candidate


def finalize_manifest(
    manifest: RunManifest,
    run_directory: RunDirectory,
    *,
    ended_at: datetime | None = None,
    artifact_paths: Mapping[str, str | Path] | None = None,
) -> RunManifest:
    """Hash declared artifacts and atomically persist a completed run manifest."""

    if not isinstance(manifest, RunManifest):
        raise TypeError("manifest must be a RunManifest")
    if not isinstance(run_directory, RunDirectory):
        raise TypeError("run_directory must be a RunDirectory")
    if manifest.run_id != run_directory.run_id:
        raise ValueError("manifest run_id must match RunDirectory run_id")
    if manifest.deterministic_demo_id is not run_directory.deterministic_demo_id:
        raise ValueError(
            "manifest deterministic_demo_id must match RunDirectory creation mode"
        )
    declared = {} if artifact_paths is None else artifact_paths
    if not isinstance(declared, Mapping):
        raise TypeError("artifact_paths must be a mapping")
    if any(not isinstance(name, str) for name in declared):
        raise TypeError("artifact_paths mappings require string keys")
    missing_paths = set(manifest.artifact_hashes) - set(declared)
    if missing_paths:
        raise ValueError(
            "artifact_paths must verify every predeclared artifact hash: "
            f"{sorted(missing_paths)}"
        )

    artifact_hashes = dict(manifest.artifact_hashes)
    captured_artifacts: dict[str, FileProvenance] = {}
    for name, relative_path in sorted(declared.items()):
        if not name:
            raise ValueError("artifact_paths keys must be nonempty")
        normalized_path = _normalize_artifact_path(relative_path)
        if name != normalized_path:
            raise ValueError("artifact_paths key must equal its portable relative path")
        candidate = run_directory.artifact_path(relative_path)
        manifest_path = run_directory.artifact_path("run_manifest.json")
        if candidate == manifest_path:
            raise ValueError("run_manifest.json cannot hash itself as an artifact")
        record = capture_file_provenance(
            candidate, base_directory=run_directory.path
        )
        if record.state != "available":
            raise ValueError(
                f"artifact {name} provenance unavailable: {record.unavailable_reason}"
            )
        assert record.sha256 is not None
        existing = artifact_hashes.get(name)
        if existing is not None and existing != record.sha256:
            raise ValueError(f"artifact {name} does not match its declared SHA-256")
        artifact_hashes[name] = record.sha256
        captured_artifacts[name] = record

    completion = ended_at
    if completion is None:
        completion = manifest.ended_at
    if completion is None:
        completion = datetime.now(timezone.utc)
    finalized = replace(
        manifest,
        ended_at=completion,
        artifact_hashes=artifact_hashes,
    )
    for name, relative_path in sorted(declared.items()):
        candidate = run_directory.artifact_path(relative_path)
        repeated = capture_file_provenance(
            candidate, base_directory=run_directory.path
        )
        if repeated != captured_artifacts[name]:
            raise ValueError(
                f"artifact {name} changed during manifest finalization"
            )
    destination = run_directory.artifact_path("run_manifest.json")
    atomic_create_bytes(
        destination,
        canonical_json_bytes(finalized.to_dict()) + b"\n",
        _expected_parent_identity=run_directory._path_identity,
    )
    return finalized


def _validate_runs_root(path: Path) -> None:
    if ".." in path.parts or path.name != "runs" or path.parent.name != "outputs":
        raise ValueError("run root must be the literal outputs/runs directory")


def _validate_run_id(run_id: object) -> None:
    if type(run_id) is not str or not re.fullmatch(
        r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}", run_id
    ):
        raise ValueError("run_id must be one safe path component")
    if not _is_portable_component(run_id):
        raise ValueError("run_id must be a portable path component")


def _normalize_artifact_path(relative_path: str | Path) -> str:
    if not isinstance(relative_path, (str, Path)):
        raise TypeError("artifact path must be a string or Path")
    relative = Path(relative_path)
    if (
        not str(relative_path)
        or relative.is_absolute()
        or bool(relative.drive)
        or any(part in {"", ".", ".."} for part in relative.parts)
    ):
        raise ValueError("artifact path must be a nonempty relative path without traversal")
    if any(not _is_portable_component(part) for part in relative.parts):
        raise ValueError("artifact path must contain only portable path components")
    return relative.as_posix()


_WINDOWS_RESERVED_NAMES = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    *(f"COM{index}" for index in range(1, 10)),
    *(f"LPT{index}" for index in range(1, 10)),
}


def _is_portable_component(component: str) -> bool:
    if not component or component.endswith((".", " ")):
        return False
    if any(ord(character) < 32 or character in '<>:"/\\|?*' for character in component):
        return False
    stem = component.split(".", 1)[0].upper()
    return stem not in _WINDOWS_RESERVED_NAMES


def _directory_identity(path: Path) -> tuple[int, int]:
    if os.name != "nt":
        descriptor = _open_directory_descriptor(path)
        try:
            metadata = os.fstat(descriptor)
        finally:
            os.close(descriptor)
        return (metadata.st_dev, metadata.st_ino)
    metadata = path.stat(follow_symlinks=False)
    if not stat.S_ISDIR(metadata.st_mode):
        raise ValueError("claimed run path is not a directory")
    return (metadata.st_dev, metadata.st_ino)


def _open_directory_descriptor(path: Path, *, create: bool = False) -> int:
    """Open a POSIX directory by walking every component without following links."""

    if os.name == "nt":
        raise NotImplementedError("Windows lacks portable dir_fd no-follow traversal")
    absolute = Path(os.path.abspath(path))
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
    descriptor = os.open(absolute.anchor, flags)
    try:
        for component in absolute.parts[1:]:
            try:
                child = os.open(component, flags, dir_fd=descriptor)
            except FileNotFoundError:
                if not create:
                    raise
                os.mkdir(component, mode=0o700, dir_fd=descriptor)
                child = os.open(component, flags, dir_fd=descriptor)
            except OSError as error:
                if error.errno in {
                    getattr(os, "ELOOP", 40),
                    getattr(os, "ENOTDIR", 20),
                }:
                    raise _FilesystemLinkRefused(str(path)) from error
                raise
            os.close(descriptor)
            descriptor = child
        metadata = os.fstat(descriptor)
        if not stat.S_ISDIR(metadata.st_mode):
            raise ValueError("claimed run path is not a directory")
        return descriptor
    except BaseException:
        os.close(descriptor)
        raise


def _descriptor_identity(descriptor: int) -> tuple[int, int]:
    metadata = os.fstat(descriptor)
    return (metadata.st_dev, metadata.st_ino)


def _require_descriptor_identity(
    descriptor: int, expected_identity: tuple[int, int] | None
) -> tuple[int, int]:
    actual = _descriptor_identity(descriptor)
    if expected_identity is not None and actual != expected_identity:
        raise RuntimeError("destination directory identity was replaced")
    return actual


def _require_path_matches_descriptor(
    path: Path,
    descriptor: int,
    expected_identity: tuple[int, int] | None,
) -> tuple[int, int]:
    held_identity = _require_descriptor_identity(descriptor, expected_identity)
    if _directory_identity(path) != held_identity:
        raise RuntimeError("destination directory path was replaced")
    return held_identity


def _rmdir_name_if_identity(
    parent_descriptor: int,
    name: str,
    expected_identity: tuple[int, int],
) -> None:
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
    try:
        descriptor = os.open(name, flags, dir_fd=parent_descriptor)
    except (FileNotFoundError, OSError):
        return
    try:
        actual = _descriptor_identity(descriptor)
    finally:
        os.close(descriptor)
    if actual == expected_identity:
        os.rmdir(name, dir_fd=parent_descriptor)


def _rmdir_path_if_identity(
    path: Path, expected_identity: tuple[int, int]
) -> None:
    try:
        if _directory_identity(path) != expected_identity:
            return
    except (FileNotFoundError, OSError, ValueError):
        return
    path.rmdir()


def _rename_directory_noreplace(
    parent_descriptor: int, source_name: str, target_name: str
) -> None:
    """Publish a private POSIX directory with an atomic no-replace rename."""

    import ctypes

    library = ctypes.CDLL(None, use_errno=True)
    source = os.fsencode(source_name)
    target = os.fsencode(target_name)
    if sys.platform.startswith("linux"):
        try:
            rename = library.renameat2
        except AttributeError as error:
            raise RuntimeError(
                "secure no-replace directory publication is unavailable"
            ) from error
        rename.argtypes = [
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_uint,
        ]
        rename.restype = ctypes.c_int
        result = rename(
            parent_descriptor,
            source,
            parent_descriptor,
            target,
            1,  # RENAME_NOREPLACE
        )
    elif sys.platform == "darwin":
        try:
            rename = library.renameatx_np
        except AttributeError as error:
            raise RuntimeError(
                "secure no-replace directory publication is unavailable"
            ) from error
        rename.argtypes = [
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_uint,
        ]
        rename.restype = ctypes.c_int
        result = rename(
            parent_descriptor,
            source,
            parent_descriptor,
            target,
            0x00000004,  # RENAME_EXCL
        )
    else:
        raise RuntimeError(
            "secure no-replace directory publication is unavailable"
        )
    if result == 0:
        return
    error_number = ctypes.get_errno()
    if error_number == errno.EEXIST:
        raise FileExistsError(error_number, os.strerror(error_number), target_name)
    raise OSError(error_number, os.strerror(error_number), target_name)


def _path_is_link(path: Path) -> bool:
    if path.is_symlink():
        return True
    junction_probe = getattr(path, "is_junction", None)
    return bool(junction_probe()) if junction_probe is not None else False


def _assert_no_links(path: Path) -> None:
    for candidate in (path, *path.parents):
        if _path_is_link(candidate):
            raise ValueError(f"filesystem link or symlink refused: {candidate.name}")


def capture_runtime_provenance() -> RuntimeProvenance:
    """Capture the exact active interpreter and operating-system description."""

    return RuntimeProvenance(
        interpreter_path=str(Path(sys.executable).resolve()),
        python_version=platform.python_version(),
        python_implementation=platform.python_implementation(),
        os_text=platform.platform(),
    )


def _freeze_digest_mapping(
    value: object, field_path: str, *, portable_paths: bool = False
) -> Mapping[str, str]:
    if not isinstance(value, Mapping):
        raise TypeError(f"{field_path} must be a mapping")
    if any(not isinstance(key, str) for key in value):
        raise TypeError(f"{field_path} mappings require string keys")
    normalized: dict[str, str] = {}
    for key, digest in value.items():
        if not key:
            raise ValueError(f"{field_path} keys must be nonempty")
        if portable_paths and _normalize_artifact_path(key) != key:
            raise ValueError(f"{field_path} keys must be portable relative paths")
        if not _is_sha256(digest):
            raise ValueError(f"{field_path}.{key} must be an exact lowercase SHA-256")
        assert isinstance(digest, str)
        normalized[key] = digest
    return MappingProxyType(dict(sorted(normalized.items())))


def _freeze_model_versions(value: object) -> Mapping[str, str]:
    if not isinstance(value, Mapping):
        raise TypeError("model_versions must be a mapping")
    if any(not isinstance(key, str) for key in value):
        raise TypeError("model_versions mappings require string keys")
    normalized: dict[str, str] = {}
    for name, version in value.items():
        if not name or type(version) is not str or not version:
            raise TypeError("each model version must have nonempty string name and value")
        normalized[name] = version
    return MappingProxyType(dict(sorted(normalized.items())))


def _deep_freeze_json(value: object, field_path: str) -> object:
    if isinstance(value, Mapping):
        if any(not isinstance(key, str) for key in value):
            raise TypeError(f"{field_path} mappings require string keys")
        return MappingProxyType(
            {
                key: _deep_freeze_json(item, f"{field_path}.{key}")
                for key, item in sorted(value.items())
            }
        )
    if isinstance(value, (list, tuple)):
        return tuple(
            _deep_freeze_json(item, f"{field_path}[{index}]")
            for index, item in enumerate(value)
        )
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError(f"{field_path} must contain only finite numbers")
    if value is None or isinstance(value, (str, bool, int, float)):
        return value
    raise TypeError(f"{field_path} is not a JSON value")


def _thaw_json(value: object) -> object:
    if isinstance(value, Mapping):
        return {key: _thaw_json(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_thaw_json(item) for item in value]
    return value


def _utc_datetime(value: object, field_path: str) -> datetime:
    if not isinstance(value, datetime):
        raise TypeError(f"{field_path} must be a timezone-aware datetime")
    if value.tzinfo is None or value.utcoffset() != timedelta(0):
        raise ValueError(f"{field_path} must be expressed in UTC")
    return value.astimezone(timezone.utc)


def _format_utc(value: datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")


def capture_file_provenance(
    source: str | Path, *, base_directory: str | Path | None = None
) -> FileProvenance:
    """Capture exact bytes and a portable path for a regular, nonsymlink file.

    POSIX opens every component descriptor-relative with ``O_NOFOLLOW``.
    Windows uses lstat/reparse and identity checks with the explicit residual
    limitation reported by ``FILESYSTEM_CONFINEMENT_LIMITATION``.
    """

    path = Path(source)
    if base_directory is not None and not path.is_absolute():
        path = Path(base_directory) / path
    display_path = _portable_file_path(path, base_directory)
    if os.name != "nt":
        return _capture_file_provenance_posix(path, display_path)
    base = None if base_directory is None else Path(base_directory).absolute()
    if _contains_link(path.absolute(), stop_at=base):
        return _unavailable_file(display_path, "link")
    try:
        path_metadata = path.lstat()
    except FileNotFoundError:
        return _unavailable_file(display_path, "missing")
    except OSError:
        return _unavailable_file(display_path, "unreadable")
    if not stat.S_ISREG(path_metadata.st_mode):
        return _unavailable_file(display_path, "not_regular_file")
    try:
        with path.open("rb") as handle:
            before = os.fstat(handle.fileno())
            if not stat.S_ISREG(before.st_mode):
                return _unavailable_file(display_path, "not_regular_file")
            digest = hashlib.sha256()
            size = 0
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
                size += len(chunk)
            after = os.fstat(handle.fileno())
    except FileNotFoundError:
        return _unavailable_file(display_path, "missing")
    except (OSError, PermissionError):
        return _unavailable_file(display_path, "unreadable")
    try:
        repeated_metadata = path.lstat()
    except OSError:
        return _unavailable_file(display_path, "changed_during_capture")
    if (
        path_metadata.st_dev != before.st_dev
        or path_metadata.st_ino != before.st_ino
        or before.st_size != after.st_size
        or before.st_mtime_ns != after.st_mtime_ns
        or before.st_ctime_ns != after.st_ctime_ns
        or size != after.st_size
        or repeated_metadata.st_dev != after.st_dev
        or repeated_metadata.st_ino != after.st_ino
        or repeated_metadata.st_size != after.st_size
        or _contains_link(path.absolute(), stop_at=base)
    ):
        return _unavailable_file(display_path, "changed_during_capture")
    return FileProvenance(
        path=display_path,
        sha256=digest.hexdigest(),
        size_bytes=size,
        state="available",
        unavailable_reason=None,
    )


def _capture_file_provenance_posix(
    path: Path, display_path: str
) -> FileProvenance:
    try:
        descriptor = _open_regular_file_descriptor(path)
    except _FilesystemLinkRefused:
        return _unavailable_file(display_path, "link")
    except FileNotFoundError:
        return _unavailable_file(display_path, "missing")
    except OSError:
        return _unavailable_file(display_path, "unreadable")
    try:
        with os.fdopen(descriptor, "rb") as handle:
            before = os.fstat(handle.fileno())
            if not stat.S_ISREG(before.st_mode):
                return _unavailable_file(display_path, "not_regular_file")
            digest = hashlib.sha256()
            size = 0
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
                size += len(chunk)
            after = os.fstat(handle.fileno())
    except OSError:
        return _unavailable_file(display_path, "unreadable")
    if (
        before.st_dev != after.st_dev
        or before.st_ino != after.st_ino
        or before.st_size != after.st_size
        or before.st_mtime_ns != after.st_mtime_ns
        or before.st_ctime_ns != after.st_ctime_ns
        or size != after.st_size
    ):
        return _unavailable_file(display_path, "changed_during_capture")
    try:
        repeated_descriptor = _open_regular_file_descriptor(path)
        try:
            repeated = os.fstat(repeated_descriptor)
        finally:
            os.close(repeated_descriptor)
    except (OSError, _FilesystemLinkRefused):
        return _unavailable_file(display_path, "changed_during_capture")
    if (
        (repeated.st_dev, repeated.st_ino) != (before.st_dev, before.st_ino)
        or repeated.st_size != after.st_size
        or repeated.st_mtime_ns != after.st_mtime_ns
        or repeated.st_ctime_ns != after.st_ctime_ns
    ):
        return _unavailable_file(display_path, "changed_during_capture")
    return FileProvenance(
        path=display_path,
        sha256=digest.hexdigest(),
        size_bytes=size,
        state="available",
        unavailable_reason=None,
    )


def _open_regular_file_descriptor(path: Path) -> int:
    absolute = Path(os.path.abspath(path))
    parent_descriptor = _open_directory_descriptor(absolute.parent)
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    flags |= getattr(os, "O_CLOEXEC", 0)
    try:
        try:
            return os.open(absolute.name, flags, dir_fd=parent_descriptor)
        except OSError as error:
            if error.errno == getattr(os, "ELOOP", 40):
                raise _FilesystemLinkRefused(str(path)) from error
            raise
    finally:
        os.close(parent_descriptor)


def capture_git_provenance(repository: str | Path) -> GitProvenance:
    """Capture exact Git HEAD/status bytes without leaking machine-specific errors."""

    candidate = Path(repository)
    working_directory = candidate.parent if candidate.is_file() else candidate
    if not working_directory.exists() or not working_directory.is_dir():
        return _unavailable_git("path_missing")
    try:
        subprocess.run(
            ["git", "--version"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return _unavailable_git("git_unavailable")
    try:
        root_result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=working_directory,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True,
        )
        root = Path(root_result.stdout.decode("utf-8", errors="strict").strip())
    except (OSError, UnicodeError, subprocess.CalledProcessError):
        return _unavailable_git("not_a_git_repository")
    try:
        commit_result = subprocess.run(
            ["git", "rev-parse", "--verify", "HEAD"],
            cwd=root,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True,
        )
        commit_sha = commit_result.stdout.decode("ascii", errors="strict").strip()
        if not _is_git_sha(commit_sha):
            return _unavailable_git("invalid_head")
        first_snapshot = _capture_git_snapshot(root)
        second_snapshot = _capture_git_snapshot(root)
        final_commit = _git_output(root, "rev-parse", "--verify", "HEAD").decode(
            "ascii", errors="strict"
        ).strip()
    except _GitSnapshotUnavailable as error:
        return _unavailable_git(error.reason)
    except (OSError, UnicodeError, subprocess.CalledProcessError):
        return _unavailable_git("capture_failed")
    if first_snapshot != second_snapshot or final_commit != commit_sha:
        return _unavailable_git("changed_during_capture")
    (
        status_bytes,
        index_diff_bytes,
        worktree_diff_bytes,
        untracked_records,
    ) = first_snapshot
    if status_bytes:
        status_identity = canonical_json_bytes(
            {
                "porcelain_sha256": sha256_bytes(status_bytes),
                "index_diff_sha256": sha256_bytes(index_diff_bytes),
                "worktree_diff_sha256": sha256_bytes(worktree_diff_bytes),
                "untracked": untracked_records,
            }
        )
    else:
        status_identity = b""
    return GitProvenance(
        commit_sha=commit_sha,
        dirty=bool(status_bytes),
        status_sha256=sha256_bytes(status_identity),
        state="available",
        unavailable_reason=None,
        unavailable=(),
    )


@dataclass(frozen=True, slots=True)
class _GitSnapshotUnavailable(Exception):
    reason: str


def _capture_git_snapshot(
    root: Path,
) -> tuple[bytes, bytes, bytes, tuple[dict[str, object], ...]]:
    _require_clean_submodules(root)
    status_bytes = _git_output(
        root,
        "-c",
        "core.quotepath=false",
        "status",
        "--porcelain=v1",
        "-z",
        "--untracked-files=all",
        "--ignore-submodules=none",
    )
    index_diff_bytes = _git_output(
        root,
        "-c",
        "core.quotepath=false",
        "diff",
        "--cached",
        "--binary",
        "--full-index",
        "--no-ext-diff",
        "--no-renames",
        "--ignore-submodules=none",
        "HEAD",
        "--",
    )
    worktree_diff_bytes = _git_output(
        root,
        "-c",
        "core.quotepath=false",
        "diff",
        "--binary",
        "--full-index",
        "--no-ext-diff",
        "--no-renames",
        "--ignore-submodules=none",
        "--",
    )
    untracked_bytes = _git_output(
        root,
        "-c",
        "core.quotepath=false",
        "ls-files",
        "--others",
        "--exclude-standard",
        "-z",
    )
    records: list[dict[str, object]] = []
    for encoded_path in untracked_bytes.split(b"\0"):
        if not encoded_path:
            continue
        try:
            relative_path = encoded_path.decode("utf-8", errors="strict")
        except UnicodeError as error:
            raise _GitSnapshotUnavailable("untracked_path_not_utf8") from error
        record = capture_file_provenance(
            root / relative_path, base_directory=root
        )
        if record.state != "available":
            raise _GitSnapshotUnavailable(
                f"untracked_file_{record.unavailable_reason}"
            )
        records.append(record.to_dict())
    return status_bytes, index_diff_bytes, worktree_diff_bytes, tuple(records)


def _require_clean_submodules(root: Path) -> None:
    staged = _git_output(root, "ls-files", "--stage", "-z")
    for entry in staged.split(b"\0"):
        if not entry:
            continue
        metadata, separator, encoded_path = entry.partition(b"\t")
        fields = metadata.split()
        if not separator or len(fields) != 3:
            raise _GitSnapshotUnavailable("submodule_index_invalid")
        mode, expected_commit, _stage = fields
        if mode != b"160000":
            continue
        try:
            relative_path = encoded_path.decode("utf-8", errors="strict")
        except UnicodeError as error:
            raise _GitSnapshotUnavailable("submodule_path_not_utf8") from error
        submodule = root / relative_path
        if not submodule.is_dir() or _contains_link(submodule, stop_at=root):
            raise _GitSnapshotUnavailable("submodule_unavailable")
        try:
            top_level = Path(
                _git_output(submodule, "rev-parse", "--show-toplevel")
                .decode("utf-8", errors="strict")
                .strip()
            ).absolute()
            actual_commit = _git_output(
                submodule, "rev-parse", "--verify", "HEAD"
            ).strip()
            status = _git_output(
                submodule,
                "-c",
                "core.quotepath=false",
                "status",
                "--porcelain=v1",
                "-z",
                "--untracked-files=all",
                "--ignore-submodules=none",
            )
        except (OSError, UnicodeError, subprocess.CalledProcessError) as error:
            raise _GitSnapshotUnavailable("submodule_unavailable") from error
        if top_level != submodule.absolute():
            raise _GitSnapshotUnavailable("submodule_unavailable")
        if actual_commit != expected_commit or status:
            raise _GitSnapshotUnavailable("dirty_submodule")
        _require_clean_submodules(submodule)


def _git_output(root: Path, *arguments: str) -> bytes:
    return subprocess.run(
        ["git", *arguments],
        cwd=root,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=True,
    ).stdout


def _portable_file_path(
    path: Path, base_directory: str | Path | None
) -> str:
    if base_directory is None:
        return path.name if path.is_absolute() else path.as_posix()
    base = Path(base_directory).absolute()
    absolute = path.absolute()
    try:
        return absolute.relative_to(base).as_posix()
    except ValueError as error:
        raise ValueError("file provenance path must remain inside base_directory") from error


def _contains_link(path: Path, *, stop_at: Path | None) -> bool:
    for candidate in (path, *path.parents):
        if _path_is_link(candidate):
            return True
        if stop_at is not None and candidate == stop_at:
            break
    return False


def _unavailable_file(path: str, reason: str) -> FileProvenance:
    return FileProvenance(
        path=path,
        sha256=None,
        size_bytes=None,
        state="unavailable",
        unavailable_reason=reason,
    )


def _unavailable_git(reason: str) -> GitProvenance:
    return GitProvenance(
        commit_sha=None,
        dirty=None,
        status_sha256=None,
        state="unavailable",
        unavailable_reason=reason,
        unavailable=("commit_sha", "dirty", "status_sha256"),
    )


def _is_sha256(value: object) -> bool:
    return isinstance(value, str) and bool(re.fullmatch(r"[0-9a-f]{64}", value))


def _is_git_sha(value: object) -> bool:
    return isinstance(value, str) and bool(re.fullmatch(r"[0-9a-f]{40}", value))


_SEED_NAME_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$")


@dataclass(frozen=True, slots=True)
class SeedNode:
    """One immutable, reconstructable node in a named SeedSequence tree."""

    name: str
    entropy: int
    spawn_key: tuple[int, ...]
    pool_size: int
    n_children_spawned: int
    state: tuple[int, ...]
    children: Mapping[str, "SeedNode"]

    def __post_init__(self) -> None:
        if type(self.name) is not str or not _SEED_NAME_PATTERN.fullmatch(self.name):
            raise ValueError("seed node name is invalid")
        if type(self.entropy) is not int or self.entropy < 0:
            raise TypeError("seed entropy must be a nonnegative integer without coercion")
        spawn_key = _freeze_seed_integers(self.spawn_key, "seed spawn_key")
        if type(self.pool_size) is not int or self.pool_size < 4:
            raise TypeError("seed pool_size must be an integer of at least four")
        if type(self.n_children_spawned) is not int or self.n_children_spawned < 0:
            raise TypeError(
                "seed n_children_spawned must be a nonnegative integer without coercion"
            )
        state = _freeze_seed_integers(self.state, "seed state", length=4)
        if not isinstance(self.children, Mapping):
            raise TypeError("seed children must be a mapping")
        if any(type(name) is not str for name in self.children):
            raise TypeError("seed children mappings require string keys")
        children = dict(sorted(self.children.items()))
        if self.n_children_spawned != len(children):
            raise ValueError(
                "seed n_children_spawned must equal the recorded named child count"
            )
        for index, (name, child) in enumerate(children.items()):
            if not isinstance(child, SeedNode):
                raise TypeError("seed children must contain only SeedNode records")
            if child.name != name:
                raise ValueError("seed child mapping keys must match node names")
            if child.entropy != self.entropy or child.pool_size != self.pool_size:
                raise ValueError("seed children must share parent entropy and pool size")
            if child.spawn_key != spawn_key + (index,):
                raise ValueError("seed child spawn keys must match sorted name order")
        object.__setattr__(self, "spawn_key", spawn_key)
        object.__setattr__(self, "state", state)
        object.__setattr__(
            self,
            "children",
            MappingProxyType(children),
        )

    def to_dict(self) -> dict[str, object]:
        """Return a mutable JSON representation without exposing internal state."""

        return {
            "name": self.name,
            "entropy": self.entropy,
            "spawn_key": list(self.spawn_key),
            "pool_size": self.pool_size,
            "n_children_spawned": self.n_children_spawned,
            "state": list(self.state),
            "children": {
                name: child.to_dict() for name, child in self.children.items()
            },
        }


def _freeze_seed_integers(
    value: object, field_path: str, *, length: int | None = None
) -> tuple[int, ...]:
    if isinstance(value, (str, bytes, bytearray)) or not isinstance(value, Sequence):
        raise TypeError(f"{field_path} must be an integer sequence")
    frozen = tuple(value)
    if length is not None and len(frozen) != length:
        raise ValueError(f"{field_path} must contain exactly {length} integers")
    if any(type(item) is not int or not 0 <= item < 2**32 for item in frozen):
        raise TypeError(f"{field_path} requires unsigned 32-bit integers without coercion")
    return frozen


@dataclass(frozen=True, slots=True, init=False)
class SeedTree:
    """A complete immutable tree of deterministically named NumPy RNG streams."""

    root_seed: int
    root: SeedNode

    def __init__(self, root_seed: int, structure: object) -> None:
        if type(root_seed) is not int:
            raise TypeError("root_seed must be an integer without coercion")
        if root_seed < 0:
            raise ValueError("root_seed must be nonnegative")
        normalized = _normalize_seed_structure(structure)
        root_sequence = np.random.SeedSequence(root_seed)
        object.__setattr__(self, "root_seed", root_seed)
        object.__setattr__(
            self,
            "root",
            _build_seed_node("root", root_sequence, normalized),
        )

    @classmethod
    def from_seed(cls, root_seed: int, structure: object) -> "SeedTree":
        """Preallocate a complete tree from nested mappings or child-name lists."""

        return cls(root_seed, structure)

    @property
    def children(self) -> Mapping[str, SeedNode]:
        return self.root.children

    def node(self, *path: str) -> SeedNode:
        """Return the recorded node at a sequence of child names."""

        current = self.root
        for name in path:
            if not isinstance(name, str):
                raise TypeError("seed name must be a string")
            try:
                current = current.children[name]
            except KeyError as error:
                joined = "/".join(path)
                raise KeyError(f"unknown seed path: {joined}") from error
        return current

    def seed_sequence(self, *path: str) -> np.random.SeedSequence:
        """Reconstruct the exact NumPy SeedSequence recorded for a named node."""

        node = self.node(*path)
        return np.random.SeedSequence(
            entropy=node.entropy,
            spawn_key=node.spawn_key,
            pool_size=node.pool_size,
            n_children_spawned=node.n_children_spawned,
        )

    def generator(self, *path: str) -> np.random.Generator:
        """Create a fresh Generator for one predeclared named node."""

        return np.random.default_rng(self.seed_sequence(*path))

    def to_dict(self) -> dict[str, object]:
        return {
            "algorithm": "numpy.random.SeedSequence",
            "root_seed": self.root_seed,
            "root": self.root.to_dict(),
        }


def _normalize_seed_structure(
    structure: object, field_path: str = "seed children"
) -> dict[str, dict[str, object]]:
    if isinstance(structure, Mapping):
        if any(not isinstance(name, str) for name in structure):
            raise TypeError(f"{field_path} require string seed child names")
        items = list(structure.items())
    elif isinstance(structure, Sequence) and not isinstance(
        structure, (str, bytes, bytearray)
    ):
        if any(not isinstance(name, str) for name in structure):
            raise TypeError(f"{field_path} require string seed child names")
        names = list(structure)
        if len(set(names)) != len(names):
            raise ValueError(f"{field_path} contain a duplicate seed name")
        items = [(name, None) for name in names]
    else:
        raise TypeError(f"{field_path} must be a mapping or sequence of seed names")

    normalized: dict[str, dict[str, object]] = {}
    for name, child_structure in items:
        if not _SEED_NAME_PATTERN.fullmatch(name):
            raise ValueError(f"invalid seed name at {field_path}: {name!r}")
        if child_structure is None:
            normalized[name] = {}
        elif isinstance(child_structure, Mapping) or (
            isinstance(child_structure, Sequence)
            and not isinstance(child_structure, (str, bytes, bytearray))
        ):
            normalized[name] = _normalize_seed_structure(
                child_structure, f"{field_path}.{name}"
            )
        else:
            raise TypeError(f"seed child {field_path}.{name} has an invalid structure")
    return dict(sorted(normalized.items()))


def _build_seed_node(
    name: str,
    sequence: np.random.SeedSequence,
    structure: Mapping[str, Mapping[str, object]],
) -> SeedNode:
    names = tuple(sorted(structure))
    child_sequences = sequence.spawn(len(names))
    children = {
        child_name: _build_seed_node(
            child_name,
            child_sequence,
            structure[child_name],
        )
        for child_name, child_sequence in zip(names, child_sequences, strict=True)
    }
    entropy = sequence.entropy
    if type(entropy) is not int:
        raise TypeError("root_seed must produce scalar integer entropy")
    return SeedNode(
        name=name,
        entropy=entropy,
        spawn_key=tuple(int(index) for index in sequence.spawn_key),
        pool_size=int(sequence.pool_size),
        n_children_spawned=int(sequence.n_children_spawned),
        state=tuple(
            int(value)
            for value in sequence.generate_state(4, dtype=np.uint32).tolist()
        ),
        children=children,
    )


def atomic_write_bytes(
    destination: str | Path,
    payload: bytes,
    *,
    _expected_parent_identity: tuple[int, int] | None = None,
) -> Path:
    """Durably replace one file without exposing a partial destination.

    The temporary file is created beside the destination, flushed before the
    replace, and always removed on failure.  Claimed run directories pass an
    expected directory identity, which is checked immediately before and after
    the mutation.  POSIX directory metadata is flushed after replacement;
    Windows does not expose portable directory ``fsync``, so identity/reparse
    checks narrow but cannot eliminate a privileged concurrent swap race.
    """

    target = Path(destination)
    if os.name != "nt":
        return _atomic_commit_posix(
            target,
            payload,
            expected_parent_identity=_expected_parent_identity,
            exclusive=False,
        )
    target.parent.mkdir(parents=True, exist_ok=True)
    _require_directory_identity(target.parent, _expected_parent_identity)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{target.name}.", suffix=".tmp", dir=target.parent
    )
    temporary = Path(temporary_name)
    temporary_identity = _descriptor_identity(descriptor)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            _require_directory_identity(target.parent, _expected_parent_identity)
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        _require_directory_identity(target.parent, _expected_parent_identity)
        os.replace(temporary, target)
        try:
            _fsync_directory(target.parent, _expected_parent_identity)
        except BaseException as error:
            raise AtomicCommitUncertainError(target) from error
    finally:
        _unlink_path_if_identity(temporary, temporary_identity)
    return target


def atomic_create_bytes(
    destination: str | Path,
    payload: bytes,
    *,
    _expected_parent_identity: tuple[int, int] | None = None,
) -> Path:
    """Atomically create a new file, refusing every pre-existing destination."""

    target = Path(destination)
    if os.name != "nt":
        return _atomic_commit_posix(
            target,
            payload,
            expected_parent_identity=_expected_parent_identity,
            exclusive=True,
        )
    target.parent.mkdir(parents=True, exist_ok=True)
    _require_directory_identity(target.parent, _expected_parent_identity)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{target.name}.", suffix=".tmp", dir=target.parent
    )
    temporary = Path(temporary_name)
    temporary_identity = _descriptor_identity(descriptor)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            _require_directory_identity(target.parent, _expected_parent_identity)
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        _require_directory_identity(target.parent, _expected_parent_identity)
        os.link(temporary, target, follow_symlinks=False)
        if not _unlink_path_if_identity(temporary, temporary_identity):
            raise AtomicCommitUncertainError(target)
        try:
            _fsync_directory(target.parent, _expected_parent_identity)
        except BaseException as error:
            raise AtomicCommitUncertainError(target) from error
    finally:
        _unlink_path_if_identity(temporary, temporary_identity)
    return target


def _atomic_commit_posix(
    target: Path,
    payload: bytes,
    *,
    expected_parent_identity: tuple[int, int] | None,
    exclusive: bool,
) -> Path:
    parent_descriptor = _open_directory_descriptor(target.parent, create=True)
    temporary_name = f".{target.name}.{secrets.token_hex(16)}.tmp"
    temporary_identity: tuple[int, int] | None = None
    temporary_present = False
    try:
        _require_path_matches_descriptor(
            target.parent, parent_descriptor, expected_parent_identity
        )
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        flags |= getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
        descriptor = os.open(
            temporary_name, flags, 0o600, dir_fd=parent_descriptor
        )
        temporary_present = True
        temporary_identity = _descriptor_identity(descriptor)
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        _require_path_matches_descriptor(
            target.parent, parent_descriptor, expected_parent_identity
        )
        if exclusive:
            os.link(
                temporary_name,
                target.name,
                src_dir_fd=parent_descriptor,
                dst_dir_fd=parent_descriptor,
                follow_symlinks=False,
            )
            if not _unlink_name_if_identity(
                parent_descriptor, temporary_name, temporary_identity
            ):
                raise AtomicCommitUncertainError(target)
        else:
            os.replace(
                temporary_name,
                target.name,
                src_dir_fd=parent_descriptor,
                dst_dir_fd=parent_descriptor,
            )
        temporary_present = False
        try:
            _fsync_directory(target.parent, expected_parent_identity)
        except BaseException as error:
            raise AtomicCommitUncertainError(target) from error
    finally:
        if temporary_present and temporary_identity is not None:
            _unlink_name_if_identity(
                parent_descriptor, temporary_name, temporary_identity
            )
        os.close(parent_descriptor)
    return target


def _unlink_name_if_identity(
    parent_descriptor: int,
    name: str,
    expected_identity: tuple[int, int],
) -> bool:
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    flags |= getattr(os, "O_CLOEXEC", 0)
    try:
        descriptor = os.open(name, flags, dir_fd=parent_descriptor)
    except FileNotFoundError:
        return True
    except OSError:
        return False
    try:
        actual = _descriptor_identity(descriptor)
    finally:
        os.close(descriptor)
    if actual == expected_identity:
        try:
            os.unlink(name, dir_fd=parent_descriptor)
        except OSError:
            return False
        else:
            return True
    return False


def _unlink_path_if_identity(
    path: Path, expected_identity: tuple[int, int]
) -> bool:
    try:
        metadata = path.stat(follow_symlinks=False)
    except FileNotFoundError:
        return True
    if (metadata.st_dev, metadata.st_ino) == expected_identity:
        try:
            path.unlink()
        except OSError:
            return False
        else:
            return True
    return False


def _require_directory_identity(
    directory: Path, expected_identity: tuple[int, int] | None
) -> tuple[int, int]:
    _assert_no_links(directory)
    actual = _directory_identity(directory)
    if expected_identity is not None and actual != expected_identity:
        raise RuntimeError("destination directory identity was replaced")
    return actual


def _fsync_directory(
    directory: Path, expected_identity: tuple[int, int] | None
) -> None:
    if os.name == "nt":
        _require_directory_identity(directory, expected_identity)
        return
    descriptor = _open_directory_descriptor(directory)
    try:
        _require_path_matches_descriptor(
            directory, descriptor, expected_identity
        )
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
