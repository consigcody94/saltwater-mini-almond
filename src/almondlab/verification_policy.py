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
CANONICAL_PHYSICAL_STOPS = MappingProxyType(
    {
        "concentration_mmol_l": (None, 4.0, EvidenceLabel.SYNTHETIC_ONLY),
        "ecw_ds_m": (None, 10.0, EvidenceLabel.SYNTHETIC_ONLY),
        "osmolality_osmol_kg": (None, 0.40, EvidenceLabel.SYNTHETIC_ONLY),
        "volume_l": (0.1, 1000.0, EvidenceLabel.SYNTHETIC_ONLY),
        "injury": (None, 1.0, EvidenceLabel.SYNTHETIC_ONLY),
        "containment_discharge_l": (
            None,
            0.0,
            EvidenceLabel.SYNTHETIC_ONLY,
        ),
    }
)
CANONICAL_NUMERICAL_STOPS = (True, -1.0e-12, 1.0e-10)
CANONICAL_VERIFICATION_TOLERANCES = MappingProxyType(
    {
        1: MappingProxyType({"absolute": 1.0e-10}),
        2: MappingProxyType({"absolute": 1.0e-10}),
        3: MappingProxyType({"relative": 1.0e-6}),
        4: MappingProxyType(
            {"trajectory_relative": 1.0e-5, "terminal_absolute": 1.0e-6}
        ),
        5: MappingProxyType(
            {"mass_blend_absolute": 1.0e-10, "sar_absolute": 1.0e-9}
        ),
        13: MappingProxyType({"absolute": 1.0e-6}),
        19: MappingProxyType({"absolute": 0.0}),
        20: MappingProxyType({"absolute": 1.0e-10}),
    }
)
CONSERVATION_CANDIDATE_SET_SHA256 = (
    "6dadb7aaa883e113b28c6833ac544389a79c31c21b8b452097ddca3b17ef621e"
)
FROZEN_CASE_SETTINGS = MappingProxyType(
    {
        "blend": MappingProxyType({"seed": 20260814, "max_examples": 2}),
        "flow": MappingProxyType({"seed": 20260812, "max_examples": 2}),
        "ro": MappingProxyType({"seed": 20260813, "max_examples": 2}),
    }
)
_BLEND_EXPECTED_FIELDS = frozenset(
    {
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
)


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
    if any(not isinstance(key, str) for key in payload):
        raise ValueError(f"{field_path} keys must be strings")
    observed = set(payload)
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


_MANIFEST_ENTITY_IDS = ("water", "na", "cl")
_MANIFEST_EXTREMA_SCHEMA = MappingProxyType(
    {
        "flow": MappingProxyType(
            {
                "global_relative_residual": _MANIFEST_ENTITY_IDS,
                "compartment_relative_residual": _MANIFEST_ENTITY_IDS,
                "literal_absolute_error": _MANIFEST_ENTITY_IDS,
            }
        ),
        "ro": MappingProxyType(
            {
                "conservation_absolute_residual": _MANIFEST_ENTITY_IDS,
                "literal_absolute_error": _MANIFEST_ENTITY_IDS,
            }
        ),
        "blend": MappingProxyType(
            {
                "literal_absolute_error": (
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
                )
            }
        ),
    }
)


def _schema2_stock_record(
    value: object,
    field_path: str,
    *,
    density: float,
) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ValueError(f"{field_path} must be a mapping")
    _exact_keys(value, {"volume_l", "water_mass_kg", "stocks"}, field_path)
    volume = _strict_number(value["volume_l"], f"{field_path}.volume_l")
    water = _strict_number(value["water_mass_kg"], f"{field_path}.water_mass_kg")
    if volume < 0.0 or water < 0.0 or abs(water - volume * density) > 1e-12:
        raise ValueError(f"{field_path} water mass/density identity is invalid")
    stocks = _strict_numeric_mapping(
        value["stocks"],
        f"{field_path}.stocks",
        expected_keys={"na", "cl"},
    )
    return {"volume_l": volume, "water_mass_kg": water, "stocks": stocks}


def _validate_schema2_flow_case(case: object, path: str) -> None:
    if not isinstance(case, dict):
        raise ValueError(f"{path} must be a mapping")
    _exact_keys(
        case,
        {
            "id",
            "density_kg_l",
            "source",
            "target",
            "rate_l_per_hour",
            "duration_hours",
            "expected",
        },
        path,
    )
    density = _strict_number(case["density_kg_l"], f"{path}.density_kg_l")
    if density <= 0.0:
        raise ValueError(f"{path}.density_kg_l must be positive")
    source = _schema2_stock_record(case["source"], f"{path}.source", density=density)
    _schema2_stock_record(case["target"], f"{path}.target", density=density)
    rate = _strict_number(case["rate_l_per_hour"], f"{path}.rate_l_per_hour")
    duration = _strict_number(case["duration_hours"], f"{path}.duration_hours")
    if rate <= 0.0 or duration <= 0.0 or rate * duration >= source["volume_l"]:
        raise ValueError(f"{path} flow domain is invalid or exceeds its source")
    expected = case["expected"]
    if not isinstance(expected, dict):
        raise ValueError(f"{path}.expected must be a mapping")
    _exact_keys(expected, {"source", "target"}, f"{path}.expected")
    for branch in ("source", "target"):
        _schema2_stock_record(
            expected[branch], f"{path}.expected.{branch}", density=density
        )


def _validate_schema2_ro_case(case: object, path: str) -> None:
    if not isinstance(case, dict):
        raise ValueError(f"{path} must be a mapping")
    _exact_keys(
        case,
        {"id", "density_kg_l", "feed", "parameters", "expected"},
        path,
    )
    density = _strict_number(case["density_kg_l"], f"{path}.density_kg_l")
    if density <= 0.0:
        raise ValueError(f"{path}.density_kg_l must be positive")
    _schema2_stock_record(case["feed"], f"{path}.feed", density=density)
    parameters = case["parameters"]
    if not isinstance(parameters, dict):
        raise ValueError(f"{path}.parameters must be a mapping")
    _exact_keys(parameters, {"recovery", "rejection"}, f"{path}.parameters")
    recovery = _strict_number(parameters["recovery"], f"{path}.parameters.recovery")
    if not 0.0 < recovery < 1.0:
        raise ValueError(f"{path}.parameters.recovery is outside the RO domain")
    rejection = _strict_numeric_mapping(
        parameters["rejection"],
        f"{path}.parameters.rejection",
        expected_keys={"na", "cl"},
    )
    if any(value > 1.0 for value in rejection.values()):
        raise ValueError(f"{path}.parameters.rejection must be within [0, 1]")
    expected = case["expected"]
    if not isinstance(expected, dict):
        raise ValueError(f"{path}.expected must be a mapping")
    _exact_keys(expected, {"permeate", "concentrate"}, f"{path}.expected")
    for branch in ("permeate", "concentrate"):
        _schema2_stock_record(
            expected[branch], f"{path}.expected.{branch}", density=density
        )


def load_conservation_case_manifest(
    source: Path | None = None,
) -> tuple[Mapping[str, object], str]:
    """Load the exact frozen schema-1 property manifest and candidate digest."""

    contents = (
        resources.files(RESOURCE_PACKAGE)
        .joinpath("fixtures/conservation_case_manifest.yaml")
        .read_bytes()
        if source is None
        else Path(source).read_bytes()
    )
    payload = _load_yaml(contents, "conservation_case_manifest.yaml")
    _exact_keys(
        payload,
        {"schema_version", "generator", "extrema_schema", "cases"},
        "manifest",
    )
    if payload["schema_version"] != "1.0":
        raise ValueError("manifest.schema_version must be '1.0'")
    generator = payload["generator"]
    if not isinstance(generator, dict):
        raise ValueError("manifest.generator must be a mapping")
    _exact_keys(
        generator,
        {
            "name",
            "version",
            "phase",
            "strategy",
            "candidate_set_sha256",
            "shrinking",
            "properties",
        },
        "manifest.generator",
    )
    candidate_bytes = (
        resources.files(RESOURCE_PACKAGE)
        .joinpath("fixtures/conservation_case_manifest.candidates.json")
        .read_bytes()
    )
    candidate_digest = hashlib.sha256(candidate_bytes).hexdigest()
    if candidate_digest != CONSERVATION_CANDIDATE_SET_SHA256:
        raise ValueError("manifest frozen candidate-set bytes are not canonical")
    if (
        generator["name"] != "hypothesis"
        or generator["version"] != "6.165.5"
        or generator["phase"] != "generate_only"
        or generator["strategy"] != "sampled_from_frozen_candidate_set"
        or generator["candidate_set_sha256"]
        != CONSERVATION_CANDIDATE_SET_SHA256
        or generator["shrinking"] is not False
    ):
        raise ValueError(
            "manifest generator phase, strategy, candidate digest, and shrinking are locked"
        )
    properties = generator["properties"]
    if not isinstance(properties, dict):
        raise ValueError("manifest.generator.properties must be a mapping")
    _exact_keys(properties, set(FROZEN_CASE_SETTINGS), "manifest.generator.properties")
    for property_id, expected in FROZEN_CASE_SETTINGS.items():
        value = properties[property_id]
        if not isinstance(value, dict):
            raise ValueError(f"manifest generator {property_id} must be a mapping")
        _exact_keys(value, {"seed", "max_examples"}, f"generator.{property_id}")
        if value != expected:
            raise ValueError(f"manifest generator {property_id} settings are locked")

    extrema = payload["extrema_schema"]
    if not isinstance(extrema, dict):
        raise ValueError("manifest.extrema_schema must be a mapping")
    _exact_keys(extrema, set(_MANIFEST_EXTREMA_SCHEMA), "manifest.extrema_schema")
    for property_id, branches in _MANIFEST_EXTREMA_SCHEMA.items():
        received = extrema[property_id]
        if not isinstance(received, dict):
            raise ValueError(f"manifest extrema {property_id} must be a mapping")
        _exact_keys(received, set(branches), f"extrema_schema.{property_id}")
        for branch, expected_names in branches.items():
            values = received[branch]
            if (
                not isinstance(values, list)
                or tuple(values) != tuple(expected_names)
            ):
                raise ValueError(
                    f"manifest extrema {property_id}.{branch} must cover the exact canonical set"
                )

    cases = payload["cases"]
    if not isinstance(cases, dict):
        raise ValueError("manifest.cases must be a mapping")
    _exact_keys(cases, {"flow", "ro", "blend"}, "manifest.cases")
    observed_ids: set[str] = set()
    for property_id in ("flow", "ro", "blend"):
        values = cases[property_id]
        expected_settings = FROZEN_CASE_SETTINGS[property_id]
        if not isinstance(values, list) or len(values) != expected_settings["max_examples"]:
            raise ValueError(f"manifest.cases.{property_id} count is locked")
        for index, case in enumerate(values, start=1):
            path = f"manifest.cases.{property_id}.{index - 1}"
            if not isinstance(case, dict):
                raise ValueError(f"{path} must be a mapping")
            expected_id = f"{property_id}_seed_{expected_settings['seed']}_{index:02d}"
            if case.get("id") != expected_id or expected_id in observed_ids:
                raise ValueError(f"{path}.id must be the exact unique seeded ID")
            observed_ids.add(expected_id)
            if property_id == "flow":
                _validate_schema2_flow_case(case, path)
            elif property_id == "ro":
                _validate_schema2_ro_case(case, path)
            else:
                _validate_blend_case(case, path)
    frozen = _freeze_resource(payload)
    assert isinstance(frozen, Mapping)
    return frozen, hashlib.sha256(contents).hexdigest()


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


def validate_threshold_policy(policy: ThresholdPolicy) -> None:
    """Revalidate a complete schema-1 object against code-owned authority."""

    if not isinstance(policy, ThresholdPolicy) or policy.schema_version != "1.0":
        raise ValueError("threshold policy must be the canonical schema 1.0 record")
    if tuple(policy.physical_stops) != PHYSICAL_STOP_IDS:
        raise ValueError("threshold physical-stop registry is not canonical")
    for stop_id, expected in CANONICAL_PHYSICAL_STOPS.items():
        stop = policy.physical_stops.get(stop_id)
        if not isinstance(stop, PhysicalStopPolicy) or (
            stop.minimum,
            stop.maximum,
            stop.evidence_label,
        ) != expected:
            raise ValueError(f"physical stop {stop_id} is not locked to schema 1.0")
    numerical = policy.numerical_stops
    if not isinstance(numerical, NumericalStops) or (
        numerical.require_finite_state,
        numerical.minimum_stock,
        numerical.maximum_relative_ledger_residual,
    ) != CANONICAL_NUMERICAL_STOPS:
        raise ValueError("schema 1.0 numerical stops are not locked")
    if (
        not isinstance(policy.sha256, str)
        or len(policy.sha256) != 64
        or any(character not in "0123456789abcdef" for character in policy.sha256)
    ):
        raise ValueError("threshold policy hash must be a lowercase SHA-256 digest")


def validate_verification_policy(policy: VerificationPolicy) -> None:
    """Revalidate every normalized schema-1 verification field exactly."""

    if not isinstance(policy, VerificationPolicy) or policy.schema_version != "1.0":
        raise ValueError("verification policy must be canonical schema 1.0")
    if policy.artifact_path_template != "verification/test_<NN>.json":
        raise ValueError("verification artifact template is not canonical")
    if policy.core_acceptance_tests != CORE_ACCEPTANCE_TESTS:
        raise ValueError("verification registry is not canonical")
    if policy.evidence_label is not EvidenceLabel.PHYSICS_CONSTRAINED:
        raise ValueError("verification evidence label is not canonical")
    if tuple(policy.tolerances) != CORE_ACCEPTANCE_TESTS:
        raise ValueError("verification tolerance registry is not canonical")
    for test_number, expected in CANONICAL_VERIFICATION_TOLERANCES.items():
        if dict(policy.tolerances.get(test_number, {})) != dict(expected):
            raise ValueError(
                f"verification tolerance {test_number} is not locked to schema 1.0"
            )
    if (
        not isinstance(policy.sha256, str)
        or len(policy.sha256) != 64
        or any(character not in "0123456789abcdef" for character in policy.sha256)
    ):
        raise ValueError("verification policy hash must be a lowercase SHA-256 digest")


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
    policy = ThresholdPolicy(
        schema_version="1.0",
        physical_stops=MappingProxyType(parsed_physical),
        numerical_stops=NumericalStops(
            raw_numerical["require_finite_state"], minimum_stock, maximum_residual
        ),
        sha256=hashlib.sha256(contents).hexdigest(),
    )
    validate_threshold_policy(policy)
    return policy


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
    policy = VerificationPolicy(
        schema_version="1.0",
        artifact_path_template="verification/test_<NN>.json",
        core_acceptance_tests=CORE_ACCEPTANCE_TESTS,
        evidence_label=label,
        tolerances=MappingProxyType(tolerances),
        sha256=hashlib.sha256(contents).hexdigest(),
    )
    validate_verification_policy(policy)
    return policy
