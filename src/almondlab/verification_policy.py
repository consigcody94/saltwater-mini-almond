"""Strict, hashed runtime policies and packaged verification resources."""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from dataclasses import dataclass
from importlib import resources
from math import isfinite
from pathlib import Path
from types import MappingProxyType

import yaml

from almondlab.contracts import EvidenceLabel


RESOURCE_PACKAGE = "almondlab.resources"
CORE_ACCEPTANCE_TESTS = (1, 2, 3, 4, 5, 13, 19, 20)
PHYSICAL_STOP_IDS = (
    "concentration_mmol_l",
    "ecw_ds_m",
    "osmolality_osmol_kg",
    "volume_l",
    "injury",
    "containment_discharge_l",
)
_FROZEN_CASE_SETTINGS = {
    "blend": {"seed": 20260814, "max_examples": 2},
    "flow": {"seed": 20260812, "max_examples": 2},
    "ro": {"seed": 20260813, "max_examples": 2},
}
_BLEND_EXPECTED_FIELDS = {
    "alkalinity_mmol_c_l",
    "na_mmol_l",
    "cl_mmol_l",
    "ca_mmol_l",
    "mg_mmol_l",
    "k_mmol_l",
    "total_b_mmol_l",
    "sulfate_mmol_l",
    "bicarbonate_mmol_l",
    "nitrate_mmol_l",
    "phosphate_mmol_l",
}


class _UniqueKeyLoader(yaml.SafeLoader):
    pass


def _construct_mapping(
    loader: _UniqueKeyLoader, node: yaml.nodes.MappingNode, deep: bool = False
) -> dict[object, object]:
    result: dict[object, object] = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if key in result:
            raise ValueError(f"duplicate YAML key: {key}")
        result[key] = loader.construct_object(value_node, deep=deep)
    return result


_UniqueKeyLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _construct_mapping
)


def _load_yaml(contents: bytes, resource_id: str) -> dict[str, object]:
    try:
        payload = yaml.load(contents, Loader=_UniqueKeyLoader)
    except yaml.YAMLError as error:
        raise ValueError(f"{resource_id} is not valid YAML") from error
    if not isinstance(payload, dict):
        raise ValueError(f"{resource_id} must contain a mapping")
    return payload


def _exact_keys(
    payload: Mapping[object, object], expected: set[str], field_path: str
) -> None:
    observed = {str(key) for key in payload}
    if observed != expected:
        missing = sorted(expected - observed)
        extra = sorted(observed - expected)
        raise ValueError(f"{field_path} keys mismatch; missing={missing}, extra={extra}")


def _strict_number(value: object, field_path: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{field_path} must be a numeric YAML scalar")
    converted = float(value)
    if not isfinite(converted):
        raise ValueError(f"{field_path} must be finite")
    return converted


def _strict_positive_integer(value: object, field_path: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{field_path} must be a positive integer")
    return value


def _strict_numeric_mapping(
    value: object,
    field_path: str,
    *,
    expected_keys: set[str] | None = None,
    nonnegative: bool = True,
) -> dict[str, float]:
    if not isinstance(value, dict) or not value:
        raise ValueError(f"{field_path} must be a nonempty mapping")
    if any(not isinstance(key, str) or not key for key in value):
        raise ValueError(f"{field_path} keys must be nonempty strings")
    if expected_keys is not None:
        _exact_keys(value, expected_keys, field_path)
    parsed = {
        key: _strict_number(item, f"{field_path}.{key}")
        for key, item in value.items()
    }
    if nonnegative and any(item < 0.0 for item in parsed.values()):
        raise ValueError(f"{field_path} values must be nonnegative")
    return parsed


def _freeze_resource(value: object) -> object:
    if isinstance(value, Mapping):
        return MappingProxyType(
            {str(key): _freeze_resource(item) for key, item in value.items()}
        )
    if isinstance(value, list | tuple):
        return tuple(_freeze_resource(item) for item in value)
    return value


def _read_policy_bytes(kind: str, source: Path | None) -> bytes:
    if source is not None:
        return Path(source).read_bytes()
    return resources.files(RESOURCE_PACKAGE).joinpath(f"configs/{kind}.yaml").read_bytes()


def load_fixture_bytes(
    name: str, *, fixture_directory: Path | None = None
) -> tuple[bytes, str]:
    """Read one immutable verification fixture without assuming a repository layout."""
    if Path(name).name != name or name in {"", ".", ".."}:
        raise ValueError("fixture name must be one plain file name")
    contents = (
        (Path(fixture_directory) / name).read_bytes()
        if fixture_directory is not None
        else resources.files(RESOURCE_PACKAGE).joinpath(f"fixtures/{name}").read_bytes()
    )
    return contents, hashlib.sha256(contents).hexdigest()


def load_fixture(
    name: str, *, fixture_directory: Path | None = None
) -> tuple[dict[str, object], str]:
    contents, digest = load_fixture_bytes(name, fixture_directory=fixture_directory)
    return _load_yaml(contents, name), digest


def load_conservation_case_manifest(
    source: Path | None = None,
) -> tuple[Mapping[str, object], str]:
    """Load the pinned property cases only after strict provenance/domain checks."""
    if source is None:
        contents = resources.files(RESOURCE_PACKAGE).joinpath(
            "fixtures/conservation_case_manifest.yaml"
        ).read_bytes()
    else:
        contents = Path(source).read_bytes()
    payload = _load_yaml(contents, "conservation_case_manifest.yaml")
    _exact_keys(payload, {"schema_version", "generator", "cases"}, "manifest")
    if payload["schema_version"] != "1.0":
        raise ValueError("manifest.schema_version must be '1.0'")
    generator = payload["generator"]
    if not isinstance(generator, dict):
        raise ValueError("manifest.generator must be a mapping")
    _exact_keys(generator, {"name", "version", "properties"}, "manifest.generator")
    if generator["name"] != "hypothesis" or generator["version"] != "6.165.5":
        raise ValueError("manifest generator must pin hypothesis 6.165.5")
    properties = generator["properties"]
    if not isinstance(properties, dict):
        raise ValueError("manifest.generator.properties must be a mapping")
    _exact_keys(properties, set(_FROZEN_CASE_SETTINGS), "manifest.generator.properties")
    for property_id, locked in _FROZEN_CASE_SETTINGS.items():
        settings = properties[property_id]
        if not isinstance(settings, dict):
            raise ValueError(f"manifest.generator.properties.{property_id} must be a mapping")
        _exact_keys(
            settings,
            {"seed", "max_examples", "database", "deadline"},
            f"manifest.generator.properties.{property_id}",
        )
        seed = _strict_positive_integer(settings["seed"], f"{property_id}.seed")
        maximum = _strict_positive_integer(
            settings["max_examples"], f"{property_id}.max_examples"
        )
        if seed != locked["seed"] or maximum != locked["max_examples"]:
            raise ValueError(f"manifest {property_id} seed/settings are not pinned")
        if settings["database"] is not None or settings["deadline"] is not None:
            raise ValueError(f"manifest {property_id} database/deadline must be null")

    cases = payload["cases"]
    if not isinstance(cases, dict):
        raise ValueError("manifest.cases must be a mapping")
    _exact_keys(cases, set(_FROZEN_CASE_SETTINGS), "manifest.cases")
    observed_ids: set[str] = set()
    for property_id, locked in _FROZEN_CASE_SETTINGS.items():
        property_cases = cases[property_id]
        if not isinstance(property_cases, list) or len(property_cases) != locked["max_examples"]:
            raise ValueError(f"manifest.cases.{property_id} count must equal max_examples")
        for index, case in enumerate(property_cases, start=1):
            path = f"manifest.cases.{property_id}.{index - 1}"
            if not isinstance(case, dict):
                raise ValueError(f"{path} must be a mapping")
            expected_id = f"{property_id}_seed_{locked['seed']}_{index:02d}"
            case_id = case.get("id")
            if not isinstance(case_id, str) or not case_id:
                raise ValueError(f"{path}.id must be a nonempty string")
            if case_id in observed_ids:
                raise ValueError("manifest case IDs must be unique")
            observed_ids.add(case_id)
            if case_id != expected_id:
                raise ValueError(f"{path}.id must match its property seed")
            if property_id == "flow":
                _validate_flow_case(case, path)
            elif property_id == "ro":
                _validate_ro_case(case, path)
            else:
                _validate_blend_case(case, path)
    frozen = _freeze_resource(payload)
    assert isinstance(frozen, Mapping)
    return frozen, hashlib.sha256(contents).hexdigest()


def _validate_flow_case(case: dict[str, object], path: str) -> None:
    _exact_keys(
        case,
        {
            "id",
            "source_volume_l",
            "target_volume_l",
            "source_stocks_mmol",
            "target_stocks_mmol",
            "rate_l_per_hour",
            "duration_hours",
            "expected",
        },
        path,
    )
    source_volume = _strict_number(case["source_volume_l"], f"{path}.source_volume_l")
    target_volume = _strict_number(case["target_volume_l"], f"{path}.target_volume_l")
    rate = _strict_number(case["rate_l_per_hour"], f"{path}.rate_l_per_hour")
    duration = _strict_number(case["duration_hours"], f"{path}.duration_hours")
    if source_volume <= 0.0 or target_volume < 0.0 or rate <= 0.0 or duration <= 0.0:
        raise ValueError(f"{path} flow numeric domain is invalid")
    if rate * duration >= source_volume:
        raise ValueError(f"{path} flow exceeds its source volume")
    source_stocks = _strict_numeric_mapping(case["source_stocks_mmol"], f"{path}.source_stocks_mmol")
    entity_keys = set(source_stocks)
    _strict_numeric_mapping(
        case["target_stocks_mmol"],
        f"{path}.target_stocks_mmol",
        expected_keys=entity_keys,
    )
    expected = case["expected"]
    if not isinstance(expected, dict):
        raise ValueError(f"{path}.expected must be a mapping")
    _exact_keys(expected, {"volumes_l", "stocks_mmol"}, f"{path}.expected")
    _strict_numeric_mapping(
        expected["volumes_l"],
        f"{path}.expected.volumes_l",
        expected_keys={"source", "target"},
    )
    expected_stocks = expected["stocks_mmol"]
    if not isinstance(expected_stocks, dict):
        raise ValueError(f"{path}.expected.stocks_mmol must be a mapping")
    _exact_keys(expected_stocks, {"source", "target"}, f"{path}.expected.stocks_mmol")
    for compartment in ("source", "target"):
        _strict_numeric_mapping(
            expected_stocks[compartment],
            f"{path}.expected.stocks_mmol.{compartment}",
            expected_keys=entity_keys,
        )


def _validate_ro_case(case: dict[str, object], path: str) -> None:
    _exact_keys(
        case,
        {"id", "feed_volume_l", "feed_stocks_mmol", "recovery", "rejection", "expected"},
        path,
    )
    feed_volume = _strict_number(case["feed_volume_l"], f"{path}.feed_volume_l")
    recovery = _strict_number(case["recovery"], f"{path}.recovery")
    if feed_volume <= 0.0 or not 0.0 < recovery < 1.0:
        raise ValueError(f"{path} RO numeric domain is invalid")
    feed = _strict_numeric_mapping(case["feed_stocks_mmol"], f"{path}.feed_stocks_mmol")
    entities = set(feed)
    rejection = _strict_numeric_mapping(
        case["rejection"], f"{path}.rejection", expected_keys=entities
    )
    if any(value > 1.0 for value in rejection.values()):
        raise ValueError(f"{path}.rejection must be within [0, 1]")
    expected = case["expected"]
    if not isinstance(expected, dict):
        raise ValueError(f"{path}.expected must be a mapping")
    _exact_keys(
        expected,
        {"volumes_l", "permeate_stocks_mmol", "concentrate_stocks_mmol"},
        f"{path}.expected",
    )
    _strict_numeric_mapping(
        expected["volumes_l"],
        f"{path}.expected.volumes_l",
        expected_keys={"feed", "permeate", "concentrate"},
    )
    for branch in ("permeate_stocks_mmol", "concentrate_stocks_mmol"):
        _strict_numeric_mapping(
            expected[branch], f"{path}.expected.{branch}", expected_keys=entities
        )


def _validate_blend_case(case: dict[str, object], path: str) -> None:
    _exact_keys(case, {"id", "volumes_l", "expected"}, path)
    volumes = case["volumes_l"]
    if not isinstance(volumes, list) or len(volumes) != 2:
        raise ValueError(f"{path}.volumes_l must contain exactly two numbers")
    parsed_volumes = [
        _strict_number(value, f"{path}.volumes_l.{index}")
        for index, value in enumerate(volumes)
    ]
    if any(value < 0.0 for value in parsed_volumes) or sum(parsed_volumes) <= 0.0:
        raise ValueError(f"{path}.volumes_l is outside the blend domain")
    _strict_numeric_mapping(
        case["expected"],
        f"{path}.expected",
        expected_keys=_BLEND_EXPECTED_FIELDS,
    )


@dataclass(frozen=True)
class NumericalStops:
    require_finite_state: bool
    minimum_stock: float
    maximum_relative_ledger_residual: float


@dataclass(frozen=True)
class PhysicalStopPolicy:
    minimum: float | None
    maximum: float | None
    evidence_label: EvidenceLabel


@dataclass(frozen=True)
class ThresholdPolicy:
    schema_version: str
    physical_stops: Mapping[str, PhysicalStopPolicy]
    numerical_stops: NumericalStops
    sha256: str


@dataclass(frozen=True)
class VerificationPolicy:
    schema_version: str
    artifact_path_template: str
    core_acceptance_tests: tuple[int, ...]
    evidence_label: EvidenceLabel
    tolerances: Mapping[int, Mapping[str, float]]
    sha256: str


def load_threshold_policy(source: Path | None = None) -> ThresholdPolicy:
    contents = _read_policy_bytes("thresholds", source)
    payload = _load_yaml(contents, "thresholds.yaml")
    _exact_keys(
        payload,
        {"schema_version", "physical_stops", "numerical_stops"},
        "thresholds",
    )
    if payload["schema_version"] != "1.0":
        raise ValueError("thresholds.schema_version must be '1.0'")
    raw_physical = payload["physical_stops"]
    if not isinstance(raw_physical, dict):
        raise ValueError("physical_stops must be a mapping")
    _exact_keys(raw_physical, set(PHYSICAL_STOP_IDS), "physical_stops")
    parsed_physical: dict[str, PhysicalStopPolicy] = {}
    for stop_id in PHYSICAL_STOP_IDS:
        raw = raw_physical[stop_id]
        if not isinstance(raw, dict):
            raise ValueError(f"physical_stops.{stop_id} must be a mapping")
        allowed = {"minimum", "maximum", "evidence_label"}
        if not set(raw).issubset(allowed) or "evidence_label" not in raw:
            raise ValueError(f"physical_stops.{stop_id} has invalid keys")
        minimum = (
            None
            if "minimum" not in raw
            else _strict_number(raw["minimum"], f"physical_stops.{stop_id}.minimum")
        )
        maximum = (
            None
            if "maximum" not in raw
            else _strict_number(raw["maximum"], f"physical_stops.{stop_id}.maximum")
        )
        if minimum is None and maximum is None:
            raise ValueError(f"physical_stops.{stop_id} requires minimum or maximum")
        if minimum is not None and maximum is not None and minimum > maximum:
            raise ValueError(f"physical_stops.{stop_id} minimum exceeds maximum")
        try:
            label = EvidenceLabel(raw["evidence_label"])
        except ValueError as error:
            raise ValueError(f"physical_stops.{stop_id}.evidence_label is invalid") from error
        if label not in {EvidenceLabel.SYNTHETIC_ONLY, EvidenceLabel.HYPOTHESIS_PRIOR}:
            raise ValueError(
                f"physical_stops.{stop_id}.evidence_label must be weakly labeled"
            )
        parsed_physical[stop_id] = PhysicalStopPolicy(minimum, maximum, label)

    raw_numerical = payload["numerical_stops"]
    if not isinstance(raw_numerical, dict):
        raise ValueError("numerical_stops must be a mapping")
    _exact_keys(
        raw_numerical,
        {
            "require_finite_state",
            "minimum_stock",
            "maximum_relative_ledger_residual",
        },
        "numerical_stops",
    )
    if not isinstance(raw_numerical["require_finite_state"], bool):
        raise ValueError("numerical_stops.require_finite_state must be boolean")
    minimum_stock = _strict_number(
        raw_numerical["minimum_stock"], "numerical_stops.minimum_stock"
    )
    maximum_residual = _strict_number(
        raw_numerical["maximum_relative_ledger_residual"],
        "numerical_stops.maximum_relative_ledger_residual",
    )
    if (
        raw_numerical["require_finite_state"] is not True
        or minimum_stock != -1.0e-12
        or maximum_residual != 1.0e-10
    ):
        raise ValueError(
            "schema 1.0 numerical stops are locked to finite state, -1e-12 stock, "
            "and 1e-10 relative ledger residual"
        )
    return ThresholdPolicy(
        schema_version="1.0",
        physical_stops=MappingProxyType(parsed_physical),
        numerical_stops=NumericalStops(
            raw_numerical["require_finite_state"], minimum_stock, maximum_residual
        ),
        sha256=hashlib.sha256(contents).hexdigest(),
    )


_TOLERANCE_KEYS = {
    1: {"absolute"},
    2: {"absolute"},
    3: {"relative"},
    4: {"trajectory_relative", "terminal_absolute"},
    5: {"mass_blend_absolute", "sar_absolute"},
    13: {"absolute"},
    19: {"absolute"},
    20: {"absolute"},
}


def load_verification_policy(source: Path | None = None) -> VerificationPolicy:
    contents = _read_policy_bytes("verification", source)
    payload = _load_yaml(contents, "verification.yaml")
    _exact_keys(
        payload,
        {
            "schema_version",
            "artifact_path_template",
            "core_acceptance_tests",
            "evidence_label",
            "tolerances",
        },
        "verification",
    )
    if payload["schema_version"] != "1.0":
        raise ValueError("verification.schema_version must be '1.0'")
    if payload["artifact_path_template"] != "verification/test_<NN>.json":
        raise ValueError("verification artifact_path_template is unsafe or unsupported")
    raw_tests = payload["core_acceptance_tests"]
    if (
        not isinstance(raw_tests, list)
        or any(isinstance(item, bool) or not isinstance(item, int) for item in raw_tests)
        or tuple(raw_tests) != CORE_ACCEPTANCE_TESTS
    ):
        raise ValueError("core_acceptance_tests must match the canonical ordered registry")
    try:
        label = EvidenceLabel(payload["evidence_label"])
    except ValueError as error:
        raise ValueError("verification.evidence_label is invalid") from error
    if label is not EvidenceLabel.PHYSICS_CONSTRAINED:
        raise ValueError("verification.evidence_label must be physics_constrained")
    raw_tolerances = payload["tolerances"]
    if not isinstance(raw_tolerances, dict):
        raise ValueError("verification.tolerances must be a mapping")
    normalized_keys: set[int] = set()
    for key in raw_tolerances:
        if isinstance(key, bool) or not isinstance(key, int):
            raise ValueError("verification tolerance keys must be integer test IDs")
        normalized_keys.add(key)
    if normalized_keys != set(CORE_ACCEPTANCE_TESTS):
        raise ValueError("verification tolerances must cover the exact core registry")
    tolerances: dict[int, Mapping[str, float]] = {}
    for test_number in CORE_ACCEPTANCE_TESTS:
        raw = raw_tolerances[test_number]
        if not isinstance(raw, dict):
            raise ValueError(f"tolerances.{test_number} must be a mapping")
        _exact_keys(raw, _TOLERANCE_KEYS[test_number], f"tolerances.{test_number}")
        parsed = {
            str(name): _strict_number(value, f"tolerances.{test_number}.{name}")
            for name, value in raw.items()
        }
        if any(value < 0.0 for value in parsed.values()):
            raise ValueError(f"tolerances.{test_number} must be nonnegative")
        tolerances[test_number] = MappingProxyType(parsed)
    return VerificationPolicy(
        schema_version="1.0",
        artifact_path_template="verification/test_<NN>.json",
        core_acceptance_tests=CORE_ACCEPTANCE_TESTS,
        evidence_label=label,
        tolerances=MappingProxyType(tolerances),
        sha256=hashlib.sha256(contents).hexdigest(),
    )
