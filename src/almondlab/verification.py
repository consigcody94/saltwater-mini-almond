"""Atomic scientific verification records and core acceptance oracles."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import tempfile
from collections.abc import Mapping
from dataclasses import dataclass
from importlib.metadata import PackageNotFoundError, version
from math import exp, isfinite
from pathlib import Path
from types import MappingProxyType
from typing import Literal

import yaml

from almondlab.chemistry import BlendMeasurement, blend_by_volume, sodium_adsorption_ratio
from almondlab.contracts import ConservedEntity, DataOrigin, ECKind, EvidenceLabel
from almondlab.errors import AlmondLabError
from almondlab.hydraulics import HydraulicInputs, hydraulic_uptake
from almondlab.mass_balance import ExternalFlux, Flow, NetworkState, audit_ledger, step_state
from almondlab.schemas import WaterBatch, WaterChemistry
from almondlab.treatment import ro_split


NEGATIVE_TOLERANCE = 1e-12
LEDGER_RESIDUAL_TOLERANCE = 1e-10
_CORE_TESTS = (1, 2, 3, 4, 5, 13, 19, 20)


def _freeze_json(value: object) -> object:
    if isinstance(value, Mapping):
        return MappingProxyType({str(key): _freeze_json(item) for key, item in value.items()})
    if isinstance(value, list | tuple):
        return tuple(_freeze_json(item) for item in value)
    return value


def _json_value(value: object, field_path: str) -> object:
    if isinstance(value, Mapping):
        return {str(key): _json_value(item, f"{field_path}.{key}") for key, item in value.items()}
    if isinstance(value, tuple):
        return [_json_value(item, field_path) for item in value]
    if isinstance(value, EvidenceLabel):
        return value.value
    if isinstance(value, float) and not isfinite(value):
        raise ValueError(f"{field_path} must not contain nonfinite numbers")
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    raise ValueError(f"{field_path} is not JSON serializable")


@dataclass(frozen=True)
class VerificationRecord:
    """Immutable, labeled record of one independently specified acceptance oracle."""

    acceptance_test: int
    fixture_sha256: str
    observed_value: object
    oracle: object
    tolerance: object
    passed: bool
    code_version: str
    evidence_label: EvidenceLabel
    fixture_sha256s: Mapping[str, str] | None = None
    validity: Literal["valid", "invalid"] = "valid"
    censored: bool = False
    reason_code: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.evidence_label, EvidenceLabel):
            raise TypeError("evidence_label must be an EvidenceLabel")
        if self.validity == "invalid" and self.passed:
            raise ValueError("invalid record cannot be marked passed")
        object.__setattr__(self, "observed_value", _freeze_json(self.observed_value))
        object.__setattr__(self, "oracle", _freeze_json(self.oracle))
        object.__setattr__(self, "tolerance", _freeze_json(self.tolerance))
        hashes = {"primary": self.fixture_sha256} if self.fixture_sha256s is None else dict(self.fixture_sha256s)
        object.__setattr__(self, "fixture_sha256s", MappingProxyType(hashes))

    def validate(self) -> None:
        if self.acceptance_test not in range(1, 23):
            raise ValueError("acceptance_test must be in [1, 22]")
        if len(self.fixture_sha256) != 64 or any(
            character not in "0123456789abcdefABCDEF" for character in self.fixture_sha256
        ):
            raise ValueError("fixture_sha256 must be an exact SHA-256 hex digest")
        for name, digest in self.fixture_sha256s.items():
            if not name or len(digest) != 64 or any(character not in "0123456789abcdefABCDEF" for character in digest):
                raise ValueError("fixture_sha256s must contain exact named SHA-256 hex digests")
        if not self.code_version.strip():
            raise ValueError("code_version must be supplied from metadata or an explicit unavailable gate")
        if self.validity not in {"valid", "invalid"}:
            raise ValueError("validity must be valid or invalid")
        if self.censored and self.validity != "valid":
            raise ValueError("an invalid numerical run cannot be a physical censoring result")
        if (self.censored or self.validity == "invalid") and not self.reason_code:
            raise ValueError("censored or invalid records require a reason_code")
        if self.validity == "invalid" and self.passed:
            raise ValueError("invalid record cannot be marked passed")
        _json_value(self.observed_value, "observed_value")
        _json_value(self.oracle, "oracle")
        _json_value(self.tolerance, "tolerance")

    def to_dict(self) -> dict[str, object]:
        self.validate()
        return {
            "acceptance_test": self.acceptance_test,
            "fixture_sha256": self.fixture_sha256.lower(),
            "fixture_sha256s": {name: digest.lower() for name, digest in self.fixture_sha256s.items()},
            "observed_value": _json_value(self.observed_value, "observed_value"),
            "oracle": _json_value(self.oracle, "oracle"),
            "tolerance": _json_value(self.tolerance, "tolerance"),
            "passed": self.passed,
            "code_version": self.code_version,
            "evidence_label": self.evidence_label.value,
            "validity": self.validity,
            "censored": self.censored,
            "reason_code": self.reason_code,
        }


@dataclass(frozen=True)
class RunStopStatus:
    """A numerical invalidation or a valid physical censoring outcome."""

    valid: bool
    censored: bool
    reason_code: str | None


@dataclass(frozen=True)
class PhysicalStop:
    """A fixture-labeled physical boundary, distinct from numerical validity."""

    minimum: float | None
    maximum: float | None
    evidence_label: EvidenceLabel


@dataclass
class AnalysisBoundary:
    """Minimal executable analysis boundary that only admits validated chemistry."""

    accepted_records: int = 0

    def submit(
        self, source: WaterBatch, measurement: BlendMeasurement
    ) -> None:
        blend_by_volume([source], [1.0], measurement=measurement)
        self.accepted_records += 1


def load_physical_stops(path: Path) -> Mapping[str, PhysicalStop]:
    """Load bounded, weakly labeled physical fixture stops from YAML."""
    payload = yaml.safe_load(path.read_bytes())
    if not isinstance(payload, dict) or not isinstance(payload.get("physical_stops"), dict):
        raise ValueError("physical_stops configuration is required")
    stops: dict[str, PhysicalStop] = {}
    for name, raw in payload["physical_stops"].items():
        if not isinstance(raw, dict):
            raise ValueError(f"physical_stops.{name} must be a mapping")
        try:
            label = EvidenceLabel(raw["evidence_label"])
        except (KeyError, ValueError) as error:
            raise ValueError(f"physical_stops.{name}.evidence_label is invalid") from error
        if label not in {EvidenceLabel.SYNTHETIC_ONLY, EvidenceLabel.HYPOTHESIS_PRIOR}:
            raise ValueError(f"physical_stops.{name}.evidence_label must be synthetic_only or hypothesis_prior")
        minimum = raw.get("minimum")
        maximum = raw.get("maximum")
        if minimum is None and maximum is None:
            raise ValueError(f"physical_stops.{name} requires minimum or maximum")
        if minimum is not None and not isfinite(float(minimum)):
            raise ValueError(f"physical_stops.{name}.minimum must be finite")
        if maximum is not None and not isfinite(float(maximum)):
            raise ValueError(f"physical_stops.{name}.maximum must be finite")
        if minimum is not None and maximum is not None and float(minimum) > float(maximum):
            raise ValueError(f"physical_stops.{name} minimum exceeds maximum")
        stops[str(name)] = PhysicalStop(
            None if minimum is None else float(minimum),
            None if maximum is None else float(maximum),
            label,
        )
    return MappingProxyType(stops)


def evaluate_run_stops(
    *,
    numerical_values: Mapping[str, float],
    stocks: Mapping[str, float],
    ledger_relative_residuals: Mapping[str, float],
    physical_values: Mapping[str, float],
    physical_stops: Mapping[str, PhysicalStop],
) -> RunStopStatus:
    """Keep numerical invalidity separate from configured physical censoring."""
    if any(not isfinite(float(value)) for value in numerical_values.values()):
        return RunStopStatus(False, False, "NONFINITE_STATE")
    if any(not isfinite(float(value)) for value in stocks.values()):
        return RunStopStatus(False, False, "NONFINITE_STOCK")
    if any(not isfinite(float(value)) for value in ledger_relative_residuals.values()):
        return RunStopStatus(False, False, "NONFINITE_LEDGER_RESIDUAL")
    if any(float(value) < -NEGATIVE_TOLERANCE for value in stocks.values()):
        return RunStopStatus(False, False, "STOCK_BELOW_NUMERICAL_TOLERANCE")
    if any(abs(float(value)) > LEDGER_RESIDUAL_TOLERANCE for value in ledger_relative_residuals.values()):
        return RunStopStatus(False, False, "LEDGER_RESIDUAL_EXCEEDED")
    for name, stop in physical_stops.items():
        value = physical_values.get(name)
        if value is None:
            continue
        if not isfinite(float(value)):
            return RunStopStatus(False, False, "NONFINITE_STATE")
        if stop.minimum is not None and float(value) <= stop.minimum:
            return RunStopStatus(True, True, f"PHYSICAL_STOP_{name.upper()}_MINIMUM")
        if stop.maximum is not None and float(value) >= stop.maximum:
            return RunStopStatus(True, True, f"PHYSICAL_STOP_{name.upper()}_MAXIMUM")
    return RunStopStatus(True, False, None)


def write_verification_record(target: Path, record: VerificationRecord) -> Path:
    """Validate fully, then atomically promote one JSON verification artifact."""
    payload = json.dumps(record.to_dict(), sort_keys=True, indent=2, allow_nan=False) + "\n"
    target.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{target.name}.", suffix=".tmp", dir=target.parent
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, target)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise
    return target


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _fixture(name: str) -> tuple[Path, dict[str, object], str]:
    path = _repo_root() / "tests" / "fixtures" / name
    contents = path.read_bytes()
    return path, yaml.safe_load(contents), hashlib.sha256(contents).hexdigest()


def _code_version() -> str:
    try:
        return f"package:{version('saltwater-mini-almond')}"
    except PackageNotFoundError:
        try:
            completed = subprocess.run(
                ["git", "rev-parse", "--verify", "HEAD"],
                cwd=_repo_root(), capture_output=True, text=True, check=True
            )
            return f"git:{completed.stdout.strip()}"
        except (OSError, subprocess.CalledProcessError):
            return "unavailable:package-metadata-and-git-unavailable"


def _state(initial: Mapping[str, object]) -> NetworkState:
    return NetworkState.from_dict(
        initial["volumes_l"], initial["stocks_mmol"]  # type: ignore[arg-type]
    )


def _record(
    acceptance_test: int, fixture_sha256: str, observed: object, oracle: object,
    tolerance: object, passed: bool, *, reason_code: str | None = None,
    censored: bool = False, fixture_sha256s: Mapping[str, str] | None = None,
) -> VerificationRecord:
    return VerificationRecord(
        acceptance_test=acceptance_test,
        fixture_sha256=fixture_sha256,
        observed_value=observed,
        oracle=oracle,
        tolerance=tolerance,
        passed=passed,
        code_version=_code_version(),
        evidence_label=EvidenceLabel.PHYSICS_CONSTRAINED,
        fixture_sha256s=fixture_sha256s,
        reason_code=reason_code,
        censored=censored,
    )


def _acceptance_01() -> VerificationRecord:
    _, fixture, digest = _fixture("water_one_day.yaml")
    before = _state(fixture["initial"])  # type: ignore[arg-type]
    flow = Flow(**fixture["flow"])  # type: ignore[arg-type]
    result = step_state(before, [flow], [], float(fixture["duration_hours"]))
    audit = audit_ledger(before, result.state, result.ledger)
    expected = fixture["expected_volumes_l"]
    stock_error = max(abs(result.state.volumes_l[name] - value) for name, value in expected.items())  # type: ignore[union-attr]
    residual = max(audit.relative_residuals.values())
    observed = max(stock_error, residual)
    return _record(1, digest, observed, 0.0, 1e-10, observed <= 1e-10)


def _acceptance_02() -> VerificationRecord:
    _, fixture, digest = _fixture("ions_conservative.yaml")
    before = _state(fixture["initial"])  # type: ignore[arg-type]
    result = step_state(before, [Flow(**fixture["flow"])], [], float(fixture["duration_hours"]))  # type: ignore[arg-type]
    audit = audit_ledger(before, result.state, result.ledger)
    expected = fixture["expected_stocks_mmol"]
    stock_error = max(
        abs(result.state.stocks_mmol[compartment][entity] - value)
        for compartment, stocks in expected.items()  # type: ignore[union-attr]
        for entity, value in stocks.items()
    )
    residual = max(audit.relative_residuals.values())
    observed = max(stock_error, residual)
    return _record(2, digest, observed, 0.0, 1e-10, observed <= 1e-10)


def _acceptance_03() -> VerificationRecord:
    _, fixture, digest = _fixture("no_purge.yaml")
    expected_stop = float(fixture["volume"]) * float(fixture["c0"]) / float(fixture["m_dot"])
    stop_error = abs(float(fixture["expected_stop_hours"]) - expected_stop) / expected_stop
    before = _state(fixture["initial"])  # type: ignore[arg-type]
    result = step_state(before, [], [ExternalFlux(**fixture["source_flux"])], expected_stop)  # type: ignore[arg-type]
    observed_concentration = result.state.concentration("tank", "na")
    oracle_concentration = float(fixture["c0"]) + float(fixture["m_dot"]) * expected_stop / float(fixture["volume"])
    concentration_error = abs(observed_concentration - oracle_concentration)
    observed = max(stop_error, concentration_error)
    stop = evaluate_run_stops(
        numerical_values={"concentration": observed_concentration},
        stocks={"na": result.state.total_stock("na")},
        ledger_relative_residuals=audit_ledger(before, result.state, result.ledger).relative_residuals,
        physical_values={"concentration_mmol_l": observed_concentration},
        physical_stops=load_physical_stops(_repo_root() / "configs" / "thresholds.yaml"),
    )
    return _record(
        3,
        digest,
        observed,
        0.0,
        1e-6,
        observed <= 1e-6 and stop.valid and stop.censored,
        censored=stop.censored,
        reason_code=stop.reason_code,
    )


def _acceptance_04() -> VerificationRecord:
    _, fixture, digest = _fixture("sufficient_purge.yaml")
    before = _state(fixture["initial"])  # type: ignore[arg-type]
    sample_hours = float(fixture["sample_hours"])
    samples = int(fixture["samples"])
    state = before
    ledger = []
    relative_errors = []
    for index in range(1, samples + 1):
        result = step_state(state, [], [ExternalFlux(**fixture["influx"]), ExternalFlux(**fixture["purge_flux"])], sample_hours)  # type: ignore[arg-type]
        state = result.state
        ledger.extend(result.ledger)
        time = index * sample_hours
        c_ss = float(fixture["c_in"]) + float(fixture["m_dot"]) / float(fixture["purge"])
        oracle = c_ss + (float(fixture["c0"]) - c_ss) * exp(-float(fixture["purge"]) * time / float(fixture["volume"]))
        relative_errors.append(abs(state.concentration("tank", "na") - oracle) / max(abs(oracle), 1e-30))
    terminal_ratio = (state.concentration("tank", "na") - c_ss) / (float(fixture["c0"]) - c_ss)
    observed = {
        "trajectory_relative_error": max(relative_errors),
        "terminal_exponential_error": abs(terminal_ratio - exp(-12.0)),
    }
    tolerance = {"trajectory_relative_error": 1e-5, "terminal_exponential_error": 1e-6}
    passed = observed["trajectory_relative_error"] <= 1e-5 and observed["terminal_exponential_error"] <= 1e-6
    return _record(4, digest, observed, {"trajectory_relative_error": 0.0, "terminal_exponential_error": 0.0}, tolerance, passed)


def _chemistry_sources(fixture: Mapping[str, object]) -> tuple[list[WaterBatch], BlendMeasurement]:
    blend = fixture["blend"]  # type: ignore[index]
    sources = [
        WaterBatch(water_batch_id=f"source-{suffix}", chemistry=WaterChemistry(**payload), data_origin=DataOrigin.SYNTHETIC, evidence_label=EvidenceLabel.SYNTHETIC_ONLY, schema_version="1.0")
        for suffix, payload in (("a", blend["source_a"]), ("b", blend["source_b"]))
    ]
    measurement = BlendMeasurement(measurement_id="acceptance-blend", ec_kind=ECKind.ECW, ec_ds_m=7.2, temperature_k=298.15, measured_osmolality_osmol_kg=0.185, ph=7.5, data_origin=DataOrigin.SYNTHETIC, evidence_label=EvidenceLabel.SYNTHETIC_ONLY)
    return sources, measurement


def _acceptance_05() -> VerificationRecord:
    _, fixture, digest = _fixture("chemistry_handcheck.yaml")
    sources, measurement = _chemistry_sources(fixture)
    blend = fixture["blend"]  # type: ignore[index]
    result = blend_by_volume(sources, blend["volumes_l"], measurement=measurement)
    mass_error = max(abs(getattr(result.chemistry, field) - value) for field, value in blend["expected"].items())
    observed_sar = sodium_adsorption_ratio(10.0, 4.0, 2.0)
    sar_error = abs(observed_sar - 5.773502692)
    try:
        ro_split(1.0, {"na": 1.0}, 0.5, {"ECw": 0.5})
    except AlmondLabError as error:
        ec_rejected = error.code == "RO_EC_REJECTION_FORBIDDEN"
    else:
        ec_rejected = False
    observed = {
        "mass_blend_error": mass_error,
        "sar": observed_sar,
        "ec_to_mass_rejected": ec_rejected,
    }
    passed = mass_error <= 1e-10 and sar_error <= 1e-9 and ec_rejected
    return _record(5, digest, observed, {"mass_blend_error": 0.0, "sar": 5.773502692, "ec_to_mass_rejected": True}, {"mass_blend_error": 1e-10, "sar": 1e-9}, passed)


def _acceptance_13() -> VerificationRecord:
    _, fixture, digest = _fixture("perfect_na_exclusion.yaml")
    fresh = hydraulic_uptake(HydraulicInputs(osmolality_osmol_kg=float(fixture["fresh_osmolality_osmol_kg"]), **{key: value for key, value in fixture.items() if key not in {"fresh_osmolality_osmol_kg", "saline_osmolality_osmol_kg"}}))
    saline = hydraulic_uptake(HydraulicInputs(osmolality_osmol_kg=float(fixture["saline_osmolality_osmol_kg"]), **{key: value for key, value in fixture.items() if key not in {"fresh_osmolality_osmol_kg", "saline_osmolality_osmol_kg"}}))
    ratio = saline.actual_l_day / fresh.actual_l_day
    observed = {
        "fresh_l_day": fresh.actual_l_day,
        "saline_l_day": saline.actual_l_day,
        "ratio": ratio,
    }
    oracle = {"fresh_l_day": 0.888212, "saline_l_day": 0.455696, "ratio": 0.513049}
    error = max(abs(observed[key] - oracle[key]) for key in oracle)
    return _record(13, digest, observed, oracle, 1e-6, error <= 1e-6)


def _acceptance_19() -> VerificationRecord:
    _, fixture, digest = _fixture("chemistry_handcheck.yaml")
    source_payload = fixture["blend"]["source_a"]  # type: ignore[index]
    boundary = AnalysisBoundary()
    cases: list[dict[str, object]] = []
    for source_kind in ECKind:
        for measurement_kind in ECKind:
            if source_kind is measurement_kind:
                continue
            payload = dict(source_payload)
            payload["ec_kind"] = source_kind
            source = WaterBatch(water_batch_id="ec-source", chemistry=WaterChemistry(**payload), data_origin=DataOrigin.SYNTHETIC, evidence_label=EvidenceLabel.SYNTHETIC_ONLY, schema_version="1.0")
            measurement = BlendMeasurement(measurement_id="ec-substitution", ec_kind=measurement_kind, ec_ds_m=1.0, temperature_k=298.15, measured_osmolality_osmol_kg=0.1, ph=7.0, data_origin=DataOrigin.SYNTHETIC, evidence_label=EvidenceLabel.SYNTHETIC_ONLY)
            try:
                boundary.submit(source, measurement)
            except AlmondLabError as error:
                cases.append(
                    {
                        "source_ec_kind": source_kind.value,
                        "measurement_ec_kind": measurement_kind.value,
                        "code": error.code,
                    }
                )
            else:
                cases.append(
                    {
                        "source_ec_kind": source_kind.value,
                        "measurement_ec_kind": measurement_kind.value,
                        "code": "ACCEPTED",
                    }
                )
    expected_substitutions = 6
    observed = {"cases": cases, "records_reached_analysis": boundary.accepted_records}
    oracle = {"rejected_substitutions": expected_substitutions, "records_reached_analysis": 0, "required_code": "EC_TYPE_MISMATCH"}
    passed = (
        len(cases) == expected_substitutions
        and boundary.accepted_records == 0
        and all(case["code"] == "EC_TYPE_MISMATCH" for case in cases)
    )
    return _record(19, digest, observed, oracle, 0.0, passed)


def _acceptance_20() -> VerificationRecord:
    _, fixture, digest = _fixture("all_conserved_entities.yaml")
    _, ions_fixture, ions_digest = _fixture("ions_conservative.yaml")
    _, chemistry_fixture, chemistry_digest = _fixture("chemistry_handcheck.yaml")
    before = _state(fixture["initial"])  # type: ignore[arg-type]
    result = step_state(
        before,
        [Flow(**fixture["flow"])],  # type: ignore[arg-type]
        [],
        float(fixture["duration_hours"]),
    )
    audit = audit_ledger(before, result.state, result.ledger)
    entities = dict(before.stocks_mmol["source"])
    ro = ro_split(
        float(fixture["ro"]["feed_volume_l"]),  # type: ignore[index]
        entities,
        float(fixture["ro"]["recovery"]),  # type: ignore[index]
        {entity: float(fixture["ro"]["rejection"]) for entity in entities},  # type: ignore[index]
    )
    ions_before = _state(ions_fixture["initial"])  # type: ignore[arg-type]
    ions_result = step_state(
        ions_before,
        [Flow(**ions_fixture["flow"])],  # type: ignore[arg-type]
        [],
        float(ions_fixture["duration_hours"]),
    )
    ions_audit = audit_ledger(ions_before, ions_result.state, ions_result.ledger)
    sources, measurement = _chemistry_sources(chemistry_fixture)
    blend_data = chemistry_fixture["blend"]  # type: ignore[index]
    blend = blend_by_volume(sources, blend_data["volumes_l"], measurement=measurement)
    blend_bounds = {
        field: abs(getattr(blend.chemistry, field) - value)
        for field, value in blend_data["expected"].items()
    }
    state_values = list(result.state.all_values())
    stop = evaluate_run_stops(
        numerical_values={f"value_{index}": value for index, value in enumerate(state_values)},
        stocks={entity: result.state.total_stock(entity) for entity in entities},
        ledger_relative_residuals=audit.relative_residuals,
        physical_values={},
        physical_stops=load_physical_stops(_repo_root() / "configs" / "thresholds.yaml"),
    )
    entity_observed = {
        "water": {
            "transfer_residual": audit.relative_residuals["water"],
            "ro_feed_permeate_concentrate_residual": abs(
                ro.permeate_volume_l + ro.concentrate_volume_l - ro.feed_volume_l
            ),
        },
        **{
            entity: {
                "transfer_residual": audit.relative_residuals[entity],
                "ro_feed_permeate_concentrate_residual": abs(
                    ro.permeate_stock_mmol[entity]
                    + ro.concentrate_stock_mmol[entity]
                    - stock
                ),
            }
            for entity, stock in entities.items()
        },
    }
    entity_oracle = {
        entity: {
            "transfer_residual": 0.0,
            "ro_feed_permeate_concentrate_residual": 0.0,
        }
        for entity in entity_observed
    }
    entity_tolerance = {
        entity: {
            "transfer_residual": 1e-10,
            "ro_feed_permeate_concentrate_residual": 1e-10,
        }
        for entity in entity_observed
    }
    observed = {
        "minimum_state": min(state_values),
        "entities": entity_observed,
        "water_residual": entity_observed["water"]["ro_feed_permeate_concentrate_residual"],
        "ions_fixture_transfer_residual": max(ions_audit.relative_residuals.values()),
        "blend_bounds": blend_bounds,
        "registered_entities": len(entity_observed),
    }
    passed = (
        stop.valid
        and not stop.censored
        and observed["minimum_state"] >= -1e-12
        and all(
            value <= 1e-10
            for measurements in entity_observed.values()
            for value in measurements.values()
        )
        and observed["ions_fixture_transfer_residual"] <= 1e-10
        and all(value <= 1e-10 for value in blend_bounds.values())
        and set(entity_observed) == {entity.value for entity in ConservedEntity}
    )
    return _record(
        20,
        digest,
        observed,
        {"minimum_state": -1e-12, "entities": entity_oracle, "blend_bounds": {field: 0.0 for field in blend_bounds}},
        {"minimum_state": -1e-12, "entities": entity_tolerance, "blend_bounds": {field: 1e-10 for field in blend_bounds}},
        passed,
        fixture_sha256s={
            "all_conserved_entities.yaml": digest,
            "ions_conservative.yaml": ions_digest,
            "chemistry_handcheck.yaml": chemistry_digest,
        },
    )


def run_core_acceptance(run_directory: Path) -> tuple[VerificationRecord, ...]:
    """Run only the eight core-owned acceptance oracles into a caller-owned run directory."""
    records = tuple(function() for function in (_acceptance_01, _acceptance_02, _acceptance_03, _acceptance_04, _acceptance_05, _acceptance_13, _acceptance_19, _acceptance_20))
    if tuple(record.acceptance_test for record in records) != _CORE_TESTS:
        raise RuntimeError("core acceptance registry is incomplete")
    for record in records:
        write_verification_record(run_directory / "verification" / f"test_{record.acceptance_test:02d}.json", record)
    return records
