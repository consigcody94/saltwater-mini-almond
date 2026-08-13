"""Stable, immutable vocabulary for AlmondLab artifacts and conservation gates."""

from __future__ import annotations

from dataclasses import dataclass, replace
from math import isclose
import re
from types import MappingProxyType
from typing import Final, Mapping

from almondlab.errors import fail, finite_float

from enum import StrEnum


class EvidenceLabel(StrEnum):
    PHYSICS_CONSTRAINED = "physics_constrained"
    EMPIRICALLY_CALIBRATED = "empirically_calibrated"
    HYPOTHESIS_PRIOR = "hypothesis_prior"
    SYNTHETIC_ONLY = "synthetic_only"


class DataOrigin(StrEnum):
    SYNTHETIC = "synthetic"
    EMPIRICAL = "empirical"
    LITERATURE_DERIVED = "literature_derived"
    MODEL_DERIVED = "model_derived"


class ECKind(StrEnum):
    ECW = "ECw"
    PORE_WATER = "pore_water_EC"
    ECE = "ECe"


class ConservedEntity(StrEnum):
    WATER = "water"
    NA = "na"
    CL = "cl"
    CA = "ca"
    MG = "mg"
    K = "k"
    TOTAL_B = "total_b"
    N = "n"
    P = "p"
    S = "s"
    DIC = "dissolved_inorganic_carbon"
    ALKALINITY = "alkalinity"


class GateState(StrEnum):
    PASS = "pass"
    FAIL = "fail"
    NOT_EVALUABLE = "not_evaluable"


class StockUnit(StrEnum):
    """Canonical stock units used by the conservation ledger."""

    KG = "kg"
    MMOL = "mmol"
    MMOL_C = "mmol_c"


class ConcentrationUnit(StrEnum):
    """Canonical concentration units for non-carrier entities."""

    MMOL_PER_L = "mmol/L"
    MMOL_C_PER_L = "mmol_c/L"


@dataclass(frozen=True, slots=True)
class EntitySpec:
    """Canonical amount and concentration basis for one conserved entity."""

    entity: ConservedEntity
    stock_unit: StockUnit
    concentration_unit: ConcentrationUnit | None
    basis: str


_ENTITY_BASES: Final[Mapping[ConservedEntity, str]] = MappingProxyType(
    {
        ConservedEntity.WATER: "reserved water carrier mass",
        ConservedEntity.NA: "elemental sodium amount",
        ConservedEntity.CL: "chloride ion amount",
        ConservedEntity.CA: "elemental calcium amount",
        ConservedEntity.MG: "elemental magnesium amount",
        ConservedEntity.K: "elemental potassium amount",
        ConservedEntity.TOTAL_B: "total dissolved boron amount",
        ConservedEntity.N: "total nitrogen amount",
        ConservedEntity.P: "total phosphorus amount",
        ConservedEntity.S: "total sulfur amount",
        ConservedEntity.DIC: "dissolved inorganic carbon amount as carbon",
        ConservedEntity.ALKALINITY: "charge-equivalent alkalinity amount",
    }
)


def _make_entity_specs() -> Mapping[ConservedEntity, EntitySpec]:
    specs: dict[ConservedEntity, EntitySpec] = {}
    for entity in ConservedEntity:
        if entity is ConservedEntity.WATER:
            stock_unit = StockUnit.KG
            concentration_unit = None
        elif entity is ConservedEntity.ALKALINITY:
            stock_unit = StockUnit.MMOL_C
            concentration_unit = ConcentrationUnit.MMOL_C_PER_L
        else:
            stock_unit = StockUnit.MMOL
            concentration_unit = ConcentrationUnit.MMOL_PER_L
        specs[entity] = EntitySpec(
            entity=entity,
            stock_unit=stock_unit,
            concentration_unit=concentration_unit,
            basis=_ENTITY_BASES[entity],
        )
    if set(specs) != set(ConservedEntity) or len(specs) != len(ConservedEntity):
        raise RuntimeError("conserved-entity registry must have exact enum coverage")
    if any(entity is not spec.entity for entity, spec in specs.items()):
        raise RuntimeError("conserved-entity registry keys and records must agree")
    return MappingProxyType(specs)


ENTITY_SPECS: Final[Mapping[ConservedEntity, EntitySpec]] = _make_entity_specs()


def entity_spec(entity: ConservedEntity) -> EntitySpec:
    """Return the canonical immutable record for an explicitly typed entity."""

    if not isinstance(entity, ConservedEntity):
        fail("ENTITY_TYPE_REQUIRED", "entity must be a ConservedEntity", "entity")
    return ENTITY_SPECS[entity]


class ExternalBoundaryCategory(StrEnum):
    SOURCE_FEED = "source_feed"
    EXTERNAL_MAKEUP = "external_makeup"
    AMENDMENT = "amendment"
    DISPOSED_CONCENTRATE = "disposed_concentrate"
    PURGE_OR_DISCHARGE = "purge_or_discharge"
    SAMPLING = "sampling"
    LEAK = "leak"
    VENTED_VAPOR = "vented_vapor"
    HARVESTED_TISSUE = "harvested_tissue"
    REMOVED_SOLID = "removed_solid"
    TREATMENT_LOSS = "treatment_loss"
    OTHER_MEASURED_OUTPUT = "other_measured_output"


class InternalEntityFluxKind(StrEnum):
    PLANT_UPTAKE = "plant_uptake"
    PLANT_EFFLUX = "plant_efflux"
    XYLEM_RETRIEVAL = "xylem_retrieval"
    SEQUESTRATION = "sequestration"
    VACUOLE_RELEASE = "vacuole_release"
    XYLEM_LOADING = "xylem_loading"
    TISSUE_DEPOSITION = "tissue_deposition"


class OperatorPhase(StrEnum):
    EXTERNAL_FEED_AMENDMENT = "external_feed_amendment"
    TREATMENT_BLENDING = "treatment_blending"
    IRRIGATION = "irrigation"
    EVAPORATION_TRANSPIRATION = "evaporation_transpiration"
    LAYER_DRAINAGE = "layer_drainage"
    PLANT_ION_TRANSITIONS = "plant_ion_transitions"
    REACTION_ADAPTERS = "reaction_adapters"
    DRAINAGE_CONDENSATE_RETURN = "drainage_condensate_return"
    PURGE_DISPOSAL = "purge_disposal"
    NUMERICAL_CLOSURE = "numerical_closure"


_READABLE_ID_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}\Z", re.ASCII
)


def _readable_id(value: object, *, code: str, field_path: str) -> str:
    if not isinstance(value, str) or _READABLE_ID_PATTERN.fullmatch(value) is None:
        fail(code, "identifier must use 1-64 readable ASCII characters", field_path)
    return value


_CANONICAL_PHASES: Final[tuple[OperatorPhase, ...]] = tuple(OperatorPhase)


@dataclass(frozen=True, slots=True)
class OperatorSchedule:
    """The immutable core operator ordering; alternate orderings are invalid."""

    schedule_id: str
    phases: tuple[OperatorPhase, ...]

    def __post_init__(self) -> None:
        _readable_id(
            self.schedule_id,
            code="OPERATOR_SCHEDULE_ID_INVALID",
            field_path="schedule_id",
        )
        try:
            supplied = tuple(self.phases)
        except (TypeError, ValueError):
            fail(
                "OPERATOR_SCHEDULE_EXTRA_PHASE",
                "phases must contain only OperatorPhase values",
                "phases",
            )
        if any(not isinstance(phase, OperatorPhase) for phase in supplied):
            fail(
                "OPERATOR_SCHEDULE_EXTRA_PHASE",
                "phases must contain only OperatorPhase values",
                "phases",
            )
        typed = tuple(supplied)
        if len(set(typed)) != len(typed):
            fail(
                "OPERATOR_SCHEDULE_DUPLICATE_PHASE",
                "operator phases cannot be duplicated",
                "phases",
            )
        missing = set(_CANONICAL_PHASES) - set(typed)
        if missing:
            fail(
                "OPERATOR_SCHEDULE_MISSING_PHASE",
                "operator schedule must include every core phase",
                "phases",
                {"missing": sorted(phase.value for phase in missing)},
            )
        extra = set(typed) - set(_CANONICAL_PHASES)
        if extra:
            fail(
                "OPERATOR_SCHEDULE_EXTRA_PHASE",
                "operator schedule contains a non-core phase",
                "phases",
            )
        if typed != _CANONICAL_PHASES:
            fail(
                "OPERATOR_SCHEDULE_ORDER_INVALID",
                "operator phases must use the core order",
                "phases",
            )
        object.__setattr__(self, "phases", typed)


CORE_V1_OPERATOR_SCHEDULE: Final[OperatorSchedule] = OperatorSchedule(
    schedule_id="core_v1",
    phases=_CANONICAL_PHASES,
)


class CompartmentKind(StrEnum):
    """Typed physical locations used by treatment, water, and plant models."""

    SOURCE_WATER = "source_water"
    TREATMENT_FEED = "treatment_feed"
    TREATMENT_PRODUCT = "treatment_product"
    TREATMENT_CONCENTRATE = "treatment_concentrate"
    BLEND_TANK = "blend_tank"
    IRRIGATION_TANK = "irrigation_tank"
    ROOT_ZONE = "root_zone"
    ROOT_APOPLAST = "root_apoplast"
    ROOT_SYMPLAST = "root_symplast"
    ROOT_VACUOLE = "root_vacuole"
    XYLEM = "xylem"
    SHOOT_TISSUE = "shoot_tissue"
    DRAINAGE = "drainage"
    CONDENSATE = "condensate"
    GREENHOUSE_AIR = "greenhouse_air"
    PURGE_HOLDING = "purge_holding"
    REMOVED_SOLID = "removed_solid"


class InternalWaterFlowKind(StrEnum):
    """Physical water-flow mechanisms; only the first advects source solutes."""

    AQUEOUS_TRANSFER = "aqueous_transfer"
    EVAPORATION = "evaporation"
    TRANSPIRATION = "transpiration"
    CONDENSATE_RETURN = "condensate_return"


class MaterialTransferMode(StrEnum):
    """What material an event moves, independent of its physical endpoint."""

    ADVECTIVE_AQUEOUS = "advective_aqueous"
    WATER_ONLY = "water_only"
    ENTITY_ONLY = "entity_only"


# Compatibility vocabulary for the two kernels while retaining one ledger type.
FlowMaterialMode = MaterialTransferMode
BoundaryMaterialMode = MaterialTransferMode


class LedgerEntryKind(StrEnum):
    INTERNAL = "internal"
    EXTERNAL = "external"


MAX_LEDGER_ORDINAL: Final[int] = 999_999_999_999
_EXHAUSTED_LEDGER_ORDINAL: Final[int] = MAX_LEDGER_ORDINAL + 1


@dataclass(frozen=True, slots=True)
class LedgerCursor:
    """A deterministic, immutable transaction namespace and ordinal cursor."""

    run_id: str
    chain_id: str
    next_ordinal: int = 0

    def __post_init__(self) -> None:
        _readable_id(self.run_id, code="LEDGER_ID_INVALID", field_path="run_id")
        _readable_id(self.chain_id, code="LEDGER_ID_INVALID", field_path="chain_id")
        if isinstance(self.next_ordinal, bool) or not isinstance(self.next_ordinal, int):
            fail(
                "LEDGER_ORDINAL_INVALID",
                "next_ordinal must be a nonnegative integer",
                "next_ordinal",
            )
        if self.next_ordinal < 0:
            fail(
                "LEDGER_ORDINAL_INVALID",
                "next_ordinal must be a nonnegative integer",
                "next_ordinal",
            )
        if self.next_ordinal > _EXHAUSTED_LEDGER_ORDINAL:
            fail(
                "LEDGER_ORDINAL_OVERFLOW",
                "next_ordinal exceeds the 12-digit ledger namespace",
                "next_ordinal",
            )

    def issue(self) -> tuple[str, LedgerCursor]:
        """Return this ordinal's ID and an advanced cursor without mutation."""

        if self.next_ordinal > MAX_LEDGER_ORDINAL:
            fail(
                "LEDGER_ORDINAL_OVERFLOW",
                "cannot advance beyond the 12-digit ledger namespace",
                "next_ordinal",
            )
        transaction_id = (
            f"tx:{self.run_id}:{self.chain_id}:{self.next_ordinal:012d}"
        )
        return transaction_id, replace(self, next_ordinal=self.next_ordinal + 1)


_TRANSACTION_ID_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"tx:[A-Za-z0-9][A-Za-z0-9._-]{0,63}:"
    r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}:[0-9]{12}\Z",
    re.ASCII,
)
_SHA256_PATTERN: Final[re.Pattern[str]] = re.compile(r"[0-9a-f]{64}\Z", re.ASCII)


def _optional_readable_id(value: str | None, field_path: str) -> str | None:
    if value is None:
        return None
    return _readable_id(value, code="LEDGER_ID_INVALID", field_path=field_path)


@dataclass(frozen=True, slots=True, kw_only=True)
class LedgerEntry:
    """One immutable, typed row in the shared conservation ledger.

    Water is conserved as mass while ``carrier_volume_l`` remains explicit for
    hydraulic calculations.  All optional numerical metadata is copied to plain
    finite floats during construction, leaving no nested mutable state.
    """

    transaction_id: str
    event_id: str
    kind: LedgerEntryKind
    phase: OperatorPhase
    transfer_mode: MaterialTransferMode
    compartment: str
    counterparty: str
    entity: ConservedEntity
    amount: float
    unit: StockUnit
    evidence_label: EvidenceLabel
    boundary_category: ExternalBoundaryCategory | None = None
    internal_flux_kind: InternalEntityFluxKind | None = None
    physical_transfer_id: str | None = None
    carrier_volume_l: float | None = None
    water_density_kg_l: float | None = None
    requested_amount: float | None = None
    applied_amount: float | None = None
    cap_fraction: float | None = None
    adapter_id: str | None = None
    adapter_version: str | None = None
    adapter_hash: str | None = None

    def __post_init__(self) -> None:
        if (
            not isinstance(self.transaction_id, str)
            or _TRANSACTION_ID_PATTERN.fullmatch(self.transaction_id) is None
        ):
            fail(
                "LEDGER_TRANSACTION_ID_INVALID",
                "transaction_id must be issued by LedgerCursor",
                "transaction_id",
            )
        _readable_id(self.event_id, code="LEDGER_ID_INVALID", field_path="event_id")
        _readable_id(
            self.compartment, code="LEDGER_ID_INVALID", field_path="compartment"
        )
        _readable_id(
            self.counterparty, code="LEDGER_ID_INVALID", field_path="counterparty"
        )
        _optional_readable_id(self.physical_transfer_id, "physical_transfer_id")

        typed_fields: tuple[tuple[object, type[object], str], ...] = (
            (self.kind, LedgerEntryKind, "kind"),
            (self.phase, OperatorPhase, "phase"),
            (self.transfer_mode, MaterialTransferMode, "transfer_mode"),
            (self.entity, ConservedEntity, "entity"),
            (self.unit, StockUnit, "unit"),
            (self.evidence_label, EvidenceLabel, "evidence_label"),
        )
        for value, expected_type, field_path in typed_fields:
            if not isinstance(value, expected_type):
                fail(
                    "LEDGER_TYPE_INVALID",
                    f"{field_path} must be a {expected_type.__name__}",
                    field_path,
                )
        if self.boundary_category is not None and not isinstance(
            self.boundary_category, ExternalBoundaryCategory
        ):
            fail(
                "LEDGER_TYPE_INVALID",
                "boundary_category must be an ExternalBoundaryCategory",
                "boundary_category",
            )
        if self.internal_flux_kind is not None and not isinstance(
            self.internal_flux_kind, InternalEntityFluxKind
        ):
            fail(
                "LEDGER_TYPE_INVALID",
                "internal_flux_kind must be an InternalEntityFluxKind",
                "internal_flux_kind",
            )

        amount = finite_float(
            self.amount,
            code="LEDGER_NUMERIC_INVALID",
            field_path="amount",
        )
        object.__setattr__(self, "amount", amount)

        expected_unit = entity_spec(self.entity).stock_unit
        if self.unit is not expected_unit:
            fail(
                "LEDGER_UNIT_MISMATCH",
                "unit must equal the entity registry stock unit",
                "unit",
                {"expected": expected_unit.value, "received": self.unit.value},
            )

        carrier_volume = self._optional_number(
            "carrier_volume_l", self.carrier_volume_l, nonnegative=True
        )
        density = self._optional_number(
            "water_density_kg_l", self.water_density_kg_l, positive=True
        )
        requested = self._optional_number(
            "requested_amount", self.requested_amount, nonnegative=True
        )
        applied = self._optional_number(
            "applied_amount", self.applied_amount, nonnegative=True
        )
        cap_fraction = self._optional_number(
            "cap_fraction", self.cap_fraction, nonnegative=True
        )
        if cap_fraction is not None and cap_fraction > 1.0:
            fail(
                "LEDGER_NUMERIC_INVALID",
                "cap_fraction cannot exceed one",
                "cap_fraction",
            )

        if self.entity is ConservedEntity.WATER:
            if carrier_volume is None:
                fail(
                    "LEDGER_WATER_CARRIER_REQUIRED",
                    "water rows require carrier volume",
                    "carrier_volume_l",
                )
            if density is None:
                fail(
                    "LEDGER_WATER_CARRIER_REQUIRED",
                    "water rows require water density",
                    "water_density_kg_l",
                )
            if not isclose(
                abs(amount), carrier_volume * density, rel_tol=1e-12, abs_tol=1e-12
            ):
                fail(
                    "LEDGER_WATER_IDENTITY_MISMATCH",
                    "water amount must equal carrier volume times density",
                    "amount",
                )
        elif carrier_volume is not None or density is not None:
            offending = (
                "carrier_volume_l" if carrier_volume is not None else "water_density_kg_l"
            )
            fail(
                "LEDGER_SOLUTE_CARRIER_FORBIDDEN",
                "non-water rows cannot carry water volume or density metadata",
                offending,
            )

        if (
            self.transfer_mode is MaterialTransferMode.WATER_ONLY
            and self.entity is not ConservedEntity.WATER
        ) or (
            self.transfer_mode is MaterialTransferMode.ENTITY_ONLY
            and self.entity is ConservedEntity.WATER
        ):
            fail(
                "LEDGER_TRANSFER_MODE_MISMATCH",
                "transfer_mode is incompatible with the row entity",
                "transfer_mode",
            )

        if (
            self.kind is LedgerEntryKind.INTERNAL
            and self.boundary_category is not None
        ):
            fail(
                "LEDGER_BOUNDARY_KIND_MISMATCH",
                "internal rows cannot have an external boundary category",
                "boundary_category",
            )
        if (
            self.kind is LedgerEntryKind.EXTERNAL
            and self.internal_flux_kind is not None
        ):
            fail(
                "LEDGER_INTERNAL_FLUX_KIND_MISMATCH",
                "external rows cannot have an internal entity-flux kind",
                "internal_flux_kind",
            )
        if self.internal_flux_kind is not None:
            if self.phase is not OperatorPhase.PLANT_ION_TRANSITIONS:
                fail(
                    "LEDGER_INTERNAL_FLUX_PHASE_MISMATCH",
                    "internal entity fluxes belong to plant_ion_transitions",
                    "phase",
                )
            if (
                self.kind is not LedgerEntryKind.INTERNAL
                or self.transfer_mode is not MaterialTransferMode.ENTITY_ONLY
                or self.entity is ConservedEntity.WATER
            ):
                fail(
                    "LEDGER_INTERNAL_FLUX_KIND_MISMATCH",
                    "internal entity flux metadata requires an ion-only internal row",
                    "internal_flux_kind",
                )

        self._validate_capping(requested, applied, cap_fraction, amount)
        self._validate_adapter()

    def _optional_number(
        self,
        field_path: str,
        value: float | None,
        *,
        nonnegative: bool = False,
        positive: bool = False,
    ) -> float | None:
        if value is None:
            return None
        converted = finite_float(
            value,
            code="LEDGER_NUMERIC_INVALID",
            field_path=field_path,
            nonnegative=nonnegative,
            positive=positive,
        )
        object.__setattr__(self, field_path, converted)
        return converted

    def _validate_capping(
        self,
        requested: float | None,
        applied: float | None,
        cap_fraction: float | None,
        amount: float,
    ) -> None:
        if (requested is None) != (applied is None):
            missing = "requested_amount" if requested is None else "applied_amount"
            fail(
                "LEDGER_CAP_METADATA_INCOMPLETE",
                "requested_amount and applied_amount must be supplied together",
                missing,
            )
        if cap_fraction is not None and (requested is None or applied is None):
            fail(
                "LEDGER_CAP_METADATA_INCOMPLETE",
                "cap_fraction requires requested and applied amounts",
                "cap_fraction",
            )
        if requested is None or applied is None:
            return
        if applied > requested and not isclose(
            applied, requested, rel_tol=1e-12, abs_tol=1e-12
        ):
            fail(
                "LEDGER_APPLIED_EXCEEDS_REQUESTED",
                "applied_amount cannot exceed requested_amount",
                "applied_amount",
            )
        if not isclose(abs(amount), applied, rel_tol=1e-12, abs_tol=1e-12):
            fail(
                "LEDGER_APPLIED_IDENTITY_MISMATCH",
                "absolute row amount must equal applied_amount",
                "applied_amount",
            )
        if cap_fraction is None:
            return
        expected_fraction = 1.0 if requested == 0.0 else applied / requested
        if not isclose(
            cap_fraction, expected_fraction, rel_tol=1e-12, abs_tol=1e-12
        ):
            fail(
                "LEDGER_CAP_IDENTITY_MISMATCH",
                "cap_fraction must equal applied_amount / requested_amount",
                "cap_fraction",
            )

    def _validate_adapter(self) -> None:
        values = (self.adapter_id, self.adapter_version, self.adapter_hash)
        supplied = tuple(value is not None for value in values)
        if any(supplied) and not all(supplied):
            fail(
                "LEDGER_ADAPTER_REFERENCE_INVALID",
                "adapter id, version, and SHA-256 hash are all required",
                "adapter_id",
            )
        if all(supplied):
            _readable_id(
                self.adapter_id,
                code="LEDGER_ADAPTER_REFERENCE_INVALID",
                field_path="adapter_id",
            )
            _readable_id(
                self.adapter_version,
                code="LEDGER_ADAPTER_REFERENCE_INVALID",
                field_path="adapter_version",
            )
            if (
                not isinstance(self.adapter_hash, str)
                or _SHA256_PATTERN.fullmatch(self.adapter_hash) is None
            ):
                fail(
                    "LEDGER_ADAPTER_REFERENCE_INVALID",
                    "adapter_hash must be a lowercase SHA-256 digest",
                    "adapter_hash",
                )
            if self.phase is not OperatorPhase.REACTION_ADAPTERS:
                fail(
                    "LEDGER_ADAPTER_PHASE_MISMATCH",
                    "adapter references belong to reaction_adapters",
                    "phase",
                )
        elif self.phase is OperatorPhase.REACTION_ADAPTERS:
            fail(
                "LEDGER_ADAPTER_REFERENCE_INVALID",
                "reaction adapter rows require a validated adapter reference",
                "adapter_id",
            )
