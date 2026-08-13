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
from math import exp, isclose, isfinite
from pathlib import Path
from types import MappingProxyType
from typing import Literal

from almondlab.chemistry import (
    BlendMeasurement,
    blend_by_volume,
    charge_balance_error,
    sodium_adsorption_ratio,
)
from almondlab.contracts import (
    CompartmentKind,
    ConservedEntity,
    DataOrigin,
    ECKind,
    EvidenceLabel,
    ExternalBoundaryCategory,
    InternalWaterFlowKind,
    LedgerCursor,
    LedgerEntry,
    LedgerEntryKind,
    MaterialTransferMode,
    OperatorPhase,
    StockUnit,
    entity_spec,
)
from almondlab.errors import AlmondLabError
from almondlab.hydraulics import HydraulicDomain, HydraulicInputs, hydraulic_uptake
from almondlab.mass_balance import (
    BalanceAudit,
    CompartmentState,
    ExternalBoundaryFlux,
    InternalWaterFlow,
    LedgerTransactionExpectation,
    NetworkState,
    StepResult,
    audit_ledger,
    step_state,
)
from almondlab.schemas import WaterBatch, WaterChemistry
from almondlab.treatment import ROParameters, ROResult, TreatmentStream, ro_split
from almondlab.verification_policy import (
    CONSERVATION_CANDIDATE_SET_SHA256,
    CORE_ACCEPTANCE_TESTS,
    PhysicalStopPolicy,
    ThresholdPolicy,
    load_conservation_case_manifest,
    load_fixture,
    load_fixture_bytes,
    load_threshold_policy,
    load_verification_policy,
    validate_threshold_policy,
)


_CORE_TESTS = CORE_ACCEPTANCE_TESTS


def _freeze_json(value: object, field_path: str = "value") -> object:
    if isinstance(value, Mapping):
        if any(not isinstance(key, str) for key in value):
            raise ValueError(f"{field_path} mappings require string keys")
        return MappingProxyType(
            {
                key: _freeze_json(item, f"{field_path}.{key}")
                for key, item in value.items()
            }
        )
    if isinstance(value, list | tuple):
        return tuple(
            _freeze_json(item, f"{field_path}.{index}")
            for index, item in enumerate(value)
        )
    return value


def _json_value(value: object, field_path: str) -> object:
    if isinstance(value, Mapping):
        if any(not isinstance(key, str) for key in value):
            raise ValueError(f"{field_path} mappings require string keys")
        return {
            key: _json_value(item, f"{field_path}.{key}")
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
    if type(value) is int:
        return "integer"
    if type(value) is float:
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
            return False
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
            return False
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
        if tolerance is not None and (
            type(tolerance) not in (int, float)
            or not isfinite(tolerance)
            or tolerance != 0
        ):
            raise ValueError(f"{field_path} eq tolerance must be zero")
        oracle_kind = _json_scalar_kind(oracle)
        if oracle_kind.startswith("unsupported:") or (
            type(oracle) is float and not isfinite(oracle)
        ):
            raise ValueError(f"{field_path} oracle must be a finite JSON scalar")
        observed_kind = _json_scalar_kind(observed)
        if observed_kind.startswith("unsupported:") or (
            type(observed) is float and not isfinite(observed)
        ):
            return False
        return (
            observed_kind == oracle_kind
            and observed == oracle
        )
    if type(oracle) not in (int, float) or not isfinite(oracle):
        raise ValueError(f"{field_path} oracle must be a finite primitive number")
    if type(tolerance) not in (int, float) or not isfinite(tolerance):
        raise ValueError(f"{field_path} tolerance must be a finite primitive number")
    if tolerance < 0.0:
        raise ValueError(f"{field_path} tolerance must be nonnegative")
    if type(observed) not in (int, float) or not isfinite(observed):
        return False
    observed_number = observed
    oracle_number = oracle
    tolerance_number = tolerance
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
    code_provenance: Mapping[str, object] = field(default_factory=dict)
    fixture_sha256s: Mapping[str, str] | None = None
    auxiliary_artifacts_sha256s: Mapping[str, str] | None = None
    validity: Literal["valid", "invalid"] = "valid"
    censored: bool = False
    reason_code: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.evidence_label, EvidenceLabel):
            raise TypeError("evidence_label must be an EvidenceLabel")
        observed = _freeze_json(self.observed_value, "observed_value")
        oracle = _freeze_json(self.oracle, "oracle")
        tolerance = _freeze_json(self.tolerance, "tolerance")
        comparison = _freeze_json(self.comparison, "comparison")
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
        frozen_provenance = _freeze_json(self.code_provenance, "code_provenance")
        assert isinstance(frozen_provenance, Mapping)
        object.__setattr__(self, "code_provenance", frozen_provenance)
        # Validate the oracle/comparison schema at construction.  Invalid observed
        # values are deliberately a failed comparison, not an exception.
        _evaluate_comparison(observed, oracle, tolerance, comparison)

    @property
    def passed(self) -> bool:
        """Derived acceptance state; callers cannot initialize or mutate it."""

        return self.validity == "valid" and _evaluate_comparison(
            self.observed_value,
            self.oracle,
            self.tolerance,
            self.comparison,
        )

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
        if not isinstance(self.code_version, str) or not self.code_version.strip():
            raise ValueError("code_version is required")
        required_provenance = {
            "package_version",
            "git_sha",
            "git_dirty",
            "git_status_sha256",
            "unavailable",
        }
        if set(self.code_provenance) != required_provenance:
            raise ValueError("code_provenance must expose package, Git SHA, dirty state, and unavailable fields")
        provenance = self.code_provenance
        package_version = provenance["package_version"]
        git_sha = provenance["git_sha"]
        git_dirty = provenance["git_dirty"]
        status_sha = provenance["git_status_sha256"]
        unavailable = provenance["unavailable"]
        if package_version is not None and (
            not isinstance(package_version, str) or not package_version.strip()
        ):
            raise ValueError("code provenance package_version must be string or null")
        if git_sha is not None and (
            not isinstance(git_sha, str)
            or len(git_sha) != 40
            or any(character not in "0123456789abcdef" for character in git_sha)
        ):
            raise ValueError("code provenance git_sha must be exact lowercase SHA or null")
        if git_dirty is not None and type(git_dirty) is not bool:
            raise ValueError("code provenance git_dirty must be boolean or null")
        if status_sha is not None and (
            not isinstance(status_sha, str)
            or len(status_sha) != 64
            or any(character not in "0123456789abcdef" for character in status_sha)
        ):
            raise ValueError("code provenance git_status_sha256 must be SHA-256 or null")
        if not isinstance(unavailable, tuple) or any(
            not isinstance(item, str) for item in unavailable
        ):
            raise ValueError("code provenance unavailable must be an immutable string list")
        nullable_fields = (
            "package_version",
            "git_sha",
            "git_dirty",
            "git_status_sha256",
        )
        expected_unavailable = tuple(
            name for name in nullable_fields if provenance[name] is None
        )
        if tuple(unavailable) != expected_unavailable:
            raise ValueError(
                "code provenance unavailable must exactly match null provenance fields"
            )
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
    threshold_policy: ThresholdPolicy,
    applicable_stop_ids: Sequence[str] | None = None,
) -> RunStopStatus:
    """Evaluate required numerical stops before explicitly applicable physical stops."""
    validate_threshold_policy(threshold_policy)
    policy = threshold_policy.numerical_stops
    physical_stops = threshold_policy.physical_stops
    supplied = (numerical_values, stocks, ledger_relative_residuals, physical_values)
    if any(
        not isinstance(mapping, Mapping)
        or any(
            not isinstance(name, str)
            or type(value) not in (int, float)
            for name, value in mapping.items()
        )
        for mapping in supplied
    ):
        return RunStopStatus(False, False, "NONNUMERIC_STATE")
    numerical = dict(numerical_values)
    normalized_stocks = dict(stocks)
    residuals = dict(ledger_relative_residuals)
    physical = dict(physical_values)
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


def capture_code_provenance() -> Mapping[str, object]:
    """Capture exact package/Git provenance for the loaded verification module."""

    try:
        package_version: str | None = version("saltwater-mini-almond")
    except PackageNotFoundError:
        package_version = None
    git_sha: str | None = None
    git_dirty: bool | None = None
    git_status_sha256: str | None = None
    try:
        module_path = Path(__file__).resolve()
        root_text = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=module_path.parent,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
        worktree = Path(root_text).resolve()
        relative_module = module_path.relative_to(worktree).as_posix()
        subprocess.run(
            ["git", "ls-files", "--error-unmatch", "--", relative_module],
            cwd=worktree,
            capture_output=True,
            check=True,
        )
        candidate_sha = subprocess.run(
            ["git", "rev-parse", "--verify", "HEAD"],
            cwd=worktree,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
        if len(candidate_sha) != 40 or any(
            character not in "0123456789abcdef" for character in candidate_sha
        ):
            raise ValueError("Git returned a noncanonical SHA")
        status_bytes = subprocess.run(
            ["git", "status", "--porcelain=v1", "--untracked-files=all"],
            cwd=worktree,
            capture_output=True,
            check=True,
        ).stdout
        git_sha = candidate_sha
        git_dirty = bool(status_bytes)
        git_status_sha256 = hashlib.sha256(status_bytes).hexdigest()
    except (OSError, ValueError, subprocess.CalledProcessError):
        git_sha = None
        git_dirty = None
        git_status_sha256 = None
    fields = {
        "package_version": package_version,
        "git_sha": git_sha,
        "git_dirty": git_dirty,
        "git_status_sha256": git_status_sha256,
    }
    unavailable = tuple(name for name, value in fields.items() if value is None)
    return MappingProxyType(
        {
            **fields,
            "unavailable": tuple(unavailable),
        }
    )


def code_version_from_provenance(provenance: Mapping[str, object]) -> str:
    """Render the stable code-version summary from a validated provenance map."""

    frozen = _freeze_json(provenance, "code_provenance")
    assert isinstance(frozen, Mapping)
    probe = VerificationRecord(
        acceptance_test=1,
        fixture_sha256="0" * 64,
        observed_value=0,
        oracle=0,
        tolerance=0,
        comparison="eq",
        code_version="provenance-validation",
        code_provenance=frozen,
        evidence_label=EvidenceLabel.SYNTHETIC_ONLY,
    )
    probe.validate()
    parts = [f"package:{provenance['package_version'] or 'unavailable'}"]
    parts.append(f"git:{provenance['git_sha'] or 'unavailable'}")
    parts.append(
        "dirty:unavailable"
        if provenance["git_dirty"] is None
        else f"dirty:{str(provenance['git_dirty']).lower()}"
    )
    return ";".join(parts)


# Compatibility aliases for internal callers and existing downstream tests.
_code_provenance = capture_code_provenance
_code_version = code_version_from_provenance


def _entity(value: object, field_path: str) -> ConservedEntity:
    if not isinstance(value, str):
        raise ValueError(f"{field_path} must be a conserved-entity identifier")
    try:
        return ConservedEntity(value)
    except ValueError as error:
        raise ValueError(f"{field_path} is not a registered conserved entity") from error


def _state(fixture: Mapping[str, object]) -> NetworkState:
    """Build only canonical schema-v2 states; no volume-only compatibility path."""

    if fixture.get("schema_version") != 2:
        raise ValueError("verification state fixtures require schema_version 2")
    initial = fixture.get("initial")
    raw_entities = fixture.get("tracked_entities")
    raw_label = fixture.get("evidence_label")
    if not isinstance(initial, Mapping) or not isinstance(raw_entities, list):
        raise ValueError("schema-v2 state fixture is incomplete")
    try:
        label = EvidenceLabel(raw_label)
    except (TypeError, ValueError) as error:
        raise ValueError("fixture evidence_label is invalid") from error
    tracked = frozenset(
        _entity(value, f"tracked_entities.{index}")
        for index, value in enumerate(raw_entities)
    )
    compartments: dict[str, CompartmentState] = {}
    for compartment_id, raw in initial.items():
        if not isinstance(compartment_id, str) or not isinstance(raw, Mapping):
            raise ValueError("fixture compartments require string IDs and mappings")
        stocks = raw.get("stocks")
        if not isinstance(stocks, Mapping):
            raise ValueError(f"initial.{compartment_id}.stocks must be a mapping")
        compartments[compartment_id] = CompartmentState(
            compartment_id=compartment_id,
            kind=CompartmentKind(raw["kind"]),
            loop_id=raw["loop_id"],  # type: ignore[arg-type]
            volume_l=raw["volume_l"],  # type: ignore[arg-type]
            water_mass_kg=raw["water_mass_kg"],  # type: ignore[arg-type]
            empty_reference_density_kg_l=raw["empty_reference_density_kg_l"],  # type: ignore[arg-type]
            stocks={
                _entity(entity, f"initial.{compartment_id}.stocks"): amount
                for entity, amount in stocks.items()
            },
            evidence_label=label,
        )
    return NetworkState(
        compartments=compartments,
        tracked_entities=tracked,
        evidence_label=label,
    )


def _water_flow(fixture: Mapping[str, object]) -> InternalWaterFlow:
    raw = fixture.get("flow")
    if not isinstance(raw, Mapping):
        raise ValueError("fixture.flow must be a mapping")
    return InternalWaterFlow(
        event_id=raw["event_id"],  # type: ignore[arg-type]
        source=raw["source"],  # type: ignore[arg-type]
        target=raw["target"],  # type: ignore[arg-type]
        rate_l_per_hour=raw["rate_l_per_hour"],  # type: ignore[arg-type]
        flow_kind=InternalWaterFlowKind(raw["flow_kind"]),
        phase=OperatorPhase(raw["phase"]),
        evidence_label=EvidenceLabel(raw["evidence_label"]),
        physical_transfer_id=raw.get("physical_transfer_id"),  # type: ignore[arg-type]
    )


def _cursor(fixture: Mapping[str, object]) -> LedgerCursor:
    raw = fixture.get("cursor")
    if not isinstance(raw, Mapping):
        raise ValueError("fixture.cursor must be a mapping")
    return LedgerCursor(
        run_id=raw["run_id"],  # type: ignore[arg-type]
        chain_id=raw["chain_id"],  # type: ignore[arg-type]
        next_ordinal=raw["start_ordinal"],  # type: ignore[arg-type]
    )


def _fixture(name: str) -> tuple[dict[str, object], str]:
    return load_fixture(name)


def _tree_constant(template: object, value: object) -> object:
    if isinstance(template, Mapping):
        return {key: _tree_constant(item, value) for key, item in template.items()}
    if isinstance(template, (tuple, list)):
        return [_tree_constant(item, value) for item in template]
    return value


def _comparison_tree(template: object, numeric: str = "abs_le") -> object:
    if isinstance(template, Mapping):
        return {key: _comparison_tree(item, numeric) for key, item in template.items()}
    if isinstance(template, (tuple, list)):
        return [_comparison_tree(item, numeric) for item in template]
    return numeric if type(template) is float else "eq"


def _tolerance_tree(template: object, tolerance: float) -> object:
    if isinstance(template, Mapping):
        return {key: _tolerance_tree(item, tolerance) for key, item in template.items()}
    if isinstance(template, (tuple, list)):
        return [_tolerance_tree(item, tolerance) for item in template]
    return tolerance if type(template) is float else 0


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
    provenance = capture_code_provenance()
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
        code_version=code_version_from_provenance(provenance),
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
) -> tuple[tuple[LedgerEntry, ...], str | None]:
    if transform is None:
        return ledger, None
    try:
        return tuple(transform(ledger)), None
    except (AlmondLabError, TypeError, ValueError) as error:
        return (), f"{type(error).__name__}:{error}"


def _ledger_rows(ledger: tuple[LedgerEntry, ...]) -> list[dict[str, object]]:
    return [
        {
            "transaction_id": row.transaction_id,
            "event_id": row.event_id,
            "kind": row.kind.value,
            "phase": row.phase.value,
            "transfer_mode": row.transfer_mode.value,
            "compartment": row.compartment,
            "counterparty": row.counterparty,
            "quantity": row.entity.value,
            "amount": row.amount,
            "unit": row.unit.value,
            "evidence_label": row.evidence_label.value,
            "boundary_category": (
                None if row.boundary_category is None else row.boundary_category.value
            ),
            "internal_flux_kind": (
                None if row.internal_flux_kind is None else row.internal_flux_kind.value
            ),
            "internal_water_flow_kind": (
                None
                if row.internal_water_flow_kind is None
                else row.internal_water_flow_kind.value
            ),
            "physical_transfer_id": row.physical_transfer_id,
            "carrier_volume_l": row.carrier_volume_l,
            "water_density_kg_l": row.water_density_kg_l,
            "requested_amount": row.requested_amount,
            "applied_amount": row.applied_amount,
            "cap_fraction": row.cap_fraction,
            "adapter_id": row.adapter_id,
            "adapter_version": row.adapter_version,
            "adapter_hash": row.adapter_hash,
            "treatment_model_id": row.treatment_model_id,
            "treatment_model_version": row.treatment_model_version,
        }
        for row in ledger
    ]


def _ledger_audit(
    audit: BalanceAudit,
    ledger: tuple[LedgerEntry, ...],
    *,
    expected_events: Sequence[InternalWaterFlow],
    transform_error: str | None,
) -> dict[str, object]:
    quantities = tuple(sorted(entity.value for entity in audit.quantities))
    compartments = tuple(sorted(audit.relative_compartment_residuals))
    return {
        "balanced": audit.balanced,
        "structural_errors": list(audit.structural_errors),
        "transform_error": transform_error,
        "quantities": list(quantities),
        "compartments": list(compartments),
        "global_relative_residuals": {
            entity.value: audit.relative_residuals[entity]
            for entity in sorted(audit.quantities, key=lambda item: item.value)
        },
        "compartment_relative_residuals": {
            compartment: {
                entity.value: audit.relative_compartment_residuals[compartment][entity]
                for entity in sorted(audit.quantities, key=lambda item: item.value)
            }
            for compartment in compartments
        },
        "relative_volume_residual": audit.relative_volume_residual,
        "relative_compartment_volume_residuals": {
            compartment: audit.relative_compartment_volume_residuals[compartment]
            for compartment in compartments
        },
        "extrema": {
            "global_relative_by_quantity": {
                entity.value: abs(audit.relative_residuals[entity])
                for entity in sorted(audit.quantities, key=lambda item: item.value)
            },
            "compartment_relative_by_quantity": {
                entity.value: max(
                    abs(audit.relative_compartment_residuals[compartment][entity])
                    for compartment in compartments
                )
                for entity in sorted(audit.quantities, key=lambda item: item.value)
            },
            "volume_relative_global": abs(audit.relative_volume_residual),
            "volume_relative_by_compartment": {
                compartment: abs(
                    audit.relative_compartment_volume_residuals[compartment]
                )
                for compartment in compartments
            },
        },
    }


_EXPECTED_LEDGER_KEYS = frozenset(
    {
        "run_id",
        "chain_id",
        "start_ordinal",
        "transaction_count",
        "row_count",
        "event_id",
        "phase",
        "transfer_mode",
        "flow_kind",
        "source",
        "target",
        "evidence_label",
        "carrier_volume_l",
        "transaction_duration_hours",
        "water_density_kg_l",
        "per_transaction_amounts",
    }
)


def _strict_fixture_number(
    value: object, field_path: str, *, positive: bool = False
) -> float:
    if type(value) not in (int, float):
        raise ValueError(f"{field_path} must be a primitive JSON number")
    try:
        converted = float(value)
    except OverflowError as error:
        raise ValueError(f"{field_path} must be finite") from error
    if not isfinite(converted) or (positive and converted <= 0.0):
        qualifier = "finite and positive" if positive else "finite"
        raise ValueError(f"{field_path} must be {qualifier}")
    return converted


def _strict_fixture_integer(
    value: object, field_path: str, *, positive: bool = False
) -> int:
    if type(value) is not int or value < (1 if positive else 0):
        qualifier = "positive" if positive else "nonnegative"
        raise ValueError(f"{field_path} must be a {qualifier} primitive integer")
    return value


def _validate_expected_ledger(
    expected_ledger: Mapping[str, object],
    *,
    required_quantities: Sequence[ConservedEntity] | None = None,
) -> None:
    if not isinstance(expected_ledger, Mapping) or any(
        not isinstance(key, str) for key in expected_ledger
    ):
        raise ValueError("expected ledger must be a string-keyed mapping")
    if set(expected_ledger) != _EXPECTED_LEDGER_KEYS:
        raise ValueError("expected ledger must expose the exact schema-v2 fields")
    for field_name in (
        "run_id",
        "chain_id",
        "event_id",
        "source",
        "target",
    ):
        value = expected_ledger[field_name]
        if not isinstance(value, str) or not value:
            raise ValueError(f"expected_ledger.{field_name} must be a nonempty string")
    if expected_ledger["source"] == expected_ledger["target"]:
        raise ValueError("expected ledger source and target must differ")
    try:
        OperatorPhase(expected_ledger["phase"])
        mode = MaterialTransferMode(expected_ledger["transfer_mode"])
        flow_kind = InternalWaterFlowKind(expected_ledger["flow_kind"])
        EvidenceLabel(expected_ledger["evidence_label"])
    except (TypeError, ValueError) as error:
        raise ValueError("expected ledger contains invalid typed metadata") from error
    if (
        mode is not MaterialTransferMode.ADVECTIVE_AQUEOUS
        or flow_kind is not InternalWaterFlowKind.AQUEOUS_TRANSFER
    ):
        raise ValueError("expected ledger is not an advective aqueous transfer")
    first = _strict_fixture_integer(
        expected_ledger["start_ordinal"], "expected_ledger.start_ordinal"
    )
    count = _strict_fixture_integer(
        expected_ledger["transaction_count"],
        "expected_ledger.transaction_count",
        positive=True,
    )
    row_count = _strict_fixture_integer(
        expected_ledger["row_count"], "expected_ledger.row_count", positive=True
    )
    if first + count - 1 > 999_999_999_999:
        raise ValueError("expected ledger transaction namespace overflows 12 digits")
    carrier = _strict_fixture_number(
        expected_ledger["carrier_volume_l"],
        "expected_ledger.carrier_volume_l",
        positive=True,
    )
    density = _strict_fixture_number(
        expected_ledger["water_density_kg_l"],
        "expected_ledger.water_density_kg_l",
        positive=True,
    )
    _strict_fixture_number(
        expected_ledger["transaction_duration_hours"],
        "expected_ledger.transaction_duration_hours",
        positive=True,
    )
    raw_amounts = expected_ledger["per_transaction_amounts"]
    if not isinstance(raw_amounts, Mapping) or not raw_amounts or any(
        not isinstance(key, str) for key in raw_amounts
    ):
        raise ValueError("expected ledger amounts must be a nonempty string-keyed mapping")
    parsed_entities: set[ConservedEntity] = set()
    parsed_amounts: dict[ConservedEntity, float] = {}
    for raw_entity, raw_amount in raw_amounts.items():
        entity = _entity(raw_entity, "expected_ledger.per_transaction_amounts")
        if entity in parsed_entities:
            raise ValueError("expected ledger contains a duplicate conserved entity")
        parsed_entities.add(entity)
        parsed_amounts[entity] = _strict_fixture_number(
            raw_amount,
            f"expected_ledger.per_transaction_amounts.{raw_entity}",
        )
        if parsed_amounts[entity] < 0.0:
            raise ValueError("expected ledger amounts must be nonnegative")
    if ConservedEntity.WATER not in parsed_entities:
        raise ValueError("expected ledger must contain explicit water mass")
    if required_quantities is not None and parsed_entities != set(required_quantities):
        raise ValueError("expected ledger quantities do not match the canonical registry")
    if row_count != count * len(parsed_entities) * 2:
        raise ValueError("expected ledger row count disagrees with its literal inventory")
    if not isclose(
        parsed_amounts[ConservedEntity.WATER],
        carrier * density,
        rel_tol=1e-12,
        abs_tol=1e-12,
    ):
        raise ValueError("expected ledger water mass disagrees with carrier and density")


def _expected_transaction_ids(expected_ledger: Mapping[str, object]) -> list[str]:
    _validate_expected_ledger(expected_ledger)
    first = expected_ledger["start_ordinal"]
    count = expected_ledger["transaction_count"]
    assert type(first) is int and type(count) is int
    run_id = expected_ledger["run_id"]
    chain_id = expected_ledger["chain_id"]
    return [
        f"tx:{run_id}:{chain_id}:{ordinal:012d}"
        for ordinal in range(first, first + count)
    ]


def _ledger_transaction_expectations(
    expected_ledger: Mapping[str, object],
) -> tuple[LedgerTransactionExpectation, ...]:
    """Map fixture literals into mass-audit authority without consulting rows."""

    _validate_expected_ledger(expected_ledger)
    raw_amounts = expected_ledger["per_transaction_amounts"]
    raw_duration = expected_ledger["transaction_duration_hours"]
    assert isinstance(raw_amounts, Mapping)
    duration = _strict_fixture_number(
        raw_duration,
        "expected_ledger.transaction_duration_hours",
        positive=True,
    )
    amounts: dict[ConservedEntity, float] = {}
    for raw_entity, raw_amount in raw_amounts.items():
        if not isinstance(raw_entity, str):
            raise ValueError("expected ledger amount keys must be strings")
        amounts[_entity(raw_entity, "expected_ledger.per_transaction_amounts")] = (
            _strict_fixture_number(
                raw_amount,
                f"expected_ledger.per_transaction_amounts.{raw_entity}",
            )
        )
    return tuple(
        LedgerTransactionExpectation(
            transaction_id=transaction_id,
            event_id=expected_ledger["event_id"],  # type: ignore[arg-type]
            dt_hours=duration,
            amounts=amounts,
        )
        for transaction_id in _expected_transaction_ids(expected_ledger)
    )


def _validate_flow_authority_fixture(
    fixture: Mapping[str, object], event: InternalWaterFlow
) -> None:
    expected_ledger = fixture.get("expected_ledger")
    if not isinstance(expected_ledger, Mapping):
        raise ValueError("fixture.expected_ledger must be a mapping")
    _validate_expected_ledger(expected_ledger)
    duration = _strict_fixture_number(
        fixture.get("duration_hours"), "fixture.duration_hours", positive=True
    )
    transaction_duration = _strict_fixture_number(
        expected_ledger["transaction_duration_hours"],
        "expected_ledger.transaction_duration_hours",
        positive=True,
    )
    count = expected_ledger["transaction_count"]
    assert type(count) is int
    carrier = _strict_fixture_number(
        expected_ledger["carrier_volume_l"],
        "expected_ledger.carrier_volume_l",
        positive=True,
    )
    if not isclose(
        count * transaction_duration,
        duration,
        rel_tol=1e-12,
        abs_tol=1e-12,
    ):
        raise ValueError("expected ledger intervals do not cover fixture duration")
    if not isclose(
        event.rate_l_per_hour * transaction_duration,
        carrier,
        rel_tol=1e-12,
        abs_tol=1e-12,
    ):
        raise ValueError("expected ledger carrier disagrees with event rate and interval")


def _ledger_oracle(
    expected_ledger: Mapping[str, object],
    *,
    required_quantities: Sequence[ConservedEntity],
    expected_compartments: Sequence[str],
) -> dict[str, object]:
    _validate_expected_ledger(
        expected_ledger, required_quantities=required_quantities
    )
    amounts = expected_ledger["per_transaction_amounts"]
    if not isinstance(amounts, Mapping):
        raise ValueError("expected ledger amounts must be a mapping")
    expected_quantity_names = {entity.value for entity in required_quantities}
    quantity_order = (
        [ConservedEntity.WATER]
        if ConservedEntity.WATER in required_quantities
        else []
    ) + sorted(
        (entity for entity in required_quantities if entity is not ConservedEntity.WATER),
        key=lambda item: item.value,
    )
    rows: list[dict[str, object]] = []
    for transaction_id in _expected_transaction_ids(expected_ledger):
        for entity in quantity_order:
            amount = amounts[entity.value]
            parsed_amount = _strict_fixture_number(
                amount, f"expected_ledger.per_transaction_amounts.{entity.value}"
            )
            common = {
                "transaction_id": transaction_id,
                "event_id": expected_ledger["event_id"],
                "kind": LedgerEntryKind.INTERNAL.value,
                "phase": expected_ledger["phase"],
                "transfer_mode": expected_ledger["transfer_mode"],
                "quantity": entity.value,
                "unit": entity_spec(entity).stock_unit.value,
                "evidence_label": expected_ledger["evidence_label"],
                "boundary_category": None,
                "internal_flux_kind": None,
                "internal_water_flow_kind": (
                    expected_ledger["flow_kind"]
                    if entity is ConservedEntity.WATER
                    else None
                ),
                "physical_transfer_id": expected_ledger.get("physical_transfer_id"),
                "carrier_volume_l": (
                    expected_ledger["carrier_volume_l"]
                    if entity is ConservedEntity.WATER
                    else None
                ),
                "water_density_kg_l": (
                    expected_ledger["water_density_kg_l"]
                    if entity is ConservedEntity.WATER
                    else None
                ),
                "requested_amount": None,
                "applied_amount": None,
                "cap_fraction": None,
                "adapter_id": None,
                "adapter_version": None,
                "adapter_hash": None,
                "treatment_model_id": None,
                "treatment_model_version": None,
            }
            rows.extend(
                (
                    {
                        **common,
                        "compartment": expected_ledger["source"],
                        "counterparty": expected_ledger["target"],
                        "amount": -parsed_amount,
                    },
                    {
                        **common,
                        "compartment": expected_ledger["target"],
                        "counterparty": expected_ledger["source"],
                        "amount": parsed_amount,
                    },
                )
            )
    quantity_names = sorted(expected_quantity_names)
    compartments = sorted(expected_compartments)
    return {
        "ledger": rows,
        "audit": {
            "balanced": True,
            "structural_errors": [],
            "transform_error": None,
            "quantities": quantity_names,
            "compartments": compartments,
            "global_relative_residuals": {name: 0.0 for name in quantity_names},
        "compartment_relative_residuals": {
                compartment: {name: 0.0 for name in quantity_names}
                for compartment in compartments
            },
            "relative_volume_residual": 0.0,
            "relative_compartment_volume_residuals": {
                compartment: 0.0 for compartment in compartments
            },
            "extrema": {
                "global_relative_by_quantity": {
                    name: 0.0 for name in quantity_names
                },
                "compartment_relative_by_quantity": {
                    name: 0.0 for name in quantity_names
                },
                "volume_relative_global": 0.0,
                "volume_relative_by_compartment": {
                    compartment: 0.0 for compartment in compartments
                },
            },
        },
        "next_cursor": {
            "run_id": expected_ledger["run_id"],
            "chain_id": expected_ledger["chain_id"],
            "next_ordinal": expected_ledger["start_ordinal"]
            + expected_ledger["transaction_count"],  # type: ignore[operator]
        },
    }


def _ledger_comparison(oracle: object) -> object:
    return _comparison_tree(oracle)


def _ledger_tolerance(oracle: object, residual_tolerance: float) -> object:
    return _tolerance_tree(oracle, residual_tolerance)


def _state_payload(state: NetworkState) -> dict[str, object]:
    return {
        compartment_id: {
            "kind": compartment.kind.value,
            "loop_id": compartment.loop_id,
            "volume_l": compartment.volume_l,
            "water_mass_kg": compartment.water_mass_kg,
            "density_kg_l": compartment.density_kg_l,
            "stocks": {
                entity.value: compartment.stocks[entity]
                for entity in sorted(state.tracked_entities, key=lambda item: item.value)
            },
            "evidence_label": compartment.evidence_label.value,
        }
        for compartment_id, compartment in state.compartments.items()
    }


def _state_oracle(fixture: Mapping[str, object]) -> dict[str, object]:
    initial = fixture["initial"]
    expected = fixture["expected"]
    if not isinstance(initial, Mapping) or not isinstance(expected, Mapping):
        raise ValueError("state fixture must declare initial and expected mappings")
    result: dict[str, object] = {}
    for compartment_id, values in expected.items():
        source = initial[compartment_id]
        if not isinstance(values, Mapping) or not isinstance(source, Mapping):
            raise ValueError("state oracle compartments must be mappings")
        volume = values["volume_l"]
        water = values["water_mass_kg"]
        result[compartment_id] = {
            "kind": source["kind"],
            "loop_id": source["loop_id"],
            "volume_l": volume,
            "water_mass_kg": water,
            "density_kg_l": (
                source["empty_reference_density_kg_l"]
                if volume == 0
                else water / volume  # type: ignore[operator]
            ),
            "stocks": dict(values["stocks"]),  # type: ignore[arg-type]
            "evidence_label": fixture["evidence_label"],
        }
    return result


def _conservation_acceptance_bundle(
    test_number: int,
    fixture_name: str,
    *,
    ledger_transform: Callable[[tuple[LedgerEntry, ...]], tuple[LedgerEntry, ...]]
    | None = None,
) -> tuple[VerificationRecord, object]:
    fixture, digest = _fixture(fixture_name)
    policy = load_verification_policy()
    before = _state(fixture)
    event = _water_flow(fixture)
    _validate_flow_authority_fixture(fixture, event)
    expected_transactions = _ledger_transaction_expectations(
        fixture["expected_ledger"]  # type: ignore[arg-type]
    )
    result = step_state(
        before,
        dt_hours=fixture["duration_hours"],  # type: ignore[arg-type]
        cursor=_cursor(fixture),
        water_flows=(event,),
    )
    ledger, transform_error = _apply_ledger_transform(
        result.ledger, ledger_transform
    )
    try:
        audit = audit_ledger(
            before,
            result.state,
            ledger,
            expected_events=(event,),
            expected_transactions=expected_transactions,
        )
        audit_payload = _ledger_audit(
            audit,
            ledger,
            expected_events=(event,),
            transform_error=transform_error,
        )
    except AlmondLabError as error:
        # Keep the comparison shape independent and expose the rejected candidate.
        baseline = audit_ledger(
            before,
            result.state,
            (),
            expected_events=(event,),
            expected_transactions=expected_transactions,
        )
        audit_payload = _ledger_audit(
            baseline,
            (),
            expected_events=(event,),
            transform_error=f"{error.code}:{error.field_path}",
        )
    required = tuple(
        sorted(
            {ConservedEntity.WATER, *before.tracked_entities},
            key=lambda item: item.value,
        )
    )
    ledger_oracle = _ledger_oracle(
        fixture["expected_ledger"],  # type: ignore[arg-type]
        required_quantities=required,
        expected_compartments=tuple(before.compartments),
    )
    observed = {
        "post_state": _state_payload(result.state),
        "ledger": _ledger_rows(ledger),
        "audit": audit_payload,
        "next_cursor": {
            "run_id": result.next_cursor.run_id,
            "chain_id": result.next_cursor.chain_id,
            "next_ordinal": result.next_cursor.next_ordinal,
        },
    }
    oracle = {
        "post_state": _state_oracle(fixture),
        **ledger_oracle,
    }
    absolute = policy.tolerances[test_number]["absolute"]
    record = _record(
        test_number,
        digest,
        observed,
        oracle,
        _tolerance_tree(oracle, absolute),
        comparison=_comparison_tree(oracle),
        fixture_sha256s={fixture_name: digest},
    )
    return record, observed["ledger"]


def _acceptance_01_bundle(
    *, ledger_transform: Callable[[tuple[LedgerEntry, ...]], tuple[LedgerEntry, ...]] | None = None
) -> tuple[VerificationRecord, object]:
    return _conservation_acceptance_bundle(
        1, "water_one_day.yaml", ledger_transform=ledger_transform
    )


def _acceptance_02_bundle(
    *, ledger_transform: Callable[[tuple[LedgerEntry, ...]], tuple[LedgerEntry, ...]] | None = None
) -> tuple[VerificationRecord, object]:
    return _conservation_acceptance_bundle(
        2, "ions_conservative.yaml", ledger_transform=ledger_transform
    )


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
    state = _state(fixture)
    cursor = _cursor(fixture)
    source = fixture["source_flux"]
    if not isinstance(source, Mapping):
        raise ValueError("no-purge source_flux must be a mapping")
    source_event = ExternalBoundaryFlux(
        event_id=source["event_id"],  # type: ignore[arg-type]
        compartment="tank",
        boundary_id=source["boundary_id"],  # type: ignore[arg-type]
        category=ExternalBoundaryCategory(source["category"]),
        material_mode=MaterialTransferMode(source["material_mode"]),
        volume_rate_l_per_hour=0.0,
        entity_rates_per_hour={ConservedEntity.NA: source["na_mmol_per_hour"]},  # type: ignore[dict-item]
        current_mixture_advection=False,
        phase=OperatorPhase(source["phase"]),
        evidence_label=EvidenceLabel.PHYSICS_CONSTRAINED,
    )
    time_hours = 0.0
    sample_hours = float(fixture["sample_hours"])
    trajectory: list[dict[str, float]] = [
        {
            "time_hours": 0.0,
            "concentration_mmol_l": state.concentration("tank", ConservedEntity.NA),
        }
    ]
    stop = evaluate_run_stops(
        numerical_values={"concentration": trajectory[-1]["concentration_mmol_l"]},
        stocks={"na": state.total_stock(ConservedEntity.NA)},
        ledger_relative_residuals={"water": 0.0, "na": 0.0},
        physical_values={
            "concentration_mmol_l": trajectory[-1]["concentration_mmol_l"]
        },
        threshold_policy=threshold_policy,
        applicable_stop_ids=("concentration_mmol_l",),
    )
    while stop.valid and not stop.censored:
        before = state
        result = step_state(
            state,
            dt_hours=sample_hours,
            cursor=cursor,
            boundary_fluxes=(source_event,),
        )
        state = result.state
        cursor = result.next_cursor
        time_hours += sample_hours
        concentration = state.concentration("tank", ConservedEntity.NA)
        audit = audit_ledger(
            before, state, result.ledger, expected_events=(source_event,)
        )
        trajectory.append(
            {"time_hours": time_hours, "concentration_mmol_l": concentration}
        )
        stop = evaluate_run_stops(
            numerical_values={"concentration": concentration},
            stocks={"na": state.total_stock(ConservedEntity.NA)},
            ledger_relative_residuals={
                entity.value: value
                for entity, value in audit.relative_residuals.items()
            },
            physical_values={"concentration_mmol_l": concentration},
            threshold_policy=threshold_policy,
            applicable_stop_ids=("concentration_mmol_l",),
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
    state = _state(fixture)
    cursor = _cursor(fixture)
    influx_data = fixture["influx"]
    purge_data = fixture["purge_flux"]
    if not isinstance(influx_data, Mapping) or not isinstance(purge_data, Mapping):
        raise ValueError("purge fixture events must be mappings")
    influx = ExternalBoundaryFlux(
        event_id=influx_data["event_id"],  # type: ignore[arg-type]
        compartment="tank",
        boundary_id=influx_data["boundary_id"],  # type: ignore[arg-type]
        category=ExternalBoundaryCategory(influx_data["category"]),
        material_mode=MaterialTransferMode.ADVECTIVE_AQUEOUS,
        volume_rate_l_per_hour=influx_data["volume_l_per_hour"],  # type: ignore[arg-type]
        water_density_kg_l=influx_data["water_density_kg_l"],  # type: ignore[arg-type]
        entity_rates_per_hour={
            ConservedEntity.NA: influx_data["na_mmol_per_hour"]  # type: ignore[dict-item]
        },
        current_mixture_advection=False,
        phase=OperatorPhase.EXTERNAL_FEED_AMENDMENT,
        evidence_label=EvidenceLabel.PHYSICS_CONSTRAINED,
    )
    purge = ExternalBoundaryFlux(
        event_id=purge_data["event_id"],  # type: ignore[arg-type]
        compartment="tank",
        boundary_id=purge_data["boundary_id"],  # type: ignore[arg-type]
        category=ExternalBoundaryCategory.PURGE_OR_DISCHARGE,
        material_mode=MaterialTransferMode.ADVECTIVE_AQUEOUS,
        volume_rate_l_per_hour=purge_data["volume_l_per_hour"],  # type: ignore[arg-type]
        entity_rates_per_hour={},
        current_mixture_advection=True,
        phase=OperatorPhase.PURGE_DISPOSAL,
        evidence_label=EvidenceLabel.PHYSICS_CONSTRAINED,
    )
    sample_hours = float(fixture["sample_hours"])
    samples = int(fixture["samples"])
    c_ss = float(fixture["c_in"]) + float(fixture["m_dot"]) / float(fixture["purge"])
    trajectory = [
        {
            "time_hours": 0.0,
            "concentration_mmol_l": state.concentration("tank", ConservedEntity.NA),
            "oracle_concentration_mmol_l": float(fixture["c0"]),
            "relative_error": 0.0,
        }
    ]
    for index in range(1, samples + 1):
        result = step_state(
            state,
            dt_hours=sample_hours,
            cursor=cursor,
            boundary_fluxes=(influx, purge),
            max_substep_hours=fixture["verification_max_substep_hours"],  # type: ignore[arg-type]
        )
        state = result.state
        cursor = result.next_cursor
        time_hours = index * sample_hours
        oracle_concentration = c_ss + (float(fixture["c0"]) - c_ss) * exp(
            -float(fixture["purge"]) * time_hours / float(fixture["volume"])
        )
        concentration = state.concentration("tank", ConservedEntity.NA)
        trajectory.append(
            {
                "time_hours": time_hours,
                "concentration_mmol_l": concentration,
                "oracle_concentration_mmol_l": oracle_concentration,
                "relative_error": abs(concentration - oracle_concentration)
                / max(abs(oracle_concentration), 1e-30),
            }
        )
    terminal_ratio = (state.concentration("tank", ConservedEntity.NA) - c_ss) / (
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
    feed_data = rejection_data["feed"]
    parameters_data = rejection_data["parameters"]
    feed_stocks = {
        _entity(entity, "ec_rejection.feed.stocks"): amount
        for entity, amount in feed_data["stocks"].items()
    }
    feed = TreatmentStream(
        stream_id=feed_data["stream_id"],
        volume_l=feed_data["volume_l"],
        water_mass_kg=feed_data["water_mass_kg"],
        stocks=feed_stocks,
        evidence_label=EvidenceLabel(feed_data["evidence_label"]),
    )
    try:
        ROParameters(
            model_id=parameters_data["model_id"],
            version=parameters_data["version"],
            recovery=parameters_data["recovery"],
            rejection=parameters_data["rejection"],
            evidence_label=EvidenceLabel(parameters_data["evidence_label"]),
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
                "feed": dict(feed_data),
                "parameters": dict(parameters_data),
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
                "feed": feed_data,
                "parameters": parameters_data,
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
    domain = HydraulicDomain(**fixture["hydraulic_domain"])  # type: ignore[arg-type]
    common = {
        key: value
        for key, value in fixture.items()
        if key
        not in {
            "fresh_osmolality_osmol_kg",
            "saline_osmolality_osmol_kg",
            "hydraulic_domain",
        }
    }
    fresh = hydraulic_uptake(
        HydraulicInputs(
            osmolality_osmol_kg=float(fixture["fresh_osmolality_osmol_kg"]),
            **common,
        ),
        domain=domain,
    )
    saline = hydraulic_uptake(
        HydraulicInputs(
            osmolality_osmol_kg=float(fixture["saline_osmolality_osmol_kg"]),
            **common,
        ),
        domain=domain,
    )
    domain_policy = {
        "model_id": domain.model_id,
        "version": domain.version,
        "purpose": domain.purpose,
        "scope": "numerical_oracle_not_almond_applicability",
        "sha256": domain.sha256,
    }
    observed = {
        "fresh_l_day": fresh.actual_l_day,
        "saline_l_day": saline.actual_l_day,
        "ratio": saline.actual_l_day / fresh.actual_l_day,
        "domain_policy": domain_policy,
    }
    oracle = {
        "fresh_l_day": 0.888212,
        "saline_l_day": 0.455696,
        "ratio": 0.513049,
        "domain_policy": domain_policy,
    }
    tolerances = {
        "fresh_l_day": tolerance,
        "saline_l_day": tolerance,
        "ratio": tolerance,
        "domain_policy": _tree_constant(domain_policy, 0.0),
    }
    comparison = {
        "fresh_l_day": "abs_le",
        "saline_l_day": "abs_le",
        "ratio": "abs_le",
        "domain_policy": _tree_constant(domain_policy, "eq"),
    }
    return _record(
        13,
        digest,
        observed,
        oracle,
        tolerances,
        comparison=comparison,
        fixture_sha256s={
            "perfect_na_exclusion.yaml": digest,
            "perfect_na_exclusion.hydraulic_domain": domain.sha256,
        },
    )


@dataclass
class AnalysisBoundary:
    accepted_records: int = 0

    def submit(self, source: WaterBatch, measurement: BlendMeasurement) -> None:
        blend_by_volume([source], [1.0], measurement=measurement)
        self.accepted_records += 1


EC_DIRECTIONAL_MISMATCH_ORACLE = (
    ("ECw", "pore_water_EC"),
    ("ECw", "ECe"),
    ("pore_water_EC", "ECw"),
    ("pore_water_EC", "ECe"),
    ("ECe", "ECw"),
    ("ECe", "pore_water_EC"),
)


def _acceptance_19(
    *, cases: Sequence[tuple[str, str]] = EC_DIRECTIONAL_MISMATCH_ORACLE
) -> VerificationRecord:
    fixture, digest = _fixture("chemistry_handcheck.yaml")
    policy_tolerance = load_verification_policy().tolerances[19]["absolute"]
    source_payload = fixture["blend"]["source_a"]  # type: ignore[index]
    boundary = AnalysisBoundary()
    observed_cases: list[dict[str, object]] = []
    for source_kind_id, measurement_kind_id in cases:
            source_kind = ECKind(source_kind_id)
            measurement_kind = ECKind(measurement_kind_id)
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
            observed_cases.append(
                {
                    "source_ec_kind": source_kind.value,
                    "measurement_ec_kind": measurement_kind.value,
                    "code": code,
                }
            )
    observed = {
        "cases": observed_cases,
        "records_reached_analysis": boundary.accepted_records,
    }
    oracle = {
        "cases": [
            {
                "source_ec_kind": source_kind,
                "measurement_ec_kind": measurement_kind,
                "code": "EC_TYPE_MISMATCH",
            }
            for source_kind, measurement_kind in EC_DIRECTIONAL_MISMATCH_ORACLE
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


# Canonical schema for the final property/conservation acceptance.  These
# registries are deliberately independent of both the manifest and observations.
_T20_FLOW_QUANTITIES = ("water", "na", "cl")
_T20_RO_QUANTITIES = ("water", "na", "cl")
_T20_BLEND_FIELDS = (
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
_T20_COUNTEREXAMPLE_SEMANTICS = MappingProxyType(
    {
        "population": "frozen_manifest_cases",
        "selection": "first_in_manifest_order",
        "hypothesis_shrunk": False,
    }
)


def _case_input(value: object) -> object:
    return _json_value(value, "case")


def _flow_case_default(case: Mapping[str, object]) -> dict[str, object]:
    density = case["density_kg_l"]
    source = case["source"]
    target = case["target"]
    assert isinstance(source, Mapping) and isinstance(target, Mapping)
    tracked = frozenset({ConservedEntity.NA, ConservedEntity.CL})
    state = NetworkState(
        compartments={
            "source": CompartmentState(
                compartment_id="source",
                kind=CompartmentKind.IRRIGATION_TANK,
                loop_id="property",
                volume_l=source["volume_l"],  # type: ignore[arg-type]
                water_mass_kg=source["water_mass_kg"],  # type: ignore[arg-type]
                empty_reference_density_kg_l=density,  # type: ignore[arg-type]
                stocks={
                    ConservedEntity.NA: source["stocks"]["na"],  # type: ignore[index]
                    ConservedEntity.CL: source["stocks"]["cl"],  # type: ignore[index]
                },
                evidence_label=EvidenceLabel.PHYSICS_CONSTRAINED,
            ),
            "target": CompartmentState(
                compartment_id="target",
                kind=CompartmentKind.ROOT_ZONE,
                loop_id="property",
                volume_l=target["volume_l"],  # type: ignore[arg-type]
                water_mass_kg=target["water_mass_kg"],  # type: ignore[arg-type]
                empty_reference_density_kg_l=density,  # type: ignore[arg-type]
                stocks={
                    ConservedEntity.NA: target["stocks"]["na"],  # type: ignore[index]
                    ConservedEntity.CL: target["stocks"]["cl"],  # type: ignore[index]
                },
                evidence_label=EvidenceLabel.PHYSICS_CONSTRAINED,
            ),
        },
        tracked_entities=tracked,
        evidence_label=EvidenceLabel.PHYSICS_CONSTRAINED,
    )
    event = InternalWaterFlow(
        event_id="property-flow",
        source="source",
        target="target",
        rate_l_per_hour=case["rate_l_per_hour"],  # type: ignore[arg-type]
        flow_kind=InternalWaterFlowKind.AQUEOUS_TRANSFER,
        phase=OperatorPhase.IRRIGATION,
        evidence_label=EvidenceLabel.PHYSICS_CONSTRAINED,
    )
    result = step_state(
        state,
        dt_hours=case["duration_hours"],  # type: ignore[arg-type]
        cursor=LedgerCursor("PROPERTY", str(case["id"])),
        water_flows=(event,),
    )
    audit = audit_ledger(
        state, result.state, result.ledger, expected_events=(event,)
    )
    quantities = {
        "water": ConservedEntity.WATER,
        "na": ConservedEntity.NA,
        "cl": ConservedEntity.CL,
    }
    return {
        "post": {
            name: {
                "volume_l": result.state.compartments[name].volume_l,
                "water_mass_kg": result.state.compartments[name].water_mass_kg,
                "stocks": {
                    entity: result.state.compartments[name].stocks[typed]
                    for entity, typed in quantities.items()
                    if entity != "water"
                },
            }
            for name in ("source", "target")
        },
        "global_relative_residual": {
            name: audit.relative_residuals[entity]
            for name, entity in quantities.items()
        },
        "compartment_relative_residual": {
            name: max(
                audit.relative_compartment_residuals[compartment][entity]
                for compartment in ("source", "target")
            )
            for name, entity in quantities.items()
        },
        "balanced": audit.balanced,
    }


def _ro_case_default(case: Mapping[str, object]) -> dict[str, object]:
    feed_data = case["feed"]
    parameters_data = case["parameters"]
    assert isinstance(feed_data, Mapping) and isinstance(parameters_data, Mapping)
    feed = TreatmentStream(
        stream_id="property-feed",
        volume_l=feed_data["volume_l"],  # type: ignore[arg-type]
        water_mass_kg=feed_data["water_mass_kg"],  # type: ignore[arg-type]
        stocks={
            ConservedEntity.NA: feed_data["stocks"]["na"],  # type: ignore[index]
            ConservedEntity.CL: feed_data["stocks"]["cl"],  # type: ignore[index]
        },
        evidence_label=EvidenceLabel.PHYSICS_CONSTRAINED,
    )
    parameters = ROParameters(
        model_id="property-ro",
        version="1.0.0",
        recovery=parameters_data["recovery"],  # type: ignore[arg-type]
        rejection={
            ConservedEntity.NA: parameters_data["rejection"]["na"],  # type: ignore[index]
            ConservedEntity.CL: parameters_data["rejection"]["cl"],  # type: ignore[index]
        },
        evidence_label=EvidenceLabel.PHYSICS_CONSTRAINED,
    )
    result = ro_split(
        feed,
        parameters,
        permeate_stream_id="property-permeate",
        concentrate_stream_id="property-concentrate",
        cursor=LedgerCursor("PROPERTY", str(case["id"])),
    )
    return {
        "feed": {
            "volume_l": result.feed.volume_l,
            "water_mass_kg": result.feed.water_mass_kg,
            "stocks": {entity.value: amount for entity, amount in result.feed.stocks.items()},
        },
        "permeate": {
            "volume_l": result.permeate.volume_l,
            "water_mass_kg": result.permeate.water_mass_kg,
            "stocks": {
                entity.value: amount for entity, amount in result.permeate.stocks.items()
            },
        },
        "concentrate": {
            "volume_l": result.concentrate.volume_l,
            "water_mass_kg": result.concentrate.water_mass_kg,
            "stocks": {
                entity.value: amount
                for entity, amount in result.concentrate.stocks.items()
            },
        },
    }


def _blend_case_default(
    case: Mapping[str, object], chemistry_fixture: Mapping[str, object]
) -> dict[str, float]:
    sources, measurement, _ = _chemistry_sources(
        chemistry_fixture, case["volumes_l"]  # type: ignore[arg-type]
    )
    result = blend_by_volume(
        sources, case["volumes_l"], measurement=measurement  # type: ignore[arg-type]
    )
    return {
        field: getattr(result.chemistry, field) for field in _T20_BLEND_FIELDS
    }


def _t20_extrema_oracle() -> dict[str, object]:
    return {
        "flow": {
            "global_relative_residual": {
                name: 0.0 for name in _T20_FLOW_QUANTITIES
            },
            "compartment_relative_residual": {
                name: 0.0 for name in _T20_FLOW_QUANTITIES
            },
            "literal_absolute_error": {
                name: 0.0 for name in _T20_FLOW_QUANTITIES
            },
        },
        "ro": {
            "conservation_absolute_residual": {
                name: 0.0 for name in _T20_RO_QUANTITIES
            },
            "literal_absolute_error": {
                name: 0.0 for name in _T20_RO_QUANTITIES
            },
        },
        "blend": {
            "literal_absolute_error": {
                name: 0.0 for name in _T20_BLEND_FIELDS
            }
        },
    }


def _generator_oracle() -> dict[str, object]:
    return {
        "name": "hypothesis",
        "version": "6.165.5",
        "phase": "generate_only",
        "strategy": "sampled_from_frozen_candidate_set",
        "candidate_set_sha256": CONSERVATION_CANDIDATE_SET_SHA256,
        "shrinking": False,
        "properties": {
            "blend": {"seed": 20260814, "max_examples": 2},
            "flow": {"seed": 20260812, "max_examples": 2},
            "ro": {"seed": 20260813, "max_examples": 2},
        },
    }


def _run_case_manifest(
    manifest: Mapping[str, object],
    chemistry_fixture: Mapping[str, object],
    absolute_tolerance: float,
    *,
    flow_case_model: Callable[[Mapping[str, object]], object] | None = None,
    ro_case_model: Callable[[Mapping[str, object]], object] | None = None,
    blend_case_model: Callable[[Mapping[str, object], Mapping[str, object]], object]
    | None = None,
) -> dict[str, object]:
    """Execute frozen cases and report the first failure in manifest order."""

    flow_model = flow_case_model or _flow_case_default
    ro_model = ro_case_model or _ro_case_default
    blend_model = blend_case_model or _blend_case_default
    cases = manifest["cases"]
    assert isinstance(cases, Mapping)
    extrema = _t20_extrema_oracle()
    counterexample: dict[str, object] | None = None

    def maximum(branch: dict[str, float], name: str, value: float) -> None:
        branch[name] = max(branch[name], abs(value))

    def fail_case(
        property_id: str,
        case: Mapping[str, object],
        failing_metrics: Mapping[str, object],
    ) -> None:
        nonlocal counterexample
        if counterexample is None:
            counterexample = {
                "property_id": property_id,
                "case_id": case["id"],
                "input": _case_input(case),
                "failing_metrics": _case_input(failing_metrics),
            }

    for property_id in ("flow", "ro", "blend"):
        property_cases = cases[property_id]
        assert isinstance(property_cases, tuple)
        for case in property_cases:
            assert isinstance(case, Mapping)
            try:
                if property_id == "flow":
                    output = flow_model(case)
                    if not isinstance(output, Mapping):
                        raise ValueError("flow model output must be a mapping")
                    expected = case["expected"]
                    assert isinstance(expected, Mapping)
                    residuals = output["global_relative_residual"]
                    compartment = output["compartment_relative_residual"]
                    post = output["post"]
                    if not all(isinstance(value, Mapping) for value in (residuals, compartment, post)):
                        raise ValueError("flow model output shape is invalid")
                    literal = {name: 0.0 for name in _T20_FLOW_QUANTITIES}
                    for location in ("source", "target"):
                        literal["water"] = max(
                            literal["water"],
                            abs(
                                post[location]["water_mass_kg"]
                                - expected[location]["water_mass_kg"]
                            ),
                        )
                        for name in ("na", "cl"):
                            literal[name] = max(
                                literal[name],
                                abs(
                                    post[location]["stocks"][name]
                                    - expected[location]["stocks"][name]
                                ),
                            )
                    for name in _T20_FLOW_QUANTITIES:
                        maximum(
                            extrema["flow"]["global_relative_residual"],  # type: ignore[index]
                            name,
                            residuals[name],
                        )
                        maximum(
                            extrema["flow"]["compartment_relative_residual"],  # type: ignore[index]
                            name,
                            compartment[name],
                        )
                        maximum(
                            extrema["flow"]["literal_absolute_error"],  # type: ignore[index]
                            name,
                            literal[name],
                        )
                    failing = {
                        "balanced": output.get("balanced") is not True,
                        "maximum_error": max(
                            *(abs(residuals[name]) for name in _T20_FLOW_QUANTITIES),
                            *(abs(compartment[name]) for name in _T20_FLOW_QUANTITIES),
                            *literal.values(),
                        ),
                    }
                elif property_id == "ro":
                    output = ro_model(case)
                    if not isinstance(output, Mapping):
                        raise ValueError("RO model output must be a mapping")
                    feed = output["feed"]
                    permeate = output["permeate"]
                    concentrate = output["concentrate"]
                    expected = case["expected"]
                    assert all(
                        isinstance(value, Mapping)
                        for value in (feed, permeate, concentrate, expected)
                    )
                    conservation = {
                        "water": abs(
                            permeate["water_mass_kg"]
                            + concentrate["water_mass_kg"]
                            - feed["water_mass_kg"]
                        ),
                        **{
                            name: abs(
                                permeate["stocks"][name]
                                + concentrate["stocks"][name]
                                - feed["stocks"][name]
                            )
                            for name in ("na", "cl")
                        },
                    }
                    literal = {
                        "water": max(
                            abs(
                                permeate["water_mass_kg"]
                                - expected["permeate"]["water_mass_kg"]
                            ),
                            abs(
                                concentrate["water_mass_kg"]
                                - expected["concentrate"]["water_mass_kg"]
                            ),
                        ),
                        **{
                            name: max(
                                abs(
                                    permeate["stocks"][name]
                                    - expected["permeate"]["stocks"][name]
                                ),
                                abs(
                                    concentrate["stocks"][name]
                                    - expected["concentrate"]["stocks"][name]
                                ),
                            )
                            for name in ("na", "cl")
                        },
                    }
                    for name in _T20_RO_QUANTITIES:
                        maximum(
                            extrema["ro"]["conservation_absolute_residual"],  # type: ignore[index]
                            name,
                            conservation[name],
                        )
                        maximum(
                            extrema["ro"]["literal_absolute_error"],  # type: ignore[index]
                            name,
                            literal[name],
                        )
                    failing = {"maximum_error": max(*conservation.values(), *literal.values())}
                else:
                    output = blend_model(case, chemistry_fixture)
                    if not isinstance(output, Mapping):
                        raise ValueError("blend model output must be a mapping")
                    expected = case["expected"]
                    assert isinstance(expected, Mapping)
                    literal = {
                        name: abs(output[name] - expected[name])
                        for name in _T20_BLEND_FIELDS
                    }
                    for name, value in literal.items():
                        maximum(
                            extrema["blend"]["literal_absolute_error"],  # type: ignore[index]
                            name,
                            value,
                        )
                    failing = {"maximum_error": max(literal.values())}
                if failing["maximum_error"] > absolute_tolerance or failing.get("balanced"):
                    fail_case(property_id, case, failing)
            except (AlmondLabError, KeyError, TypeError, ValueError, ArithmeticError) as error:
                # Keep the extrema schema exact on malformed injected output.
                branch = extrema[property_id]
                assert isinstance(branch, dict)
                for values in branch.values():
                    assert isinstance(values, dict)
                    for name in values:
                        values[name] = max(values[name], 1.0)
                fail_case(
                    property_id,
                    case,
                    {"error_type": type(error).__name__, "message": str(error)},
                )
    return {
        "counts": {"flow": 2, "ro": 2, "blend": 2},
        "per_quantity_extrema": extrema,
        "counterexample_semantics": dict(_T20_COUNTEREXAMPLE_SEMANTICS),
        "counterexample": counterexample,
        "generator": _generator_oracle(),
    }


def _stream_payload(stream: TreatmentStream) -> dict[str, object]:
    return {
        "stream_id": stream.stream_id,
        "volume_l": stream.volume_l,
        "water_mass_kg": stream.water_mass_kg,
        "density_kg_l": stream.density_kg_l,
        "stocks": {entity.value: amount for entity, amount in stream.stocks.items()},
        "evidence_label": stream.evidence_label.value,
    }


def _ro_anchor_oracle(ro_data: Mapping[str, object]) -> dict[str, object]:
    feed_data = ro_data["feed"]
    parameters = ro_data["parameters"]
    expected = ro_data["expected"]
    cursor = ro_data["cursor"]
    assert all(
        isinstance(value, Mapping)
        for value in (feed_data, parameters, expected, cursor)
    )
    feed_stocks = feed_data["stocks"]
    rejection = parameters["rejection"]
    assert isinstance(feed_stocks, Mapping) and isinstance(rejection, Mapping)
    rows: list[dict[str, object]] = []
    for ordinal, (branch, event_id) in enumerate(
        (("permeate", "ro-permeate"), ("concentrate", "ro-concentrate"))
    ):
        branch_data = expected[branch]
        assert isinstance(branch_data, Mapping)
        transaction_id = (
            f"tx:{cursor['run_id']}:{cursor['chain_id']}:"
            f"{int(cursor['start_ordinal']) + ordinal:012d}"
        )
        destination = ro_data[f"{branch}_stream_id"]
        for entity in (ConservedEntity.WATER, ConservedEntity.NA, ConservedEntity.CL):
            amount = (
                branch_data["water_mass_kg"]
                if entity is ConservedEntity.WATER
                else branch_data["stocks"][entity.value]
            )
            common = {
                "transaction_id": transaction_id,
                "event_id": event_id,
                "kind": "internal",
                "phase": "treatment_blending",
                "transfer_mode": "advective_aqueous",
                "quantity": entity.value,
                "unit": entity_spec(entity).stock_unit.value,
                "evidence_label": "physics_constrained",
                "boundary_category": None,
                "internal_flux_kind": None,
                "internal_water_flow_kind": (
                    "aqueous_transfer" if entity is ConservedEntity.WATER else None
                ),
                "physical_transfer_id": event_id,
                "carrier_volume_l": (
                    branch_data["volume_l"]
                    if entity is ConservedEntity.WATER
                    else None
                ),
                "water_density_kg_l": (
                    branch_data["water_mass_kg"] / branch_data["volume_l"]
                    if entity is ConservedEntity.WATER
                    else None
                ),
                "requested_amount": None,
                "applied_amount": None,
                "cap_fraction": None,
                "adapter_id": None,
                "adapter_version": None,
                "adapter_hash": None,
                "treatment_model_id": parameters["model_id"],
                "treatment_model_version": parameters["version"],
            }
            rows.extend(
                (
                    {
                        **common,
                        "compartment": feed_data["stream_id"],
                        "counterparty": destination,
                        "amount": -float(amount),
                    },
                    {
                        **common,
                        "compartment": destination,
                        "counterparty": feed_data["stream_id"],
                        "amount": float(amount),
                    },
                )
            )
    feed_density = feed_data["water_mass_kg"] / feed_data["volume_l"]
    return {
        "feed": {
            **dict(feed_data),
            "density_kg_l": feed_density,
        },
        "permeate": {
            "stream_id": ro_data["permeate_stream_id"],
            **dict(expected["permeate"]),
            "density_kg_l": expected["permeate"]["water_mass_kg"]
            / expected["permeate"]["volume_l"],
            "evidence_label": "physics_constrained",
        },
        "concentrate": {
            "stream_id": ro_data["concentrate_stream_id"],
            **dict(expected["concentrate"]),
            "density_kg_l": expected["concentrate"]["water_mass_kg"]
            / expected["concentrate"]["volume_l"],
            "evidence_label": "physics_constrained",
        },
        "parameters": {
            **dict(parameters),
            "evidence_label": parameters["evidence_label"],
        },
        "removal": {
            "selectively_rejected": dict(expected["selectively_rejected"]),
            "destination_stream_id": ro_data["concentrate_stream_id"],
            "destination_stock": dict(expected["concentrate"]["stocks"]),
        },
        "ledger": rows,
        "next_cursor": {
            "run_id": cursor["run_id"],
            "chain_id": cursor["chain_id"],
            "next_ordinal": expected["next_ordinal"],
        },
        "evidence_label": "physics_constrained",
    }


def _acceptance_20_bundle(
    *,
    stepper: Callable[..., StepResult] = step_state,
    ro_model: Callable[..., ROResult] = ro_split,
    ledger_transform: Callable[[tuple[LedgerEntry, ...]], tuple[LedgerEntry, ...]]
    | None = None,
    flow_case_model: Callable[[Mapping[str, object]], object] | None = None,
    ro_case_model: Callable[[Mapping[str, object]], object] | None = None,
    blend_case_model: Callable[[Mapping[str, object], Mapping[str, object]], object]
    | None = None,
) -> tuple[VerificationRecord, object]:
    fixture, digest = _fixture("all_conserved_entities.yaml")
    chemistry_fixture, chemistry_digest = _fixture("chemistry_handcheck.yaml")
    manifest, manifest_digest = load_conservation_case_manifest()
    _, candidate_digest = load_fixture_bytes(
        "conservation_case_manifest.candidates.json"
    )
    threshold_policy = load_threshold_policy()
    policy = load_verification_policy()
    absolute = policy.tolerances[20]["absolute"]

    before = _state(fixture)
    event = _water_flow(fixture)
    _validate_flow_authority_fixture(fixture, event)
    expected_transactions = _ledger_transaction_expectations(
        fixture["expected_ledger"]  # type: ignore[arg-type]
    )
    result = stepper(
        before,
        dt_hours=fixture["duration_hours"],
        cursor=_cursor(fixture),
        water_flows=(event,),
    )
    ledger, transform_error = _apply_ledger_transform(
        result.ledger, ledger_transform
    )
    try:
        audit = audit_ledger(
            before,
            result.state,
            ledger,
            expected_events=(event,),
            expected_transactions=expected_transactions,
        )
        audit_payload = _ledger_audit(
            audit,
            ledger,
            expected_events=(event,),
            transform_error=transform_error,
        )
    except AlmondLabError as error:
        audit = audit_ledger(
            before,
            result.state,
            (),
            expected_events=(event,),
            expected_transactions=expected_transactions,
        )
        audit_payload = _ledger_audit(
            audit,
            (),
            expected_events=(event,),
            transform_error=f"{error.code}:{error.field_path}",
        )
    required = tuple(
        sorted(
            {ConservedEntity.WATER, *before.tracked_entities},
            key=lambda entity: entity.value,
        )
    )
    transfer_oracle = _ledger_oracle(
        fixture["expected_ledger"],
        required_quantities=required,
        expected_compartments=tuple(before.compartments),
    )
    transfer_observed = {
        "post_state": _state_payload(result.state),
        "ledger": _ledger_rows(ledger),
        "audit": audit_payload,
        "next_cursor": {
            "run_id": result.next_cursor.run_id,
            "chain_id": result.next_cursor.chain_id,
            "next_ordinal": result.next_cursor.next_ordinal,
        },
    }
    transfer_expected = {
        "post_state": _state_oracle(fixture),
        **transfer_oracle,
    }

    ro_data = fixture["ro"]
    assert isinstance(ro_data, Mapping)
    feed_data = ro_data["feed"]
    params_data = ro_data["parameters"]
    cursor_data = ro_data["cursor"]
    assert all(isinstance(value, Mapping) for value in (feed_data, params_data, cursor_data))
    feed = TreatmentStream(
        stream_id=feed_data["stream_id"],
        volume_l=feed_data["volume_l"],
        water_mass_kg=feed_data["water_mass_kg"],
        stocks={
            _entity(name, "ro.feed.stocks"): amount
            for name, amount in feed_data["stocks"].items()
        },
        evidence_label=EvidenceLabel(feed_data["evidence_label"]),
    )
    parameters = ROParameters(
        model_id=params_data["model_id"],
        version=params_data["version"],
        recovery=params_data["recovery"],
        rejection={
            _entity(name, "ro.parameters.rejection"): value
            for name, value in params_data["rejection"].items()
        },
        evidence_label=EvidenceLabel(params_data["evidence_label"]),
    )
    ro = ro_model(
        feed,
        parameters,
        permeate_stream_id=ro_data["permeate_stream_id"],
        concentrate_stream_id=ro_data["concentrate_stream_id"],
        cursor=LedgerCursor(
            cursor_data["run_id"],
            cursor_data["chain_id"],
            cursor_data["start_ordinal"],
        ),
    )
    ro_observed = {
        "feed": _stream_payload(ro.feed),
        "permeate": _stream_payload(ro.permeate),
        "concentrate": _stream_payload(ro.concentrate),
        "parameters": {
            "model_id": ro.parameters.model_id,
            "version": ro.parameters.version,
            "recovery": ro.parameters.recovery,
            "rejection": {
                entity.value: value for entity, value in ro.parameters.rejection.items()
            },
            "evidence_label": ro.parameters.evidence_label.value,
        },
        "removal": {
            "selectively_rejected": {
                entity.value: value
                for entity, value in ro.removal.selectively_rejected_stock.items()
            },
            "destination_stream_id": ro.removal.destination_stream_id,
            "destination_stock": {
                entity.value: value
                for entity, value in ro.removal.destination_stock.items()
            },
        },
        "ledger": _ledger_rows(ro.ledger),
        "next_cursor": {
            "run_id": ro.next_cursor.run_id,
            "chain_id": ro.next_cursor.chain_id,
            "next_ordinal": ro.next_cursor.next_ordinal,
        },
        "evidence_label": ro.evidence_label.value,
    }
    ro_oracle = _ro_anchor_oracle(ro_data)

    sources, measurement, volumes = _chemistry_sources(chemistry_fixture)
    blend = blend_by_volume(sources, volumes, measurement=measurement)
    blend_expected = chemistry_fixture["blend"]
    blend_observed = {
        "total_volume_l": blend.total_volume_l,
        "concentrations": {
            field: getattr(blend.chemistry, field) for field in _T20_BLEND_FIELDS
        },
        "provenance": _blend_provenance(blend, measurement),
    }
    blend_oracle = {
        "total_volume_l": blend_expected["expected_total_volume_l"],
        "concentrations": {
            field: blend_expected["expected"][field] for field in _T20_BLEND_FIELDS
        },
        "provenance": blend_expected["expected_provenance"],
    }

    cases = _run_case_manifest(
        manifest,
        chemistry_fixture,
        absolute,
        flow_case_model=flow_case_model,
        ro_case_model=ro_case_model,
        blend_case_model=blend_case_model,
    )
    cases_oracle = {
        "counts": {"flow": 2, "ro": 2, "blend": 2},
        "per_quantity_extrema": _t20_extrema_oracle(),
        "counterexample_semantics": dict(_T20_COUNTEREXAMPLE_SEMANTICS),
        "counterexample": None,
        "generator": _generator_oracle(),
    }
    stop = evaluate_run_stops(
        numerical_values={
            f"state_{index}": value
            for index, value in enumerate(result.state.all_values())
        },
        stocks={
            entity.value: result.state.total_stock(entity)
            for entity in before.tracked_entities
        },
        ledger_relative_residuals={
            entity.value: value for entity, value in audit.relative_residuals.items()
        },
        physical_values={},
        threshold_policy=threshold_policy,
        applicable_stop_ids=(),
    )
    observed = {
        "minimum_state": min(result.state.all_values()),
        "run_stop_valid": stop.valid and not stop.censored,
        "registered_entities": [entity.value for entity in ConservedEntity],
        "transfer": transfer_observed,
        "ro": ro_observed,
        "blend": blend_observed,
        "case_manifest": cases,
    }
    oracle = {
        "minimum_state": threshold_policy.numerical_stops.minimum_stock,
        "run_stop_valid": True,
        "registered_entities": [entity.value for entity in ConservedEntity],
        "transfer": transfer_expected,
        "ro": ro_oracle,
        "blend": blend_oracle,
        "case_manifest": cases_oracle,
    }
    comparison = _comparison_tree(oracle)
    tolerance = _tolerance_tree(oracle, absolute)
    assert isinstance(comparison, dict) and isinstance(tolerance, dict)
    comparison["minimum_state"] = "ge"
    tolerance["minimum_state"] = 0.0
    record = _record(
        20,
        digest,
        observed,
        oracle,
        tolerance,
        comparison=comparison,
        fixture_sha256s={
            "all_conserved_entities.yaml": digest,
            "chemistry_handcheck.yaml": chemistry_digest,
            "conservation_case_manifest.yaml": manifest_digest,
            "conservation_case_manifest.candidates.json": candidate_digest,
            "configs/thresholds.yaml": threshold_policy.sha256,
        },
    )
    return record, {
        "transfer_ledger": transfer_observed["ledger"],
        "ro_ledger": ro_observed["ledger"],
    }


def _acceptance_20(
    *,
    stepper: Callable[..., StepResult] = step_state,
    ro_model: Callable[..., ROResult] = ro_split,
    ledger_transform: Callable[[tuple[LedgerEntry, ...]], tuple[LedgerEntry, ...]]
    | None = None,
    flow_case_model: Callable[[Mapping[str, object]], object] | None = None,
    ro_case_model: Callable[[Mapping[str, object]], object] | None = None,
    blend_case_model: Callable[[Mapping[str, object], Mapping[str, object]], object]
    | None = None,
) -> VerificationRecord:
    return _acceptance_20_bundle(
        stepper=stepper,
        ro_model=ro_model,
        ledger_transform=ledger_transform,
        flow_case_model=flow_case_model,
        ro_case_model=ro_case_model,
        blend_case_model=blend_case_model,
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
