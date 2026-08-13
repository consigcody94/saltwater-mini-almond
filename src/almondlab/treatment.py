"""Ion-specific, density-aware treatment and remineralization accounting."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from math import fsum
import re
from types import MappingProxyType
from typing import Final

from almondlab.contracts import (
    ConservedEntity,
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
from almondlab.errors import fail, finite_float
from almondlab.evidence_policy import compose_evidence_labels


_READABLE_ID: Final[re.Pattern[str]] = re.compile(
    r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}\Z", re.ASCII
)
_EC_REJECTION_KEYS: Final[frozenset[str]] = frozenset(
    {
        "ec",
        "ecw",
        "ec_ds_m",
        "pore_water_ec",
        "ece",
        *(kind.value.casefold() for kind in ECKind),
    }
)


def _readable_id(value: object, *, code: str, field_path: str) -> str:
    if not isinstance(value, str) or _READABLE_ID.fullmatch(value) is None:
        fail(code, "identifier must use 1-64 readable ASCII characters", field_path)
    return value


def _evidence_label(value: object, field_path: str) -> EvidenceLabel:
    if not isinstance(value, EvidenceLabel):
        fail(
            "TREATMENT_EVIDENCE_LABEL_INVALID",
            "evidence label must be an EvidenceLabel",
            field_path,
        )
    return value


def _stock_mapping(
    values: object,
    *,
    field_path: str,
    water_error_code: str = "TREATMENT_WATER_STOCK_FORBIDDEN",
) -> Mapping[ConservedEntity, float]:
    if not isinstance(values, Mapping):
        fail(
            "TREATMENT_STOCKS_INVALID",
            "stocks must be a mapping from ConservedEntity to amount",
            field_path,
        )
    converted: dict[ConservedEntity, float] = {}
    for entity, amount in values.items():
        if not isinstance(entity, ConservedEntity):
            fail(
                "TREATMENT_ENTITY_TYPE_REQUIRED",
                "stock keys must be ConservedEntity values",
                field_path,
            )
        if entity is ConservedEntity.WATER:
            fail(
                water_error_code,
                "water is represented by water_mass_kg, not the stock mapping",
                f"{field_path}.water",
            )
        converted[entity] = finite_float(
            amount,
            code="TREATMENT_NUMERIC_INVALID",
            field_path=f"{field_path}.{entity.value}",
            nonnegative=True,
        )
    ordered = {
        entity: converted[entity]
        for entity in ConservedEntity
        if entity in converted and entity is not ConservedEntity.WATER
    }
    return MappingProxyType(ordered)


def _rejection_mapping(values: object) -> Mapping[ConservedEntity, float]:
    if not isinstance(values, Mapping):
        fail(
            "RO_REJECTION_INVALID",
            "rejection must be a mapping from ConservedEntity to fraction",
            "rejection",
        )
    for key in values:
        if isinstance(key, str) and key.casefold() in _EC_REJECTION_KEYS:
            fail(
                "RO_EC_REJECTION_FORBIDDEN",
                "EC cannot substitute for ion-specific rejection",
                "rejection",
            )
    converted: dict[ConservedEntity, float] = {}
    for entity, value in values.items():
        if not isinstance(entity, ConservedEntity):
            fail(
                "TREATMENT_ENTITY_TYPE_REQUIRED",
                "rejection keys must be ConservedEntity values",
                "rejection",
            )
        if entity is ConservedEntity.WATER:
            fail(
                "RO_WATER_REJECTION_FORBIDDEN",
                "water recovery is explicit and cannot be a rejection entry",
                "rejection.water",
            )
        converted_value = finite_float(
            value,
            code="TREATMENT_NUMERIC_INVALID",
            field_path=f"rejection.{entity.value}",
        )
        if not 0.0 <= converted_value <= 1.0:
            fail(
                "RO_REJECTION_OUT_OF_RANGE",
                "entity rejection must be between zero and one inclusive",
                f"rejection.{entity.value}",
            )
        converted[entity] = converted_value
    ordered = {
        entity: converted[entity]
        for entity in ConservedEntity
        if entity in converted and entity is not ConservedEntity.WATER
    }
    return MappingProxyType(ordered)


@dataclass(frozen=True, slots=True)
class TreatmentStream:
    """A positive water carrier and explicitly typed dissolved stocks."""

    stream_id: str
    volume_l: float
    water_mass_kg: float
    stocks: Mapping[ConservedEntity, float]
    evidence_label: EvidenceLabel

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "stream_id",
            _readable_id(
                self.stream_id,
                code="TREATMENT_STREAM_ID_INVALID",
                field_path="stream_id",
            ),
        )
        object.__setattr__(
            self,
            "volume_l",
            finite_float(
                self.volume_l,
                code="TREATMENT_NUMERIC_INVALID",
                field_path="volume_l",
                positive=True,
            ),
        )
        object.__setattr__(
            self,
            "water_mass_kg",
            finite_float(
                self.water_mass_kg,
                code="TREATMENT_NUMERIC_INVALID",
                field_path="water_mass_kg",
                positive=True,
            ),
        )
        finite_float(
            self.water_mass_kg / self.volume_l,
            code="TREATMENT_NUMERIC_INVALID",
            field_path="density_kg_l",
            positive=True,
        )
        object.__setattr__(
            self,
            "stocks",
            _stock_mapping(self.stocks, field_path="stocks"),
        )
        object.__setattr__(
            self,
            "evidence_label",
            _evidence_label(self.evidence_label, "evidence_label"),
        )

    @property
    def density_kg_l(self) -> float:
        return self.water_mass_kg / self.volume_l


@dataclass(frozen=True, slots=True)
class ROParameters:
    """Versioned recovery and per-entity rejection assumptions."""

    model_id: str
    version: str
    recovery: float
    rejection: Mapping[ConservedEntity, float]
    evidence_label: EvidenceLabel

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "model_id",
            _readable_id(
                self.model_id,
                code="RO_PARAMETER_ID_INVALID",
                field_path="model_id",
            ),
        )
        object.__setattr__(
            self,
            "version",
            _readable_id(
                self.version,
                code="RO_PARAMETER_ID_INVALID",
                field_path="version",
            ),
        )
        recovery = finite_float(
            self.recovery,
            code="TREATMENT_NUMERIC_INVALID",
            field_path="recovery",
        )
        if not 0.0 < recovery < 1.0:
            fail(
                "RO_RECOVERY_OUT_OF_RANGE",
                "recovery must be strictly between zero and one",
                "recovery",
            )
        object.__setattr__(self, "recovery", recovery)
        object.__setattr__(self, "rejection", _rejection_mapping(self.rejection))
        object.__setattr__(
            self,
            "evidence_label",
            _evidence_label(self.evidence_label, "evidence_label"),
        )


@dataclass(frozen=True, slots=True)
class RORemovalResult:
    """Selective-rejection diagnostic and its physical concentrate destination."""

    selectively_rejected_stock: Mapping[ConservedEntity, float]
    destination_stream_id: str
    destination_stock: Mapping[ConservedEntity, float]

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "selectively_rejected_stock",
            _stock_mapping(
                self.selectively_rejected_stock,
                field_path="selectively_rejected_stock",
            ),
        )
        object.__setattr__(
            self,
            "destination_stream_id",
            _readable_id(
                self.destination_stream_id,
                code="TREATMENT_STREAM_ID_INVALID",
                field_path="destination_stream_id",
            ),
        )
        object.__setattr__(
            self,
            "destination_stock",
            _stock_mapping(self.destination_stock, field_path="destination_stock"),
        )


@dataclass(frozen=True, slots=True)
class ROResult:
    """Complete immutable RO state, diagnostic, ledger, and advanced cursor."""

    feed: TreatmentStream
    permeate: TreatmentStream
    concentrate: TreatmentStream
    removal: RORemovalResult
    parameters: ROParameters
    ledger: tuple[LedgerEntry, ...]
    next_cursor: LedgerCursor
    evidence_label: EvidenceLabel

    def __post_init__(self) -> None:
        for field_path, value, expected in (
            ("feed", self.feed, TreatmentStream),
            ("permeate", self.permeate, TreatmentStream),
            ("concentrate", self.concentrate, TreatmentStream),
            ("removal", self.removal, RORemovalResult),
            ("parameters", self.parameters, ROParameters),
            ("next_cursor", self.next_cursor, LedgerCursor),
        ):
            if not isinstance(value, expected):
                fail(
                    "RO_RESULT_TYPE_INVALID",
                    f"{field_path} must be a {expected.__name__}",
                    field_path,
                )
        try:
            ledger = tuple(self.ledger)
        except TypeError:
            fail("RO_LEDGER_INVALID", "ledger must be iterable", "ledger")
        if any(not isinstance(row, LedgerEntry) for row in ledger):
            fail("RO_LEDGER_INVALID", "ledger rows must be LedgerEntry values", "ledger")
        object.__setattr__(self, "ledger", ledger)
        object.__setattr__(
            self,
            "evidence_label",
            _evidence_label(self.evidence_label, "evidence_label"),
        )
        if self.removal.destination_stream_id != self.concentrate.stream_id:
            fail(
                "RO_REMOVAL_DESTINATION_MISMATCH",
                "selective-removal destination must be the concentrate",
                "removal.destination_stream_id",
            )
        if self.removal.destination_stock != self.concentrate.stocks:
            fail(
                "RO_REMOVAL_DESTINATION_MISMATCH",
                "selective-removal destination stock must equal concentrate stock",
                "removal.destination_stock",
            )


@dataclass(frozen=True, slots=True)
class FormulaResolvedAmendment:
    """A dose whose water and elemental/charge stocks are already resolved."""

    dose_id: str
    water_volume_l: float
    water_density_kg_l: float
    stock_additions: Mapping[ConservedEntity, float]
    evidence_label: EvidenceLabel

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "dose_id",
            _readable_id(
                self.dose_id,
                code="AMENDMENT_ID_INVALID",
                field_path="dose_id",
            ),
        )
        object.__setattr__(
            self,
            "water_volume_l",
            finite_float(
                self.water_volume_l,
                code="TREATMENT_NUMERIC_INVALID",
                field_path="water_volume_l",
                nonnegative=True,
            ),
        )
        object.__setattr__(
            self,
            "water_density_kg_l",
            finite_float(
                self.water_density_kg_l,
                code="TREATMENT_NUMERIC_INVALID",
                field_path="water_density_kg_l",
                positive=True,
            ),
        )
        finite_float(
            self.water_volume_l * self.water_density_kg_l,
            code="TREATMENT_NUMERIC_INVALID",
            field_path="water_mass_kg",
            nonnegative=True,
        )
        additions = _stock_mapping(
            self.stock_additions,
            field_path="stock_additions",
        )
        if self.water_volume_l == 0.0 and not any(additions.values()):
            fail(
                "AMENDMENT_EMPTY",
                "an amendment must add water or at least one positive stock",
                "stock_additions",
            )
        object.__setattr__(self, "stock_additions", additions)
        object.__setattr__(
            self,
            "evidence_label",
            _evidence_label(self.evidence_label, "evidence_label"),
        )

    @property
    def water_mass_kg(self) -> float:
        return self.water_volume_l * self.water_density_kg_l


@dataclass(frozen=True, slots=True)
class RemineralizationResult:
    """Exact before/dose/after records and one-sided amendment ledger."""

    before: TreatmentStream
    doses: tuple[FormulaResolvedAmendment, ...]
    after: TreatmentStream
    ledger: tuple[LedgerEntry, ...]
    next_cursor: LedgerCursor
    evidence_label: EvidenceLabel

    def __post_init__(self) -> None:
        if not isinstance(self.before, TreatmentStream) or not isinstance(
            self.after, TreatmentStream
        ):
            fail(
                "REMINERALIZATION_RESULT_TYPE_INVALID",
                "before and after must be TreatmentStream records",
                "before",
            )
        try:
            doses = tuple(self.doses)
            ledger = tuple(self.ledger)
        except TypeError:
            fail(
                "REMINERALIZATION_RESULT_TYPE_INVALID",
                "doses and ledger must be iterable",
                "doses",
            )
        if any(not isinstance(dose, FormulaResolvedAmendment) for dose in doses):
            fail(
                "REMINERALIZATION_RESULT_TYPE_INVALID",
                "doses must contain FormulaResolvedAmendment records",
                "doses",
            )
        if any(not isinstance(row, LedgerEntry) for row in ledger):
            fail(
                "REMINERALIZATION_RESULT_TYPE_INVALID",
                "ledger must contain LedgerEntry records",
                "ledger",
            )
        if not isinstance(self.next_cursor, LedgerCursor):
            fail(
                "REMINERALIZATION_RESULT_TYPE_INVALID",
                "next_cursor must be a LedgerCursor",
                "next_cursor",
            )
        object.__setattr__(self, "doses", doses)
        object.__setattr__(self, "ledger", ledger)
        object.__setattr__(
            self,
            "evidence_label",
            _evidence_label(self.evidence_label, "evidence_label"),
        )


def _ro_transfer_rows(
    *,
    transaction_id: str,
    event_id: str,
    feed: TreatmentStream,
    destination: TreatmentStream,
    parameters: ROParameters,
    evidence_label: EvidenceLabel,
) -> tuple[LedgerEntry, ...]:
    rows: list[LedgerEntry] = []
    transfer_entities = (ConservedEntity.WATER, *feed.stocks.keys())
    for entity in transfer_entities:
        if entity is ConservedEntity.WATER:
            amount = destination.water_mass_kg
            carrier_volume_l = destination.volume_l
            density = destination.density_kg_l
            flow_kind = InternalWaterFlowKind.AQUEOUS_TRANSFER
        else:
            amount = destination.stocks[entity]
            carrier_volume_l = None
            density = None
            flow_kind = None
        unit = entity_spec(entity).stock_unit
        common: dict[str, object] = {
            "transaction_id": transaction_id,
            "event_id": event_id,
            "kind": LedgerEntryKind.INTERNAL,
            "phase": OperatorPhase.TREATMENT_BLENDING,
            "transfer_mode": MaterialTransferMode.ADVECTIVE_AQUEOUS,
            "entity": entity,
            "unit": unit,
            "evidence_label": evidence_label,
            "physical_transfer_id": event_id,
            "carrier_volume_l": carrier_volume_l,
            "water_density_kg_l": density,
            "internal_water_flow_kind": flow_kind,
            "treatment_model_id": parameters.model_id,
            "treatment_model_version": parameters.version,
        }
        rows.append(
            LedgerEntry(
                **common,
                compartment=feed.stream_id,
                counterparty=destination.stream_id,
                amount=-amount,
            )
        )
        rows.append(
            LedgerEntry(
                **common,
                compartment=destination.stream_id,
                counterparty=feed.stream_id,
                amount=amount,
            )
        )
    return tuple(rows)


def ro_split(
    feed: TreatmentStream,
    parameters: ROParameters,
    *,
    permeate_stream_id: str,
    concentrate_stream_id: str,
    cursor: LedgerCursor,
) -> ROResult:
    """Split water and each tracked entity with two complete paired ledgers."""
    if not isinstance(feed, TreatmentStream):
        fail("RO_INPUT_TYPE_INVALID", "feed must be a TreatmentStream", "feed")
    if not isinstance(parameters, ROParameters):
        fail("RO_INPUT_TYPE_INVALID", "parameters must be ROParameters", "parameters")
    if not isinstance(cursor, LedgerCursor):
        fail("RO_INPUT_TYPE_INVALID", "cursor must be a LedgerCursor", "cursor")
    permeate_id = _readable_id(
        permeate_stream_id,
        code="TREATMENT_STREAM_ID_INVALID",
        field_path="permeate_stream_id",
    )
    concentrate_id = _readable_id(
        concentrate_stream_id,
        code="TREATMENT_STREAM_ID_INVALID",
        field_path="concentrate_stream_id",
    )
    if len({feed.stream_id, permeate_id, concentrate_id}) != 3:
        fail(
            "RO_STREAM_IDS_NOT_UNIQUE",
            "feed, permeate, and concentrate stream IDs must be unique",
            "permeate_stream_id",
        )
    if set(parameters.rejection) != set(feed.stocks):
        fail(
            "RO_REJECTION_KEYS_MISMATCH",
            "rejection keys must exactly match feed tracked entities",
            "parameters.rejection",
            {
                "missing": sorted(
                    entity.value for entity in set(feed.stocks) - set(parameters.rejection)
                ),
                "extra": sorted(
                    entity.value for entity in set(parameters.rejection) - set(feed.stocks)
                ),
            },
        )

    recovery = parameters.recovery
    permeate_volume = feed.volume_l * recovery
    concentrate_volume = feed.volume_l - permeate_volume
    permeate_water = feed.water_mass_kg * recovery
    concentrate_water = feed.water_mass_kg - permeate_water
    permeate_stocks: dict[ConservedEntity, float] = {}
    concentrate_stocks: dict[ConservedEntity, float] = {}
    selectively_rejected: dict[ConservedEntity, float] = {}
    for entity in ConservedEntity:
        if entity not in feed.stocks:
            continue
        feed_stock = feed.stocks[entity]
        rejection = parameters.rejection[entity]
        permeate_stock = feed_stock * recovery * (1.0 - rejection)
        permeate_stocks[entity] = permeate_stock
        concentrate_stocks[entity] = feed_stock - permeate_stock
        selectively_rejected[entity] = feed_stock * recovery * rejection

    label = compose_evidence_labels(feed.evidence_label, parameters.evidence_label)
    permeate = TreatmentStream(
        permeate_id,
        permeate_volume,
        permeate_water,
        permeate_stocks,
        label,
    )
    concentrate = TreatmentStream(
        concentrate_id,
        concentrate_volume,
        concentrate_water,
        concentrate_stocks,
        label,
    )
    removal = RORemovalResult(
        selectively_rejected,
        concentrate.stream_id,
        concentrate.stocks,
    )
    # The result diagnostic points at the exact immutable concentrate mapping.
    object.__setattr__(removal, "destination_stock", concentrate.stocks)

    permeate_tx, next_cursor = cursor.issue()
    concentrate_tx, next_cursor = next_cursor.issue()
    ledger = (
        *_ro_transfer_rows(
            transaction_id=permeate_tx,
            event_id="ro-permeate",
            feed=feed,
            destination=permeate,
            parameters=parameters,
            evidence_label=label,
        ),
        *_ro_transfer_rows(
            transaction_id=concentrate_tx,
            event_id="ro-concentrate",
            feed=feed,
            destination=concentrate,
            parameters=parameters,
            evidence_label=label,
        ),
    )
    result = ROResult(
        feed=feed,
        permeate=permeate,
        concentrate=concentrate,
        removal=removal,
        parameters=parameters,
        ledger=ledger,
        next_cursor=next_cursor,
        evidence_label=label,
    )
    audit_ro_ledger(result)
    return result


def _ledger_fingerprint(row: LedgerEntry) -> tuple[object, ...]:
    """Return every ledger field explicitly; the audit compares no row builders."""
    return (
        row.transaction_id,
        row.event_id,
        row.kind,
        row.phase,
        row.transfer_mode,
        row.compartment,
        row.counterparty,
        row.entity,
        row.amount,
        row.unit,
        row.evidence_label,
        row.boundary_category,
        row.internal_flux_kind,
        row.internal_water_flow_kind,
        row.physical_transfer_id,
        row.carrier_volume_l,
        row.water_density_kg_l,
        row.requested_amount,
        row.applied_amount,
        row.cap_fraction,
        row.adapter_id,
        row.adapter_version,
        row.adapter_hash,
        row.treatment_model_id,
        row.treatment_model_version,
    )


def _expected_ro_row_fingerprints(result: ROResult) -> tuple[tuple[object, ...], ...]:
    """Derive canonical rows directly from the RO equations and cursor namespace."""
    start_ordinal = result.next_cursor.next_ordinal - 2
    if start_ordinal < 0:
        fail(
            "RO_LEDGER_AUDIT_FAILED",
            "advanced cursor cannot identify two RO transactions",
            "next_cursor",
        )
    cursor = LedgerCursor(
        result.next_cursor.run_id,
        result.next_cursor.chain_id,
        start_ordinal,
    )
    permeate_tx, cursor = cursor.issue()
    concentrate_tx, cursor = cursor.issue()
    feed = result.feed
    parameters = result.parameters
    recovery = parameters.recovery
    branches = (
        (
            permeate_tx,
            "ro-permeate",
            result.permeate.stream_id,
            feed.volume_l * recovery,
            feed.water_mass_kg * recovery,
        ),
        (
            concentrate_tx,
            "ro-concentrate",
            result.concentrate.stream_id,
            feed.volume_l - feed.volume_l * recovery,
            feed.water_mass_kg - feed.water_mass_kg * recovery,
        ),
    )
    expected: list[tuple[object, ...]] = []
    for transaction_id, event_id, destination_id, volume_l, water_mass_kg in branches:
        for entity in (ConservedEntity.WATER, *tuple(feed.stocks)):
            if entity is ConservedEntity.WATER:
                amount = water_mass_kg
                carrier_volume_l: float | None = volume_l
                density: float | None = water_mass_kg / volume_l
                flow_kind: InternalWaterFlowKind | None = (
                    InternalWaterFlowKind.AQUEOUS_TRANSFER
                )
            else:
                permeate_stock = (
                    feed.stocks[entity]
                    * recovery
                    * (1.0 - parameters.rejection[entity])
                )
                amount = (
                    permeate_stock
                    if event_id == "ro-permeate"
                    else feed.stocks[entity] - permeate_stock
                )
                carrier_volume_l = None
                density = None
                flow_kind = None
            common = (
                transaction_id,
                event_id,
                LedgerEntryKind.INTERNAL,
                OperatorPhase.TREATMENT_BLENDING,
                MaterialTransferMode.ADVECTIVE_AQUEOUS,
            )
            trailing = (
                entity,
                entity_spec(entity).stock_unit,
                result.evidence_label,
                None,
                None,
                flow_kind,
                event_id,
                carrier_volume_l,
                density,
                None,
                None,
                None,
                None,
                None,
                None,
                parameters.model_id,
                parameters.version,
            )
            expected.append(
                (
                    *common,
                    feed.stream_id,
                    destination_id,
                    *trailing[:1],
                    -amount,
                    *trailing[1:],
                )
            )
            expected.append(
                (
                    *common,
                    destination_id,
                    feed.stream_id,
                    *trailing[:1],
                    amount,
                    *trailing[1:],
                )
            )
    return tuple(expected)


def audit_ro_ledger(
    result: ROResult,
    ledger: Iterable[LedgerEntry] | None = None,
) -> None:
    """Refuse any missing, duplicate, reordered, or corrupted RO ledger row."""
    if not isinstance(result, ROResult):
        fail("RO_LEDGER_AUDIT_FAILED", "result must be an ROResult", "result")
    try:
        candidate = result.ledger if ledger is None else tuple(ledger)
    except TypeError:
        fail("RO_LEDGER_AUDIT_FAILED", "ledger must be iterable", "ledger")
    if any(not isinstance(row, LedgerEntry) for row in candidate):
        fail(
            "RO_LEDGER_AUDIT_FAILED",
            "RO ledger must contain only LedgerEntry rows",
            "ledger",
        )

    feed = result.feed
    parameters = result.parameters
    recovery = parameters.recovery
    label = compose_evidence_labels(feed.evidence_label, parameters.evidence_label)
    permeate_volume = feed.volume_l * recovery
    permeate_water = feed.water_mass_kg * recovery
    expected_permeate = {
        entity: feed.stocks[entity]
        * recovery
        * (1.0 - parameters.rejection[entity])
        for entity in feed.stocks
    }
    expected_concentrate = {
        entity: feed.stocks[entity] - expected_permeate[entity]
        for entity in feed.stocks
    }
    expected_rejected = {
        entity: feed.stocks[entity] * recovery * parameters.rejection[entity]
        for entity in feed.stocks
    }
    result_invariants = (
        result.evidence_label is label,
        result.permeate.evidence_label is label,
        result.concentrate.evidence_label is label,
        result.permeate.volume_l == permeate_volume,
        result.concentrate.volume_l == feed.volume_l - permeate_volume,
        result.permeate.water_mass_kg == permeate_water,
        result.concentrate.water_mass_kg == feed.water_mass_kg - permeate_water,
        result.permeate.stocks == expected_permeate,
        result.concentrate.stocks == expected_concentrate,
        result.removal.selectively_rejected_stock == expected_rejected,
        result.removal.destination_stream_id == result.concentrate.stream_id,
        result.removal.destination_stock is result.concentrate.stocks,
        len(
            {
                feed.stream_id,
                result.permeate.stream_id,
                result.concentrate.stream_id,
            }
        )
        == 3,
    )
    if not all(result_invariants):
        fail(
            "RO_LEDGER_AUDIT_FAILED",
            "RO result does not satisfy the independently derived split equations",
            "result",
        )

    expected = _expected_ro_row_fingerprints(result)
    received = tuple(_ledger_fingerprint(row) for row in candidate)
    if received != expected:
        fail(
            "RO_LEDGER_AUDIT_FAILED",
            "RO ledger does not match the independently reconstructed paired transfers",
            "ledger",
            {"expected_rows": len(expected), "received_rows": len(received)},
        )


def _amendment_rows(
    dose: FormulaResolvedAmendment,
    *,
    output_stream_id: str,
    transaction_id: str,
) -> tuple[LedgerEntry, ...]:
    rows: list[LedgerEntry] = []
    has_water = dose.water_volume_l > 0.0
    transfer_mode = (
        MaterialTransferMode.ADVECTIVE_AQUEOUS
        if has_water
        else MaterialTransferMode.ENTITY_ONLY
    )
    if has_water:
        rows.append(
            LedgerEntry(
                transaction_id=transaction_id,
                event_id=dose.dose_id,
                kind=LedgerEntryKind.EXTERNAL,
                phase=OperatorPhase.EXTERNAL_FEED_AMENDMENT,
                transfer_mode=MaterialTransferMode.ADVECTIVE_AQUEOUS,
                compartment=output_stream_id,
                counterparty=dose.dose_id,
                entity=ConservedEntity.WATER,
                amount=dose.water_mass_kg,
                unit=StockUnit.KG,
                evidence_label=dose.evidence_label,
                boundary_category=ExternalBoundaryCategory.AMENDMENT,
                physical_transfer_id=dose.dose_id,
                carrier_volume_l=dose.water_volume_l,
                water_density_kg_l=dose.water_density_kg_l,
            )
        )
    for entity in ConservedEntity:
        if entity not in dose.stock_additions:
            continue
        rows.append(
            LedgerEntry(
                transaction_id=transaction_id,
                event_id=dose.dose_id,
                kind=LedgerEntryKind.EXTERNAL,
                phase=OperatorPhase.EXTERNAL_FEED_AMENDMENT,
                transfer_mode=transfer_mode,
                compartment=output_stream_id,
                counterparty=dose.dose_id,
                entity=entity,
                amount=dose.stock_additions[entity],
                unit=entity_spec(entity).stock_unit,
                evidence_label=dose.evidence_label,
                boundary_category=ExternalBoundaryCategory.AMENDMENT,
                physical_transfer_id=dose.dose_id,
            )
        )
    return tuple(rows)


def remineralize(
    product: TreatmentStream,
    doses: Iterable[FormulaResolvedAmendment],
    *,
    output_stream_id: str,
    cursor: LedgerCursor,
) -> RemineralizationResult:
    """Add formula-resolved water and stocks once, with no invented reaction."""
    if not isinstance(product, TreatmentStream):
        fail(
            "REMINERALIZATION_INPUT_TYPE_INVALID",
            "product must be a TreatmentStream",
            "product",
        )
    if not isinstance(cursor, LedgerCursor):
        fail(
            "REMINERALIZATION_INPUT_TYPE_INVALID",
            "cursor must be a LedgerCursor",
            "cursor",
        )
    output_id = _readable_id(
        output_stream_id,
        code="TREATMENT_STREAM_ID_INVALID",
        field_path="output_stream_id",
    )
    if output_id == product.stream_id:
        fail(
            "REMINERALIZATION_STREAM_ID_COLLISION",
            "output stream ID must differ from the input product",
            "output_stream_id",
        )
    try:
        supplied_doses = tuple(doses)
    except TypeError:
        fail(
            "REMINERALIZATION_INPUT_TYPE_INVALID",
            "doses must be iterable",
            "doses",
        )
    if any(not isinstance(dose, FormulaResolvedAmendment) for dose in supplied_doses):
        fail(
            "REMINERALIZATION_INPUT_TYPE_INVALID",
            "doses must contain FormulaResolvedAmendment records",
            "doses",
        )
    dose_ids = tuple(dose.dose_id for dose in supplied_doses)
    if len(set(dose_ids)) != len(dose_ids):
        fail(
            "AMENDMENT_DUPLICATE_DOSE_ID",
            "dose IDs must be unique",
            "doses",
        )
    ordered_doses = tuple(sorted(supplied_doses, key=lambda dose: dose.dose_id))

    try:
        output_volume = fsum(
            [product.volume_l, *(dose.water_volume_l for dose in ordered_doses)]
        )
    except OverflowError:
        fail(
            "TREATMENT_NUMERIC_INVALID",
            "remineralization volume aggregate must remain finite",
            "after.volume_l",
        )
    finite_float(
        output_volume,
        code="TREATMENT_NUMERIC_INVALID",
        field_path="after.volume_l",
        positive=True,
    )
    try:
        output_water = fsum(
            [product.water_mass_kg, *(dose.water_mass_kg for dose in ordered_doses)]
        )
    except OverflowError:
        fail(
            "TREATMENT_NUMERIC_INVALID",
            "remineralization water-mass aggregate must remain finite",
            "after.water_mass_kg",
        )
    finite_float(
        output_water,
        code="TREATMENT_NUMERIC_INVALID",
        field_path="after.water_mass_kg",
        positive=True,
    )
    represented_entities = set(product.stocks)
    for dose in ordered_doses:
        represented_entities.update(dose.stock_additions)
    output_stocks: dict[ConservedEntity, float] = {}
    for entity in ConservedEntity:
        if entity not in represented_entities or entity is ConservedEntity.WATER:
            continue
        try:
            total = fsum(
                [
                    product.stocks.get(entity, 0.0),
                    *(dose.stock_additions.get(entity, 0.0) for dose in ordered_doses),
                ]
            )
        except OverflowError:
            fail(
                "TREATMENT_NUMERIC_INVALID",
                "remineralization stock aggregate must remain finite",
                f"after.stocks.{entity.value}",
            )
        output_stocks[entity] = finite_float(
            total,
            code="TREATMENT_NUMERIC_INVALID",
            field_path=f"after.stocks.{entity.value}",
            nonnegative=True,
        )
    label = compose_evidence_labels(
        product.evidence_label,
        *(dose.evidence_label for dose in ordered_doses),
    )
    after = TreatmentStream(
        output_id,
        output_volume,
        output_water,
        output_stocks,
        label,
    )

    ledger: list[LedgerEntry] = []
    next_cursor = cursor
    for dose in ordered_doses:
        transaction_id, next_cursor = next_cursor.issue()
        ledger.extend(
            _amendment_rows(
                dose,
                output_stream_id=output_id,
                transaction_id=transaction_id,
            )
        )
    return RemineralizationResult(
        before=product,
        doses=ordered_doses,
        after=after,
        ledger=tuple(ledger),
        next_cursor=next_cursor,
        evidence_label=label,
    )
