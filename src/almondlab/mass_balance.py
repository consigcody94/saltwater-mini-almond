"""Immutable, auditable finite-volume transport for conserved water and solutes."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from math import exp, isclose, isfinite
from types import MappingProxyType

from almondlab.contracts import EvidenceLabel
from almondlab.errors import fail


NEGATIVE_TOLERANCE = 1e-12
BALANCE_TOLERANCE = 1e-10
MAX_SUBSTEP_HOURS = 0.25
MAX_ADVECTIVE_WITHDRAWAL_FRACTION = 0.10


def _finite(value: float, code: str, field_path: str) -> float:
    converted = float(value)
    if not isfinite(converted):
        fail(code, "value must be finite", field_path)
    return converted


def _state_value(value: float, field_path: str) -> float:
    converted = _finite(value, "NONFINITE_STATE", field_path)
    if converted < -NEGATIVE_TOLERANCE:
        fail("NEGATIVE_STATE", "state cannot be negative", field_path)
    return max(0.0, converted)


def _frozen_mapping(values: Mapping[str, float]) -> Mapping[str, float]:
    return MappingProxyType(dict(values))


@dataclass(frozen=True)
class NetworkState:
    """A deeply immutable snapshot with explicit compartment loop membership."""

    volumes_l: Mapping[str, float]
    stocks_mmol: Mapping[str, Mapping[str, float]]
    loop_ids: Mapping[str, str]
    entities: frozenset[str]

    @classmethod
    def from_dict(
        cls,
        volumes_l: Mapping[str, float],
        stocks_mmol: Mapping[str, Mapping[str, float]],
        loop_ids: Mapping[str, str] | None = None,
    ) -> NetworkState:
        compartments = tuple(str(name) for name in volumes_l)
        if not compartments:
            fail("EMPTY_NETWORK", "at least one compartment is required", "volumes_l")
        if set(compartments) != {str(name) for name in stocks_mmol}:
            fail(
                "STATE_COMPARTMENT_MISMATCH",
                "volumes and stocks must name exactly the same compartments",
                "stocks_mmol",
            )

        normalized_loops = (
            {name: "default" for name in compartments}
            if loop_ids is None
            else {str(name): str(loop_id) for name, loop_id in loop_ids.items()}
        )
        if set(normalized_loops) != set(compartments):
            fail(
                "STATE_LOOP_MISMATCH",
                "every compartment requires exactly one loop_id",
                "loop_ids",
            )
        if any(not loop_id.strip() for loop_id in normalized_loops.values()):
            fail("STATE_LOOP_REQUIRED", "loop_id cannot be empty", "loop_ids")

        entities = frozenset(
            str(entity)
            for compartment in compartments
            for entity in stocks_mmol[compartment]
        )
        volumes = {
            compartment: _state_value(
                volumes_l[compartment], f"volumes_l.{compartment}"
            )
            for compartment in compartments
        }
        stocks: dict[str, Mapping[str, float]] = {}
        for compartment in compartments:
            supplied = stocks_mmol[compartment]
            stocks[compartment] = _frozen_mapping(
                {
                    entity: _state_value(
                        supplied.get(entity, 0.0),
                        f"stocks_mmol.{compartment}.{entity}",
                    )
                    for entity in entities
                }
            )

        return cls(
            volumes_l=_frozen_mapping(volumes),
            stocks_mmol=MappingProxyType(stocks),
            loop_ids=MappingProxyType(normalized_loops),
            entities=entities,
        )

    def total_volume(self) -> float:
        return sum(self.volumes_l.values())

    def total_stock(self, entity: str) -> float:
        return sum(stocks.get(entity, 0.0) for stocks in self.stocks_mmol.values())

    def concentration(self, compartment: str, entity: str) -> float:
        volume = self.volumes_l[compartment]
        stock = self.stocks_mmol[compartment].get(entity, 0.0)
        if volume <= 0.0:
            if stock > NEGATIVE_TOLERANCE:
                fail(
                    "STOCK_WITHOUT_WATER",
                    "a nonempty stock has no water volume",
                    f"stocks_mmol.{compartment}.{entity}",
                )
            return 0.0
        return stock / volume

    def all_values(self) -> tuple[float, ...]:
        return tuple(self.volumes_l.values()) + tuple(
            value for stocks in self.stocks_mmol.values() for value in stocks.values()
        )


@dataclass(frozen=True)
class Flow:
    """An internal volumetric transfer that advects source concentrations."""

    source: str
    target: str
    rate_l_per_hour: float
    physical_transfer_id: str | None = None


@dataclass(frozen=True)
class ExternalFlux:
    """A named boundary flux; negative water advects the compartment mixture."""

    compartment: str
    boundary: str
    volume_rate_l_per_hour: float = 0.0
    entity_rates_mmol_per_hour: Mapping[str, float] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "entity_rates_mmol_per_hour",
            _frozen_mapping(
                {
                    str(entity): float(rate)
                    for entity, rate in self.entity_rates_mmol_per_hour.items()
                }
            ),
        )


@dataclass(frozen=True)
class LedgerEntry:
    """One signed compartment row in a transfer transaction."""

    transaction_id: str
    compartment: str
    counterparty: str
    quantity: str
    amount: float
    unit: str
    kind: str
    evidence_label: EvidenceLabel
    physical_transfer_id: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.evidence_label, EvidenceLabel):
            raise TypeError("evidence_label must be an EvidenceLabel")

    @property
    def entity(self) -> str:
        """Compatibility alias for consumers that call the audited item an entity."""
        return self.quantity


@dataclass(frozen=True)
class StepResult:
    state: NetworkState
    ledger: tuple[LedgerEntry, ...]
    substeps: int


@dataclass(frozen=True)
class BalanceAudit:
    residuals: Mapping[str, float]
    relative_residuals: Mapping[str, float]
    quantities: frozenset[str]
    internal_transaction_errors: tuple[str, ...]
    compartment_residuals: Mapping[str, Mapping[str, float]]
    relative_compartment_residuals: Mapping[str, Mapping[str, float]]

    def residual(self, quantity: str) -> float:
        return self.residuals[quantity]

    def relative_residual(self, quantity: str) -> float:
        return self.relative_residuals[quantity]

    def compartment_residual(self, compartment: str, quantity: str) -> float:
        return self.compartment_residuals[compartment][quantity]

    def relative_compartment_residual(
        self, compartment: str, quantity: str
    ) -> float:
        return self.relative_compartment_residuals[compartment][quantity]

    @property
    def balanced(self) -> bool:
        return (
            not self.internal_transaction_errors
            and all(
                value <= BALANCE_TOLERANCE
                for value in self.relative_residuals.values()
            )
            and all(
                value <= BALANCE_TOLERANCE
                for compartment in self.relative_compartment_residuals.values()
                for value in compartment.values()
            )
        )


def _validate_events(
    state: NetworkState, flows: Iterable[Flow], external: Iterable[ExternalFlux]
) -> None:
    compartments = set(state.volumes_l)
    for index, flow in enumerate(flows):
        if flow.source not in compartments or flow.target not in compartments:
            fail(
                "UNKNOWN_COMPARTMENT",
                "internal flow references an unknown compartment",
                f"flows.{index}",
            )
        rate = _finite(flow.rate_l_per_hour, "NONFINITE_FLOW", f"flows.{index}.rate")
        if rate < 0.0:
            fail("NEGATIVE_FLOW", "internal flow rate cannot be negative", f"flows.{index}.rate")
        if state.loop_ids[flow.source] != state.loop_ids[flow.target] and not (
            flow.physical_transfer_id and flow.physical_transfer_id.strip()
        ):
            fail(
                "CROSS_LOOP_TRANSFER",
                "cross-loop flow requires a physical_transfer_id",
                f"flows.{index}.physical_transfer_id",
            )
    for index, flux in enumerate(external):
        if flux.compartment not in compartments:
            fail(
                "UNKNOWN_COMPARTMENT",
                "external flux references an unknown compartment",
                f"external.{index}.compartment",
            )
        if not flux.boundary.strip():
            fail(
                "EXTERNAL_BOUNDARY_REQUIRED",
                "external flux must name its boundary source or sink",
                f"external.{index}.boundary",
            )
        _finite(
            flux.volume_rate_l_per_hour,
            "NONFINITE_FLOW",
            f"external.{index}.volume_rate_l_per_hour",
        )
        unknown = set(flux.entity_rates_mmol_per_hour) - state.entities
        if unknown:
            fail(
                "UNREGISTERED_ENTITY",
                "external flux references an unregistered conserved entity",
                f"external.{index}.entity_rates_mmol_per_hour",
                {"entities": sorted(unknown)},
            )
        for entity, rate in flux.entity_rates_mmol_per_hour.items():
            _finite(
                rate,
                "NONFINITE_FLOW",
                f"external.{index}.entity_rates_mmol_per_hour.{entity}",
            )


def _derivatives(
    volumes: Mapping[str, float],
    stocks: Mapping[str, Mapping[str, float]],
    entities: frozenset[str],
    flows: list[Flow],
    external: list[ExternalFlux],
) -> tuple[dict[str, float], dict[str, dict[str, float]], dict[tuple[str, int, str], float]]:
    dv = {compartment: 0.0 for compartment in volumes}
    ds = {
        compartment: {entity: 0.0 for entity in entities}
        for compartment in volumes
    }
    movements: dict[tuple[str, int, str], float] = {}

    def concentration(compartment: str, entity: str) -> float:
        volume = volumes[compartment]
        stock = stocks[compartment][entity]
        if volume <= 0.0:
            if stock > NEGATIVE_TOLERANCE:
                fail(
                    "STOCK_WITHOUT_WATER",
                    "advective source has stock but no water",
                    f"stocks_mmol.{compartment}.{entity}",
                )
            return 0.0
        return stock / volume

    for index, flow in enumerate(flows):
        rate = float(flow.rate_l_per_hour)
        dv[flow.source] -= rate
        dv[flow.target] += rate
        movements[("internal", index, "water")] = rate
        for entity in entities:
            entity_rate = rate * concentration(flow.source, entity)
            ds[flow.source][entity] -= entity_rate
            ds[flow.target][entity] += entity_rate
            movements[("internal", index, entity)] = entity_rate

    for index, flux in enumerate(external):
        water_rate = float(flux.volume_rate_l_per_hour)
        dv[flux.compartment] += water_rate
        movements[("external", index, "water")] = abs(water_rate)
        if water_rate < 0.0:
            for entity in entities:
                entity_rate = -water_rate * concentration(flux.compartment, entity)
                ds[flux.compartment][entity] -= entity_rate
                movements[("external-advective", index, entity)] = entity_rate
        for entity, rate in flux.entity_rates_mmol_per_hour.items():
            if rate > 0.0:
                ds[flux.compartment][entity] += rate
                movements[("external-source", index, entity)] = rate
    return dv, ds, movements


def _stage(
    base_volumes: Mapping[str, float],
    base_stocks: Mapping[str, Mapping[str, float]],
    dv: Mapping[str, float],
    ds: Mapping[str, Mapping[str, float]],
    scale: float,
) -> tuple[dict[str, float], dict[str, dict[str, float]]]:
    volumes = {
        compartment: base_volumes[compartment] + scale * dv[compartment]
        for compartment in base_volumes
    }
    stocks = {
        compartment: {
            entity: base_stocks[compartment][entity] + scale * ds[compartment][entity]
            for entity in base_stocks[compartment]
        }
        for compartment in base_stocks
    }
    if any(value < -NEGATIVE_TOLERANCE for value in volumes.values()) or any(
        value < -NEGATIVE_TOLERANCE
        for compartment_stocks in stocks.values()
        for value in compartment_stocks.values()
    ):
        fail(
            "NEGATIVE_STATE",
            "a numerical stage fell below the state tolerance",
            "step_state",
        )
    return volumes, stocks


def _rk4_substep(
    volumes: dict[str, float],
    stocks: dict[str, dict[str, float]],
    entities: frozenset[str],
    flows: list[Flow],
    external: list[ExternalFlux],
    dt: float,
) -> tuple[dict[tuple[str, int, str], float], list[tuple[int, str, float]]]:
    k1v, k1s, movement1 = _derivatives(volumes, stocks, entities, flows, external)
    stage2v, stage2s = _stage(volumes, stocks, k1v, k1s, dt / 2.0)
    k2v, k2s, movement2 = _derivatives(stage2v, stage2s, entities, flows, external)
    stage3v, stage3s = _stage(volumes, stocks, k2v, k2s, dt / 2.0)
    k3v, k3s, movement3 = _derivatives(stage3v, stage3s, entities, flows, external)
    stage4v, stage4s = _stage(volumes, stocks, k3v, k3s, dt)
    k4v, k4s, movement4 = _derivatives(stage4v, stage4s, entities, flows, external)

    for compartment in volumes:
        volumes[compartment] += dt * (
            k1v[compartment]
            + 2.0 * k2v[compartment]
            + 2.0 * k3v[compartment]
            + k4v[compartment]
        ) / 6.0
        for entity in entities:
            stocks[compartment][entity] += dt * (
                k1s[compartment][entity]
                + 2.0 * k2s[compartment][entity]
                + 2.0 * k3s[compartment][entity]
                + k4s[compartment][entity]
            ) / 6.0

    movement_amounts = {
        key: dt
        * (
            movement1.get(key, 0.0)
            + 2.0 * movement2.get(key, 0.0)
            + 2.0 * movement3.get(key, 0.0)
            + movement4.get(key, 0.0)
        )
        / 6.0
        for key in movement1.keys() | movement2.keys() | movement3.keys() | movement4.keys()
    }

    capped_sinks: list[tuple[int, str, float]] = []
    for index, flux in enumerate(external):
        for entity, rate in flux.entity_rates_mmol_per_hour.items():
            if rate < 0.0:
                requested = -rate * dt
                removed = min(requested, max(0.0, stocks[flux.compartment][entity]))
                stocks[flux.compartment][entity] -= removed
                capped_sinks.append((index, entity, removed))
    return movement_amounts, capped_sinks


def _substep_limit(
    volumes: Mapping[str, float],
    flows: list[Flow],
    external: list[ExternalFlux],
    requested: float,
) -> float:
    withdrawals = {compartment: 0.0 for compartment in volumes}
    for flow in flows:
        withdrawals[flow.source] += float(flow.rate_l_per_hour)
    for flux in external:
        if flux.volume_rate_l_per_hour < 0.0:
            withdrawals[flux.compartment] -= float(flux.volume_rate_l_per_hour)

    allowed = requested
    for compartment, rate in withdrawals.items():
        if rate == 0.0:
            continue
        volume = volumes[compartment]
        if volume <= NEGATIVE_TOLERANCE:
            fail(
                "FLOW_EXCEEDS_SOURCE",
                "advective withdrawal has no source water",
                f"volumes_l.{compartment}",
            )
        allowed = min(
            allowed,
            MAX_ADVECTIVE_WITHDRAWAL_FRACTION * volume / rate,
        )
    return allowed


def _append_ledger(
    ledger: list[LedgerEntry],
    step_number: int,
    movement_amounts: Mapping[tuple[str, int, str], float],
    capped_sinks: list[tuple[int, str, float]],
    flows: list[Flow],
    external: list[ExternalFlux],
) -> None:
    for index, flow in enumerate(flows):
        transaction_id = f"internal:{step_number}:{index}"
        quantities = sorted(
            quantity
            for kind, event_index, quantity in movement_amounts
            if kind == "internal" and event_index == index
        )
        for quantity in quantities:
            amount = movement_amounts[("internal", index, quantity)]
            unit = "L" if quantity == "water" else "mmol"
            ledger.extend(
                (
                    LedgerEntry(
                        transaction_id,
                        flow.source,
                        flow.target,
                        quantity,
                        -amount,
                        unit,
                        "internal",
                        EvidenceLabel.PHYSICS_CONSTRAINED,
                        flow.physical_transfer_id,
                    ),
                    LedgerEntry(
                        transaction_id,
                        flow.target,
                        flow.source,
                        quantity,
                        amount,
                        unit,
                        "internal",
                        EvidenceLabel.PHYSICS_CONSTRAINED,
                        flow.physical_transfer_id,
                    ),
                )
            )

    for index, flux in enumerate(external):
        transaction_id = f"external:{step_number}:{index}"
        water_rate = float(flux.volume_rate_l_per_hour)
        if water_rate != 0.0:
            amount = movement_amounts[("external", index, "water")]
            ledger.append(
                LedgerEntry(
                    transaction_id,
                    flux.compartment,
                    flux.boundary,
                    "water",
                    amount if water_rate > 0.0 else -amount,
                    "L",
                    "external",
                    EvidenceLabel.PHYSICS_CONSTRAINED,
                )
            )
        for key_kind, sign in (("external-advective", -1.0), ("external-source", 1.0)):
            quantities = sorted(
                quantity
                for kind, event_index, quantity in movement_amounts
                if kind == key_kind and event_index == index
            )
            for quantity in quantities:
                ledger.append(
                    LedgerEntry(
                        transaction_id,
                        flux.compartment,
                        flux.boundary,
                        quantity,
                        sign * movement_amounts[(key_kind, index, quantity)],
                        "mmol",
                        "external",
                        EvidenceLabel.PHYSICS_CONSTRAINED,
                    )
                )
    for index, entity, amount in capped_sinks:
        flux = external[index]
        ledger.append(
            LedgerEntry(
                f"external:{step_number}:{index}",
                flux.compartment,
                flux.boundary,
                entity,
                -amount,
                "mmol",
                "external",
                EvidenceLabel.PHYSICS_CONSTRAINED,
            )
        )


def step_state(
    state: NetworkState,
    flows: list[Flow],
    external: list[ExternalFlux],
    dt_hours: float,
    *,
    max_substep_hours: float = MAX_SUBSTEP_HOURS,
) -> StepResult:
    """Advance state with RK4 finite-volume fluxes and an atomic ledger."""
    duration = _finite(dt_hours, "INVALID_TIMESTEP", "dt_hours")
    maximum_step = _finite(
        max_substep_hours, "INVALID_TIMESTEP", "max_substep_hours"
    )
    if duration < 0.0 or maximum_step <= 0.0 or maximum_step > MAX_SUBSTEP_HOURS:
        fail(
            "INVALID_TIMESTEP",
            "duration must be nonnegative and maximum substep in (0, 0.25] hours",
            "dt_hours",
        )
    flow_events = list(flows)
    external_events = list(external)
    _validate_events(state, flow_events, external_events)

    volumes = dict(state.volumes_l)
    stocks = {
        compartment: dict(compartment_stocks)
        for compartment, compartment_stocks in state.stocks_mmol.items()
    }
    ledger: list[LedgerEntry] = []
    elapsed = 0.0
    substeps = 0
    while elapsed < duration:
        remaining = duration - elapsed
        requested = min(maximum_step, remaining)
        substep = _substep_limit(volumes, flow_events, external_events, requested)
        if substep <= max(1e-15, 1e-14 * max(1.0, duration)):
            fail(
                "FLOW_EXCEEDS_SOURCE",
                "requested flow would exhaust its source; flow was not clipped",
                "flows",
            )
        movement_amounts, capped_sinks = _rk4_substep(
            volumes,
            stocks,
            state.entities,
            flow_events,
            external_events,
            substep,
        )
        substeps += 1
        _append_ledger(
            ledger,
            substeps,
            movement_amounts,
            capped_sinks,
            flow_events,
            external_events,
        )
        elapsed += substep
        if substeps > 1_000_000:
            fail(
                "FLOW_EXCEEDS_SOURCE",
                "adaptive subdivision could not complete without exhausting a source",
                "flows",
            )

    result_state = NetworkState.from_dict(volumes, stocks, state.loop_ids)
    return StepResult(result_state, tuple(ledger), substeps)


def audit_ledger(
    before: NetworkState,
    after: NetworkState,
    ledger: list[LedgerEntry] | tuple[LedgerEntry, ...],
) -> BalanceAudit:
    """Audit every quantity globally and within each physical compartment."""
    quantities = frozenset({"water", *before.entities, *after.entities})
    compartments = frozenset({*before.volumes_l, *after.volumes_l})
    loop_ids = {**before.loop_ids, **after.loop_ids}
    ledger_net = {quantity: 0.0 for quantity in quantities}
    compartment_ledger_net = {
        compartment: {quantity: 0.0 for quantity in quantities}
        for compartment in compartments
    }
    for index, row in enumerate(ledger):
        if row.quantity not in quantities:
            fail(
                "LEDGER_UNKNOWN_QUANTITY",
                "ledger row references an unaudited quantity",
                f"ledger.{index}.quantity",
            )
        if not isfinite(row.amount):
            fail(
                "NONFINITE_LEDGER",
                "ledger amount must be finite",
                f"ledger.{index}.amount",
            )
        if row.compartment not in compartments:
            fail(
                "LEDGER_UNKNOWN_COMPARTMENT",
                "ledger row names an owning compartment absent from both states",
                f"ledger.{index}.compartment",
            )
        if row.kind == "internal" and row.counterparty not in compartments:
            fail(
                "LEDGER_UNKNOWN_COMPARTMENT",
                "internal ledger row names an endpoint absent from both states",
                f"ledger.{index}.counterparty",
            )
        ledger_net[row.quantity] += row.amount
        compartment_ledger_net[row.compartment][row.quantity] += row.amount

    transaction_errors = _audit_internal_transactions(
        loop_ids, ledger, quantities
    )

    residuals: dict[str, float] = {}
    relative: dict[str, float] = {}
    for quantity in quantities:
        before_total = (
            before.total_volume() if quantity == "water" else before.total_stock(quantity)
        )
        after_total = (
            after.total_volume() if quantity == "water" else after.total_stock(quantity)
        )
        residual = after_total - before_total - ledger_net[quantity]
        scale = max(abs(before_total), abs(after_total), abs(ledger_net[quantity]), 1e-30)
        residuals[quantity] = residual
        relative[quantity] = abs(residual) / scale

    compartment_residuals: dict[str, dict[str, float]] = {}
    relative_compartment_residuals: dict[str, dict[str, float]] = {}
    for compartment in compartments:
        compartment_residuals[compartment] = {}
        relative_compartment_residuals[compartment] = {}
        for quantity in quantities:
            before_amount = _compartment_quantity(before, compartment, quantity)
            after_amount = _compartment_quantity(after, compartment, quantity)
            ledger_amount = compartment_ledger_net[compartment][quantity]
            residual = after_amount - before_amount - ledger_amount
            scale = max(
                abs(before_amount),
                abs(after_amount),
                abs(ledger_amount),
                1e-30,
            )
            compartment_residuals[compartment][quantity] = residual
            relative_compartment_residuals[compartment][quantity] = (
                abs(residual) / scale
            )

    return BalanceAudit(
        residuals=MappingProxyType(residuals),
        relative_residuals=MappingProxyType(relative),
        quantities=quantities,
        internal_transaction_errors=transaction_errors,
        compartment_residuals=_freeze_nested(compartment_residuals),
        relative_compartment_residuals=_freeze_nested(
            relative_compartment_residuals
        ),
    )


def _compartment_quantity(
    state: NetworkState, compartment: str, quantity: str
) -> float:
    if compartment not in state.volumes_l:
        return 0.0
    if quantity == "water":
        return state.volumes_l[compartment]
    return state.stocks_mmol[compartment].get(quantity, 0.0)


def _freeze_nested(
    values: Mapping[str, Mapping[str, float]],
) -> Mapping[str, Mapping[str, float]]:
    return MappingProxyType(
        {
            outer_key: MappingProxyType(dict(inner_values))
            for outer_key, inner_values in values.items()
        }
    )


def _audit_internal_transactions(
    loop_ids: Mapping[str, str],
    ledger: list[LedgerEntry] | tuple[LedgerEntry, ...],
    quantities: frozenset[str],
) -> tuple[str, ...]:
    """Return structural defects in otherwise globally net-zero transfers."""
    transactions: dict[str, list[LedgerEntry]] = {}
    for row in ledger:
        if row.kind == "internal":
            transactions.setdefault(row.transaction_id, []).append(row)

    errors: list[str] = []
    for transaction_id, rows in transactions.items():
        transfer_ids: set[str | None] = set()
        observed_quantities = {row.quantity for row in rows}
        if observed_quantities != quantities:
            errors.append(f"{transaction_id}: quantities do not match network registry")

        water_pair = [row for row in rows if row.quantity == "water"]
        water_direction = (
            _signed_pair_direction(*water_pair)
            if len(water_pair) == 2
            else None
        )
        water_endpoints = (
            frozenset(row.compartment for row in water_pair)
            if len(water_pair) == 2
            else None
        )
        for quantity in quantities:
            pair = [row for row in rows if row.quantity == quantity]
            if len(pair) != 2:
                errors.append(
                    f"{transaction_id}:{quantity}: expected exactly two paired rows"
                )
                continue
            first, second = pair
            expected_unit = "L" if quantity == "water" else "mmol"
            if first.unit != expected_unit or second.unit != expected_unit:
                errors.append(f"{transaction_id}:{quantity}: unit mismatch")
            if (
                first.compartment != second.counterparty
                or first.counterparty != second.compartment
                or first.compartment == first.counterparty
            ):
                errors.append(f"{transaction_id}:{quantity}: counterparties are not reciprocal")
            if not isclose(
                first.amount,
                -second.amount,
                rel_tol=1e-12,
                abs_tol=1e-12,
            ):
                errors.append(f"{transaction_id}:{quantity}: amounts are not equal and opposite")
            if first.amount * second.amount > 0.0:
                errors.append(f"{transaction_id}:{quantity}: rows have the same sign")
            if first.physical_transfer_id != second.physical_transfer_id:
                errors.append(f"{transaction_id}:{quantity}: transfer metadata mismatch")
            transfer_ids.update(
                (first.physical_transfer_id, second.physical_transfer_id)
            )
            pair_direction = _signed_pair_direction(first, second)
            pair_endpoints = frozenset((first.compartment, second.compartment))
            if water_endpoints is not None and pair_endpoints != water_endpoints:
                errors.append(
                    f"{transaction_id}:{quantity}: endpoints disagree with water pair"
                )
            if (
                quantity != "water"
                and pair_direction is not None
                and water_direction is not None
                and pair_direction != water_direction
            ):
                errors.append(
                    f"{transaction_id}:{quantity}: direction disagrees with water pair"
                )
            if (
                loop_ids[first.compartment] != loop_ids[first.counterparty]
                and not (
                    first.physical_transfer_id
                    and first.physical_transfer_id.strip()
                )
            ):
                errors.append(
                    f"{transaction_id}:{quantity}: cross-loop pair lacks physical transfer ID"
                )
        if len(transfer_ids) > 1:
            errors.append(f"{transaction_id}: quantity pairs disagree on transfer metadata")
    return tuple(errors)


def _signed_pair_direction(
    first: LedgerEntry, second: LedgerEntry
) -> tuple[str, str] | None:
    if first.amount < 0.0 < second.amount:
        return first.compartment, first.counterparty
    if second.amount < 0.0 < first.amount:
        return second.compartment, second.counterparty
    return None


def closed_form_tank_concentration(
    c0: float,
    c_in: float,
    m_dot: float,
    volume: float,
    purge: float,
    time: float,
) -> float:
    """Return the well-mixed constant-volume accumulation/purge oracle."""
    values = {
        "c0": c0,
        "c_in": c_in,
        "m_dot": m_dot,
        "volume": volume,
        "purge": purge,
        "time": time,
    }
    converted = {
        name: _finite(value, "INVALID_ANALYTIC_INPUT", name)
        for name, value in values.items()
    }
    if converted["volume"] <= 0.0 or converted["purge"] < 0.0 or converted["time"] < 0.0:
        fail(
            "INVALID_ANALYTIC_INPUT",
            "volume must be positive and purge/time nonnegative",
            "closed_form_tank_concentration",
        )
    if converted["purge"] == 0.0:
        return converted["c0"] + converted["m_dot"] * converted["time"] / converted["volume"]
    steady_state = converted["c_in"] + converted["m_dot"] / converted["purge"]
    return steady_state + (converted["c0"] - steady_state) * exp(
        -converted["purge"] * converted["time"] / converted["volume"]
    )
