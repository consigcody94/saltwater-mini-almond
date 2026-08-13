"""Atomic scientific verification records and core acceptance oracles."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import tempfile
from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict, dataclass, field
from importlib.metadata import PackageNotFoundError, version
from math import exp, isfinite
from pathlib import Path
from types import MappingProxyType
from typing import Literal

from almondlab.chemistry import (
    BlendMeasurement,
    blend_by_volume,
    charge_balance_error,
    sodium_adsorption_ratio,
)
from almondlab.contracts import ConservedEntity, DataOrigin, ECKind, EvidenceLabel
from almondlab.errors import AlmondLabError
from almondlab.hydraulics import HydraulicInputs, hydraulic_uptake
from almondlab.mass_balance import (
    BalanceAudit,
    ExternalFlux,
    Flow,
    LedgerEntry,
    NetworkState,
    StepResult,
    audit_ledger,
    step_state,
)
from almondlab.schemas import WaterBatch, WaterChemistry
from almondlab.treatment import ROResult, ro_split
from almondlab.verification_policy import (
    CORE_ACCEPTANCE_TESTS,
    NumericalStops,
    PhysicalStopPolicy,
    load_conservation_case_manifest,
    load_fixture,
    load_threshold_policy,
    load_verification_policy,
)


_CORE_TESTS = CORE_ACCEPTANCE_TESTS


def _freeze_json(value: object) -> object:
    if isinstance(value, Mapping):
        return MappingProxyType(
            {str(key): _freeze_json(item) for key, item in value.items()}
        )
    if isinstance(value, list | tuple):
        return tuple(_freeze_json(item) for item in value)
    return value


def _json_value(value: object, field_path: str) -> object:
    if isinstance(value, Mapping):
        return {
            str(key): _json_value(item, f"{field_path}.{key}")
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [_json_value(item, field_path) for item in value]
    if isinstance(value, EvidenceLabel):
        return value.value
    if isinstance(value, float) and not isfinite(value):
        raise ValueError(f"{field_path} must not contain nonfinite numbers")
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    raise ValueError(f"{field_path} is not JSON serializable")


def _leaf(tree: object, key: object) -> object:
    return tree[key] if isinstance(tree, Mapping) else tree  # type: ignore[index]


def _json_scalar_kind(value: object) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, (int, float)):
        return "number"
    if isinstance(value, str):
        return "string"
    return f"unsupported:{type(value).__qualname__}"


def _evaluate_comparison(
    observed: object,
    oracle: object,
    tolerance: object,
    comparison: object,
    *,
    field_path: str = "comparison",
) -> bool:
    """Evaluate one complete oracle tree; no acceptance owns a separate pass gate."""
    if isinstance(oracle, Mapping):
        if not isinstance(observed, Mapping) or set(observed) != set(oracle):
            raise ValueError(f"{field_path} observed/oracle mapping shape mismatch")
        if isinstance(tolerance, Mapping) and set(tolerance) != set(oracle):
            raise ValueError(f"{field_path} tolerance mapping shape mismatch")
        if isinstance(comparison, Mapping) and set(comparison) != set(oracle):
            raise ValueError(f"{field_path} comparison mapping shape mismatch")
        return all(
            _evaluate_comparison(
                observed[key],
                oracle[key],
                _leaf(tolerance, key),
                _leaf(comparison, key),
                field_path=f"{field_path}.{key}",
            )
            for key in oracle
        )
    if isinstance(oracle, (tuple, list)):
        if not isinstance(observed, (tuple, list)) or len(observed) != len(oracle):
            raise ValueError(f"{field_path} observed/oracle sequence shape mismatch")
        if isinstance(tolerance, (tuple, list)) and len(tolerance) != len(oracle):
            raise ValueError(f"{field_path} tolerance sequence shape mismatch")
        if isinstance(comparison, (tuple, list)) and len(comparison) != len(oracle):
            raise ValueError(f"{field_path} comparison sequence shape mismatch")
        return all(
            _evaluate_comparison(
                observed[index],
                expected,
                tolerance[index] if isinstance(tolerance, (tuple, list)) else tolerance,
                comparison[index]
                if isinstance(comparison, (tuple, list))
                else comparison,
                field_path=f"{field_path}.{index}",
            )
            for index, expected in enumerate(oracle)
        )
    if not isinstance(comparison, str) or comparison not in {
        "abs_le",
        "rel_le",
        "ge",
        "le",
        "eq",
    }:
        raise ValueError(f"{field_path} has unknown comparison operator")
    if comparison == "eq":
        if tolerance not in (0, 0.0, None):
            raise ValueError(f"{field_path} eq tolerance must be zero")
        return (
            _json_scalar_kind(observed) == _json_scalar_kind(oracle)
            and observed == oracle
        )
    if any(isinstance(value, bool) for value in (observed, oracle, tolerance)):
        raise ValueError(f"{field_path} numeric comparison rejects booleans")
    try:
        observed_number = float(observed)
        oracle_number = float(oracle)
        tolerance_number = float(tolerance)
    except (TypeError, ValueError, OverflowError) as error:
        raise ValueError(f"{field_path} numeric comparison requires numbers") from error
    if (
        not all(isfinite(value) for value in (observed_number, oracle_number, tolerance_number))
        or tolerance_number < 0.0
    ):
        raise ValueError(f"{field_path} requires finite values and nonnegative tolerance")
    if comparison == "abs_le":
        return abs(observed_number - oracle_number) <= tolerance_number
    if comparison == "rel_le":
        scale = max(abs(oracle_number), 1e-30)
        return abs(observed_number - oracle_number) / scale <= tolerance_number
    if comparison == "ge":
        return observed_number + tolerance_number >= oracle_number
    return observed_number - tolerance_number <= oracle_number


@dataclass(frozen=True)
class VerificationRecord:
    """Immutable, labeled record whose pass state is derived from its oracle tree."""

    acceptance_test: int
    fixture_sha256: str
    observed_value: object
    oracle: object
    tolerance: object
    code_version: str
    evidence_label: EvidenceLabel
    comparison: object = "abs_le"
    passed: bool | None = None
    code_provenance: Mapping[str, object] = field(default_factory=dict)
    fixture_sha256s: Mapping[str, str] | None = None
    auxiliary_artifacts_sha256s: Mapping[str, str] | None = None
    validity: Literal["valid", "invalid"] = "valid"
    censored: bool = False
    reason_code: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.evidence_label, EvidenceLabel):
            raise TypeError("evidence_label must be an EvidenceLabel")
        observed = _freeze_json(self.observed_value)
        oracle = _freeze_json(self.oracle)
        tolerance = _freeze_json(self.tolerance)
        comparison = _freeze_json(self.comparison)
        object.__setattr__(self, "observed_value", observed)
        object.__setattr__(self, "oracle", oracle)
        object.__setattr__(self, "tolerance", tolerance)
        object.__setattr__(self, "comparison", comparison)
        hashes = (
            {"primary": self.fixture_sha256}
            if self.fixture_sha256s is None
            else dict(self.fixture_sha256s)
        )
        object.__setattr__(self, "fixture_sha256s", MappingProxyType(hashes))
        object.__setattr__(
            self,
            "auxiliary_artifacts_sha256s",
            MappingProxyType(dict(self.auxiliary_artifacts_sha256s or {})),
        )
        object.__setattr__(
            self, "code_provenance", MappingProxyType(dict(self.code_provenance))
        )
        derived = (
            self.validity == "valid"
            and _evaluate_comparison(observed, oracle, tolerance, comparison)
        )
        if self.passed is not None and self.passed is not derived:
            raise ValueError("manual passed field is inconsistent with the derived result")
        object.__setattr__(self, "passed", derived)

    def validate(self) -> None:
        if self.acceptance_test not in range(1, 23):
            raise ValueError("acceptance_test must be in [1, 22]")
        all_hashes = {
            "primary": self.fixture_sha256,
            **dict(self.fixture_sha256s),
            **dict(self.auxiliary_artifacts_sha256s),
        }
        for name, digest in all_hashes.items():
            if not name or len(digest) != 64 or any(
                character not in "0123456789abcdefABCDEF" for character in digest
            ):
                raise ValueError("resource hashes must contain exact named SHA-256 hex digests")
        if not self.code_version.strip():
            raise ValueError("code_version is required")
        required_provenance = {
            "package_version",
            "git_sha",
            "git_dirty",
            "unavailable",
        }
        if set(self.code_provenance) != required_provenance:
            raise ValueError("code_provenance must expose package, Git SHA, dirty state, and unavailable fields")
        if self.validity not in {"valid", "invalid"}:
            raise ValueError("validity must be valid or invalid")
        if self.censored and self.validity != "valid":
            raise ValueError("an invalid numerical run cannot be physically censored")
        if (self.censored or self.validity == "invalid") and not self.reason_code:
            raise ValueError("censored or invalid records require a reason_code")
        _json_value(self.observed_value, "observed_value")
        _json_value(self.oracle, "oracle")
        _json_value(self.tolerance, "tolerance")
        _json_value(self.comparison, "comparison")
        _json_value(self.code_provenance, "code_provenance")

    def to_dict(self) -> dict[str, object]:
        self.validate()
        return {
            "acceptance_test": self.acceptance_test,
            "fixture_sha256": self.fixture_sha256.lower(),
            "fixture_sha256s": {
                name: digest.lower() for name, digest in self.fixture_sha256s.items()
            },
            "auxiliary_artifacts_sha256s": {
                name: digest.lower()
                for name, digest in self.auxiliary_artifacts_sha256s.items()
            },
            "observed_value": _json_value(self.observed_value, "observed_value"),
            "oracle": _json_value(self.oracle, "oracle"),
            "tolerance": _json_value(self.tolerance, "tolerance"),
            "comparison": _json_value(self.comparison, "comparison"),
            "passed": self.passed,
            "code_version": self.code_version,
            "code_provenance": _json_value(self.code_provenance, "code_provenance"),
            "evidence_label": self.evidence_label.value,
            "validity": self.validity,
            "censored": self.censored,
            "reason_code": self.reason_code,
        }


@dataclass(frozen=True)
class RunStopStatus:
    valid: bool
    censored: bool
    reason_code: str | None
    evidence_label: EvidenceLabel | None = None


PhysicalStop = PhysicalStopPolicy


def load_physical_stops(path: Path | None = None) -> Mapping[str, PhysicalStop]:
    return load_threshold_policy(path).physical_stops


def evaluate_run_stops(
    *,
    numerical_values: Mapping[str, float],
    stocks: Mapping[str, float],
    ledger_relative_residuals: Mapping[str, float],
    physical_values: Mapping[str, float],
    physical_stops: Mapping[str, PhysicalStop],
    applicable_stop_ids: Sequence[str] | None = None,
    numerical_policy: NumericalStops | None = None,
) -> RunStopStatus:
    """Evaluate required numerical stops before explicitly applicable physical stops."""
    policy = numerical_policy or load_threshold_policy().numerical_stops
    try:
        numerical = {name: float(value) for name, value in numerical_values.items()}
        normalized_stocks = {name: float(value) for name, value in stocks.items()}
        residuals = {
            name: float(value) for name, value in ledger_relative_residuals.items()
        }
        physical = {name: float(value) for name, value in physical_values.items()}
    except (TypeError, ValueError, OverflowError):
        return RunStopStatus(False, False, "NONNUMERIC_STATE")
    if policy.require_finite_state and any(
        not isfinite(value)
        for mapping in (numerical, normalized_stocks, residuals, physical)
        for value in mapping.values()
    ):
        return RunStopStatus(False, False, "NONFINITE_STATE")
    if any(value < policy.minimum_stock for value in normalized_stocks.values()):
        return RunStopStatus(False, False, "STOCK_BELOW_NUMERICAL_TOLERANCE")
    if any(
        abs(value) > policy.maximum_relative_ledger_residual
        for value in residuals.values()
    ):
        return RunStopStatus(False, False, "LEDGER_RESIDUAL_EXCEEDED")
    if applicable_stop_ids is None:
        return RunStopStatus(False, False, "APPLICABLE_PHYSICAL_STOPS_REQUIRED")
    declared = tuple(applicable_stop_ids)
    if len(set(declared)) != len(declared) or any(
        stop_id not in physical_stops for stop_id in declared
    ):
        return RunStopStatus(False, False, "INVALID_APPLICABLE_PHYSICAL_STOP")
    for stop_id in declared:
        if stop_id not in physical:
            return RunStopStatus(False, False, "MISSING_APPLICABLE_PHYSICAL_VALUE")
        stop = physical_stops[stop_id]
        value = physical[stop_id]
        if stop.minimum is not None and value <= stop.minimum:
            return RunStopStatus(
                True, True, f"PHYSICAL_STOP_{stop_id.upper()}_MINIMUM", stop.evidence_label
            )
        if stop.maximum is not None and value >= stop.maximum:
            return RunStopStatus(
                True, True, f"PHYSICAL_STOP_{stop_id.upper()}_MAXIMUM", stop.evidence_label
            )
    return RunStopStatus(True, False, None)


def _atomic_write_bytes(target: Path, contents: bytes) -> Path:
    target.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{target.name}.", suffix=".tmp", dir=target.parent
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(contents)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, target)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise
    return target


def _json_bytes(payload: object) -> bytes:
    return (
        json.dumps(payload, sort_keys=True, indent=2, allow_nan=False) + "\n"
    ).encode("utf-8")


def write_verification_record(target: Path, record: VerificationRecord) -> Path:
    return _atomic_write_bytes(target, _json_bytes(record.to_dict()))


def _code_provenance() -> Mapping[str, object]:
    unavailable: list[str] = []
    try:
        package_version: str | None = version("saltwater-mini-almond")
    except PackageNotFoundError:
        package_version = None
        unavailable.append("package_version")
    git_sha: str | None = None
    git_dirty: bool | None = None
    try:
        root = Path(__file__).resolve().parent
        git_sha = subprocess.run(
            ["git", "rev-parse", "--verify", "HEAD"],
            cwd=root,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
        dirty_result = subprocess.run(
            ["git", "status", "--porcelain", "--untracked-files=no"],
            cwd=root,
            capture_output=True,
            text=True,
            check=True,
        )
        git_dirty = bool(dirty_result.stdout.strip())
    except (OSError, subprocess.CalledProcessError):
        unavailable.extend(["git_sha", "git_dirty"])
    return MappingProxyType(
        {
            "package_version": package_version,
            "git_sha": git_sha,
            "git_dirty": git_dirty,
            "unavailable": tuple(unavailable),
        }
    )


def _code_version(provenance: Mapping[str, object]) -> str:
    parts = [f"package:{provenance['package_version'] or 'unavailable'}"]
    parts.append(f"git:{provenance['git_sha'] or 'unavailable'}")
    parts.append(
        "dirty:unavailable"
        if provenance["git_dirty"] is None
        else f"dirty:{str(provenance['git_dirty']).lower()}"
    )
    return ";".join(parts)


def _state(initial: Mapping[str, object]) -> NetworkState:
    return NetworkState.from_dict(
        initial["volumes_l"], initial["stocks_mmol"]  # type: ignore[arg-type]
    )


def _fixture(name: str) -> tuple[dict[str, object], str]:
    return load_fixture(name)


def _tree_constant(template: object, value: object) -> object:
    if isinstance(template, Mapping):
        return {key: _tree_constant(item, value) for key, item in template.items()}
    if isinstance(template, (tuple, list)):
        return [_tree_constant(item, value) for item in template]
    return value


def _record(
    acceptance_test: int,
    fixture_sha256: str,
    observed: object,
    oracle: object,
    tolerance: object,
    *,
    comparison: object = "abs_le",
    reason_code: str | None = None,
    censored: bool = False,
    validity: Literal["valid", "invalid"] = "valid",
    fixture_sha256s: Mapping[str, str] | None = None,
    auxiliary_artifacts_sha256s: Mapping[str, str] | None = None,
    evidence_label: EvidenceLabel = EvidenceLabel.PHYSICS_CONSTRAINED,
) -> VerificationRecord:
    provenance = _code_provenance()
    verification_policy = load_verification_policy()
    hashes = dict(fixture_sha256s or {"primary": fixture_sha256})
    hashes["configs/verification.yaml"] = verification_policy.sha256
    return VerificationRecord(
        acceptance_test=acceptance_test,
        fixture_sha256=fixture_sha256,
        observed_value=observed,
        oracle=oracle,
        tolerance=tolerance,
        comparison=comparison,
        code_version=_code_version(provenance),
        code_provenance=provenance,
        evidence_label=evidence_label,
        fixture_sha256s=hashes,
        auxiliary_artifacts_sha256s=auxiliary_artifacts_sha256s,
        validity=validity,
        censored=censored,
        reason_code=reason_code,
    )


def _apply_ledger_transform(
    ledger: tuple[LedgerEntry, ...],
    transform: Callable[[tuple[LedgerEntry, ...]], tuple[LedgerEntry, ...]] | None,
) -> tuple[LedgerEntry, ...]:
    return ledger if transform is None else tuple(transform(ledger))


def _ledger_rows(ledger: tuple[LedgerEntry, ...]) -> list[dict[str, object]]:
    rows = []
    for row in ledger:
        payload = asdict(row)
        payload["evidence_label"] = row.evidence_label.value
        rows.append(payload)
    return rows


def _ledger_audit(
    audit: BalanceAudit,
    ledger: tuple[LedgerEntry, ...],
    required_quantities: set[str],
    expected_ledger: Mapping[str, object],
) -> dict[str, object]:
    internal_transactions = {row.transaction_id for row in ledger if row.kind == "internal"}
    transaction_ids = sorted(internal_transactions)
    labels = sorted({row.evidence_label.value for row in ledger})
    expected_ids = _expected_transaction_ids(expected_ledger)
    expected_transfer = {
        str(quantity): float(amount)
        for quantity, amount in expected_ledger["per_transaction_transfer"].items()  # type: ignore[union-attr]
    }
    expected_source = str(expected_ledger["source"])
    expected_target = str(expected_ledger["target"])
    internal_row_count = sum(row.kind == "internal" for row in ledger)
    external_row_count = len(ledger) - internal_row_count
    canonical_transactions: dict[str, dict[str, float]] = {}
    canonical_valid = True
    for transaction_id in expected_ids:
        rows = [row for row in ledger if row.transaction_id == transaction_id]
        positive = {
            row.quantity: row.amount
            for row in rows
            if row.kind == "internal"
            and row.compartment == expected_target
            and row.counterparty == expected_source
            and row.amount >= 0.0
        }
        canonical_transactions[transaction_id] = positive
        canonical_valid = canonical_valid and set(positive) == set(expected_transfer)
        canonical_valid = canonical_valid and all(
            abs(positive.get(quantity, float("inf")) - expected_amount) <= 1.0e-12
            for quantity, expected_amount in expected_transfer.items()
        )
    compartment_extrema = {
        compartment: max(values.values(), default=0.0)
        for compartment, values in audit.relative_compartment_residuals.items()
    }
    valid = (
        bool(ledger)
        and bool(internal_transactions)
        and audit.balanced
        and not audit.internal_transaction_errors
        and set(audit.quantities) == required_quantities
        and labels == [EvidenceLabel.PHYSICS_CONSTRAINED.value]
        and len(ledger) == int(expected_ledger["row_count"])
        and internal_row_count == int(expected_ledger["row_count"])
        and external_row_count == 0
        and len(internal_transactions) == int(expected_ledger["transaction_count"])
        and transaction_ids == expected_ids
        and canonical_valid
    )
    return {
        "valid": valid,
        "balanced": audit.balanced,
        "row_count": len(ledger),
        "internal_row_count": internal_row_count,
        "external_row_count": external_row_count,
        "transaction_count": len(internal_transactions),
        "transaction_ids": transaction_ids,
        "per_transaction_transfer": canonical_transactions,
        "quantities": sorted(audit.quantities),
        "internal_transaction_errors": list(audit.internal_transaction_errors),
        "global_relative_residuals": dict(audit.relative_residuals),
        "compartment_relative_residuals": {
            compartment: dict(values)
            for compartment, values in audit.relative_compartment_residuals.items()
        },
        "compartment_residual_extrema": compartment_extrema,
        "evidence_labels": labels,
    }


def _expected_transaction_ids(expected_ledger: Mapping[str, object]) -> list[str]:
    first = int(expected_ledger["first_substep"])
    count = int(expected_ledger["transaction_count"])
    flow_index = int(expected_ledger["flow_index"])
    return sorted(
        f"internal:{substep}:{flow_index}"
        for substep in range(first, first + count)
    )


def _ledger_oracle(
    audit_payload: Mapping[str, object], expected_ledger: Mapping[str, object]
) -> dict[str, object]:
    expected_transfer = {
        str(quantity): float(amount)
        for quantity, amount in expected_ledger["per_transaction_transfer"].items()  # type: ignore[union-attr]
    }
    return {
        "valid": True,
        "balanced": True,
        "row_count": int(expected_ledger["row_count"]),
        "internal_row_count": int(expected_ledger["row_count"]),
        "external_row_count": 0,
        "transaction_count": int(expected_ledger["transaction_count"]),
        "transaction_ids": _expected_transaction_ids(expected_ledger),
        "per_transaction_transfer": {
            transaction_id: expected_transfer
            for transaction_id in _expected_transaction_ids(expected_ledger)
        },
        "quantities": audit_payload["quantities"],
        "internal_transaction_errors": [],
        "global_relative_residuals": {
            key: 0.0
            for key in audit_payload["global_relative_residuals"]  # type: ignore[union-attr]
        },
        "compartment_relative_residuals": {
            compartment: {key: 0.0 for key in values}
            for compartment, values in audit_payload[
                "compartment_relative_residuals"
            ].items()  # type: ignore[union-attr]
        },
        "compartment_residual_extrema": {
            key: 0.0
            for key in audit_payload["compartment_residual_extrema"]  # type: ignore[union-attr]
        },
        "evidence_labels": [EvidenceLabel.PHYSICS_CONSTRAINED.value],
    }


def _ledger_comparison(oracle: object) -> object:
    result = _tree_constant(oracle, "abs_le")
    assert isinstance(result, dict)
    for key in (
        "valid",
        "balanced",
        "row_count",
        "internal_row_count",
        "external_row_count",
        "transaction_count",
        "transaction_ids",
        "quantities",
        "internal_transaction_errors",
        "evidence_labels",
    ):
        result[key] = _tree_constant(oracle[key], "eq")  # type: ignore[index]
    return result


def _ledger_tolerance(oracle: object, residual_tolerance: float) -> object:
    result = _tree_constant(oracle, residual_tolerance)
    assert isinstance(result, dict)
    for key in (
        "valid",
        "balanced",
        "row_count",
        "internal_row_count",
        "external_row_count",
        "transaction_count",
        "transaction_ids",
        "quantities",
        "internal_transaction_errors",
        "evidence_labels",
    ):
        result[key] = _tree_constant(oracle[key], 0.0)  # type: ignore[index]
    return result


def _acceptance_01_bundle(
    *, ledger_transform: Callable[[tuple[LedgerEntry, ...]], tuple[LedgerEntry, ...]] | None = None
) -> tuple[VerificationRecord, object]:
    fixture, digest = _fixture("water_one_day.yaml")
    policy = load_verification_policy()
    before = _state(fixture["initial"])  # type: ignore[arg-type]
    result = step_state(
        before,
        [Flow(**fixture["flow"])],  # type: ignore[arg-type]
        [],
        float(fixture["duration_hours"]),
    )
    ledger = _apply_ledger_transform(result.ledger, ledger_transform)
    audit = audit_ledger(before, result.state, ledger)
    ledger_payload = _ledger_audit(
        audit, ledger, {"water"}, fixture["expected_ledger"]  # type: ignore[arg-type]
    )
    ledger_oracle = _ledger_oracle(
        ledger_payload, fixture["expected_ledger"]  # type: ignore[arg-type]
    )
    observed = {
        "post_volumes_l": dict(result.state.volumes_l),
        "ledger_audit": ledger_payload,
    }
    oracle = {
        "post_volumes_l": fixture["expected_volumes_l"],
        "ledger_audit": ledger_oracle,
    }
    tolerance = {
        "post_volumes_l": _tree_constant(oracle["post_volumes_l"], policy.tolerances[1]["absolute"]),
        "ledger_audit": _ledger_tolerance(ledger_oracle, policy.tolerances[1]["absolute"]),
    }
    comparison = {
        "post_volumes_l": _tree_constant(oracle["post_volumes_l"], "abs_le"),
        "ledger_audit": _ledger_comparison(ledger_oracle),
    }
    record = _record(
        1,
        digest,
        observed,
        oracle,
        tolerance,
        comparison=comparison,
        fixture_sha256s={"water_one_day.yaml": digest},
    )
    return record, _ledger_rows(ledger)


def _acceptance_02_bundle(
    *, ledger_transform: Callable[[tuple[LedgerEntry, ...]], tuple[LedgerEntry, ...]] | None = None
) -> tuple[VerificationRecord, object]:
    fixture, digest = _fixture("ions_conservative.yaml")
    policy = load_verification_policy()
    before = _state(fixture["initial"])  # type: ignore[arg-type]
    result = step_state(
        before,
        [Flow(**fixture["flow"])],  # type: ignore[arg-type]
        [],
        float(fixture["duration_hours"]),
    )
    ledger = _apply_ledger_transform(result.ledger, ledger_transform)
    audit = audit_ledger(before, result.state, ledger)
    required = {entity.value for entity in ConservedEntity}
    ledger_payload = _ledger_audit(
        audit, ledger, required, fixture["expected_ledger"]  # type: ignore[arg-type]
    )
    ledger_oracle = _ledger_oracle(
        ledger_payload, fixture["expected_ledger"]  # type: ignore[arg-type]
    )
    observed = {
        "post_state": {
            compartment: dict(stocks)
            for compartment, stocks in result.state.stocks_mmol.items()
        },
        "post_quantities": {
            compartment: {
                "water": result.state.volumes_l[compartment],
                **dict(result.state.stocks_mmol[compartment]),
            }
            for compartment in result.state.volumes_l
        },
        "ledger_audit": ledger_payload,
    }
    oracle = {
        "post_state": fixture["expected_stocks_mmol"],
        "post_quantities": fixture["expected_post_quantities"],
        "ledger_audit": ledger_oracle,
    }
    tolerance = {
        "post_state": _tree_constant(oracle["post_state"], policy.tolerances[2]["absolute"]),
        "post_quantities": _tree_constant(oracle["post_quantities"], policy.tolerances[2]["absolute"]),
        "ledger_audit": _ledger_tolerance(ledger_oracle, policy.tolerances[2]["absolute"]),
    }
    comparison = {
        "post_state": _tree_constant(oracle["post_state"], "abs_le"),
        "post_quantities": _tree_constant(oracle["post_quantities"], "abs_le"),
        "ledger_audit": _ledger_comparison(ledger_oracle),
    }
    record = _record(
        2,
        digest,
        observed,
        oracle,
        tolerance,
        comparison=comparison,
        fixture_sha256s={"ions_conservative.yaml": digest},
    )
    return record, _ledger_rows(ledger)


def _acceptance_01(
    *, ledger_transform: Callable[[tuple[LedgerEntry, ...]], tuple[LedgerEntry, ...]] | None = None
) -> VerificationRecord:
    return _acceptance_01_bundle(ledger_transform=ledger_transform)[0]


def _acceptance_02(
    *, ledger_transform: Callable[[tuple[LedgerEntry, ...]], tuple[LedgerEntry, ...]] | None = None
) -> VerificationRecord:
    return _acceptance_02_bundle(ledger_transform=ledger_transform)[0]


def _acceptance_03_bundle() -> tuple[VerificationRecord, object]:
    fixture, digest = _fixture("no_purge.yaml")
    threshold_policy = load_threshold_policy()
    verification_policy = load_verification_policy()
    state = _state(fixture["initial"])  # type: ignore[arg-type]
    time_hours = 0.0
    sample_hours = float(fixture["sample_hours"])
    trajectory: list[dict[str, float]] = [
        {
            "time_hours": 0.0,
            "concentration_mmol_l": state.concentration("tank", "na"),
        }
    ]
    stop = evaluate_run_stops(
        numerical_values={"concentration": trajectory[-1]["concentration_mmol_l"]},
        stocks={"na": state.total_stock("na")},
        ledger_relative_residuals={"water": 0.0, "na": 0.0},
        physical_values={
            "concentration_mmol_l": trajectory[-1]["concentration_mmol_l"]
        },
        physical_stops=threshold_policy.physical_stops,
        applicable_stop_ids=("concentration_mmol_l",),
        numerical_policy=threshold_policy.numerical_stops,
    )
    while stop.valid and not stop.censored:
        before = state
        result = step_state(
            state,
            [],
            [ExternalFlux(**fixture["source_flux"])],  # type: ignore[arg-type]
            sample_hours,
        )
        state = result.state
        time_hours += sample_hours
        concentration = state.concentration("tank", "na")
        audit = audit_ledger(before, state, result.ledger)
        trajectory.append(
            {"time_hours": time_hours, "concentration_mmol_l": concentration}
        )
        stop = evaluate_run_stops(
            numerical_values={"concentration": concentration},
            stocks={"na": state.total_stock("na")},
            ledger_relative_residuals=audit.relative_residuals,
            physical_values={"concentration_mmol_l": concentration},
            physical_stops=threshold_policy.physical_stops,
            applicable_stop_ids=("concentration_mmol_l",),
            numerical_policy=threshold_policy.numerical_stops,
        )
        if time_hours > 100_000.0:
            raise RuntimeError("Test 3 configured physical stop was not reached")
    if stop.evidence_label is None:
        raise RuntimeError("Test 3 physical stop lost its configured evidence label")
    observed = {
        "stop_time_hours": time_hours,
        "stop": {
            "valid": stop.valid,
            "censored": stop.censored,
            "reason_code": stop.reason_code,
            "evidence_label": stop.evidence_label.value,
        },
    }
    oracle = {
        "stop_time_hours": float(fixture["expected_stop_hours"]),
        "stop": {
            "valid": True,
            "censored": True,
            "reason_code": "PHYSICAL_STOP_CONCENTRATION_MMOL_L_MAXIMUM",
            "evidence_label": "synthetic_only",
        },
    }
    tolerance = {
        "stop_time_hours": verification_policy.tolerances[3]["relative"],
        "stop": _tree_constant(oracle["stop"], 0.0),
    }
    comparison = {
        "stop_time_hours": "rel_le",
        "stop": _tree_constant(oracle["stop"], "eq"),
    }
    return (
        _record(
            3,
            digest,
            observed,
            oracle,
            tolerance,
            comparison=comparison,
            censored=stop.censored,
            reason_code=stop.reason_code,
            evidence_label=stop.evidence_label,
            fixture_sha256s={
                "no_purge.yaml": digest,
                "configs/thresholds.yaml": threshold_policy.sha256,
            },
        ),
        trajectory,
    )


def _acceptance_04_bundle() -> tuple[VerificationRecord, object]:
    fixture, digest = _fixture("sufficient_purge.yaml")
    policy = load_verification_policy()
    state = _state(fixture["initial"])  # type: ignore[arg-type]
    sample_hours = float(fixture["sample_hours"])
    samples = int(fixture["samples"])
    c_ss = float(fixture["c_in"]) + float(fixture["m_dot"]) / float(fixture["purge"])
    trajectory = [
        {
            "time_hours": 0.0,
            "concentration_mmol_l": state.concentration("tank", "na"),
            "oracle_concentration_mmol_l": float(fixture["c0"]),
            "relative_error": 0.0,
        }
    ]
    for index in range(1, samples + 1):
        result = step_state(
            state,
            [],
            [
                ExternalFlux(**fixture["influx"]),  # type: ignore[arg-type]
                ExternalFlux(**fixture["purge_flux"]),  # type: ignore[arg-type]
            ],
            sample_hours,
        )
        state = result.state
        time_hours = index * sample_hours
        oracle_concentration = c_ss + (float(fixture["c0"]) - c_ss) * exp(
            -float(fixture["purge"]) * time_hours / float(fixture["volume"])
        )
        concentration = state.concentration("tank", "na")
        trajectory.append(
            {
                "time_hours": time_hours,
                "concentration_mmol_l": concentration,
                "oracle_concentration_mmol_l": oracle_concentration,
                "relative_error": abs(concentration - oracle_concentration)
                / max(abs(oracle_concentration), 1e-30),
            }
        )
    terminal_ratio = (state.concentration("tank", "na") - c_ss) / (
        float(fixture["c0"]) - c_ss
    )
    observed = {
        "trajectory_relative_error": max(row["relative_error"] for row in trajectory),
        "terminal_exponential_error": abs(terminal_ratio - exp(-12.0)),
    }
    oracle = {"trajectory_relative_error": 0.0, "terminal_exponential_error": 0.0}
    tolerance = {
        "trajectory_relative_error": policy.tolerances[4]["trajectory_relative"],
        "terminal_exponential_error": policy.tolerances[4]["terminal_absolute"],
    }
    return (
        _record(
            4,
            digest,
            observed,
            oracle,
            tolerance,
            fixture_sha256s={"sufficient_purge.yaml": digest},
        ),
        trajectory,
    )


def _acceptance_03() -> VerificationRecord:
    return _acceptance_03_bundle()[0]


def _acceptance_04() -> VerificationRecord:
    return _acceptance_04_bundle()[0]


def _chemistry_sources(
    fixture: Mapping[str, object], volumes_l: Sequence[float] | None = None
) -> tuple[list[WaterBatch], BlendMeasurement, Sequence[float]]:
    blend = fixture["blend"]  # type: ignore[index]
    sources = [
        WaterBatch(
            chemistry=WaterChemistry(**payload),
            **metadata,
        )
        for metadata, payload in zip(
            blend["source_metadata"],
            (blend["source_a"], blend["source_b"]),
            strict=True,
        )
    ]
    measurement = BlendMeasurement(**blend["measurement"])
    return sources, measurement, volumes_l or blend["volumes_l"]


def _blend_provenance(
    blend: object, measurement: BlendMeasurement
) -> dict[str, object]:
    return {
        "data_origin": blend.data_origin.value,  # type: ignore[attr-defined]
        "evidence_label": blend.evidence_label.value,  # type: ignore[attr-defined]
        "source_data_origins": [
            origin.value for origin in blend.source_data_origins  # type: ignore[attr-defined]
        ],
        "source_evidence_labels": [
            label.value for label in blend.source_evidence_labels  # type: ignore[attr-defined]
        ],
        "measurement_id": blend.measurement_id,  # type: ignore[attr-defined]
        "measurement_data_origin": blend.measurement_data_origin.value,  # type: ignore[attr-defined]
        "measurement_evidence_label": measurement.evidence_label.value,
    }


def _blend_measurement_output(blend: object) -> dict[str, object]:
    chemistry = blend.chemistry  # type: ignore[attr-defined]
    return {
        "ec_kind": chemistry.ec_kind.value,
        "ec_ds_m": chemistry.ec_ds_m,
        "temperature_k": chemistry.temperature_k,
        "measured_osmolality_osmol_kg": chemistry.measured_osmolality_osmol_kg,
        "ph": chemistry.ph,
    }


def _acceptance_05() -> VerificationRecord:
    fixture, digest = _fixture("chemistry_handcheck.yaml")
    policy = load_verification_policy()
    sources, measurement, volumes_l = _chemistry_sources(fixture)
    blend_data = fixture["blend"]  # type: ignore[index]
    blend = blend_by_volume(sources, volumes_l, measurement=measurement)
    sar_data = fixture["sar"]  # type: ignore[index]
    sar_inputs = sar_data["inputs_mmol_c_l"]
    sar_denominator = ((sar_inputs["ca"] + sar_inputs["mg"]) / 2.0) ** 0.5
    observed_sar = sodium_adsorption_ratio(
        sar_inputs["na"], sar_inputs["ca"], sar_inputs["mg"]
    )
    charge_data = fixture["charge_balance"]  # type: ignore[index]
    charge_water = WaterChemistry(**charge_data["input"])
    charge_cations = (
        charge_water.na_mmol_l
        + charge_water.k_mmol_l
        + 2.0 * charge_water.ca_mmol_l
        + 2.0 * charge_water.mg_mmol_l
    )
    charge_anions = (
        charge_water.cl_mmol_l
        + 2.0 * charge_water.sulfate_mmol_l
        + charge_water.alkalinity_mmol_c_l
        + charge_water.nitrate_mmol_l
    )
    observed_charge = charge_balance_error(charge_water)
    rejection_data = fixture["ec_rejection"]  # type: ignore[index]
    try:
        ro_split(
            rejection_data["feed_volume_l"],
            rejection_data["feed_stock_mmol"],
            rejection_data["recovery"],
            rejection_data["rejection"],
        )
    except AlmondLabError as error:
        rejection_observed = {
            "rejected": True,
            "code": error.code,
            "field_path": error.field_path,
            "message": error.message,
        }
    else:
        rejection_observed = {
            "rejected": False,
            "code": "ACCEPTED",
            "field_path": None,
            "message": None,
        }
    observed = {
        "blend": {
            "inputs": {
                "volumes_l": list(volumes_l),
                "source_batch_ids": [source.water_batch_id for source in sources],
                "measurement_id": measurement.measurement_id,
            },
            "total_volume_l": blend.total_volume_l,
            "concentrations_mmol_l": {
                field: getattr(blend.chemistry, field) for field in blend_data["expected"]
            },
            "measurement_output": _blend_measurement_output(blend),
            "provenance": _blend_provenance(blend, measurement),
        },
        "sar": {
            "inputs_mmol_c_l": dict(sar_inputs),
            "denominator_mmol_c_l": sar_denominator,
            "value": observed_sar,
        },
        "charge_balance": {
            "input": dict(charge_data["input"]),
            "cations_mmol_c_l": charge_cations,
            "anions_mmol_c_l": charge_anions,
            "numerator_mmol_c_l": charge_cations - charge_anions,
            "denominator_mmol_c_l": charge_cations + charge_anions,
            "percent": observed_charge,
        },
        "ec_rejection": {
            "inputs": {
                "feed_volume_l": rejection_data["feed_volume_l"],
                "feed_stock_mmol": dict(rejection_data["feed_stock_mmol"]),
                "recovery": rejection_data["recovery"],
                "rejection": dict(rejection_data["rejection"]),
            },
            "result": rejection_observed,
        },
    }
    oracle = {
        "blend": {
            "inputs": {
                "volumes_l": blend_data["volumes_l"],
                "source_batch_ids": [
                    metadata["water_batch_id"] for metadata in blend_data["source_metadata"]
                ],
                "measurement_id": blend_data["measurement"]["measurement_id"],
            },
            "total_volume_l": blend_data["expected_total_volume_l"],
            "concentrations_mmol_l": blend_data["expected"],
            "measurement_output": blend_data["expected_measurement_output"],
            "provenance": blend_data["expected_provenance"],
        },
        "sar": {
            "inputs_mmol_c_l": sar_data["inputs_mmol_c_l"],
            "denominator_mmol_c_l": sar_data["expected_denominator_mmol_c_l"],
            "value": sar_data["expected_value"],
        },
        "charge_balance": {
            "input": charge_data["input"],
            **charge_data["expected"],
        },
        "ec_rejection": {
            "inputs": {
                key: rejection_data[key]
                for key in ("feed_volume_l", "feed_stock_mmol", "recovery", "rejection")
            },
            "result": {
                "rejected": rejection_data["expected_rejected"],
                "code": rejection_data["expected_code"],
                "field_path": rejection_data["expected_field_path"],
                "message": rejection_data["expected_message"],
            },
        },
    }
    comparison = _tree_constant(oracle, "abs_le")
    tolerance = _tree_constant(
        oracle, policy.tolerances[5]["mass_blend_absolute"]
    )
    assert isinstance(comparison, dict) and isinstance(tolerance, dict)
    for branch in (
        comparison["blend"]["inputs"],
        comparison["blend"]["measurement_output"],
        comparison["blend"]["provenance"],
        comparison["charge_balance"]["input"],
        comparison["ec_rejection"],
    ):
        branch.update(_tree_constant(branch, "eq"))
    for branch in (
        tolerance["blend"]["inputs"],
        tolerance["blend"]["measurement_output"],
        tolerance["blend"]["provenance"],
        tolerance["charge_balance"]["input"],
        tolerance["ec_rejection"],
    ):
        branch.update(_tree_constant(branch, 0.0))
    comparison["sar"]["inputs_mmol_c_l"] = _tree_constant(
        oracle["sar"]["inputs_mmol_c_l"], "eq"
    )
    tolerance["sar"]["inputs_mmol_c_l"] = _tree_constant(
        oracle["sar"]["inputs_mmol_c_l"], 0.0
    )
    tolerance["sar"]["denominator_mmol_c_l"] = policy.tolerances[5]["sar_absolute"]
    tolerance["sar"]["value"] = policy.tolerances[5]["sar_absolute"]
    return _record(
        5,
        digest,
        observed,
        oracle,
        tolerance,
        comparison=comparison,
        fixture_sha256s={"chemistry_handcheck.yaml": digest},
    )


def _acceptance_13() -> VerificationRecord:
    fixture, digest = _fixture("perfect_na_exclusion.yaml")
    tolerance = load_verification_policy().tolerances[13]["absolute"]
    common = {
        key: value
        for key, value in fixture.items()
        if key not in {"fresh_osmolality_osmol_kg", "saline_osmolality_osmol_kg"}
    }
    fresh = hydraulic_uptake(
        HydraulicInputs(
            osmolality_osmol_kg=float(fixture["fresh_osmolality_osmol_kg"]),
            **common,
        )
    )
    saline = hydraulic_uptake(
        HydraulicInputs(
            osmolality_osmol_kg=float(fixture["saline_osmolality_osmol_kg"]),
            **common,
        )
    )
    observed = {
        "fresh_l_day": fresh.actual_l_day,
        "saline_l_day": saline.actual_l_day,
        "ratio": saline.actual_l_day / fresh.actual_l_day,
    }
    oracle = {"fresh_l_day": 0.888212, "saline_l_day": 0.455696, "ratio": 0.513049}
    return _record(
        13,
        digest,
        observed,
        oracle,
        tolerance,
        fixture_sha256s={"perfect_na_exclusion.yaml": digest},
    )


@dataclass
class AnalysisBoundary:
    accepted_records: int = 0

    def submit(self, source: WaterBatch, measurement: BlendMeasurement) -> None:
        blend_by_volume([source], [1.0], measurement=measurement)
        self.accepted_records += 1


def _acceptance_19() -> VerificationRecord:
    fixture, digest = _fixture("chemistry_handcheck.yaml")
    policy_tolerance = load_verification_policy().tolerances[19]["absolute"]
    source_payload = fixture["blend"]["source_a"]  # type: ignore[index]
    boundary = AnalysisBoundary()
    cases: list[dict[str, object]] = []
    for source_kind in ECKind:
        for measurement_kind in ECKind:
            if source_kind is measurement_kind:
                continue
            payload = dict(source_payload)
            payload["ec_kind"] = source_kind
            source = WaterBatch(
                water_batch_id="ec-source",
                chemistry=WaterChemistry(**payload),
                data_origin=DataOrigin.SYNTHETIC,
                evidence_label=EvidenceLabel.SYNTHETIC_ONLY,
                schema_version="1.0",
            )
            measurement_payload = dict(fixture["blend"]["measurement"])  # type: ignore[index]
            measurement_payload["ec_kind"] = measurement_kind
            measurement = BlendMeasurement(**measurement_payload)
            try:
                boundary.submit(source, measurement)
            except AlmondLabError as error:
                code = error.code
            else:
                code = "ACCEPTED"
            cases.append(
                {
                    "source_ec_kind": source_kind.value,
                    "measurement_ec_kind": measurement_kind.value,
                    "code": code,
                }
            )
    observed = {"cases": cases, "records_reached_analysis": boundary.accepted_records}
    oracle = {
        "cases": [
            {
                "source_ec_kind": case["source_ec_kind"],
                "measurement_ec_kind": case["measurement_ec_kind"],
                "code": "EC_TYPE_MISMATCH",
            }
            for case in cases
        ],
        "records_reached_analysis": 0,
    }
    comparison = _tree_constant(oracle, "eq")
    tolerance = _tree_constant(oracle, policy_tolerance)
    return _record(
        19,
        digest,
        observed,
        oracle,
        tolerance,
        comparison=comparison,
        fixture_sha256s={"chemistry_handcheck.yaml": digest},
    )


def _run_case_manifest(
    manifest: Mapping[str, object],
    chemistry_fixture: Mapping[str, object],
    absolute_tolerance: float,
) -> dict[str, object]:
    cases = manifest["cases"]  # type: ignore[index]
    extrema = {
        "flow": {
            "global_relative_residual": {},
            "compartment_relative_residual": {},
            "literal_absolute_error": {},
        },
        "ro": {
            "conservation_absolute_residual": {},
            "literal_absolute_error": {},
        },
        "blend": {"literal_absolute_error": {}},
    }
    counterexample: dict[str, object] | None = None

    def note_failure(case_type: str, case_id: str, detail: str) -> None:
        nonlocal counterexample
        candidate = {"case_type": case_type, "case_id": case_id, "detail": detail}
        if counterexample is None or (case_type, case_id, detail) < (
            counterexample["case_type"],
            counterexample["case_id"],
            counterexample["detail"],
        ):
            counterexample = candidate

    def record_max(branch: dict[str, float], quantity: str, value: float) -> None:
        branch[quantity] = max(branch.get(quantity, 0.0), value)

    for case in cases["flow"]:
        before = NetworkState.from_dict(
            {"source": case["source_volume_l"], "target": case["target_volume_l"]},
            {
                "source": case["source_stocks_mmol"],
                "target": case["target_stocks_mmol"],
            },
        )
        result = step_state(
            before,
            [Flow("source", "target", case["rate_l_per_hour"])],
            [],
            case["duration_hours"],
        )
        audit = audit_ledger(before, result.state, result.ledger)
        flow_extrema = extrema["flow"]
        for quantity, value in audit.relative_residuals.items():
            record_max(flow_extrema["global_relative_residual"], quantity, value)
            record_max(
                flow_extrema["compartment_relative_residual"],
                quantity,
                max(
                    compartment[quantity]
                    for compartment in audit.relative_compartment_residuals.values()
                ),
            )
        expected = case["expected"]
        literal_errors = {
            "water": max(
                abs(result.state.volumes_l[name] - value)
                for name, value in expected["volumes_l"].items()
            ),
            **{
                entity: max(
                    abs(result.state.stocks_mmol[compartment][entity] - stocks[entity])
                    for compartment, stocks in expected["stocks_mmol"].items()
                )
                for entity in case["source_stocks_mmol"]
            },
        }
        for quantity, value in literal_errors.items():
            record_max(
                flow_extrema["literal_absolute_error"], quantity, value
            )
        if (
            not audit.balanced
            or max(literal_errors.values(), default=0.0) > absolute_tolerance
        ):
            note_failure("flow", case["id"], "conservation or literal oracle")

    for case in cases["ro"]:
        result = ro_split(
            case["feed_volume_l"],
            case["feed_stocks_mmol"],
            case["recovery"],
            case["rejection"],
        )
        conservation_residuals = {
            "water": abs(
                result.permeate_volume_l
                + result.concentrate_volume_l
                - result.feed_volume_l
            ),
            **{
                entity: abs(
                    result.permeate_stock_mmol[entity]
                    + result.concentrate_stock_mmol[entity]
                    - stock
                )
                for entity, stock in result.feed_stock_mmol.items()
            },
        }
        expected = case["expected"]
        literal_errors = {
            "water": max(
                abs(
                    {
                        "feed": result.feed_volume_l,
                        "permeate": result.permeate_volume_l,
                        "concentrate": result.concentrate_volume_l,
                    }[name]
                    - value
                )
                for name, value in expected["volumes_l"].items()
            ),
            **{
                entity: max(
                    abs(
                        {
                            "permeate": result.permeate_stock_mmol,
                            "concentrate": result.concentrate_stock_mmol,
                        }[branch][entity]
                        - expected[f"{branch}_stocks_mmol"][entity]
                    )
                    for branch in ("permeate", "concentrate")
                )
                for entity in result.feed_stock_mmol
            },
        }
        ro_extrema = extrema["ro"]
        for quantity, value in conservation_residuals.items():
            record_max(
                ro_extrema["conservation_absolute_residual"], quantity, value
            )
        for quantity, value in literal_errors.items():
            record_max(ro_extrema["literal_absolute_error"], quantity, value)
        if max(
            *conservation_residuals.values(),
            *literal_errors.values(),
        ) > absolute_tolerance:
            note_failure("ro", case["id"], "conservation or literal oracle")

    sources, measurement, _ = _chemistry_sources(chemistry_fixture)
    for case in cases["blend"]:
        result = blend_by_volume(sources, case["volumes_l"], measurement=measurement)
        errors = {
            field: abs(getattr(result.chemistry, field) - value)
            for field, value in case["expected"].items()
        }
        for field, value in errors.items():
            record_max(
                extrema["blend"]["literal_absolute_error"], field, value
            )
        if max(errors.values(), default=0.0) > absolute_tolerance:
            note_failure("blend", case["id"], "literal oracle")
    return {
        "counts": {case_type: len(cases[case_type]) for case_type in ("blend", "flow", "ro")},
        "per_quantity_extrema": extrema,
        "minimized_counterexample": counterexample,
        "generator": manifest["generator"],
    }


def _acceptance_20_bundle(
    *,
    stepper: Callable[..., StepResult] = step_state,
    ro_model: Callable[..., ROResult] = ro_split,
    ledger_transform: Callable[[tuple[LedgerEntry, ...]], tuple[LedgerEntry, ...]] | None = None,
) -> tuple[VerificationRecord, object]:
    fixture, digest = _fixture("all_conserved_entities.yaml")
    ions_fixture, ions_digest = _fixture("ions_conservative.yaml")
    chemistry_fixture, chemistry_digest = _fixture("chemistry_handcheck.yaml")
    manifest, manifest_digest = load_conservation_case_manifest()
    threshold_policy = load_threshold_policy()
    policy = load_verification_policy()
    absolute_tolerance = policy.tolerances[20]["absolute"]
    before = _state(fixture["initial"])  # type: ignore[arg-type]
    result = stepper(
        before,
        [Flow(**fixture["flow"])],  # type: ignore[arg-type]
        [],
        float(fixture["duration_hours"]),
    )
    ledger = _apply_ledger_transform(result.ledger, ledger_transform)
    audit = audit_ledger(before, result.state, ledger)
    all_quantities = {entity.value for entity in ConservedEntity}
    ledger_payload = _ledger_audit(
        audit,
        ledger,
        all_quantities,
        fixture["expected_ledger"],  # type: ignore[arg-type]
    )
    ledger_oracle = _ledger_oracle(
        ledger_payload, fixture["expected_ledger"]  # type: ignore[arg-type]
    )
    ions_before = _state(ions_fixture["initial"])  # type: ignore[arg-type]
    ions_result = step_state(
        ions_before,
        [Flow(**ions_fixture["flow"])],  # type: ignore[arg-type]
        [],
        float(ions_fixture["duration_hours"]),
    )
    ions_audit = audit_ledger(ions_before, ions_result.state, ions_result.ledger)
    ions_ledger_payload = _ledger_audit(
        ions_audit,
        ions_result.ledger,
        all_quantities,
        ions_fixture["expected_ledger"],  # type: ignore[arg-type]
    )
    ions_ledger_oracle = _ledger_oracle(
        ions_ledger_payload,
        ions_fixture["expected_ledger"],  # type: ignore[arg-type]
    )
    ions_anchor_observed = {
        "post_quantities": {
            compartment: {
                "water": ions_result.state.volumes_l[compartment],
                **dict(ions_result.state.stocks_mmol[compartment]),
            }
            for compartment in ions_result.state.volumes_l
        },
        "ledger_audit": ions_ledger_payload,
    }
    ions_anchor_oracle = {
        "post_quantities": ions_fixture["expected_post_quantities"],
        "ledger_audit": ions_ledger_oracle,
    }

    entities = dict(before.stocks_mmol["source"])
    ro_data = fixture["ro"]  # type: ignore[index]
    ro_rejection = {entity: float(ro_data["rejection"]) for entity in entities}
    ro = ro_model(
        float(ro_data["feed_volume_l"]),
        entities,
        float(ro_data["recovery"]),
        ro_rejection,
    )
    transfer_observed = {
        "volumes_l": dict(result.state.volumes_l),
        "stocks_mmol": {
            compartment: dict(stocks)
            for compartment, stocks in result.state.stocks_mmol.items()
        },
        "concentrations_mmol_l": {
            compartment: {
                entity: result.state.concentration(compartment, entity)
                for entity in entities
            }
            for compartment in result.state.volumes_l
        },
    }
    ro_observed = {
        "inputs": {
            "feed_volume_l": ro.feed_volume_l,
            "recovery": float(ro_data["recovery"]),
            "rejection": dict(ro.rejection),
        },
        "volumes_l": {
            "feed": ro.feed_volume_l,
            "permeate": ro.permeate_volume_l,
            "concentrate": ro.concentrate_volume_l,
        },
        "stocks_mmol": {
            "feed": dict(ro.feed_stock_mmol),
            "permeate": dict(ro.permeate_stock_mmol),
            "concentrate": dict(ro.concentrate_stock_mmol),
        },
        "water_conserved": abs(
            ro.permeate_volume_l + ro.concentrate_volume_l - ro.feed_volume_l
        ) <= absolute_tolerance,
        "entities_conserved": {
            entity: abs(
                ro.permeate_stock_mmol[entity]
                + ro.concentrate_stock_mmol[entity]
                - stock
            )
            <= absolute_tolerance
            for entity, stock in entities.items()
        },
        "branches_within_bounds": (
            0.0 <= ro.permeate_volume_l <= ro.feed_volume_l
            and 0.0 <= ro.concentrate_volume_l <= ro.feed_volume_l
            and all(
                0.0 <= branch[entity] <= entities[entity]
                for branch in (ro.permeate_stock_mmol, ro.concentrate_stock_mmol)
                for entity in entities
            )
        ),
    }
    ro_oracle = {
        "inputs": {
            "feed_volume_l": float(ro_data["feed_volume_l"]),
            "recovery": float(ro_data["recovery"]),
            "rejection": ro_rejection,
        },
        "volumes_l": ro_data["expected_volumes_l"],
        "stocks_mmol": {
            "feed": entities,
            **ro_data["expected_stocks_mmol"],
        },
        "water_conserved": True,
        "entities_conserved": {entity: True for entity in entities},
        "branches_within_bounds": True,
    }
    sources, measurement, volumes_l = _chemistry_sources(chemistry_fixture)
    blend_data = chemistry_fixture["blend"]  # type: ignore[index]
    blend = blend_by_volume(sources, volumes_l, measurement=measurement)
    blend_observed = {
        "inputs": {
            "volumes_l": list(volumes_l),
            "source_batch_ids": [source.water_batch_id for source in sources],
            "measurement_id": measurement.measurement_id,
        },
        "total_volume_l": blend.total_volume_l,
        "concentrations_mmol_l": {
            field: getattr(blend.chemistry, field) for field in blend_data["expected"]
        },
        "measurement_output": _blend_measurement_output(blend),
        "provenance": _blend_provenance(blend, measurement),
    }
    blend_oracle = {
        "inputs": {
            "volumes_l": blend_data["volumes_l"],
            "source_batch_ids": [
                metadata["water_batch_id"] for metadata in blend_data["source_metadata"]
            ],
            "measurement_id": blend_data["measurement"]["measurement_id"],
        },
        "total_volume_l": blend_data["expected_total_volume_l"],
        "concentrations_mmol_l": blend_data["expected"],
        "measurement_output": blend_data["expected_measurement_output"],
        "provenance": blend_data["expected_provenance"],
    }
    state_values = list(result.state.all_values())
    stop = evaluate_run_stops(
        numerical_values={f"value_{index}": value for index, value in enumerate(state_values)},
        stocks={entity: result.state.total_stock(entity) for entity in entities},
        ledger_relative_residuals=audit.relative_residuals,
        physical_values={},
        physical_stops=threshold_policy.physical_stops,
        applicable_stop_ids=(),
        numerical_policy=threshold_policy.numerical_stops,
    )
    case_manifest = _run_case_manifest(
        manifest, chemistry_fixture, absolute_tolerance
    )
    entity_residuals = {
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
    blend_bounds = {
        field: abs(
            blend_observed["concentrations_mmol_l"][field]
            - blend_oracle["concentrations_mmol_l"][field]
        )
        for field in blend_oracle["concentrations_mmol_l"]
    }
    observed = {
        "minimum_state": min(state_values),
        "run_stop_valid": stop.valid and not stop.censored,
        "transfer": transfer_observed,
        "transfer_ledger": ledger_payload,
        "ro": ro_observed,
        "blend": blend_observed,
        "case_manifest": case_manifest,
        "ions_anchor": ions_anchor_observed,
        "entities": entity_residuals,
        "water_residual": entity_residuals["water"][
            "ro_feed_permeate_concentrate_residual"
        ],
        "registered_entities": len(entity_residuals),
        "blend_bounds": blend_bounds,
    }
    oracle = {
        "minimum_state": threshold_policy.numerical_stops.minimum_stock,
        "run_stop_valid": True,
        "transfer": fixture["expected_transfer"],
        "transfer_ledger": ledger_oracle,
        "ro": ro_oracle,
        "blend": blend_oracle,
        "case_manifest": {
            "counts": {"blend": 2, "flow": 2, "ro": 2},
            "per_quantity_extrema": _tree_constant(
                case_manifest["per_quantity_extrema"], 0.0
            ),
            "minimized_counterexample": None,
            "generator": manifest["generator"],
        },
        "ions_anchor": ions_anchor_oracle,
        "entities": {
            entity: {
                "transfer_residual": 0.0,
                "ro_feed_permeate_concentrate_residual": 0.0,
            }
            for entity in entity_residuals
        },
        "water_residual": 0.0,
        "registered_entities": len(ConservedEntity),
        "blend_bounds": {field: 0.0 for field in blend_bounds},
    }
    comparison = _tree_constant(oracle, "abs_le")
    assert isinstance(comparison, dict)
    comparison["minimum_state"] = "ge"
    comparison["run_stop_valid"] = "eq"
    comparison["transfer_ledger"] = _ledger_comparison(ledger_oracle)
    comparison["ro"]["water_conserved"] = "eq"
    comparison["ro"]["entities_conserved"] = _tree_constant(
        ro_oracle["entities_conserved"], "eq"
    )
    comparison["ro"]["branches_within_bounds"] = "eq"
    comparison["blend"]["inputs"] = _tree_constant(
        blend_oracle["inputs"], "eq"
    )
    comparison["blend"]["measurement_output"]["ec_kind"] = "eq"
    comparison["blend"]["provenance"] = _tree_constant(
        blend_oracle["provenance"], "eq"
    )
    comparison["case_manifest"]["counts"] = _tree_constant(
        oracle["case_manifest"]["counts"], "eq"
    )
    comparison["case_manifest"]["minimized_counterexample"] = "eq"
    comparison["case_manifest"]["generator"] = _tree_constant(
        manifest["generator"], "eq"
    )
    comparison["ions_anchor"]["ledger_audit"] = _ledger_comparison(
        ions_ledger_oracle
    )
    comparison["registered_entities"] = "eq"
    tolerance = _tree_constant(oracle, absolute_tolerance)
    assert isinstance(tolerance, dict)
    tolerance["minimum_state"] = 0.0
    tolerance["run_stop_valid"] = 0.0
    tolerance["transfer_ledger"] = _ledger_tolerance(
        ledger_oracle, absolute_tolerance
    )
    tolerance["ro"]["water_conserved"] = 0.0
    tolerance["ro"]["entities_conserved"] = _tree_constant(
        ro_oracle["entities_conserved"], 0.0
    )
    tolerance["ro"]["branches_within_bounds"] = 0.0
    tolerance["blend"]["inputs"] = _tree_constant(blend_oracle["inputs"], 0.0)
    tolerance["blend"]["measurement_output"]["ec_kind"] = 0.0
    tolerance["blend"]["provenance"] = _tree_constant(
        blend_oracle["provenance"], 0.0
    )
    tolerance["case_manifest"]["counts"] = _tree_constant(
        oracle["case_manifest"]["counts"], 0.0
    )
    tolerance["case_manifest"]["minimized_counterexample"] = 0.0
    tolerance["case_manifest"]["generator"] = _tree_constant(
        manifest["generator"], 0.0
    )
    tolerance["ions_anchor"]["ledger_audit"] = _ledger_tolerance(
        ions_ledger_oracle, absolute_tolerance
    )
    tolerance["registered_entities"] = 0.0
    record = _record(
        20,
        digest,
        observed,
        oracle,
        tolerance,
        comparison=comparison,
        fixture_sha256s={
            "all_conserved_entities.yaml": digest,
            "ions_conservative.yaml": ions_digest,
            "chemistry_handcheck.yaml": chemistry_digest,
            "conservation_case_manifest.yaml": manifest_digest,
            "configs/thresholds.yaml": threshold_policy.sha256,
        },
    )
    return record, {
        "anchor_ledger": _ledger_rows(ledger),
        "ions_anchor_ledger": _ledger_rows(ions_result.ledger),
    }


def _acceptance_20(
    *,
    stepper: Callable[..., StepResult] = step_state,
    ro_model: Callable[..., ROResult] = ro_split,
    ledger_transform: Callable[[tuple[LedgerEntry, ...]], tuple[LedgerEntry, ...]] | None = None,
) -> VerificationRecord:
    return _acceptance_20_bundle(
        stepper=stepper,
        ro_model=ro_model,
        ledger_transform=ledger_transform,
    )[0]


def _with_artifact_hash(
    record: VerificationRecord, resource_id: str, artifact: object
) -> tuple[VerificationRecord, bytes]:
    contents = _json_bytes(artifact)
    hashes = dict(record.auxiliary_artifacts_sha256s)
    hashes[resource_id] = hashlib.sha256(contents).hexdigest()
    return (
        VerificationRecord(
            acceptance_test=record.acceptance_test,
            fixture_sha256=record.fixture_sha256,
            observed_value=record.observed_value,
            oracle=record.oracle,
            tolerance=record.tolerance,
            comparison=record.comparison,
            code_version=record.code_version,
            code_provenance=record.code_provenance,
            evidence_label=record.evidence_label,
            fixture_sha256s=record.fixture_sha256s,
            auxiliary_artifacts_sha256s=hashes,
            validity=record.validity,
            censored=record.censored,
            reason_code=record.reason_code,
        ),
        contents,
    )


def run_core_acceptance(run_directory: Path) -> tuple[VerificationRecord, ...]:
    """Run only the core-owned registry and atomically write records plus audit data."""
    verification_policy = load_verification_policy()
    if verification_policy.core_acceptance_tests != _CORE_TESTS:
        raise RuntimeError("core acceptance policy registry is incomplete")
    raw_results: list[tuple[VerificationRecord, str | None, object | None]] = []
    for function, artifact_name in (
        (_acceptance_01_bundle, "test_01_ledger.json"),
        (_acceptance_02_bundle, "test_02_ledger.json"),
        (_acceptance_03_bundle, "test_03_trajectory.json"),
        (_acceptance_04_bundle, "test_04_trajectory.json"),
        (_acceptance_05, None),
        (_acceptance_13, None),
        (_acceptance_19, None),
        (_acceptance_20_bundle, "test_20_ledger.json"),
    ):
        result = function()
        if artifact_name is None:
            raw_results.append((result, None, None))  # type: ignore[arg-type]
        else:
            record, artifact = result  # type: ignore[misc]
            raw_results.append((record, artifact_name, artifact))
    records: list[VerificationRecord] = []
    artifact_payloads: list[tuple[Path, bytes]] = []
    for record, artifact_name, artifact in raw_results:
        if artifact_name is not None:
            resource_id = f"auxiliary/{artifact_name}"
            record, contents = _with_artifact_hash(record, resource_id, artifact)
            artifact_payloads.append(
                (run_directory / "verification" / resource_id, contents)
            )
        records.append(record)
    if tuple(record.acceptance_test for record in records) != _CORE_TESTS:
        raise RuntimeError("core acceptance implementation registry is incomplete")
    for record in records:
        record.validate()
    for target, contents in artifact_payloads:
        _atomic_write_bytes(target, contents)
    for record in records:
        write_verification_record(
            run_directory / "verification" / f"test_{record.acceptance_test:02d}.json",
            record,
        )
    return tuple(records)
