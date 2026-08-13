"""Density-aware, auditable finite-volume transport for water and solutes.

This kernel is deliberately mechanistic.  It conserves represented quantities,
orders explicitly declared operations, and carries evidence labels; it does not
infer a biological gene effect or turn a hypothesis into calibration evidence.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field, replace
from fractions import Fraction
from math import expm1, fsum, isclose
import re
from types import MappingProxyType
from typing import Final

from almondlab.contracts import (
    CORE_V1_OPERATOR_SCHEDULE,
    CompartmentKind,
    ConservedEntity,
    EvidenceLabel,
    ExternalBoundaryCategory,
    InternalEntityFluxKind,
    InternalWaterFlowKind,
    LedgerCursor,
    LedgerEntry,
    LedgerEntryKind,
    MaterialTransferMode,
    OperatorPhase,
    OperatorSchedule,
    StockUnit,
    entity_spec,
)
from almondlab.errors import AlmondLabError, fail, finite_float
from almondlab.evidence_policy import compose_evidence_labels


NEGATIVE_TOLERANCE: Final[float] = 1e-12
BALANCE_TOLERANCE: Final[float] = 1e-10
MAX_SUBSTEP_HOURS: Final[float] = 0.25
MAX_ADVECTIVE_WITHDRAWAL_FRACTION: Final[float] = 0.10

_READABLE_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}\Z", re.ASCII)
_SHA256 = re.compile(r"[0-9a-f]{64}\Z", re.ASCII)
_TRANSACTION_ID = re.compile(
    r"tx:[A-Za-z0-9][A-Za-z0-9._-]{0,63}:"
    r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}:[0-9]{12}\Z",
    re.ASCII,
)
_REACTION_ALIASES: Final[tuple[str, ...]] = (
    "uptake",
    "efflux",
    "retrieval",
    "sequestration",
    "sorption",
    "exchange",
    "precipitation",
    "dissolution",
    "volatilization",
    "reaction",
)
_INPUT_BOUNDARIES: Final[frozenset[ExternalBoundaryCategory]] = frozenset(
    {
        ExternalBoundaryCategory.SOURCE_FEED,
        ExternalBoundaryCategory.EXTERNAL_MAKEUP,
        ExternalBoundaryCategory.AMENDMENT,
    }
)
_OUTPUT_BOUNDARIES: Final[frozenset[ExternalBoundaryCategory]] = frozenset(
    set(ExternalBoundaryCategory) - set(_INPUT_BOUNDARIES)
)
_ADVECTIVE_WATER_PHASES: Final[frozenset[OperatorPhase]] = frozenset(
    {
        OperatorPhase.TREATMENT_BLENDING,
        OperatorPhase.IRRIGATION,
        OperatorPhase.LAYER_DRAINAGE,
        OperatorPhase.DRAINAGE_CONDENSATE_RETURN,
    }
)
_WATER_KIND_PHASES: Final[Mapping[InternalWaterFlowKind, frozenset[OperatorPhase]]] = (
    MappingProxyType(
        {
            InternalWaterFlowKind.AQUEOUS_TRANSFER: _ADVECTIVE_WATER_PHASES,
            InternalWaterFlowKind.EVAPORATION: frozenset(
                {OperatorPhase.EVAPORATION_TRANSPIRATION}
            ),
            InternalWaterFlowKind.TRANSPIRATION: frozenset(
                {OperatorPhase.EVAPORATION_TRANSPIRATION}
            ),
            InternalWaterFlowKind.CONDENSATE_RETURN: frozenset(
                {OperatorPhase.DRAINAGE_CONDENSATE_RETURN}
            ),
        }
    )
)
_INPUT_PHASES: Final[frozenset[OperatorPhase]] = frozenset(
    {OperatorPhase.EXTERNAL_FEED_AMENDMENT}
)
_OUTPUT_PHASES: Final[frozenset[OperatorPhase]] = frozenset(
    {OperatorPhase.PURGE_DISPOSAL}
)

_MASS_NUMERIC_CODE: Final[str] = "MASS_NUMERIC_INVALID"


def _id(value: object, field_path: str, *, code: str = "IDENTIFIER_INVALID") -> str:
    if not isinstance(value, str) or _READABLE_ID.fullmatch(value) is None:
        fail(code, "identifier must use 1-64 readable ASCII characters", field_path)
    return value


def _enum(value: object, expected: type, field_path: str) -> None:
    if not isinstance(value, expected):
        fail(
            "TYPE_INVALID",
            f"{field_path} must be a {expected.__name__}",
            field_path,
        )


def _nonnegative(value: object, field_path: str, code: str) -> float:
    return finite_float(
        value,
        code=code,
        field_path=field_path,
        nonnegative=True,
    )


def _positive(value: object, field_path: str, code: str) -> float:
    return finite_float(
        value,
        code=code,
        field_path=field_path,
        positive=True,
    )


def _finite_result(
    value: object,
    field_path: str,
    *,
    code: str = _MASS_NUMERIC_CODE,
) -> float:
    """Validate one derived floating-point result at its public quantity path."""

    return finite_float(value, code=code, field_path=field_path)


def _finite_sum(
    values: Iterable[float],
    field_path: str,
    *,
    code: str = _MASS_NUMERIC_CODE,
) -> float:
    """Sum finite quantities without leaking native ``fsum`` failures."""

    try:
        result = fsum(values)
    except (OverflowError, ValueError) as error:
        fail(code, "derived sum must remain finite", field_path, {"cause": type(error).__name__})
    return _finite_result(result, field_path, code=code)


def _finite_product(
    left: float,
    right: float,
    field_path: str,
    *,
    code: str = _MASS_NUMERIC_CODE,
) -> float:
    exact = _exact_fraction(left, field_path, code=code) * _exact_fraction(
        right, field_path, code=code
    )
    return _rounded_fraction(
        exact,
        field_path,
        code=code,
        operation="product",
    )


def _finite_ratio(
    numerator: float,
    denominator: float,
    field_path: str,
    *,
    code: str = _MASS_NUMERIC_CODE,
) -> float:
    if denominator == 0.0:
        fail(code, "derived ratio denominator must be nonzero", field_path)
    exact = _exact_fraction(numerator, field_path, code=code) / _exact_fraction(
        denominator, field_path, code=code
    )
    return _rounded_fraction(
        exact,
        field_path,
        code=code,
        operation="ratio",
    )


def _exact_fraction(
    value: float,
    field_path: str,
    *,
    code: str,
) -> Fraction:
    """Return the exact rational represented by one finite binary64 value."""

    converted = _finite_result(value, field_path, code=code)
    return Fraction.from_float(converted)


def _rounded_fraction(
    exact: Fraction,
    field_path: str,
    *,
    code: str,
    operation: str,
) -> float:
    """Correctly round an exact result and reject overflow or silent underflow."""

    if exact == 0:
        return 0.0
    try:
        result = float(exact)
    except OverflowError as error:
        fail(
            code,
            f"derived {operation} must remain finite",
            field_path,
            {"cause": type(error).__name__},
        )
    if result == 0.0:
        fail(
            code,
            f"derived {operation} must not underflow a nonzero quantity",
            field_path,
        )
    return _finite_result(result, field_path, code=code)


def _exact_multiply_divide(
    left: float,
    right: float,
    denominator: float,
    field_path: str,
    *,
    code: str,
) -> Fraction:
    if denominator == 0.0:
        fail(code, "derived ratio denominator must be nonzero", field_path)
    return (
        _exact_fraction(left, field_path, code=code)
        * _exact_fraction(right, field_path, code=code)
        / _exact_fraction(denominator, field_path, code=code)
    )


def _finite_multiply_divide(
    left: float,
    right: float,
    denominator: float,
    field_path: str,
    *,
    code: str = _MASS_NUMERIC_CODE,
) -> float:
    """Correctly round ``left * right / denominator`` as one exact expression."""

    exact = _exact_multiply_divide(
        left,
        right,
        denominator,
        field_path,
        code=code,
    )
    return _rounded_fraction(
        exact,
        field_path,
        code=code,
        operation="multiply/divide result",
    )


def _finite_multiply_divide_capped(
    left: float,
    right: float,
    denominator: float,
    upper_bound: float,
    field_path: str,
    *,
    code: str = _MASS_NUMERIC_CODE,
) -> float:
    """Return ``min(left * right / denominator, upper_bound)`` exactly.

    Comparing exact rationals before binary64 conversion lets a conservative
    limiter retain its already-safe requested interval when the unconstrained
    safe limit is larger than binary64 can represent.
    """

    exact = _exact_multiply_divide(
        left,
        right,
        denominator,
        field_path,
        code=code,
    )
    exact_upper_bound = _exact_fraction(upper_bound, field_path, code=code)
    if exact >= exact_upper_bound:
        return upper_bound
    return _rounded_fraction(
        exact,
        field_path,
        code=code,
        operation="multiply/divide result",
    )


def _freeze_stocks(
    supplied: object,
    *,
    field_path: str,
    numeric_code: str = "STATE_NUMERIC_INVALID",
) -> Mapping[ConservedEntity, float]:
    if not isinstance(supplied, Mapping):
        fail("STOCK_MAPPING_REQUIRED", "stocks must be a mapping", field_path)
    result: dict[ConservedEntity, float] = {}
    for raw_entity, raw_amount in supplied.items():
        if not isinstance(raw_entity, ConservedEntity):
            fail(
                "ENTITY_TYPE_REQUIRED",
                "stock keys must be ConservedEntity values",
                field_path,
            )
        if raw_entity is ConservedEntity.WATER:
            fail(
                "WATER_STOCK_FORBIDDEN",
                "water is represented by water_mass_kg, not the stock mapping",
                f"{field_path}.water",
            )
        if raw_entity in result:
            fail("DUPLICATE_ENTITY", "entity appears more than once", field_path)
        result[raw_entity] = _nonnegative(
            raw_amount, f"{field_path}.{raw_entity.value}", numeric_code
        )
    return MappingProxyType(result)


def _freeze_compartments(
    supplied: object,
) -> Mapping[str, "CompartmentState"]:
    if not isinstance(supplied, Mapping):
        fail(
            "COMPARTMENT_MAPPING_REQUIRED",
            "compartments must be a mapping",
            "compartments",
        )
    copied: dict[str, CompartmentState] = {}
    for raw_id, compartment in supplied.items():
        compartment_id = _id(raw_id, "compartments.key")
        if not isinstance(compartment, CompartmentState):
            fail(
                "COMPARTMENT_TYPE_REQUIRED",
                "every value must be a CompartmentState",
                f"compartments.{compartment_id}",
            )
        if compartment.compartment_id != compartment_id:
            fail(
                "COMPARTMENT_ID_MISMATCH",
                "mapping key must equal the contained compartment ID",
                f"compartments.{compartment_id}.compartment_id",
            )
        copied[compartment_id] = compartment
    if not copied:
        fail("EMPTY_NETWORK", "at least one compartment is required", "compartments")
    return MappingProxyType(copied)


def _freeze_entity_rates(
    supplied: object, *, field_path: str
) -> Mapping[ConservedEntity, float]:
    if not isinstance(supplied, Mapping):
        fail(
            "ENTITY_RATE_MAPPING_REQUIRED",
            "entity rates must be a mapping",
            field_path,
        )
    rates: dict[ConservedEntity, float] = {}
    for raw_entity, raw_rate in supplied.items():
        if not isinstance(raw_entity, ConservedEntity):
            fail(
                "ENTITY_TYPE_REQUIRED",
                "entity rate keys must be ConservedEntity values",
                field_path,
            )
        if raw_entity is ConservedEntity.WATER:
            fail(
                "WATER_STOCK_FORBIDDEN",
                "water must use the explicit volume and density fields",
                f"{field_path}.water",
            )
        rates[raw_entity] = _nonnegative(
            raw_rate,
            f"{field_path}.{raw_entity.value}",
            "FLOW_NUMERIC_INVALID",
        )
    return MappingProxyType(rates)


@dataclass(frozen=True, slots=True, kw_only=True)
class CompartmentState:
    """One canonical physical compartment with separate volume and water mass."""

    compartment_id: str
    kind: CompartmentKind
    loop_id: str
    volume_l: float
    water_mass_kg: float
    empty_reference_density_kg_l: float
    stocks: Mapping[ConservedEntity, float]
    evidence_label: EvidenceLabel

    def __post_init__(self) -> None:
        _id(self.compartment_id, "compartment_id")
        _id(self.loop_id, "loop_id")
        _enum(self.kind, CompartmentKind, "kind")
        _enum(self.evidence_label, EvidenceLabel, "evidence_label")
        volume = _nonnegative(
            self.volume_l, "volume_l", "STATE_NUMERIC_INVALID"
        )
        water_mass = _nonnegative(
            self.water_mass_kg, "water_mass_kg", "STATE_NUMERIC_INVALID"
        )
        reference_density = _positive(
            self.empty_reference_density_kg_l,
            "empty_reference_density_kg_l",
            "STATE_NUMERIC_INVALID",
        )
        stocks = _freeze_stocks(self.stocks, field_path="stocks")
        if volume == 0.0:
            if water_mass != 0.0:
                fail(
                    "WATER_MASS_WITHOUT_VOLUME",
                    "zero volume requires zero water mass",
                    "water_mass_kg",
                )
            if any(amount != 0.0 for amount in stocks.values()):
                fail(
                    "STOCK_WITHOUT_WATER",
                    "zero volume requires zero dissolved stock",
                    "stocks",
                )
        elif water_mass == 0.0:
            fail(
                "VOLUME_WITHOUT_WATER_MASS",
                "positive volume requires positive water mass",
                "water_mass_kg",
            )
        else:
            _finite_ratio(
                water_mass,
                volume,
                "density_kg_l",
            )
            for entity, amount in stocks.items():
                _finite_ratio(
                    amount,
                    volume,
                    f"stocks.{entity.value}.concentration",
                )
        object.__setattr__(self, "volume_l", volume)
        object.__setattr__(self, "water_mass_kg", water_mass)
        object.__setattr__(self, "empty_reference_density_kg_l", reference_density)
        object.__setattr__(self, "stocks", stocks)

    @property
    def density_kg_l(self) -> float:
        if self.volume_l == 0.0:
            return self.empty_reference_density_kg_l
        return _finite_ratio(
            self.water_mass_kg,
            self.volume_l,
            "density_kg_l",
        )

    def concentration(self, entity: ConservedEntity) -> float:
        _enum(entity, ConservedEntity, "entity")
        if entity is ConservedEntity.WATER:
            fail(
                "WATER_CONCENTRATION_UNDEFINED",
                "water uses mass and density, not a stock concentration",
                "entity",
            )
        if entity not in self.stocks:
            fail(
                "UNREGISTERED_ENTITY",
                "entity is absent from this compartment stock registry",
                "entity",
            )
        if self.volume_l == 0.0:
            return 0.0
        return _finite_ratio(
            self.stocks[entity],
            self.volume_l,
            f"stocks.{entity.value}.concentration",
        )


@dataclass(frozen=True, slots=True, kw_only=True)
class NetworkState:
    """Deeply immutable network state with an exhaustive run entity registry."""

    compartments: Mapping[str, CompartmentState]
    tracked_entities: frozenset[ConservedEntity]
    evidence_label: EvidenceLabel

    def __post_init__(self) -> None:
        compartments = _freeze_compartments(self.compartments)
        if not isinstance(self.tracked_entities, frozenset) or any(
            not isinstance(entity, ConservedEntity)
            for entity in self.tracked_entities
        ):
            fail(
                "ENTITY_REGISTRY_TYPE_INVALID",
                "tracked_entities must be a frozenset of ConservedEntity values",
                "tracked_entities",
            )
        if ConservedEntity.WATER in self.tracked_entities:
            fail(
                "WATER_STOCK_FORBIDDEN",
                "water is implicit in every run and cannot be a tracked stock",
                "tracked_entities",
            )
        _enum(self.evidence_label, EvidenceLabel, "evidence_label")
        for compartment_id, compartment in compartments.items():
            if frozenset(compartment.stocks) != self.tracked_entities:
                fail(
                    "STATE_ENTITY_REGISTRY_MISMATCH",
                    "every compartment must contain exactly the run entity registry",
                    f"compartments.{compartment_id}.stocks",
                    {
                        "expected": sorted(entity.value for entity in self.tracked_entities),
                        "received": sorted(entity.value for entity in compartment.stocks),
                    },
                )
        composed = compose_evidence_labels(
            *(compartment.evidence_label for compartment in compartments.values())
        )
        # An explicitly weaker state claim is allowed; a stronger one is not.
        if compose_evidence_labels(composed, self.evidence_label) is not self.evidence_label:
            fail(
                "STATE_EVIDENCE_MISMATCH",
                "network evidence cannot be stronger than its compartments",
                "evidence_label",
                {
                    "strongest_permitted": composed.value,
                    "received": self.evidence_label.value,
                },
            )
        object.__setattr__(self, "compartments", compartments)
        object.__setattr__(self, "tracked_entities", frozenset(self.tracked_entities))

    def total_volume_l(self) -> float:
        return _finite_sum(
            (item.volume_l for item in self.compartments.values()),
            "total_volume_l",
        )

    def total_water_mass_kg(self) -> float:
        return _finite_sum(
            (item.water_mass_kg for item in self.compartments.values()),
            "total_water_mass_kg",
        )

    def total_stock(self, entity: ConservedEntity) -> float:
        if not isinstance(entity, ConservedEntity) or entity is ConservedEntity.WATER:
            fail("ENTITY_TYPE_REQUIRED", "entity must be a tracked solute", "entity")
        if entity not in self.tracked_entities:
            fail("UNREGISTERED_ENTITY", "entity is not tracked by this run", "entity")
        return _finite_sum(
            (item.stocks[entity] for item in self.compartments.values()),
            f"total_stock.{entity.value}",
        )

    def concentration(self, compartment_id: str, entity: ConservedEntity) -> float:
        if compartment_id not in self.compartments:
            fail(
                "UNKNOWN_COMPARTMENT",
                "compartment is absent from the network",
                "compartment_id",
            )
        if entity not in self.tracked_entities:
            fail("UNREGISTERED_ENTITY", "entity is not tracked by this run", "entity")
        return self.compartments[compartment_id].concentration(entity)

    def all_values(self) -> tuple[float, ...]:
        return tuple(
            value
            for compartment in self.compartments.values()
            for value in (
                compartment.volume_l,
                compartment.water_mass_kg,
                *compartment.stocks.values(),
            )
        )


@dataclass(frozen=True, slots=True, kw_only=True)
class InternalWaterFlow:
    event_id: str
    source: str
    target: str
    rate_l_per_hour: float
    flow_kind: InternalWaterFlowKind
    phase: OperatorPhase
    evidence_label: EvidenceLabel
    physical_transfer_id: str | None = None

    def __post_init__(self) -> None:
        _id(self.event_id, "event_id")
        _id(self.source, "source")
        _id(self.target, "target")
        if self.source == self.target:
            fail("FLOW_ENDPOINT_INVALID", "source and target must differ", "target")
        rate = _positive(
            self.rate_l_per_hour, "rate_l_per_hour", "FLOW_NUMERIC_INVALID"
        )
        _enum(self.flow_kind, InternalWaterFlowKind, "flow_kind")
        _enum(self.phase, OperatorPhase, "phase")
        _enum(self.evidence_label, EvidenceLabel, "evidence_label")
        if self.phase not in _WATER_KIND_PHASES[self.flow_kind]:
            fail(
                "WATER_FLOW_PHASE_MISMATCH",
                "flow kind is incompatible with the declared operator phase",
                "phase",
            )
        if self.physical_transfer_id is not None:
            _id(self.physical_transfer_id, "physical_transfer_id")
        object.__setattr__(self, "rate_l_per_hour", rate)

    @property
    def transfer_mode(self) -> MaterialTransferMode:
        if self.flow_kind is InternalWaterFlowKind.AQUEOUS_TRANSFER:
            return MaterialTransferMode.ADVECTIVE_AQUEOUS
        return MaterialTransferMode.WATER_ONLY


@dataclass(frozen=True, slots=True, kw_only=True)
class ExternalBoundaryFlux:
    event_id: str
    compartment: str
    boundary_id: str
    category: ExternalBoundaryCategory
    material_mode: MaterialTransferMode
    volume_rate_l_per_hour: float
    entity_rates_per_hour: Mapping[ConservedEntity, float]
    current_mixture_advection: bool
    phase: OperatorPhase
    evidence_label: EvidenceLabel
    water_density_kg_l: float | None = None

    def __post_init__(self) -> None:
        _id(self.event_id, "event_id")
        _id(self.compartment, "compartment")
        _id(self.boundary_id, "boundary_id", code="EXTERNAL_BOUNDARY_REQUIRED")
        normalized = re.sub(r"[^a-z0-9]", "", self.boundary_id.lower())
        if any(alias in normalized for alias in _REACTION_ALIASES):
            fail(
                "REACTION_BOUNDARY_ALIAS_FORBIDDEN",
                "external boundary identifiers cannot disguise internal reactions",
                "boundary_id",
            )
        _enum(self.category, ExternalBoundaryCategory, "category")
        _enum(self.material_mode, MaterialTransferMode, "material_mode")
        _enum(self.phase, OperatorPhase, "phase")
        _enum(self.evidence_label, EvidenceLabel, "evidence_label")
        if not isinstance(self.current_mixture_advection, bool):
            fail(
                "BOUNDARY_ADVECTION_FLAG_INVALID",
                "current_mixture_advection must be boolean",
                "current_mixture_advection",
            )
        volume_rate = _nonnegative(
            self.volume_rate_l_per_hour,
            "volume_rate_l_per_hour",
            "FLOW_NUMERIC_INVALID",
        )
        rates = _freeze_entity_rates(
            self.entity_rates_per_hour,
            field_path="entity_rates_per_hour",
        )
        density = None
        if self.water_density_kg_l is not None:
            density = _positive(
                self.water_density_kg_l,
                "water_density_kg_l",
                "FLOW_NUMERIC_INVALID",
            )
        if self.category in _INPUT_BOUNDARIES and self.phase not in _INPUT_PHASES:
            fail(
                "BOUNDARY_PHASE_MISMATCH",
                "input boundaries belong to external_feed_amendment",
                "phase",
            )
        if self.category in _OUTPUT_BOUNDARIES and self.phase not in _OUTPUT_PHASES:
            fail(
                "BOUNDARY_PHASE_MISMATCH",
                "output boundaries belong to purge_disposal",
                "phase",
            )
        if self.material_mode is MaterialTransferMode.ENTITY_ONLY:
            if volume_rate != 0.0 or density is not None or self.current_mixture_advection:
                fail(
                    "BOUNDARY_MODE_MISMATCH",
                    "entity-only boundaries cannot declare water transport",
                    "material_mode",
                )
            if not rates:
                fail(
                    "BOUNDARY_EMPTY_INVENTORY",
                    "entity-only boundaries require at least one entity rate",
                    "entity_rates_per_hour",
                )
        elif self.material_mode is MaterialTransferMode.WATER_ONLY:
            if rates or self.current_mixture_advection:
                fail(
                    "BOUNDARY_MODE_MISMATCH",
                    "water-only boundaries cannot carry dissolved entities",
                    "material_mode",
                )
            if volume_rate <= 0.0:
                fail(
                    "BOUNDARY_WATER_RATE_REQUIRED",
                    "water transport requires a positive magnitude",
                    "volume_rate_l_per_hour",
                )
        else:
            if volume_rate <= 0.0:
                fail(
                    "BOUNDARY_WATER_RATE_REQUIRED",
                    "aqueous transport requires a positive magnitude",
                    "volume_rate_l_per_hour",
                )
        if self.category in _INPUT_BOUNDARIES:
            if (
                self.material_mode is not MaterialTransferMode.ENTITY_ONLY
                and density is None
            ):
                fail(
                    "BOUNDARY_INPUT_DENSITY_REQUIRED",
                    "aqueous and water-only inputs require density",
                    "water_density_kg_l",
                )
            if self.current_mixture_advection:
                fail(
                    "BOUNDARY_CURRENT_MIXTURE_FORBIDDEN",
                    "an external input cannot advect the receiving mixture",
                    "current_mixture_advection",
                )
        else:
            if density is not None:
                fail(
                    "BOUNDARY_OUTPUT_DENSITY_FORBIDDEN",
                    "output density is derived from its owning compartment",
                    "water_density_kg_l",
                )
        object.__setattr__(self, "volume_rate_l_per_hour", volume_rate)
        object.__setattr__(self, "entity_rates_per_hour", rates)
        object.__setattr__(self, "water_density_kg_l", density)

    @property
    def direction(self) -> float:
        return 1.0 if self.category in _INPUT_BOUNDARIES else -1.0


@dataclass(frozen=True, slots=True, kw_only=True)
class InternalEntityFlux:
    event_id: str
    source: str
    target: str
    kind: InternalEntityFluxKind
    entity: ConservedEntity
    rate_per_hour: float
    phase: OperatorPhase
    evidence_label: EvidenceLabel

    def __post_init__(self) -> None:
        _id(self.event_id, "event_id")
        _id(self.source, "source")
        _id(self.target, "target")
        if self.source == self.target:
            fail("FLOW_ENDPOINT_INVALID", "source and target must differ", "target")
        _enum(self.kind, InternalEntityFluxKind, "kind")
        _enum(self.entity, ConservedEntity, "entity")
        if self.entity is ConservedEntity.WATER:
            fail(
                "INTERNAL_ENTITY_WATER_FORBIDDEN",
                "water must move through an InternalWaterFlow",
                "entity",
            )
        rate = _positive(self.rate_per_hour, "rate_per_hour", "FLOW_NUMERIC_INVALID")
        _enum(self.phase, OperatorPhase, "phase")
        if self.phase is not OperatorPhase.PLANT_ION_TRANSITIONS:
            fail(
                "INTERNAL_ENTITY_PHASE_MISMATCH",
                "plant entity transfers belong to plant_ion_transitions",
                "phase",
            )
        _enum(self.evidence_label, EvidenceLabel, "evidence_label")
        object.__setattr__(self, "rate_per_hour", rate)


@dataclass(frozen=True, slots=True, kw_only=True)
class ValidatedAdapterRef:
    adapter_id: str
    version: str
    sha256: str
    domain_id: str

    def __post_init__(self) -> None:
        _id(self.adapter_id, "adapter_id")
        _id(self.version, "version")
        _id(self.domain_id, "domain_id")
        if not isinstance(self.sha256, str) or _SHA256.fullmatch(self.sha256) is None:
            fail(
                "REACTION_ADAPTER_REFERENCE_INVALID",
                "sha256 must be a lowercase SHA-256 digest",
                "sha256",
            )


@dataclass(frozen=True, slots=True, kw_only=True)
class ReactionFlux:
    event_id: str
    source: str
    target: str
    entity: ConservedEntity
    rate_per_hour: float
    adapter: ValidatedAdapterRef
    phase: OperatorPhase
    evidence_label: EvidenceLabel

    def __post_init__(self) -> None:
        _id(self.event_id, "event_id")
        _id(self.source, "source")
        _id(self.target, "target")
        if self.source == self.target:
            fail("FLOW_ENDPOINT_INVALID", "source and target must differ", "target")
        _enum(self.entity, ConservedEntity, "entity")
        if self.entity is ConservedEntity.WATER:
            fail(
                "REACTION_WATER_FORBIDDEN",
                "reaction adapters cannot create or destroy represented water",
                "entity",
            )
        object.__setattr__(
            self,
            "rate_per_hour",
            _positive(self.rate_per_hour, "rate_per_hour", "FLOW_NUMERIC_INVALID"),
        )
        if not isinstance(self.adapter, ValidatedAdapterRef):
            fail(
                "REACTION_ADAPTER_REFERENCE_INVALID",
                "adapter must be a ValidatedAdapterRef",
                "adapter",
            )
        if self.phase is not OperatorPhase.REACTION_ADAPTERS:
            fail(
                "REACTION_PHASE_MISMATCH",
                "reactions belong to reaction_adapters",
                "phase",
            )
        _enum(self.evidence_label, EvidenceLabel, "evidence_label")


@dataclass(frozen=True, slots=True)
class InternalFluxOutcome:
    event_id: str
    source: str
    target: str
    entity: ConservedEntity
    requested_amount: float
    applied_amount: float
    cap_fraction: float
    evidence_label: EvidenceLabel


@dataclass(frozen=True, slots=True)
class StepResult:
    state: NetworkState
    ledger: tuple[LedgerEntry, ...]
    internal_flux_outcomes: tuple[InternalFluxOutcome, ...]
    substeps: int
    next_cursor: LedgerCursor
    evidence_label: EvidenceLabel


@dataclass(frozen=True, slots=True, kw_only=True)
class LedgerTransactionExpectation:
    """Independent literal authority for one expected ledger transaction.

    ``amounts`` contains canonical positive magnitudes, including water mass in
    kg.  Event objects authorize semantics and rates; these literals authorize
    the transaction occurrence, interval, and quantities without consulting
    the observed ledger or simulator output.
    """

    transaction_id: str
    event_id: str
    dt_hours: float
    amounts: Mapping[ConservedEntity, float]

    def __post_init__(self) -> None:
        if (
            not isinstance(self.transaction_id, str)
            or _TRANSACTION_ID.fullmatch(self.transaction_id) is None
        ):
            fail(
                "AUDIT_AUTHORITY_INVALID",
                "transaction_id must be issued by LedgerCursor",
                "transaction_id",
            )
        _id(self.event_id, "event_id", code="AUDIT_AUTHORITY_INVALID")
        interval = _positive(
            self.dt_hours,
            "dt_hours",
            "AUDIT_AUTHORITY_INVALID",
        )
        if not isinstance(self.amounts, Mapping) or not self.amounts:
            fail(
                "AUDIT_AUTHORITY_INVALID",
                "amounts must be a nonempty entity-to-magnitude mapping",
                "amounts",
            )
        amounts: dict[ConservedEntity, float] = {}
        for raw_entity, raw_amount in self.amounts.items():
            if not isinstance(raw_entity, ConservedEntity):
                fail(
                    "AUDIT_AUTHORITY_INVALID",
                    "amount keys must be ConservedEntity values",
                    "amounts",
                )
            amounts[raw_entity] = _nonnegative(
                raw_amount,
                f"amounts.{raw_entity.value}",
                "AUDIT_AUTHORITY_INVALID",
            )
        object.__setattr__(self, "dt_hours", interval)
        object.__setattr__(self, "amounts", MappingProxyType(amounts))


@dataclass(frozen=True, slots=True)
class BalanceAudit:
    residuals: Mapping[ConservedEntity, float]
    relative_residuals: Mapping[ConservedEntity, float]
    quantities: frozenset[ConservedEntity]
    structural_errors: tuple[str, ...]
    compartment_residuals: Mapping[str, Mapping[ConservedEntity, float]]
    relative_compartment_residuals: Mapping[
        str, Mapping[ConservedEntity, float]
    ]
    volume_residual_l: float
    relative_volume_residual: float
    compartment_volume_residuals_l: Mapping[str, float]
    relative_compartment_volume_residuals: Mapping[str, float]

    @property
    def internal_transaction_errors(self) -> tuple[str, ...]:
        return self.structural_errors

    def residual(self, quantity: ConservedEntity) -> float:
        return self.residuals[quantity]

    def relative_residual(self, quantity: ConservedEntity) -> float:
        return self.relative_residuals[quantity]

    def compartment_residual(
        self, compartment: str, quantity: ConservedEntity
    ) -> float:
        return self.compartment_residuals[compartment][quantity]

    def relative_compartment_residual(
        self, compartment: str, quantity: ConservedEntity
    ) -> float:
        return self.relative_compartment_residuals[compartment][quantity]

    @property
    def balanced(self) -> bool:
        return (
            not self.structural_errors
            and self.relative_volume_residual <= BALANCE_TOLERANCE
            and all(
                value <= BALANCE_TOLERANCE
                for value in self.relative_compartment_volume_residuals.values()
            )
            and all(value <= BALANCE_TOLERANCE for value in self.relative_residuals.values())
            and all(
                value <= BALANCE_TOLERANCE
                for compartment in self.relative_compartment_residuals.values()
                for value in compartment.values()
            )
        )


@dataclass(slots=True)
class _MutableCompartment:
    template: CompartmentState
    volume_l: float
    water_mass_kg: float
    stocks: dict[ConservedEntity, float]

    @property
    def density_kg_l(self) -> float:
        if self.volume_l == 0.0:
            return self.template.empty_reference_density_kg_l
        return _finite_ratio(
            self.water_mass_kg,
            self.volume_l,
            f"compartments.{self.template.compartment_id}.density_kg_l",
        )


def _event_tuple(values: object, expected: type, field_path: str) -> tuple:
    if isinstance(values, (str, bytes, Mapping)) or not isinstance(values, Iterable):
        fail("EVENT_COLLECTION_INVALID", "events must be an iterable", field_path)
    result = tuple(values)
    for index, value in enumerate(result):
        if not isinstance(value, expected):
            fail(
                "EVENT_TYPE_INVALID",
                f"event must be a {expected.__name__}",
                f"{field_path}.{index}",
            )
    return result


def _validate_events(
    state: NetworkState,
    water_flows: tuple[InternalWaterFlow, ...],
    boundary_fluxes: tuple[ExternalBoundaryFlux, ...],
    entity_fluxes: tuple[InternalEntityFlux, ...],
    reaction_fluxes: tuple[ReactionFlux, ...],
) -> None:
    compartments = state.compartments
    all_events = (*water_flows, *boundary_fluxes, *entity_fluxes, *reaction_fluxes)
    event_ids = [event.event_id for event in all_events]
    if len(event_ids) != len(set(event_ids)):
        fail("DUPLICATE_EVENT_ID", "event IDs must be unique within a step", "events")

    for index, flow in enumerate(water_flows):
        if flow.source not in compartments or flow.target not in compartments:
            fail(
                "UNKNOWN_COMPARTMENT",
                "water flow references an unknown compartment",
                f"water_flows.{index}",
            )
        if (
            compartments[flow.source].loop_id != compartments[flow.target].loop_id
            and flow.physical_transfer_id is None
        ):
            fail(
                "CROSS_LOOP_TRANSFER",
                "cross-loop water flow requires a physical transfer identifier",
                f"water_flows.{index}.physical_transfer_id",
            )
        if flow.flow_kind in {
            InternalWaterFlowKind.EVAPORATION,
            InternalWaterFlowKind.TRANSPIRATION,
        } and compartments[flow.target].kind is not CompartmentKind.GREENHOUSE_AIR:
            fail(
                "INTERNAL_WATER_ENDPOINT_MISMATCH",
                "evaporation and transpiration must terminate in greenhouse air",
                f"water_flows.{index}.target",
            )
        if (
            flow.flow_kind is InternalWaterFlowKind.CONDENSATE_RETURN
            and compartments[flow.source].kind is not CompartmentKind.CONDENSATE
        ):
            fail(
                "INTERNAL_WATER_ENDPOINT_MISMATCH",
                "condensate return must originate in a condensate compartment",
                f"water_flows.{index}.source",
            )

    for index, flux in enumerate(boundary_fluxes):
        if flux.compartment not in compartments:
            fail(
                "UNKNOWN_COMPARTMENT",
                "boundary flux references an unknown compartment",
                f"boundary_fluxes.{index}.compartment",
            )
        if flux.boundary_id in compartments:
            fail(
                "EXTERNAL_BOUNDARY_NAMESPACE_COLLISION",
                "external boundary IDs must not name an internal compartment",
                f"boundary_fluxes.{index}.boundary_id",
            )
        if set(flux.entity_rates_per_hour) - set(state.tracked_entities):
            fail(
                "UNREGISTERED_ENTITY",
                "boundary flux references an unregistered entity",
                f"boundary_fluxes.{index}.entity_rates_per_hour",
            )
        if (
            flux.category in _INPUT_BOUNDARIES
            and flux.material_mode is not MaterialTransferMode.ENTITY_ONLY
            and flux.water_density_kg_l is None
        ):
            fail(
                "BOUNDARY_INPUT_DENSITY_REQUIRED",
                "aqueous and water-only inputs require density",
                f"boundary_fluxes.{index}.water_density_kg_l",
            )
        if (
            flux.material_mode is MaterialTransferMode.ADVECTIVE_AQUEOUS
            and flux.category in _INPUT_BOUNDARIES
            and set(flux.entity_rates_per_hour) != set(state.tracked_entities)
        ):
            fail(
                "BOUNDARY_ENTITY_REGISTRY_MISMATCH",
                "aqueous input inventory must exactly cover the run registry",
                f"boundary_fluxes.{index}.entity_rates_per_hour",
            )
        if (
            flux.material_mode is MaterialTransferMode.ADVECTIVE_AQUEOUS
            and flux.category in _OUTPUT_BOUNDARIES
            and not flux.current_mixture_advection
        ):
            fail(
                "BOUNDARY_CURRENT_MIXTURE_REQUIRED",
                "aqueous output must explicitly advect the current mixture",
                f"boundary_fluxes.{index}.current_mixture_advection",
            )
        if (
            flux.category in _OUTPUT_BOUNDARIES
            and flux.current_mixture_advection
            and flux.entity_rates_per_hour
        ):
            fail(
                "BOUNDARY_INVENTORY_WITH_ADVECTION",
                "aqueous output inventory is derived from the current mixture",
                f"boundary_fluxes.{index}.entity_rates_per_hour",
            )

    endpoint_rules: Mapping[
        InternalEntityFluxKind,
        tuple[frozenset[CompartmentKind], frozenset[CompartmentKind]],
    ] = {
        InternalEntityFluxKind.PLANT_UPTAKE: (
            frozenset({CompartmentKind.ROOT_ZONE, CompartmentKind.ROOT_APOPLAST}),
            frozenset({CompartmentKind.ROOT_SYMPLAST}),
        ),
        InternalEntityFluxKind.PLANT_EFFLUX: (
            frozenset({CompartmentKind.ROOT_SYMPLAST}),
            frozenset({CompartmentKind.ROOT_ZONE, CompartmentKind.ROOT_APOPLAST}),
        ),
        InternalEntityFluxKind.XYLEM_RETRIEVAL: (
            frozenset({CompartmentKind.XYLEM}),
            frozenset({CompartmentKind.ROOT_SYMPLAST}),
        ),
        InternalEntityFluxKind.SEQUESTRATION: (
            frozenset({CompartmentKind.ROOT_SYMPLAST}),
            frozenset({CompartmentKind.ROOT_VACUOLE}),
        ),
        InternalEntityFluxKind.VACUOLE_RELEASE: (
            frozenset({CompartmentKind.ROOT_VACUOLE}),
            frozenset({CompartmentKind.ROOT_SYMPLAST}),
        ),
        InternalEntityFluxKind.XYLEM_LOADING: (
            frozenset({CompartmentKind.ROOT_SYMPLAST}),
            frozenset({CompartmentKind.XYLEM}),
        ),
        InternalEntityFluxKind.TISSUE_DEPOSITION: (
            frozenset({CompartmentKind.XYLEM}),
            frozenset({CompartmentKind.SHOOT_TISSUE}),
        ),
    }
    for index, flux in enumerate(entity_fluxes):
        if flux.source not in compartments or flux.target not in compartments:
            fail(
                "UNKNOWN_COMPARTMENT",
                "entity flux references an unknown compartment",
                f"entity_fluxes.{index}",
            )
        if flux.entity not in state.tracked_entities:
            fail(
                "UNREGISTERED_ENTITY",
                "entity flux references an unregistered entity",
                f"entity_fluxes.{index}.entity",
            )
        allowed_source, allowed_target = endpoint_rules[flux.kind]
        if (
            compartments[flux.source].kind not in allowed_source
            or compartments[flux.target].kind not in allowed_target
        ):
            fail(
                "INTERNAL_ENTITY_ENDPOINT_MISMATCH",
                "plant transfer kind is incompatible with endpoint kinds",
                f"entity_fluxes.{index}",
            )

    for index, flux in enumerate(reaction_fluxes):
        if flux.source not in compartments or flux.target not in compartments:
            fail(
                "UNKNOWN_COMPARTMENT",
                "reaction references an unknown compartment",
                f"reaction_fluxes.{index}",
            )
        if flux.entity not in state.tracked_entities:
            fail(
                "UNREGISTERED_ENTITY",
                "reaction references an unregistered entity",
                f"reaction_fluxes.{index}.entity",
            )
        fail(
            "REACTION_ADAPTER_DISABLED",
            "core_v1 enables no reaction adapters",
            f"reaction_fluxes.{index}.adapter",
        )


def _event_evidence(
    state: NetworkState,
    water_flows: tuple[InternalWaterFlow, ...],
    boundary_fluxes: tuple[ExternalBoundaryFlux, ...],
    entity_fluxes: tuple[InternalEntityFlux, ...],
    reaction_fluxes: tuple[ReactionFlux, ...],
) -> EvidenceLabel:
    return compose_evidence_labels(
        state.evidence_label,
        *(event.evidence_label for event in (
            *water_flows,
            *boundary_fluxes,
            *entity_fluxes,
            *reaction_fluxes,
        )),
    )


def _copy_state(state: NetworkState) -> dict[str, _MutableCompartment]:
    return {
        compartment_id: _MutableCompartment(
            template=compartment,
            volume_l=compartment.volume_l,
            water_mass_kg=compartment.water_mass_kg,
            stocks=dict(compartment.stocks),
        )
        for compartment_id, compartment in state.compartments.items()
    }


def _freeze_state(
    mutable: Mapping[str, _MutableCompartment],
    tracked_entities: frozenset[ConservedEntity],
    evidence_label: EvidenceLabel,
) -> NetworkState:
    compartments: dict[str, CompartmentState] = {}
    for compartment_id, item in mutable.items():
        volume = (
            0.0
            if -NEGATIVE_TOLERANCE <= item.volume_l < 0.0
            else item.volume_l
        )
        water = (
            0.0
            if -NEGATIVE_TOLERANCE <= item.water_mass_kg < 0.0
            else item.water_mass_kg
        )
        stocks = {
            entity: (
                0.0 if -NEGATIVE_TOLERANCE <= amount < 0.0 else amount
            )
            for entity, amount in item.stocks.items()
        }
        if volume < 0.0 or water < 0.0 or any(amount < 0.0 for amount in stocks.values()):
            fail(
                "NEGATIVE_STATE",
                "an operator phase produced a materially negative state",
                f"compartments.{compartment_id}",
            )
        compartments[compartment_id] = CompartmentState(
            compartment_id=compartment_id,
            kind=item.template.kind,
            loop_id=item.template.loop_id,
            volume_l=volume,
            water_mass_kg=water,
            empty_reference_density_kg_l=item.template.empty_reference_density_kg_l,
            stocks=stocks,
            evidence_label=evidence_label,
        )
    return NetworkState(
        compartments=compartments,
        tracked_entities=tracked_entities,
        evidence_label=evidence_label,
    )


def _substep_limit(
    mutable: Mapping[str, _MutableCompartment],
    water_flows: tuple[InternalWaterFlow, ...],
    boundary_fluxes: tuple[ExternalBoundaryFlux, ...],
    requested: float,
) -> float:
    """Limit withdrawals against each canonical phase's starting inventory."""

    allowed = requested
    prior_net_rate = {compartment_id: 0.0 for compartment_id in mutable}
    for phase in CORE_V1_OPERATOR_SCHEDULE.phases:
        outgoing: dict[str, list[float]] = defaultdict(list)
        phase_net: dict[str, list[float]] = defaultdict(list)
        for flow in water_flows:
            if flow.phase is not phase:
                continue
            outgoing[flow.source].append(flow.rate_l_per_hour)
            phase_net[flow.source].append(-flow.rate_l_per_hour)
            phase_net[flow.target].append(flow.rate_l_per_hour)
        for flux in boundary_fluxes:
            if (
                flux.phase is not phase
                or flux.material_mode is MaterialTransferMode.ENTITY_ONLY
            ):
                continue
            signed_rate = _finite_product(
                flux.direction,
                flux.volume_rate_l_per_hour,
                f"boundary_fluxes.{flux.event_id}.signed_volume_rate_l_per_hour",
            )
            phase_net[flux.compartment].append(signed_rate)
            if signed_rate < 0.0:
                outgoing[flux.compartment].append(-signed_rate)
        for compartment_id, rates in outgoing.items():
            withdrawal_rate = _finite_sum(
                rates,
                f"compartments.{compartment_id}.withdrawal_rate_l_per_hour",
            )
            initial_volume = mutable[compartment_id].volume_l
            earlier_rate = prior_net_rate[compartment_id]
            denominator = _finite_sum(
                (
                    withdrawal_rate,
                    -_finite_product(
                        MAX_ADVECTIVE_WITHDRAWAL_FRACTION,
                        earlier_rate,
                        f"compartments.{compartment_id}.withdrawal_denominator",
                    ),
                ),
                f"compartments.{compartment_id}.withdrawal_denominator",
            )
            if denominator > 0.0:
                allowed = _finite_multiply_divide_capped(
                    MAX_ADVECTIVE_WITHDRAWAL_FRACTION,
                    initial_volume,
                    denominator,
                    allowed,
                    f"compartments.{compartment_id}.substep_hours",
                )
            phase_start = _finite_sum(
                (
                    initial_volume,
                    _finite_product(
                        earlier_rate,
                        allowed,
                        f"compartments.{compartment_id}.phase_start_volume_l",
                    ),
                ),
                f"compartments.{compartment_id}.phase_start_volume_l",
            )
            if phase_start <= NEGATIVE_TOLERANCE and withdrawal_rate > 0.0:
                fail(
                    "FLOW_EXCEEDS_SOURCE",
                    "water withdrawal has no phase-start source volume",
                    f"compartments.{compartment_id}.volume_l",
                )
        for compartment_id, rates in phase_net.items():
            prior_net_rate[compartment_id] = _finite_sum(
                (
                    prior_net_rate[compartment_id],
                    _finite_sum(
                        rates,
                        f"compartments.{compartment_id}.phase_net_rate_l_per_hour",
                    ),
                ),
                f"compartments.{compartment_id}.prior_net_rate_l_per_hour",
            )
    return allowed


def _ledger_water_pair(
    *,
    transaction_id: str,
    event: InternalWaterFlow,
    volume_l: float,
    density_kg_l: float,
    evidence_label: EvidenceLabel,
) -> tuple[LedgerEntry, LedgerEntry]:
    amount = _finite_product(
        volume_l,
        density_kg_l,
        f"water_flows.{event.event_id}.water_mass_kg",
    )
    common = dict(
        transaction_id=transaction_id,
        event_id=event.event_id,
        kind=LedgerEntryKind.INTERNAL,
        phase=event.phase,
        transfer_mode=event.transfer_mode,
        entity=ConservedEntity.WATER,
        unit=StockUnit.KG,
        evidence_label=evidence_label,
        physical_transfer_id=event.physical_transfer_id,
        carrier_volume_l=volume_l,
        water_density_kg_l=density_kg_l,
        internal_water_flow_kind=event.flow_kind,
    )
    return (
        LedgerEntry(
            **common,
            compartment=event.source,
            counterparty=event.target,
            amount=-amount,
        ),
        LedgerEntry(
            **common,
            compartment=event.target,
            counterparty=event.source,
            amount=amount,
        ),
    )


def _apply_water_phase(
    mutable: dict[str, _MutableCompartment],
    events: tuple[InternalWaterFlow, ...],
    dt: float,
    tracked_entities: frozenset[ConservedEntity],
    cursor: LedgerCursor,
    evidence_label: EvidenceLabel,
) -> tuple[list[LedgerEntry], LedgerCursor]:
    if not events:
        return [], cursor
    snapshot = {
        compartment_id: (
            item.volume_l,
            item.water_mass_kg,
            dict(item.stocks),
            item.density_kg_l,
        )
        for compartment_id, item in mutable.items()
    }
    volume_delta = defaultdict(list)
    water_delta = defaultdict(list)
    stock_delta: dict[tuple[str, ConservedEntity], list[float]] = defaultdict(list)
    ledger: list[LedgerEntry] = []
    next_cursor = cursor
    for event in sorted(events, key=lambda item: item.event_id):
        source_volume, _, source_stocks, density = snapshot[event.source]
        requested_volume = _finite_product(
            event.rate_l_per_hour,
            dt,
            f"water_flows.{event.event_id}.requested_volume_l",
        )
        if requested_volume > source_volume + NEGATIVE_TOLERANCE:
            fail(
                "FLOW_EXCEEDS_SOURCE",
                "water flow exceeds phase-start source volume",
                f"water_flows.{event.event_id}",
            )
        transaction_id, next_cursor = next_cursor.issue()
        volume_delta[event.source].append(-requested_volume)
        volume_delta[event.target].append(requested_volume)
        water_amount = _finite_product(
            requested_volume,
            density,
            f"water_flows.{event.event_id}.water_mass_kg",
        )
        water_delta[event.source].append(-water_amount)
        water_delta[event.target].append(water_amount)
        ledger.extend(
            _ledger_water_pair(
                transaction_id=transaction_id,
                event=event,
                volume_l=requested_volume,
                density_kg_l=density,
                evidence_label=evidence_label,
            )
        )
        if event.transfer_mode is MaterialTransferMode.ADVECTIVE_AQUEOUS:
            for entity in sorted(tracked_entities, key=lambda item: item.value):
                amount = (
                    0.0
                    if source_volume == 0.0
                    else _finite_multiply_divide(
                        requested_volume,
                        source_stocks[entity],
                        source_volume,
                        f"water_flows.{event.event_id}.amounts.{entity.value}",
                    )
                )
                stock_delta[(event.source, entity)].append(-amount)
                stock_delta[(event.target, entity)].append(amount)
                common = dict(
                    transaction_id=transaction_id,
                    event_id=event.event_id,
                    kind=LedgerEntryKind.INTERNAL,
                    phase=event.phase,
                    transfer_mode=event.transfer_mode,
                    entity=entity,
                    unit=entity_spec(entity).stock_unit,
                    evidence_label=evidence_label,
                    physical_transfer_id=event.physical_transfer_id,
                )
                ledger.extend(
                    (
                        LedgerEntry(
                            **common,
                            compartment=event.source,
                            counterparty=event.target,
                            amount=-amount,
                        ),
                        LedgerEntry(
                            **common,
                            compartment=event.target,
                            counterparty=event.source,
                            amount=amount,
                        ),
                    )
                )
    for compartment_id, values in volume_delta.items():
        mutable[compartment_id].volume_l = _finite_sum(
            (
                mutable[compartment_id].volume_l,
                _finite_sum(
                    values,
                    f"compartments.{compartment_id}.volume_delta_l",
                ),
            ),
            f"compartments.{compartment_id}.volume_l",
        )
    for compartment_id, values in water_delta.items():
        mutable[compartment_id].water_mass_kg = _finite_sum(
            (
                mutable[compartment_id].water_mass_kg,
                _finite_sum(
                    values,
                    f"compartments.{compartment_id}.water_mass_delta_kg",
                ),
            ),
            f"compartments.{compartment_id}.water_mass_kg",
        )
    for (compartment_id, entity), values in stock_delta.items():
        mutable[compartment_id].stocks[entity] = _finite_sum(
            (
                mutable[compartment_id].stocks[entity],
                _finite_sum(
                    values,
                    f"compartments.{compartment_id}.stocks.{entity.value}.delta",
                ),
            ),
            f"compartments.{compartment_id}.stocks.{entity.value}",
        )
    return ledger, next_cursor


def _apply_boundary_phase(
    mutable: dict[str, _MutableCompartment],
    events: tuple[ExternalBoundaryFlux, ...],
    dt: float,
    tracked_entities: frozenset[ConservedEntity],
    cursor: LedgerCursor,
    evidence_label: EvidenceLabel,
) -> tuple[list[LedgerEntry], LedgerCursor]:
    if not events:
        return [], cursor
    snapshot = {
        compartment_id: (
            item.volume_l,
            item.water_mass_kg,
            dict(item.stocks),
            item.density_kg_l,
        )
        for compartment_id, item in mutable.items()
    }
    volume_delta = defaultdict(list)
    water_delta = defaultdict(list)
    stock_delta: dict[tuple[str, ConservedEntity], list[float]] = defaultdict(list)
    requested_outputs: dict[tuple[str, ConservedEntity], list[float]] = defaultdict(list)
    requested_water: dict[str, list[float]] = defaultdict(list)
    staged: list[
        tuple[
            ExternalBoundaryFlux,
            str,
            float,
            float | None,
            dict[ConservedEntity, float],
        ]
    ] = []
    next_cursor = cursor
    for event in sorted(events, key=lambda item: item.event_id):
        transaction_id, next_cursor = next_cursor.issue()
        direction = event.direction
        source_volume, _, source_stocks, source_density = snapshot[event.compartment]
        volume = _finite_product(
            event.volume_rate_l_per_hour,
            dt,
            f"boundary_fluxes.{event.event_id}.volume_l",
        )
        density: float | None = None
        entity_amounts: dict[ConservedEntity, float] = {}
        if event.material_mode is not MaterialTransferMode.ENTITY_ONLY:
            density = (
                event.water_density_kg_l
                if direction > 0.0
                else source_density
            )
            requested_water[event.compartment].append(
                0.0 if direction > 0.0 else volume
            )
        if event.material_mode is MaterialTransferMode.ADVECTIVE_AQUEOUS and direction < 0.0:
            for entity in tracked_entities:
                amount = (
                    0.0
                    if source_volume == 0.0
                    else _finite_multiply_divide(
                        volume,
                        source_stocks[entity],
                        source_volume,
                        f"boundary_fluxes.{event.event_id}.amounts.{entity.value}",
                    )
                )
                entity_amounts[entity] = amount
                requested_outputs[(event.compartment, entity)].append(amount)
        else:
            for entity, rate in event.entity_rates_per_hour.items():
                amount = _finite_product(
                    rate,
                    dt,
                    f"boundary_fluxes.{event.event_id}.amounts.{entity.value}",
                )
                entity_amounts[entity] = amount
                if direction < 0.0:
                    requested_outputs[(event.compartment, entity)].append(amount)
        staged.append((event, transaction_id, volume, density, entity_amounts))

    for compartment_id, amounts in requested_water.items():
        if _finite_sum(
            amounts,
            f"compartments.{compartment_id}.requested_boundary_volume_l",
        ) > snapshot[compartment_id][0] + NEGATIVE_TOLERANCE:
            fail(
                "BOUNDARY_EXCEEDS_SOURCE",
                "boundary water output exceeds phase-start volume",
                f"compartments.{compartment_id}.volume_l",
            )
    for (compartment_id, entity), amounts in requested_outputs.items():
        if _finite_sum(
            amounts,
            f"compartments.{compartment_id}.requested_boundary_stock.{entity.value}",
        ) > snapshot[compartment_id][2][entity] + NEGATIVE_TOLERANCE:
            fail(
                "BOUNDARY_EXCEEDS_SOURCE",
                "boundary entity output exceeds phase-start stock",
                f"compartments.{compartment_id}.stocks.{entity.value}",
            )

    ledger: list[LedgerEntry] = []
    for event, transaction_id, volume, density, entity_amounts in staged:
        direction = event.direction
        if event.material_mode is not MaterialTransferMode.ENTITY_ONLY:
            if density is None:
                fail(
                    "BOUNDARY_INPUT_DENSITY_REQUIRED",
                    "water ledger construction requires density",
                    f"boundary_fluxes.{event.event_id}.water_density_kg_l",
                )
            water = _finite_product(
                volume,
                density,
                f"boundary_fluxes.{event.event_id}.water_mass_kg",
            )
            volume_delta[event.compartment].append(
                _finite_product(
                    direction,
                    volume,
                    f"boundary_fluxes.{event.event_id}.signed_volume_l",
                )
            )
            water_delta[event.compartment].append(
                _finite_product(
                    direction,
                    water,
                    f"boundary_fluxes.{event.event_id}.signed_water_mass_kg",
                )
            )
            ledger.append(
                LedgerEntry(
                    transaction_id=transaction_id,
                    event_id=event.event_id,
                    kind=LedgerEntryKind.EXTERNAL,
                    phase=event.phase,
                    transfer_mode=event.material_mode,
                    compartment=event.compartment,
                    counterparty=event.boundary_id,
                    entity=ConservedEntity.WATER,
                    amount=_finite_product(
                        direction,
                        water,
                        f"boundary_fluxes.{event.event_id}.signed_water_mass_kg",
                    ),
                    unit=StockUnit.KG,
                    evidence_label=evidence_label,
                    boundary_category=event.category,
                    carrier_volume_l=volume,
                    water_density_kg_l=density,
                )
            )
        for entity in sorted(entity_amounts, key=lambda item: item.value):
            amount = entity_amounts[entity]
            stock_delta[(event.compartment, entity)].append(
                _finite_product(
                    direction,
                    amount,
                    f"boundary_fluxes.{event.event_id}.signed_amounts.{entity.value}",
                )
            )
            ledger.append(
                LedgerEntry(
                    transaction_id=transaction_id,
                    event_id=event.event_id,
                    kind=LedgerEntryKind.EXTERNAL,
                    phase=event.phase,
                    transfer_mode=event.material_mode,
                    compartment=event.compartment,
                    counterparty=event.boundary_id,
                    entity=entity,
                    amount=_finite_product(
                        direction,
                        amount,
                        f"boundary_fluxes.{event.event_id}.signed_amounts.{entity.value}",
                    ),
                    unit=entity_spec(entity).stock_unit,
                    evidence_label=evidence_label,
                    boundary_category=event.category,
                )
            )
    for compartment_id, values in volume_delta.items():
        mutable[compartment_id].volume_l = _finite_sum(
            (
                mutable[compartment_id].volume_l,
                _finite_sum(values, f"compartments.{compartment_id}.volume_delta_l"),
            ),
            f"compartments.{compartment_id}.volume_l",
        )
    for compartment_id, values in water_delta.items():
        mutable[compartment_id].water_mass_kg = _finite_sum(
            (
                mutable[compartment_id].water_mass_kg,
                _finite_sum(values, f"compartments.{compartment_id}.water_mass_delta_kg"),
            ),
            f"compartments.{compartment_id}.water_mass_kg",
        )
    for (compartment_id, entity), values in stock_delta.items():
        mutable[compartment_id].stocks[entity] = _finite_sum(
            (
                mutable[compartment_id].stocks[entity],
                _finite_sum(
                    values,
                    f"compartments.{compartment_id}.stocks.{entity.value}.delta",
                ),
            ),
            f"compartments.{compartment_id}.stocks.{entity.value}",
        )
    return ledger, next_cursor


def _apply_entity_phase(
    mutable: dict[str, _MutableCompartment],
    events: tuple[InternalEntityFlux, ...],
    dt: float,
    cursor: LedgerCursor,
    evidence_label: EvidenceLabel,
) -> tuple[list[LedgerEntry], list[InternalFluxOutcome], LedgerCursor]:
    if not events:
        return [], [], cursor
    snapshot = {
        compartment_id: dict(item.stocks)
        for compartment_id, item in mutable.items()
    }
    demands: dict[
        tuple[str, ConservedEntity], list[tuple[InternalEntityFlux, float]]
    ] = defaultdict(list)
    for event in events:
        demands[(event.source, event.entity)].append(
            (
                event,
                _finite_product(
                    event.rate_per_hour,
                    dt,
                    f"entity_fluxes.{event.event_id}.requested_amount",
                ),
            )
        )
    scales: dict[tuple[str, ConservedEntity], float] = {}
    for key, requests in demands.items():
        available = snapshot[key[0]][key[1]]
        total_requested = _finite_sum(
            (requested for _, requested in requests),
            f"compartments.{key[0]}.requested_stock.{key[1].value}",
        )
        scales[key] = min(
            1.0,
            _finite_ratio(
                available,
                total_requested,
                f"compartments.{key[0]}.cap_fraction.{key[1].value}",
            ),
        )

    stock_delta: dict[tuple[str, ConservedEntity], list[float]] = defaultdict(list)
    ledger: list[LedgerEntry] = []
    outcomes: list[InternalFluxOutcome] = []
    next_cursor = cursor
    for event in sorted(events, key=lambda item: item.event_id):
        requested = _finite_product(
            event.rate_per_hour,
            dt,
            f"entity_fluxes.{event.event_id}.requested_amount",
        )
        cap_fraction = scales[(event.source, event.entity)]
        applied = _finite_product(
            requested,
            cap_fraction,
            f"entity_fluxes.{event.event_id}.applied_amount",
        )
        transaction_id, next_cursor = next_cursor.issue()
        stock_delta[(event.source, event.entity)].append(-applied)
        stock_delta[(event.target, event.entity)].append(applied)
        outcomes.append(
            InternalFluxOutcome(
                event_id=event.event_id,
                source=event.source,
                target=event.target,
                entity=event.entity,
                requested_amount=requested,
                applied_amount=applied,
                cap_fraction=cap_fraction,
                evidence_label=evidence_label,
            )
        )
        common = dict(
            transaction_id=transaction_id,
            event_id=event.event_id,
            kind=LedgerEntryKind.INTERNAL,
            phase=event.phase,
            transfer_mode=MaterialTransferMode.ENTITY_ONLY,
            entity=event.entity,
            unit=entity_spec(event.entity).stock_unit,
            evidence_label=evidence_label,
            internal_flux_kind=event.kind,
            requested_amount=requested,
            applied_amount=applied,
            cap_fraction=cap_fraction,
        )
        ledger.extend(
            (
                LedgerEntry(
                    **common,
                    compartment=event.source,
                    counterparty=event.target,
                    amount=-applied,
                ),
                LedgerEntry(
                    **common,
                    compartment=event.target,
                    counterparty=event.source,
                    amount=applied,
                ),
            )
        )
    for (compartment_id, entity), values in stock_delta.items():
        mutable[compartment_id].stocks[entity] = _finite_sum(
            (
                mutable[compartment_id].stocks[entity],
                _finite_sum(
                    values,
                    f"compartments.{compartment_id}.stocks.{entity.value}.delta",
                ),
            ),
            f"compartments.{compartment_id}.stocks.{entity.value}",
        )
    return ledger, outcomes, next_cursor


def step_state(
    state: NetworkState,
    *,
    dt_hours: float,
    cursor: LedgerCursor,
    water_flows: Iterable[InternalWaterFlow] = (),
    boundary_fluxes: Iterable[ExternalBoundaryFlux] = (),
    entity_fluxes: Iterable[InternalEntityFlux] = (),
    reaction_fluxes: Iterable[ReactionFlux] = (),
    schedule: OperatorSchedule = CORE_V1_OPERATOR_SCHEDULE,
    max_substep_hours: float = MAX_SUBSTEP_HOURS,
) -> StepResult:
    """Advance one immutable state through the exact core-v1 phase schedule."""

    if not isinstance(state, NetworkState):
        fail("STATE_TYPE_REQUIRED", "state must be a NetworkState", "state")
    if not isinstance(cursor, LedgerCursor):
        fail("LEDGER_CURSOR_REQUIRED", "cursor must be a LedgerCursor", "cursor")
    if schedule is not CORE_V1_OPERATOR_SCHEDULE:
        fail(
            "OPERATOR_SCHEDULE_INVALID",
            "mass balance supports only the frozen core_v1 schedule",
            "schedule",
        )
    duration = _nonnegative(dt_hours, "dt_hours", "INVALID_TIMESTEP")
    maximum_step = _positive(
        max_substep_hours, "max_substep_hours", "INVALID_TIMESTEP"
    )
    if maximum_step > MAX_SUBSTEP_HOURS:
        fail(
            "INVALID_TIMESTEP",
            "maximum substep cannot exceed 0.25 hours",
            "max_substep_hours",
        )
    typed_water = _event_tuple(water_flows, InternalWaterFlow, "water_flows")
    typed_boundaries = _event_tuple(
        boundary_fluxes, ExternalBoundaryFlux, "boundary_fluxes"
    )
    typed_entities = _event_tuple(entity_fluxes, InternalEntityFlux, "entity_fluxes")
    typed_reactions = _event_tuple(reaction_fluxes, ReactionFlux, "reaction_fluxes")
    _validate_events(
        state, typed_water, typed_boundaries, typed_entities, typed_reactions
    )
    output_evidence = _event_evidence(
        state, typed_water, typed_boundaries, typed_entities, typed_reactions
    )
    mutable = _copy_state(state)
    ledger: list[LedgerEntry] = []
    outcomes: list[InternalFluxOutcome] = []
    next_cursor = cursor
    elapsed = 0.0
    substeps = 0
    numerical_epsilon = max(
        1e-15,
        _finite_product(1e-14, max(1.0, duration), "dt_hours.epsilon"),
    )
    while elapsed < duration:
        requested = min(
            maximum_step,
            _finite_sum((duration, -elapsed), "dt_hours.remaining"),
        )
        substep = _substep_limit(
            mutable, typed_water, typed_boundaries, requested
        )
        if substep <= numerical_epsilon:
            fail(
                "FLOW_EXCEEDS_SOURCE",
                "requested duration would exhaust a water source",
                "water_flows",
            )
        for phase in schedule.phases:
            boundary_rows, next_cursor = _apply_boundary_phase(
                mutable,
                tuple(event for event in typed_boundaries if event.phase is phase),
                substep,
                state.tracked_entities,
                next_cursor,
                output_evidence,
            )
            ledger.extend(boundary_rows)
            water_rows, next_cursor = _apply_water_phase(
                mutable,
                tuple(event for event in typed_water if event.phase is phase),
                substep,
                state.tracked_entities,
                next_cursor,
                output_evidence,
            )
            ledger.extend(water_rows)
            entity_rows, phase_outcomes, next_cursor = _apply_entity_phase(
                mutable,
                tuple(event for event in typed_entities if event.phase is phase),
                substep,
                next_cursor,
                output_evidence,
            )
            ledger.extend(entity_rows)
            outcomes.extend(phase_outcomes)
        elapsed = _finite_sum((elapsed, substep), "dt_hours.elapsed")
        substeps += 1
        if substeps > 1_000_000:
            fail(
                "FLOW_EXCEEDS_SOURCE",
                "adaptive substepping could not complete the duration",
                "dt_hours",
            )
    result_state = _freeze_state(
        mutable, state.tracked_entities, output_evidence
    )
    return StepResult(
        state=result_state,
        ledger=tuple(ledger),
        internal_flux_outcomes=tuple(outcomes),
        substeps=substeps,
        next_cursor=next_cursor,
        evidence_label=output_evidence,
    )


def _quantity(state: NetworkState, compartment: str, entity: ConservedEntity) -> float:
    if compartment not in state.compartments:
        return 0.0
    item = state.compartments[compartment]
    if entity is ConservedEntity.WATER:
        return item.water_mass_kg
    return item.stocks[entity]


def _relative(
    residual: float,
    *coordinates: float,
    field_path: str,
) -> float:
    return _finite_ratio(
        abs(residual),
        max(*(abs(item) for item in coordinates), 1e-30),
        field_path,
    )


def _freeze_nested(
    values: Mapping[str, Mapping[ConservedEntity, float]],
) -> Mapping[str, Mapping[ConservedEntity, float]]:
    return MappingProxyType(
        {
            outer: MappingProxyType(dict(inner))
            for outer, inner in values.items()
        }
    )


def _audit_transactions(
    before: NetworkState,
    after: NetworkState,
    ledger: tuple[LedgerEntry, ...],
) -> tuple[str, ...]:
    compartments = frozenset((*before.compartments, *after.compartments))
    transactions: dict[str, list[LedgerEntry]] = defaultdict(list)
    errors: list[str] = []
    for index, row in enumerate(ledger):
        if not isinstance(row, LedgerEntry):
            fail(
                "LEDGER_ROW_TYPE_INVALID",
                "every ledger row must be a shared LedgerEntry",
                f"ledger.{index}",
            )
        if row.compartment not in compartments:
            fail(
                "LEDGER_UNKNOWN_COMPARTMENT",
                "ledger owning compartment is absent from both states",
                f"ledger.{index}.compartment",
            )
        if row.kind is LedgerEntryKind.INTERNAL and row.counterparty not in compartments:
            fail(
                "LEDGER_UNKNOWN_COMPARTMENT",
                "internal counterparty is absent from both states",
                f"ledger.{index}.counterparty",
            )
        if row.kind is LedgerEntryKind.EXTERNAL and row.counterparty in compartments:
            errors.append(
                f"{row.transaction_id}: external boundary collides with compartment registry"
            )
        transactions[row.transaction_id].append(row)

    for transaction_id, rows in transactions.items():
        first = rows[0]
        invariant_fields = (
            "event_id",
            "kind",
            "phase",
            "transfer_mode",
            "evidence_label",
            "boundary_category",
            "internal_flux_kind",
            "physical_transfer_id",
            "adapter_id",
            "adapter_version",
            "adapter_hash",
            "treatment_model_id",
            "treatment_model_version",
            "requested_amount",
            "applied_amount",
            "cap_fraction",
        )
        for field_name in invariant_fields:
            if any(getattr(row, field_name) != getattr(first, field_name) for row in rows[1:]):
                errors.append(f"{transaction_id}: inconsistent {field_name}")
        if first.kind is LedgerEntryKind.EXTERNAL:
            if len({row.entity for row in rows}) != len(rows):
                errors.append(f"{transaction_id}: duplicate external entity row")
            if any(
                row.compartment != first.compartment
                or row.counterparty != first.counterparty
                for row in rows
            ):
                errors.append(f"{transaction_id}: inconsistent external endpoints")
            observed_entities = frozenset(row.entity for row in rows)
            if first.transfer_mode is MaterialTransferMode.ADVECTIVE_AQUEOUS:
                expected_entities = frozenset(
                    {ConservedEntity.WATER, *before.tracked_entities}
                )
                if observed_entities != expected_entities:
                    errors.append(
                        f"{transaction_id}: aqueous boundary inventory is incomplete"
                    )
            elif first.transfer_mode is MaterialTransferMode.WATER_ONLY:
                if observed_entities != frozenset({ConservedEntity.WATER}):
                    errors.append(
                        f"{transaction_id}: water-only boundary shape is invalid"
                    )
            elif (
                not observed_entities
                or ConservedEntity.WATER in observed_entities
            ):
                errors.append(
                    f"{transaction_id}: entity-only boundary shape is invalid"
                )
            continue

        grouped: dict[ConservedEntity, list[LedgerEntry]] = defaultdict(list)
        for row in rows:
            grouped[row.entity].append(row)
        if first.transfer_mode is MaterialTransferMode.ADVECTIVE_AQUEOUS:
            expected_entities = frozenset({ConservedEntity.WATER, *before.tracked_entities})
        elif first.transfer_mode is MaterialTransferMode.WATER_ONLY:
            expected_entities = frozenset({ConservedEntity.WATER})
        else:
            expected_entities = frozenset(
                {row.entity for row in rows if row.entity is not ConservedEntity.WATER}
            )
            if len(expected_entities) != 1:
                errors.append(f"{transaction_id}: selective transfer must have one entity")
        if frozenset(grouped) != expected_entities:
            errors.append(f"{transaction_id}: transaction quantity shape mismatch")
        common_direction: tuple[str, str] | None = None
        common_endpoints: frozenset[str] | None = None
        for entity, pair in grouped.items():
            if len(pair) != 2:
                errors.append(f"{transaction_id}:{entity.value}: expected exactly two rows")
                continue
            left, right = pair
            if (
                left.compartment != right.counterparty
                or left.counterparty != right.compartment
                or left.compartment == left.counterparty
            ):
                errors.append(f"{transaction_id}:{entity.value}: endpoints are not reciprocal")
            if not isclose(left.amount, -right.amount, rel_tol=1e-12, abs_tol=1e-12):
                errors.append(f"{transaction_id}:{entity.value}: amounts are not equal/opposite")
            if entity is ConservedEntity.WATER and (
                left.carrier_volume_l != right.carrier_volume_l
                or left.water_density_kg_l != right.water_density_kg_l
                or left.internal_water_flow_kind is not right.internal_water_flow_kind
            ):
                errors.append(
                    f"{transaction_id}:{entity.value}: carrier metadata disagrees"
                )
            direction = None
            if left.amount < 0.0 < right.amount:
                direction = (left.compartment, left.counterparty)
            elif right.amount < 0.0 < left.amount:
                direction = (right.compartment, right.counterparty)
            elif left.amount != 0.0 or right.amount != 0.0:
                errors.append(f"{transaction_id}:{entity.value}: paired signs are invalid")
            endpoints = frozenset((left.compartment, right.compartment))
            if common_endpoints is None:
                common_endpoints = endpoints
            elif endpoints != common_endpoints:
                errors.append(f"{transaction_id}:{entity.value}: endpoints disagree")
            if direction is not None:
                if common_direction is None:
                    common_direction = direction
                elif direction != common_direction:
                    errors.append(f"{transaction_id}:{entity.value}: direction disagrees")
            if (
                first.transfer_mode is not MaterialTransferMode.ENTITY_ONLY
                and before.compartments[left.compartment].loop_id
                != before.compartments[left.counterparty].loop_id
                and not left.physical_transfer_id
            ):
                errors.append(f"{transaction_id}:{entity.value}: cross-loop ID missing")
        if len(rows) != 2 * len(expected_entities):
            errors.append(f"{transaction_id}: row count does not match transfer shape")
    return tuple(errors)


def _audit_event_authority(
    before: NetworkState,
    after: NetworkState,
    ledger: tuple[LedgerEntry, ...],
    expected_events: tuple[
        InternalWaterFlow | ExternalBoundaryFlux | InternalEntityFlux | ReactionFlux,
        ...,
    ] | None,
) -> tuple[str, ...]:
    """Compare ledger metadata with independent caller-supplied event authority."""

    errors: list[str] = []
    if expected_events is None:
        expected_evidence = after.evidence_label
        if (
            compose_evidence_labels(before.evidence_label, after.evidence_label)
            is not after.evidence_label
        ):
            errors.append("after-state evidence is stronger than pre-state authority")
        if any(row.evidence_label is not expected_evidence for row in ledger):
            errors.append("ledger evidence disagrees with after-state evidence")
        return tuple(errors)

    by_id: dict[
        str, InternalWaterFlow | ExternalBoundaryFlux | InternalEntityFlux | ReactionFlux
    ] = {}
    for event in expected_events:
        if event.event_id in by_id:
            fail(
                "DUPLICATE_EVENT_ID",
                "expected event IDs must be unique",
                "expected_events",
            )
        by_id[event.event_id] = event
    _validate_events(
        before,
        tuple(event for event in expected_events if isinstance(event, InternalWaterFlow)),
        tuple(event for event in expected_events if isinstance(event, ExternalBoundaryFlux)),
        tuple(event for event in expected_events if isinstance(event, InternalEntityFlux)),
        tuple(event for event in expected_events if isinstance(event, ReactionFlux)),
    )
    observed_ids = {row.event_id for row in ledger}
    unknown = observed_ids - set(by_id)
    missing = set(by_id) - observed_ids
    if unknown:
        errors.append(f"unknown ledger event IDs: {sorted(unknown)}")
    if missing:
        errors.append(f"expected event IDs absent from ledger: {sorted(missing)}")

    expected_evidence = compose_evidence_labels(
        before.evidence_label,
        *(event.evidence_label for event in expected_events),
    )
    if after.evidence_label is not expected_evidence:
        errors.append("after-state evidence disagrees with event authority")

    transactions: dict[str, list[LedgerEntry]] = defaultdict(list)
    for row in ledger:
        transactions[row.transaction_id].append(row)
    for transaction_id, rows in transactions.items():
        first = rows[0]
        event = by_id.get(first.event_id)
        if event is None:
            continue
        if any(row.evidence_label is not expected_evidence for row in rows):
            errors.append(f"{transaction_id}: evidence disagrees with event authority")
        if isinstance(event, InternalWaterFlow):
            if any(
                row.kind is not LedgerEntryKind.INTERNAL
                or row.phase is not event.phase
                or row.transfer_mode is not event.transfer_mode
                or row.boundary_category is not None
                or row.internal_flux_kind is not None
                or (row.compartment, row.counterparty)
                not in {
                    (event.source, event.target),
                    (event.target, event.source),
                }
                or (row.amount < 0.0 and row.compartment != event.source)
                or (row.amount > 0.0 and row.compartment != event.target)
                or row.physical_transfer_id != event.physical_transfer_id
                or row.requested_amount is not None
                or row.applied_amount is not None
                or row.cap_fraction is not None
                or row.adapter_id is not None
                or row.adapter_version is not None
                or row.adapter_hash is not None
                or row.treatment_model_id is not None
                or row.treatment_model_version is not None
                or (
                    row.entity is ConservedEntity.WATER
                    and (
                        row.carrier_volume_l is None
                        or row.water_density_kg_l is None
                    )
                )
                or (
                    row.entity is not ConservedEntity.WATER
                    and (
                        row.carrier_volume_l is not None
                        or row.water_density_kg_l is not None
                    )
                )
                for row in rows
            ):
                errors.append(
                    f"{transaction_id}: water transaction metadata disagrees with event"
                )
            grouped_rows: dict[ConservedEntity, list[LedgerEntry]] = defaultdict(list)
            for row in rows:
                grouped_rows[row.entity].append(row)
            if any(
                len(pair) != 2
                or (pair[0].compartment, pair[0].counterparty)
                != (event.source, event.target)
                or (pair[1].compartment, pair[1].counterparty)
                != (event.target, event.source)
                for pair in grouped_rows.values()
            ):
                errors.append(
                    f"{transaction_id}: ordered water endpoints disagree with event"
                )
            for row in rows:
                expected_kind = (
                    event.flow_kind if row.entity is ConservedEntity.WATER else None
                )
                if row.internal_water_flow_kind is not expected_kind:
                    errors.append(
                        f"{transaction_id}: water-flow kind disagrees with event"
                    )
        elif isinstance(event, ExternalBoundaryFlux):
            if any(
                row.kind is not LedgerEntryKind.EXTERNAL
                or row.phase is not event.phase
                or row.transfer_mode is not event.material_mode
                or row.compartment != event.compartment
                or row.counterparty != event.boundary_id
                or row.boundary_category is not event.category
                or (row.amount < 0.0 if event.direction > 0.0 else row.amount > 0.0)
                or row.internal_flux_kind is not None
                or row.internal_water_flow_kind is not None
                or row.physical_transfer_id is not None
                or row.requested_amount is not None
                or row.applied_amount is not None
                or row.cap_fraction is not None
                or row.adapter_id is not None
                or row.adapter_version is not None
                or row.adapter_hash is not None
                or row.treatment_model_id is not None
                or row.treatment_model_version is not None
                or (
                    row.entity is ConservedEntity.WATER
                    and (
                        row.carrier_volume_l is None
                        or row.water_density_kg_l is None
                    )
                )
                or (
                    row.entity is not ConservedEntity.WATER
                    and (
                        row.carrier_volume_l is not None
                        or row.water_density_kg_l is not None
                    )
                )
                for row in rows
            ):
                errors.append(
                    f"{transaction_id}: boundary transaction metadata disagrees with event"
                )
        elif isinstance(event, InternalEntityFlux):
            if any(
                row.kind is not LedgerEntryKind.INTERNAL
                or row.phase is not event.phase
                or row.transfer_mode is not MaterialTransferMode.ENTITY_ONLY
                or row.entity is not event.entity
                or row.boundary_category is not None
                or row.internal_flux_kind is not event.kind
                or row.internal_water_flow_kind is not None
                or row.physical_transfer_id is not None
                or row.carrier_volume_l is not None
                or row.water_density_kg_l is not None
                or row.requested_amount is None
                or row.applied_amount is None
                or row.cap_fraction is None
                or row.adapter_id is not None
                or row.adapter_version is not None
                or row.adapter_hash is not None
                or row.treatment_model_id is not None
                or row.treatment_model_version is not None
                or (row.compartment, row.counterparty)
                not in {
                    (event.source, event.target),
                    (event.target, event.source),
                }
                or (row.amount < 0.0 and row.compartment != event.source)
                or (row.amount > 0.0 and row.compartment != event.target)
                for row in rows
            ):
                errors.append(
                    f"{transaction_id}: entity transaction metadata disagrees with event"
                )
            if (
                len(rows) != 2
                or (rows[0].compartment, rows[0].counterparty)
                != (event.source, event.target)
                or (rows[1].compartment, rows[1].counterparty)
                != (event.target, event.source)
            ):
                errors.append(
                    f"{transaction_id}: ordered entity endpoints disagree with event"
                )
        else:
            errors.append(
                f"{transaction_id}: core_v1 cannot contain a reaction transaction"
            )
    return tuple(errors)


def _literal_equal(observed: float, expected: float) -> bool:
    return isclose(observed, expected, rel_tol=1e-12, abs_tol=1e-12)


def _audit_transaction_authority(
    before: NetworkState,
    ledger: tuple[LedgerEntry, ...],
    expected_events: tuple[
        InternalWaterFlow | ExternalBoundaryFlux | InternalEntityFlux | ReactionFlux,
        ...,
    ] | None,
    expected_transactions: tuple[LedgerTransactionExpectation, ...] | None,
) -> tuple[str, ...]:
    """Compare observed rows with caller-owned, literal transaction quantities."""

    if expected_transactions is None:
        return ()
    if expected_events is None:
        fail(
            "AUDIT_AUTHORITY_INVALID",
            "transaction authority requires explicit expected_events authority",
            "expected_transactions",
        )

    errors: list[str] = []
    events = {event.event_id: event for event in expected_events}
    expected_by_id: dict[str, LedgerTransactionExpectation] = {}
    for expectation in expected_transactions:
        if expectation.transaction_id in expected_by_id:
            fail(
                "AUDIT_AUTHORITY_INVALID",
                "expected transaction IDs must be unique",
                "expected_transactions",
            )
        if expectation.event_id not in events:
            fail(
                "AUDIT_AUTHORITY_INVALID",
                "expected transaction references an unauthorized event",
                "expected_transactions.event_id",
            )
        expected_by_id[expectation.transaction_id] = expectation

    observed: dict[str, list[LedgerEntry]] = defaultdict(list)
    observed_order: list[str] = []
    for row in ledger:
        if row.transaction_id not in observed:
            observed_order.append(row.transaction_id)
        observed[row.transaction_id].append(row)
    expected_order = [item.transaction_id for item in expected_transactions]
    unexpected = set(observed) - set(expected_by_id)
    missing = set(expected_by_id) - set(observed)
    if unexpected:
        errors.append(f"unexpected transaction IDs: {sorted(unexpected)}")
    if missing:
        errors.append(f"expected transaction IDs absent from ledger: {sorted(missing)}")
    if observed_order != expected_order:
        errors.append("transaction order disagrees with literal authority")

    for transaction_id, expectation in expected_by_id.items():
        rows = observed.get(transaction_id)
        if not rows:
            continue
        event = events[expectation.event_id]
        if any(row.event_id != expectation.event_id for row in rows):
            errors.append(f"{transaction_id}: event ID disagrees with literal authority")
            continue
        by_entity: dict[ConservedEntity, list[LedgerEntry]] = defaultdict(list)
        for row in rows:
            by_entity[row.entity].append(row)
        if frozenset(by_entity) != frozenset(expectation.amounts):
            errors.append(f"{transaction_id}: entity set disagrees with literal authority")
            continue

        if isinstance(event, (InternalWaterFlow, InternalEntityFlux)):
            for entity, magnitude in expectation.amounts.items():
                pair = by_entity[entity]
                source_rows = [
                    row
                    for row in pair
                    if row.compartment == event.source
                    and row.counterparty == event.target
                ]
                target_rows = [
                    row
                    for row in pair
                    if row.compartment == event.target
                    and row.counterparty == event.source
                ]
                if len(source_rows) != 1 or len(target_rows) != 1:
                    errors.append(
                        f"{transaction_id}:{entity.value}: ordered endpoints "
                        "disagree with literal authority"
                    )
                    continue
                if not _literal_equal(source_rows[0].amount, -magnitude) or not _literal_equal(
                    target_rows[0].amount, magnitude
                ):
                    errors.append(
                        f"{transaction_id}:{entity.value}: amount disagrees with literal authority"
                    )

        if isinstance(event, InternalWaterFlow):
            expected_entities = (
                frozenset({ConservedEntity.WATER, *before.tracked_entities})
                if event.transfer_mode is MaterialTransferMode.ADVECTIVE_AQUEOUS
                else frozenset({ConservedEntity.WATER})
            )
            if frozenset(expectation.amounts) != expected_entities:
                errors.append(f"{transaction_id}: water-event literal inventory is incomplete")
                continue
            carrier = _finite_product(
                event.rate_l_per_hour,
                expectation.dt_hours,
                f"expected_transactions.{transaction_id}.carrier_volume_l",
            )
            water_magnitude = expectation.amounts[ConservedEntity.WATER]
            density = _finite_ratio(
                water_magnitude,
                carrier,
                f"expected_transactions.{transaction_id}.water_density_kg_l",
            )
            if any(
                row.carrier_volume_l is None
                or not _literal_equal(row.carrier_volume_l, carrier)
                or row.water_density_kg_l is None
                or not _literal_equal(row.water_density_kg_l, density)
                for row in by_entity[ConservedEntity.WATER]
            ):
                errors.append(
                    f"{transaction_id}: water carrier disagrees with literal authority"
                )
        elif isinstance(event, InternalEntityFlux):
            if frozenset(expectation.amounts) != frozenset({event.entity}):
                errors.append(f"{transaction_id}: entity-event literal inventory is invalid")
                continue
            requested = _finite_product(
                event.rate_per_hour,
                expectation.dt_hours,
                f"expected_transactions.{transaction_id}.requested_amount",
            )
            applied = expectation.amounts[event.entity]
            cap = _finite_ratio(
                applied,
                requested,
                f"expected_transactions.{transaction_id}.cap_fraction",
            )
            if cap > 1.0 + 1e-12:
                errors.append(f"{transaction_id}: literal applied amount exceeds request")
            if any(
                row.requested_amount is None
                or not _literal_equal(row.requested_amount, requested)
                or row.applied_amount is None
                or not _literal_equal(row.applied_amount, applied)
                or row.cap_fraction is None
                or not _literal_equal(row.cap_fraction, cap)
                for row in rows
            ):
                errors.append(
                    f"{transaction_id}: cap metadata disagrees with literal authority"
                )
        elif isinstance(event, ExternalBoundaryFlux):
            direction = event.direction
            for entity, magnitude in expectation.amounts.items():
                entity_rows = by_entity[entity]
                if len(entity_rows) != 1:
                    errors.append(
                        f"{transaction_id}:{entity.value}: external literal requires one row"
                    )
                    continue
                row = entity_rows[0]
                expected_signed = _finite_product(
                    direction,
                    magnitude,
                    f"expected_transactions.{transaction_id}.amounts.{entity.value}",
                )
                if not _literal_equal(row.amount, expected_signed):
                    errors.append(
                        f"{transaction_id}:{entity.value}: amount disagrees with literal authority"
                    )
            expected_entities = (
                frozenset({ConservedEntity.WATER, *before.tracked_entities})
                if event.material_mode is MaterialTransferMode.ADVECTIVE_AQUEOUS
                else frozenset({ConservedEntity.WATER})
                if event.material_mode is MaterialTransferMode.WATER_ONLY
                else frozenset(event.entity_rates_per_hour)
            )
            if frozenset(expectation.amounts) != expected_entities:
                errors.append(f"{transaction_id}: boundary literal inventory is incomplete")
                continue
            if event.material_mode is not MaterialTransferMode.ENTITY_ONLY:
                carrier = _finite_product(
                    event.volume_rate_l_per_hour,
                    expectation.dt_hours,
                    f"expected_transactions.{transaction_id}.carrier_volume_l",
                )
                water = expectation.amounts[ConservedEntity.WATER]
                density = _finite_ratio(
                    water,
                    carrier,
                    f"expected_transactions.{transaction_id}.water_density_kg_l",
                )
                water_row = by_entity[ConservedEntity.WATER][0]
                if (
                    water_row.carrier_volume_l is None
                    or not _literal_equal(water_row.carrier_volume_l, carrier)
                    or water_row.water_density_kg_l is None
                    or not _literal_equal(water_row.water_density_kg_l, density)
                ):
                    errors.append(
                        f"{transaction_id}: boundary carrier disagrees with literal authority"
                    )
                if event.direction > 0.0 and event.water_density_kg_l is not None:
                    derived_water = _finite_product(
                        carrier,
                        event.water_density_kg_l,
                        f"expected_transactions.{transaction_id}.water_mass_kg",
                    )
                    if not _literal_equal(water, derived_water):
                        errors.append(
                            f"{transaction_id}: boundary water literal disagrees "
                            "with event rate/density"
                        )
            if event.direction > 0.0 or not event.current_mixture_advection:
                for entity, rate in event.entity_rates_per_hour.items():
                    derived = _finite_product(
                        rate,
                        expectation.dt_hours,
                        f"expected_transactions.{transaction_id}.amounts.{entity.value}",
                    )
                    if not _literal_equal(expectation.amounts.get(entity, -1.0), derived):
                        errors.append(
                            f"{transaction_id}:{entity.value}: literal disagrees with event rate"
                        )
        else:
            errors.append(f"{transaction_id}: core_v1 cannot authorize reactions")
    return tuple(errors)


def audit_ledger(
    before: NetworkState,
    after: NetworkState,
    ledger: Iterable[LedgerEntry],
    *,
    expected_events: Iterable[
        InternalWaterFlow | ExternalBoundaryFlux | InternalEntityFlux | ReactionFlux
    ] | None = None,
    expected_transactions: Iterable[LedgerTransactionExpectation] | None = None,
) -> BalanceAudit:
    """Audit water mass, hydraulic volume, solutes, and transaction shapes."""

    if not isinstance(before, NetworkState) or not isinstance(after, NetworkState):
        fail("STATE_TYPE_REQUIRED", "before and after must be NetworkState", "state")
    if frozenset(before.compartments) != frozenset(after.compartments):
        fail(
            "AUDIT_COMPARTMENT_REGISTRY_MISMATCH",
            "before and after compartment registries must match",
            "after.compartments",
        )
    if before.tracked_entities != after.tracked_entities:
        fail(
            "AUDIT_ENTITY_REGISTRY_MISMATCH",
            "before and after registries must match",
            "after.tracked_entities",
        )
    if isinstance(ledger, (str, bytes, Mapping)) or not isinstance(ledger, Iterable):
        fail("LEDGER_COLLECTION_INVALID", "ledger must be iterable", "ledger")
    rows = tuple(ledger)
    typed_expected_events = None
    if expected_events is not None:
        if (
            isinstance(expected_events, (str, bytes, Mapping))
            or not isinstance(expected_events, Iterable)
        ):
            fail(
                "EVENT_COLLECTION_INVALID",
                "expected_events must be an iterable or None",
                "expected_events",
            )
        typed_expected_events = tuple(expected_events)
        for index, event in enumerate(typed_expected_events):
            if not isinstance(
                event,
                (InternalWaterFlow, ExternalBoundaryFlux, InternalEntityFlux, ReactionFlux),
            ):
                fail(
                    "EVENT_TYPE_INVALID",
                    "expected_events contains an unsupported event",
                    f"expected_events.{index}",
                )
    typed_expected_transactions = None
    if expected_transactions is not None:
        if (
            isinstance(expected_transactions, (str, bytes, Mapping))
            or not isinstance(expected_transactions, Iterable)
        ):
            fail(
                "AUDIT_AUTHORITY_INVALID",
                "expected_transactions must be an iterable or None",
                "expected_transactions",
            )
        typed_expected_transactions = tuple(expected_transactions)
        for index, expectation in enumerate(typed_expected_transactions):
            if not isinstance(expectation, LedgerTransactionExpectation):
                fail(
                    "AUDIT_AUTHORITY_INVALID",
                    "expected transaction must be a LedgerTransactionExpectation",
                    f"expected_transactions.{index}",
                )
    quantities = frozenset({ConservedEntity.WATER, *before.tracked_entities})
    compartments = frozenset({*before.compartments, *after.compartments})
    ledger_net = {entity: 0.0 for entity in quantities}
    compartment_net = {
        compartment: {entity: 0.0 for entity in quantities}
        for compartment in compartments
    }
    volume_net = 0.0
    compartment_volume_net = {compartment: 0.0 for compartment in compartments}
    for index, row in enumerate(rows):
        if not isinstance(row, LedgerEntry):
            fail(
                "LEDGER_ROW_TYPE_INVALID",
                "every ledger row must be a shared LedgerEntry",
                f"ledger.{index}",
            )
        if row.entity not in quantities:
            fail(
                "LEDGER_UNKNOWN_QUANTITY",
                "ledger row references an unaudited entity",
                f"ledger.{index}.entity",
            )
        if row.compartment not in compartments:
            fail(
                "LEDGER_UNKNOWN_COMPARTMENT",
                "ledger row references an unknown compartment",
                f"ledger.{index}.compartment",
            )
        ledger_net[row.entity] = _finite_sum(
            (ledger_net[row.entity], row.amount),
            f"audit.ledger.{row.entity.value}",
        )
        compartment_net[row.compartment][row.entity] = _finite_sum(
            (compartment_net[row.compartment][row.entity], row.amount),
            f"audit.compartments.{row.compartment}.{row.entity.value}",
        )
        if row.entity is ConservedEntity.WATER:
            if row.carrier_volume_l is None:
                fail(
                    "LEDGER_WATER_CARRIER_REQUIRED",
                    "water rows require carrier volume",
                    f"ledger.{index}.carrier_volume_l",
                )
            signed_volume = (
                row.carrier_volume_l
                if row.amount > 0.0
                else -row.carrier_volume_l
                if row.amount < 0.0
                else 0.0
            )
            volume_net = _finite_sum(
                (volume_net, signed_volume),
                "audit.ledger.volume_l",
            )
            compartment_volume_net[row.compartment] = _finite_sum(
                (compartment_volume_net[row.compartment], signed_volume),
                f"audit.compartments.{row.compartment}.volume_l",
            )

    residuals: dict[ConservedEntity, float] = {}
    relative: dict[ConservedEntity, float] = {}
    for entity in quantities:
        before_total = (
            before.total_water_mass_kg()
            if entity is ConservedEntity.WATER
            else before.total_stock(entity)
        )
        after_total = (
            after.total_water_mass_kg()
            if entity is ConservedEntity.WATER
            else after.total_stock(entity)
        )
        residual = _finite_sum(
            (after_total, -before_total, -ledger_net[entity]),
            f"audit.residuals.{entity.value}",
        )
        residuals[entity] = residual
        relative[entity] = _relative(
            residual,
            before_total,
            after_total,
            ledger_net[entity],
            field_path=f"audit.relative_residuals.{entity.value}",
        )
    compartment_residuals: dict[str, dict[ConservedEntity, float]] = {}
    relative_compartment: dict[str, dict[ConservedEntity, float]] = {}
    for compartment in compartments:
        compartment_residuals[compartment] = {}
        relative_compartment[compartment] = {}
        for entity in quantities:
            before_amount = _quantity(before, compartment, entity)
            after_amount = _quantity(after, compartment, entity)
            ledger_amount = compartment_net[compartment][entity]
            residual = _finite_sum(
                (after_amount, -before_amount, -ledger_amount),
                f"audit.compartment_residuals.{compartment}.{entity.value}",
            )
            compartment_residuals[compartment][entity] = residual
            relative_compartment[compartment][entity] = _relative(
                residual,
                before_amount,
                after_amount,
                ledger_amount,
                field_path=(
                    f"audit.relative_compartment_residuals."
                    f"{compartment}.{entity.value}"
                ),
            )
    volume_residual = _finite_sum(
        (after.total_volume_l(), -before.total_volume_l(), -volume_net),
        "audit.volume_residual_l",
    )
    relative_volume = _relative(
        volume_residual,
        before.total_volume_l(),
        after.total_volume_l(),
        volume_net,
        field_path="audit.relative_volume_residual",
    )
    compartment_volume_residuals: dict[str, float] = {}
    relative_compartment_volumes: dict[str, float] = {}
    for compartment in compartments:
        before_volume = (
            before.compartments[compartment].volume_l
            if compartment in before.compartments
            else 0.0
        )
        after_volume = (
            after.compartments[compartment].volume_l
            if compartment in after.compartments
            else 0.0
        )
        residual = _finite_sum(
            (
                after_volume,
                -before_volume,
                -compartment_volume_net[compartment],
            ),
            f"audit.compartment_volume_residuals.{compartment}",
        )
        compartment_volume_residuals[compartment] = residual
        relative_compartment_volumes[compartment] = _relative(
            residual,
            before_volume,
            after_volume,
            compartment_volume_net[compartment],
            field_path=f"audit.relative_compartment_volume.{compartment}",
        )
    return BalanceAudit(
        residuals=MappingProxyType(residuals),
        relative_residuals=MappingProxyType(relative),
        quantities=quantities,
        structural_errors=(
            *_audit_transactions(before, after, rows),
            *_audit_event_authority(
                before, after, rows, typed_expected_events
            ),
            *_audit_transaction_authority(
                before,
                rows,
                typed_expected_events,
                typed_expected_transactions,
            ),
        ),
        compartment_residuals=_freeze_nested(compartment_residuals),
        relative_compartment_residuals=_freeze_nested(relative_compartment),
        volume_residual_l=volume_residual,
        relative_volume_residual=relative_volume,
        compartment_volume_residuals_l=MappingProxyType(compartment_volume_residuals),
        relative_compartment_volume_residuals=MappingProxyType(
            relative_compartment_volumes
        ),
    )


def closed_form_tank_concentration(
    c0: float,
    c_in: float,
    m_dot: float,
    volume: float,
    purge: float,
    time: float,
) -> float:
    """Return the hand-derived well-mixed constant-volume concentration."""

    converted = {
        name: finite_float(
            value,
            code="INVALID_ANALYTIC_INPUT",
            field_path=name,
        )
        for name, value in {
            "c0": c0,
            "c_in": c_in,
            "m_dot": m_dot,
            "volume": volume,
            "purge": purge,
            "time": time,
        }.items()
    }
    if converted["volume"] <= 0.0 or converted["purge"] < 0.0 or converted["time"] < 0.0:
        fail(
            "INVALID_ANALYTIC_INPUT",
            "volume must be positive and purge/time nonnegative",
            "closed_form_tank_concentration",
        )
    if converted["time"] == 0.0:
        return converted["c0"]
    if converted["purge"] == 0.0:
        return _finite_sum(
            (
                converted["c0"],
                _finite_multiply_divide(
                    converted["m_dot"],
                    converted["time"],
                    converted["volume"],
                    "closed_form_tank_concentration",
                ),
            ),
            "closed_form_tank_concentration",
        )
    decay_exponent = -_finite_multiply_divide(
        converted["purge"],
        converted["time"],
        converted["volume"],
        "closed_form_tank_concentration",
    )
    transition_fraction = _finite_result(
        -expm1(decay_exponent),
        "closed_form_tank_concentration.transition_fraction",
    )
    inflow_departure = _finite_sum(
        (converted["c_in"], -converted["c0"]),
        "closed_form_tank_concentration",
    )
    inflow_change = _finite_product(
        inflow_departure,
        transition_fraction,
        "closed_form_tank_concentration",
    )
    source_change = _finite_multiply_divide(
        converted["m_dot"],
        transition_fraction,
        converted["purge"],
        "closed_form_tank_concentration",
    )
    return _finite_sum(
        (
            converted["c0"],
            inflow_change,
            source_change,
        ),
        "closed_form_tank_concentration",
    )


__all__ = [
    "BalanceAudit",
    "CompartmentState",
    "ExternalBoundaryFlux",
    "InternalEntityFlux",
    "InternalFluxOutcome",
    "InternalWaterFlow",
    "LedgerEntry",
    "LedgerTransactionExpectation",
    "NetworkState",
    "ReactionFlux",
    "StepResult",
    "ValidatedAdapterRef",
    "audit_ledger",
    "closed_form_tank_concentration",
    "step_state",
]
