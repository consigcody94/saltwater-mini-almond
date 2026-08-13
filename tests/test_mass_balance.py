from dataclasses import FrozenInstanceError, replace
from hashlib import sha256
from math import exp
from pathlib import Path
from types import MappingProxyType

import pytest
import yaml
from hypothesis import given, strategies as st

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
    StockUnit,
)
from almondlab.errors import AlmondLabError
from almondlab.mass_balance import (
    CompartmentState,
    ExternalBoundaryFlux,
    InternalEntityFlux,
    InternalWaterFlow,
    LedgerTransactionExpectation,
    NetworkState,
    ReactionFlux,
    ValidatedAdapterRef,
    audit_ledger,
    closed_form_tank_concentration,
    step_state,
)


FIXTURES = Path(__file__).parent / "fixtures"
PACKAGED_FIXTURES = (
    Path(__file__).parents[1] / "src" / "almondlab" / "resources" / "fixtures"
)
PHYSICS = EvidenceLabel.PHYSICS_CONSTRAINED


def _fixture(name: str) -> dict[str, object]:
    return yaml.safe_load((FIXTURES / name).read_text(encoding="utf-8"))


def _compartment(
    compartment_id: str,
    kind: CompartmentKind,
    *,
    volume_l: float,
    water_mass_kg: float,
    stocks: dict[ConservedEntity, float],
    loop_id: str = "main",
    empty_reference_density_kg_l: float = 0.997,
    evidence_label: EvidenceLabel = PHYSICS,
) -> CompartmentState:
    return CompartmentState(
        compartment_id=compartment_id,
        kind=kind,
        loop_id=loop_id,
        volume_l=volume_l,
        water_mass_kg=water_mass_kg,
        empty_reference_density_kg_l=empty_reference_density_kg_l,
        stocks=stocks,
        evidence_label=evidence_label,
    )


def _state(
    compartments: dict[str, CompartmentState],
    tracked_entities: frozenset[ConservedEntity],
    evidence_label: EvidenceLabel = PHYSICS,
) -> NetworkState:
    return NetworkState(
        compartments=compartments,
        tracked_entities=tracked_entities,
        evidence_label=evidence_label,
    )


def _two_tank_state(
    *,
    entities: frozenset[ConservedEntity] = frozenset({ConservedEntity.NA}),
    source_stocks: dict[ConservedEntity, float] | None = None,
    source_volume_l: float = 100.0,
    source_density: float = 0.997,
    target_kind: CompartmentKind = CompartmentKind.ROOT_ZONE,
    source_loop: str = "main",
    target_loop: str = "main",
    evidence_label: EvidenceLabel = PHYSICS,
) -> NetworkState:
    supplied = source_stocks or {entity: 0.0 for entity in entities}
    target_stocks = {entity: 0.0 for entity in entities}
    return _state(
        {
            "source": _compartment(
                "source",
                CompartmentKind.IRRIGATION_TANK,
                volume_l=source_volume_l,
                water_mass_kg=source_volume_l * source_density,
                stocks=supplied,
                loop_id=source_loop,
                evidence_label=evidence_label,
            ),
            "target": _compartment(
                "target",
                target_kind,
                volume_l=0.0,
                water_mass_kg=0.0,
                stocks=target_stocks,
                loop_id=target_loop,
                empty_reference_density_kg_l=source_density,
                evidence_label=evidence_label,
            ),
        },
        entities,
        evidence_label,
    )


def _flow(
    *,
    event_id: str = "irrigate",
    rate: float = 10.0,
    phase: OperatorPhase = OperatorPhase.IRRIGATION,
    evidence_label: EvidenceLabel = PHYSICS,
    physical_transfer_id: str | None = None,
    flow_kind: InternalWaterFlowKind = InternalWaterFlowKind.AQUEOUS_TRANSFER,
) -> InternalWaterFlow:
    return InternalWaterFlow(
        event_id=event_id,
        source="source",
        target="target",
        rate_l_per_hour=rate,
        flow_kind=flow_kind,
        phase=phase,
        evidence_label=evidence_label,
        physical_transfer_id=physical_transfer_id,
    )


def _step(
    state: NetworkState,
    *,
    duration: float,
    cursor: LedgerCursor | None = None,
    water_flows: tuple[InternalWaterFlow, ...] = (),
    boundary_fluxes: tuple[ExternalBoundaryFlux, ...] = (),
    entity_fluxes: tuple[InternalEntityFlux, ...] = (),
    reaction_fluxes: tuple[ReactionFlux, ...] = (),
    max_substep_hours: float = 0.25,
):
    return step_state(
        state,
        dt_hours=duration,
        cursor=cursor or LedgerCursor("TEST", "main"),
        water_flows=water_flows,
        boundary_fluxes=boundary_fluxes,
        entity_fluxes=entity_fluxes,
        reaction_fluxes=reaction_fluxes,
        max_substep_hours=max_substep_hours,
    )


def test_density_fixture_advects_water_mass_and_canonical_entity_units() -> None:
    case = _fixture("entity_units_density.yaml")
    tracked = frozenset(
        {ConservedEntity.NA, ConservedEntity.ALKALINITY}
    )
    source = case["initial"]["source"]
    state = _state(
        {
            "source": _compartment(
                "source",
                CompartmentKind.IRRIGATION_TANK,
                volume_l=source["volume_l"],
                water_mass_kg=source["water_mass_kg"],
                stocks={
                    ConservedEntity.NA: source["stocks"]["na"],
                    ConservedEntity.ALKALINITY: source["stocks"]["alkalinity"],
                },
            ),
            "target": _compartment(
                "target",
                CompartmentKind.ROOT_ZONE,
                volume_l=0.0,
                water_mass_kg=0.0,
                stocks={entity: 0.0 for entity in tracked},
            ),
        },
        tracked,
    )
    event = _flow(rate=case["flow"]["rate_l_per_hour"])

    result = _step(state, duration=case["duration_hours"], water_flows=(event,))

    expected = case["expected"]
    for compartment_id in ("source", "target"):
        observed = result.state.compartments[compartment_id]
        wanted = expected[compartment_id]
        assert observed.volume_l == pytest.approx(wanted["volume_l"], abs=1e-12)
        assert observed.water_mass_kg == pytest.approx(
            wanted["water_mass_kg"], abs=1e-12
        )
        assert observed.stocks[ConservedEntity.NA] == pytest.approx(
            wanted["stocks"]["na"], abs=1e-12
        )
        assert observed.stocks[ConservedEntity.ALKALINITY] == pytest.approx(
            wanted["stocks"]["alkalinity"], abs=1e-12
        )
    assert result.substeps == 8
    transactions = {
        row.transaction_id: [entry for entry in result.ledger if entry.transaction_id == row.transaction_id]
        for row in result.ledger
    }
    assert len(transactions) == 8
    per_step = case["expected_per_substep"]
    for rows in transactions.values():
        debits = {row.entity: row for row in rows if row.amount < 0.0}
        assert debits[ConservedEntity.WATER].carrier_volume_l == pytest.approx(
            per_step["volume_l"]
        )
        assert abs(debits[ConservedEntity.WATER].amount) == pytest.approx(
            per_step["water_mass_kg"]
        )
        assert debits[ConservedEntity.NA].unit is StockUnit.MMOL
        assert abs(debits[ConservedEntity.NA].amount) == pytest.approx(per_step["na"])
        assert debits[ConservedEntity.ALKALINITY].unit is StockUnit.MMOL_C
        assert abs(debits[ConservedEntity.ALKALINITY].amount) == pytest.approx(
            per_step["alkalinity"]
        )
    audit = audit_ledger(state, result.state, result.ledger)
    assert audit.balanced
    assert audit.relative_residual(ConservedEntity.WATER) <= 1e-10
    assert audit.relative_volume_residual <= 1e-10


def test_state_is_deeply_immutable_and_defensively_copied() -> None:
    stocks = {ConservedEntity.NA: 2.0}
    compartment = _compartment(
        "tank",
        CompartmentKind.BLEND_TANK,
        volume_l=5.0,
        water_mass_kg=4.985,
        stocks=stocks,
    )
    compartments = {"tank": compartment}
    state = _state(compartments, frozenset({ConservedEntity.NA}))
    stocks[ConservedEntity.NA] = 99.0
    compartments["tank"] = replace(compartment, volume_l=4.0, water_mass_kg=3.988)

    assert state.compartments["tank"].stocks[ConservedEntity.NA] == 2.0
    assert state.compartments["tank"].volume_l == 5.0
    with pytest.raises(TypeError):
        state.compartments["tank"].stocks[ConservedEntity.NA] = 3.0  # type: ignore[index]
    with pytest.raises(TypeError):
        state.compartments["other"] = compartment  # type: ignore[index]
    with pytest.raises(FrozenInstanceError):
        state.evidence_label = EvidenceLabel.SYNTHETIC_ONLY  # type: ignore[misc]


def test_state_rejects_water_in_stock_mapping_and_incomplete_registry() -> None:
    with pytest.raises(AlmondLabError) as water:
        _compartment(
            "tank",
            CompartmentKind.BLEND_TANK,
            volume_l=1.0,
            water_mass_kg=0.997,
            stocks={ConservedEntity.WATER: 0.997},
        )
    assert water.value.code == "WATER_STOCK_FORBIDDEN"

    compartment = _compartment(
        "tank",
        CompartmentKind.BLEND_TANK,
        volume_l=1.0,
        water_mass_kg=0.997,
        stocks={ConservedEntity.NA: 1.0},
    )
    with pytest.raises(AlmondLabError) as incomplete:
        _state(
            {"tank": compartment},
            frozenset({ConservedEntity.NA, ConservedEntity.CL}),
        )
    assert incomplete.value.code == "STATE_ENTITY_REGISTRY_MISMATCH"


def test_compartment_concentration_rejects_unregistered_entity_structurally() -> None:
    compartment = _compartment(
        "tank",
        CompartmentKind.BLEND_TANK,
        volume_l=1.0,
        water_mass_kg=0.997,
        stocks={ConservedEntity.NA: 1.0},
    )
    with pytest.raises(AlmondLabError) as exc_info:
        compartment.concentration(ConservedEntity.CL)
    assert exc_info.value.code == "UNREGISTERED_ENTITY"


def test_state_allows_explicitly_weaker_but_never_stronger_evidence() -> None:
    compartment = _compartment(
        "tank",
        CompartmentKind.BLEND_TANK,
        volume_l=1.0,
        water_mass_kg=0.997,
        stocks={ConservedEntity.NA: 1.0},
        evidence_label=PHYSICS,
    )
    weaker = _state(
        {"tank": compartment},
        frozenset({ConservedEntity.NA}),
        EvidenceLabel.HYPOTHESIS_PRIOR,
    )
    assert weaker.evidence_label is EvidenceLabel.HYPOTHESIS_PRIOR

    hypothesis_compartment = replace(
        compartment, evidence_label=EvidenceLabel.HYPOTHESIS_PRIOR
    )
    with pytest.raises(AlmondLabError) as stronger:
        _state(
            {"tank": hypothesis_compartment},
            frozenset({ConservedEntity.NA}),
            PHYSICS,
        )
    assert stronger.value.code == "STATE_EVIDENCE_MISMATCH"


@pytest.mark.parametrize(
    ("volume_l", "water_mass_kg", "stock", "code"),
    [
        (0.0, 1.0, 0.0, "WATER_MASS_WITHOUT_VOLUME"),
        (0.0, 0.0, 1.0, "STOCK_WITHOUT_WATER"),
        (1.0, 0.0, 0.0, "VOLUME_WITHOUT_WATER_MASS"),
    ],
)
def test_zero_volume_and_carrier_invariants_are_enforced(
    volume_l: float, water_mass_kg: float, stock: float, code: str
) -> None:
    with pytest.raises(AlmondLabError) as exc_info:
        _compartment(
            "tank",
            CompartmentKind.BLEND_TANK,
            volume_l=volume_l,
            water_mass_kg=water_mass_kg,
            stocks={ConservedEntity.NA: stock},
        )
    assert exc_info.value.code == code


def test_cross_loop_water_flow_requires_physical_transfer_id() -> None:
    state = _two_tank_state(source_loop="source-loop", target_loop="root-loop")
    with pytest.raises(AlmondLabError) as missing:
        _step(state, duration=0.25, water_flows=(_flow(),))
    assert missing.value.code == "CROSS_LOOP_TRANSFER"

    result = _step(
        state,
        duration=0.25,
        water_flows=(_flow(physical_transfer_id="pipe-7"),),
    )
    assert result.state.compartments["target"].volume_l == pytest.approx(2.5)
    assert {row.physical_transfer_id for row in result.ledger} == {"pipe-7"}


def test_water_only_evaporation_moves_no_dissolved_entity() -> None:
    state = _two_tank_state(
        source_stocks={ConservedEntity.NA: 200.0},
        target_kind=CompartmentKind.GREENHOUSE_AIR,
    )
    evaporation = _flow(
        event_id="evaporate",
        rate=4.0,
        phase=OperatorPhase.EVAPORATION_TRANSPIRATION,
        flow_kind=InternalWaterFlowKind.EVAPORATION,
    )

    result = _step(state, duration=0.25, water_flows=(evaporation,))

    assert result.state.compartments["source"].volume_l == pytest.approx(99.0)
    assert result.state.compartments["source"].water_mass_kg == pytest.approx(98.703)
    assert result.state.compartments["source"].stocks[ConservedEntity.NA] == 200.0
    assert {row.entity for row in result.ledger} == {ConservedEntity.WATER}
    assert {row.transfer_mode for row in result.ledger} == {
        MaterialTransferMode.WATER_ONLY
    }
    assert audit_ledger(
        state, result.state, result.ledger, expected_events=(evaporation,)
    ).balanced


def test_internal_plant_fluxes_cap_competing_demands_proportionally() -> None:
    case = _fixture("internal_plant_flux_cap.yaml")
    tracked = frozenset({ConservedEntity.NA})
    state = _state(
        {
            "symplast": _compartment(
                "symplast",
                CompartmentKind.ROOT_SYMPLAST,
                volume_l=1.0,
                water_mass_kg=0.997,
                stocks={ConservedEntity.NA: case["initial"]["symplast_na_mmol"]},
            ),
            "root-zone": _compartment(
                "root-zone",
                CompartmentKind.ROOT_ZONE,
                volume_l=1.0,
                water_mass_kg=0.997,
                stocks={ConservedEntity.NA: 0.0},
            ),
            "vacuole": _compartment(
                "vacuole",
                CompartmentKind.ROOT_VACUOLE,
                volume_l=1.0,
                water_mass_kg=0.997,
                stocks={ConservedEntity.NA: 0.0},
            ),
        },
        tracked,
    )
    events = tuple(
        InternalEntityFlux(
            event_id=item["event_id"],
            source="symplast",
            target=item["target"],
            kind=InternalEntityFluxKind(item["kind"]),
            entity=ConservedEntity.NA,
            rate_per_hour=item["rate_mmol_per_hour"],
            phase=OperatorPhase.PLANT_ION_TRANSITIONS,
            evidence_label=EvidenceLabel.HYPOTHESIS_PRIOR,
        )
        for item in case["events"]
    )

    result = _step(state, duration=case["duration_hours"], entity_fluxes=events)

    expected = case["expected"]
    assert result.state.compartments["symplast"].stocks[ConservedEntity.NA] == 0.0
    assert result.state.compartments["root-zone"].stocks[ConservedEntity.NA] == pytest.approx(
        expected["root_zone_na_mmol"]
    )
    assert result.state.compartments["vacuole"].stocks[ConservedEntity.NA] == pytest.approx(
        expected["vacuole_na_mmol"]
    )
    assert result.evidence_label is EvidenceLabel.HYPOTHESIS_PRIOR
    assert len(result.internal_flux_outcomes) == 2
    outcomes = {outcome.event_id: outcome for outcome in result.internal_flux_outcomes}
    assert outcomes["a-efflux"].requested_amount == pytest.approx(1.0)
    assert outcomes["a-efflux"].applied_amount == pytest.approx(0.5)
    assert outcomes["b-sequester"].requested_amount == pytest.approx(0.5)
    assert outcomes["b-sequester"].applied_amount == pytest.approx(0.25)
    assert {outcome.cap_fraction for outcome in outcomes.values()} == {0.5}
    assert len({row.transaction_id for row in result.ledger}) == 2
    assert len(result.ledger) == 4
    assert all(row.internal_flux_kind is not None for row in result.ledger)
    assert all(row.transfer_mode is MaterialTransferMode.ENTITY_ONLY for row in result.ledger)
    assert audit_ledger(state, result.state, result.ledger).balanced


def test_reversing_plant_event_input_order_has_identical_result_and_ledger() -> None:
    tracked = frozenset({ConservedEntity.NA})
    state = _state(
        {
            "symplast": _compartment(
                "symplast",
                CompartmentKind.ROOT_SYMPLAST,
                volume_l=1.0,
                water_mass_kg=1.0,
                stocks={ConservedEntity.NA: 0.75},
            ),
            "root-zone": _compartment(
                "root-zone",
                CompartmentKind.ROOT_ZONE,
                volume_l=1.0,
                water_mass_kg=1.0,
                stocks={ConservedEntity.NA: 0.0},
            ),
            "vacuole": _compartment(
                "vacuole",
                CompartmentKind.ROOT_VACUOLE,
                volume_l=1.0,
                water_mass_kg=1.0,
                stocks={ConservedEntity.NA: 0.0},
            ),
        },
        tracked,
    )
    events = (
        InternalEntityFlux(
            event_id="b-sequester",
            source="symplast",
            target="vacuole",
            kind=InternalEntityFluxKind.SEQUESTRATION,
            entity=ConservedEntity.NA,
            rate_per_hour=2.0,
            phase=OperatorPhase.PLANT_ION_TRANSITIONS,
            evidence_label=EvidenceLabel.HYPOTHESIS_PRIOR,
        ),
        InternalEntityFlux(
            event_id="a-efflux",
            source="symplast",
            target="root-zone",
            kind=InternalEntityFluxKind.PLANT_EFFLUX,
            entity=ConservedEntity.NA,
            rate_per_hour=4.0,
            phase=OperatorPhase.PLANT_ION_TRANSITIONS,
            evidence_label=EvidenceLabel.HYPOTHESIS_PRIOR,
        ),
    )
    first = _step(state, duration=0.25, entity_fluxes=events)
    second = _step(state, duration=0.25, entity_fluxes=tuple(reversed(events)))

    assert first.state == second.state
    assert first.ledger == second.ledger
    assert first.internal_flux_outcomes == second.internal_flux_outcomes


@pytest.mark.parametrize(
    ("kind", "source_kind", "target_kind"),
    [
        (
            InternalEntityFluxKind.PLANT_UPTAKE,
            CompartmentKind.ROOT_SYMPLAST,
            CompartmentKind.ROOT_ZONE,
        ),
        (
            InternalEntityFluxKind.PLANT_EFFLUX,
            CompartmentKind.ROOT_ZONE,
            CompartmentKind.ROOT_SYMPLAST,
        ),
        (
            InternalEntityFluxKind.SEQUESTRATION,
            CompartmentKind.ROOT_SYMPLAST,
            CompartmentKind.XYLEM,
        ),
    ],
)
def test_internal_entity_flux_rejects_endpoint_kind_mismatch(
    kind: InternalEntityFluxKind,
    source_kind: CompartmentKind,
    target_kind: CompartmentKind,
) -> None:
    state = _state(
        {
            "source": _compartment(
                "source", source_kind, volume_l=1.0, water_mass_kg=1.0,
                stocks={ConservedEntity.NA: 1.0}
            ),
            "target": _compartment(
                "target", target_kind, volume_l=1.0, water_mass_kg=1.0,
                stocks={ConservedEntity.NA: 0.0}
            ),
        },
        frozenset({ConservedEntity.NA}),
    )
    event = InternalEntityFlux(
        event_id="bad-endpoints",
        source="source",
        target="target",
        kind=kind,
        entity=ConservedEntity.NA,
        rate_per_hour=1.0,
        phase=OperatorPhase.PLANT_ION_TRANSITIONS,
        evidence_label=EvidenceLabel.HYPOTHESIS_PRIOR,
    )
    with pytest.raises(AlmondLabError) as exc_info:
        _step(state, duration=0.25, entity_fluxes=(event,))
    assert exc_info.value.code == "INTERNAL_ENTITY_ENDPOINT_MISMATCH"


def test_internal_entity_flux_rejects_water_entity() -> None:
    with pytest.raises(AlmondLabError) as exc_info:
        InternalEntityFlux(
            event_id="bad-water",
            source="source",
            target="target",
            kind=InternalEntityFluxKind.PLANT_UPTAKE,
            entity=ConservedEntity.WATER,
            rate_per_hour=1.0,
            phase=OperatorPhase.PLANT_ION_TRANSITIONS,
            evidence_label=EvidenceLabel.HYPOTHESIS_PRIOR,
        )
    assert exc_info.value.code == "INTERNAL_ENTITY_WATER_FORBIDDEN"


@pytest.mark.parametrize(
    "boundary_id",
    [
        "uptake",
        "Up-take",
        "root_efflux_sink",
        "re.trieval",
        "sequestration",
        "sorp-tion",
        "ion_exchange",
        "precipitation",
        "dissolution",
        "volatilization",
        "reaction",
    ],
)
def test_external_boundary_rejects_reaction_like_aliases(boundary_id: str) -> None:
    with pytest.raises(AlmondLabError) as exc_info:
        ExternalBoundaryFlux(
            event_id="bad-boundary",
            compartment="source",
            boundary_id=boundary_id,
            category=ExternalBoundaryCategory.OTHER_MEASURED_OUTPUT,
            material_mode=MaterialTransferMode.ENTITY_ONLY,
            volume_rate_l_per_hour=0.0,
            entity_rates_per_hour={ConservedEntity.NA: 1.0},
            current_mixture_advection=False,
            phase=OperatorPhase.PURGE_DISPOSAL,
            evidence_label=PHYSICS,
        )
    assert exc_info.value.code == "REACTION_BOUNDARY_ALIAS_FORBIDDEN"


def test_external_feed_requires_density_and_complete_inventory() -> None:
    state = _two_tank_state(
        entities=frozenset({ConservedEntity.NA, ConservedEntity.CL}),
        source_stocks={ConservedEntity.NA: 1.0, ConservedEntity.CL: 1.0},
    )
    with pytest.raises(AlmondLabError) as density:
        ExternalBoundaryFlux(
            event_id="feed",
            compartment="source",
            boundary_id="municipal-feed",
            category=ExternalBoundaryCategory.SOURCE_FEED,
            material_mode=MaterialTransferMode.ADVECTIVE_AQUEOUS,
            volume_rate_l_per_hour=1.0,
            water_density_kg_l=None,
            entity_rates_per_hour={ConservedEntity.NA: 1.0},
            current_mixture_advection=False,
            phase=OperatorPhase.EXTERNAL_FEED_AMENDMENT,
            evidence_label=PHYSICS,
        )
    assert density.value.code == "BOUNDARY_INPUT_DENSITY_REQUIRED"

    incomplete = ExternalBoundaryFlux(
        event_id="feed",
        compartment="source",
        boundary_id="municipal-feed",
        category=ExternalBoundaryCategory.SOURCE_FEED,
        material_mode=MaterialTransferMode.ADVECTIVE_AQUEOUS,
        volume_rate_l_per_hour=1.0,
        water_density_kg_l=0.997,
        entity_rates_per_hour={ConservedEntity.NA: 1.0},
        current_mixture_advection=False,
        phase=OperatorPhase.EXTERNAL_FEED_AMENDMENT,
        evidence_label=PHYSICS,
    )
    with pytest.raises(AlmondLabError) as inventory:
        _step(state, duration=0.25, boundary_fluxes=(incomplete,))
    assert inventory.value.code == "BOUNDARY_ENTITY_REGISTRY_MISMATCH"


def test_external_aqueous_output_requires_explicit_current_mixture_advection() -> None:
    state = _two_tank_state(source_stocks={ConservedEntity.NA: 10.0})
    purge = ExternalBoundaryFlux(
        event_id="purge",
        compartment="source",
        boundary_id="measured-discharge",
        category=ExternalBoundaryCategory.PURGE_OR_DISCHARGE,
        material_mode=MaterialTransferMode.ADVECTIVE_AQUEOUS,
        volume_rate_l_per_hour=1.0,
        entity_rates_per_hour={},
        current_mixture_advection=False,
        phase=OperatorPhase.PURGE_DISPOSAL,
        evidence_label=PHYSICS,
    )
    with pytest.raises(AlmondLabError) as exc_info:
        _step(state, duration=0.25, boundary_fluxes=(purge,))
    assert exc_info.value.code == "BOUNDARY_CURRENT_MIXTURE_REQUIRED"


def test_external_rows_are_one_sided_typed_and_auditable() -> None:
    state = _two_tank_state(source_stocks={ConservedEntity.NA: 10.0})
    feed = ExternalBoundaryFlux(
        event_id="feed",
        compartment="source",
        boundary_id="measured-feed",
        category=ExternalBoundaryCategory.SOURCE_FEED,
        material_mode=MaterialTransferMode.ADVECTIVE_AQUEOUS,
        volume_rate_l_per_hour=2.0,
        water_density_kg_l=0.997,
        entity_rates_per_hour={ConservedEntity.NA: 6.0},
        current_mixture_advection=False,
        phase=OperatorPhase.EXTERNAL_FEED_AMENDMENT,
        evidence_label=PHYSICS,
    )
    result = _step(state, duration=0.25, boundary_fluxes=(feed,))

    assert len(result.ledger) == 2
    assert all(row.boundary_category is ExternalBoundaryCategory.SOURCE_FEED for row in result.ledger)
    assert all(row.compartment == "source" and row.counterparty == "measured-feed" for row in result.ledger)
    assert all(row.amount > 0.0 for row in result.ledger)
    assert audit_ledger(state, result.state, result.ledger).balanced


def test_core_v1_rejects_reaction_even_with_well_formed_adapter_reference() -> None:
    state = _two_tank_state(source_stocks={ConservedEntity.NA: 10.0})
    adapter = ValidatedAdapterRef(
        adapter_id="sorption-model",
        version="1.0",
        sha256="a" * 64,
        domain_id="core-v2-only",
    )
    reaction = ReactionFlux(
        event_id="reaction-1",
        source="source",
        target="target",
        entity=ConservedEntity.NA,
        rate_per_hour=1.0,
        adapter=adapter,
        phase=OperatorPhase.REACTION_ADAPTERS,
        evidence_label=EvidenceLabel.EMPIRICALLY_CALIBRATED,
    )
    with pytest.raises(AlmondLabError) as exc_info:
        _step(state, duration=0.25, reaction_fluxes=(reaction,))
    assert exc_info.value.code == "REACTION_ADAPTER_DISABLED"


@pytest.mark.parametrize(
    ("state_label", "event_label", "expected"),
    [
        (PHYSICS, PHYSICS, PHYSICS),
        (
            EvidenceLabel.EMPIRICALLY_CALIBRATED,
            EvidenceLabel.EMPIRICALLY_CALIBRATED,
            EvidenceLabel.EMPIRICALLY_CALIBRATED,
        ),
        (PHYSICS, EvidenceLabel.EMPIRICALLY_CALIBRATED, EvidenceLabel.HYPOTHESIS_PRIOR),
        (PHYSICS, EvidenceLabel.HYPOTHESIS_PRIOR, EvidenceLabel.HYPOTHESIS_PRIOR),
        (PHYSICS, EvidenceLabel.SYNTHETIC_ONLY, EvidenceLabel.SYNTHETIC_ONLY),
    ],
)
def test_every_evidence_composition_class_is_conservative(
    state_label: EvidenceLabel,
    event_label: EvidenceLabel,
    expected: EvidenceLabel,
) -> None:
    state = _two_tank_state(
        source_stocks={ConservedEntity.NA: 1.0}, evidence_label=state_label
    )
    result = _step(
        state,
        duration=0.25,
        water_flows=(_flow(evidence_label=event_label),),
    )
    assert result.evidence_label is expected
    assert result.state.evidence_label is expected
    assert {row.evidence_label for row in result.ledger} == {expected}


def test_invalid_operator_schedule_is_rejected_at_step_boundary() -> None:
    state = _two_tank_state(source_stocks={ConservedEntity.NA: 1.0})
    with pytest.raises(AlmondLabError) as exc_info:
        step_state(
            state,
            dt_hours=0.25,
            cursor=LedgerCursor("TEST", "main"),
            water_flows=(_flow(),),
            schedule=object(),  # type: ignore[arg-type]
        )
    assert exc_info.value.code == "OPERATOR_SCHEDULE_INVALID"


def test_event_ids_are_unique_across_all_event_types() -> None:
    state = _two_tank_state(source_stocks={ConservedEntity.NA: 1.0})
    boundary = ExternalBoundaryFlux(
        event_id="same-id",
        compartment="source",
        boundary_id="measured-loss",
        category=ExternalBoundaryCategory.SAMPLING,
        material_mode=MaterialTransferMode.ENTITY_ONLY,
        volume_rate_l_per_hour=0.0,
        entity_rates_per_hour={ConservedEntity.NA: 0.1},
        current_mixture_advection=False,
        phase=OperatorPhase.PURGE_DISPOSAL,
        evidence_label=PHYSICS,
    )
    with pytest.raises(AlmondLabError) as exc_info:
        _step(
            state,
            duration=0.25,
            water_flows=(_flow(event_id="same-id"),),
            boundary_fluxes=(boundary,),
        )
    assert exc_info.value.code == "DUPLICATE_EVENT_ID"


def test_cursor_continues_across_chained_steps_and_replay_is_deterministic() -> None:
    case = _fixture("chained_transaction_ids.yaml")
    state = _two_tank_state(source_stocks={ConservedEntity.NA: 20.0})
    cursor = LedgerCursor(case["run_a"], case["chain"], case["start_ordinal"])
    first = _step(state, duration=0.25, water_flows=(_flow(),), cursor=cursor)
    second = _step(
        first.state,
        duration=0.25,
        water_flows=(_flow(),),
        cursor=first.next_cursor,
    )
    transaction_ids = tuple(
        dict.fromkeys(row.transaction_id for row in first.ledger + second.ledger)
    )
    assert transaction_ids == tuple(case["expected_run_a_ids"])
    assert second.next_cursor.next_ordinal == case["expected_next_ordinal"]

    replay_first = _step(state, duration=0.25, water_flows=(_flow(),), cursor=cursor)
    replay_second = _step(
        replay_first.state,
        duration=0.25,
        water_flows=(_flow(),),
        cursor=replay_first.next_cursor,
    )
    assert (first, second) == (replay_first, replay_second)

    run_b = _step(
        state,
        duration=0.25,
        water_flows=(_flow(),),
        cursor=LedgerCursor(case["run_b"], case["chain"], case["start_ordinal"]),
    )
    assert set(transaction_ids).isdisjoint({row.transaction_id for row in run_b.ledger})


def test_audit_rejects_duplicate_transaction_ids_across_concatenated_chain() -> None:
    state = _two_tank_state(source_stocks={ConservedEntity.NA: 20.0})
    cursor = LedgerCursor("RUN", "main")
    first = _step(state, duration=0.25, water_flows=(_flow(),), cursor=cursor)
    second = _step(first.state, duration=0.25, water_flows=(_flow(),), cursor=cursor)

    audit = audit_ledger(state, second.state, first.ledger + second.ledger)

    assert audit.structural_errors
    assert not audit.balanced


@pytest.mark.parametrize("corruption", ["delete", "duplicate", "halve", "same_sign", "unpaired"])
def test_audit_rejects_adversarial_internal_ledger_corruption(corruption: str) -> None:
    state = _two_tank_state(source_stocks={ConservedEntity.NA: 20.0})
    result = _step(state, duration=0.25, water_flows=(_flow(),))
    rows = list(result.ledger)
    na_rows = [index for index, row in enumerate(rows) if row.entity is ConservedEntity.NA]
    if corruption == "delete":
        rows = [row for row in rows if row.entity is not ConservedEntity.NA]
    elif corruption == "duplicate":
        rows.append(rows[na_rows[0]])
    elif corruption == "halve":
        for index in na_rows:
            rows[index] = replace(rows[index], amount=rows[index].amount / 2.0)
    elif corruption == "same_sign":
        positive = next(index for index in na_rows if rows[index].amount > 0.0)
        rows[positive] = replace(rows[positive], amount=-rows[positive].amount)
    else:
        rows.pop(na_rows[0])

    audit = audit_ledger(state, result.state, tuple(rows))

    assert audit.structural_errors or any(
        audit.relative_compartment_residual(compartment, ConservedEntity.NA) > 1e-10
        for compartment in state.compartments
    )
    assert not audit.balanced


def test_ledger_constructor_rejects_alkalinity_unit_and_water_identity_mutations() -> None:
    state = _two_tank_state(
        entities=frozenset({ConservedEntity.ALKALINITY}),
        source_stocks={ConservedEntity.ALKALINITY: 35.0},
    )
    result = _step(state, duration=0.25, water_flows=(_flow(),))
    alk = next(row for row in result.ledger if row.entity is ConservedEntity.ALKALINITY)
    water = next(row for row in result.ledger if row.entity is ConservedEntity.WATER)
    with pytest.raises(AlmondLabError) as unit:
        replace(alk, unit=StockUnit.MMOL)
    assert unit.value.code == "LEDGER_UNIT_MISMATCH"
    with pytest.raises(AlmondLabError) as carrier:
        replace(water, water_density_kg_l=water.water_density_kg_l + 0.01)
    assert carrier.value.code == "LEDGER_WATER_IDENTITY_MISMATCH"


def test_audit_rejects_wrong_endpoint_and_evidence_metadata() -> None:
    state = _two_tank_state(source_stocks={ConservedEntity.NA: 20.0})
    result = _step(state, duration=0.25, water_flows=(_flow(),))
    rows = list(result.ledger)
    na_index = next(i for i, row in enumerate(rows) if row.entity is ConservedEntity.NA and row.amount > 0)
    rows[na_index] = replace(rows[na_index], counterparty="target")
    assert not audit_ledger(state, result.state, tuple(rows)).balanced

    rows = list(result.ledger)
    na_index = next(i for i, row in enumerate(rows) if row.entity is ConservedEntity.NA and row.amount > 0)
    rows[na_index] = replace(rows[na_index], evidence_label=EvidenceLabel.SYNTHETIC_ONLY)
    assert not audit_ledger(state, result.state, tuple(rows)).balanced


@pytest.mark.parametrize(
    ("field_name", "wrong_value"),
    [
        ("event_id", "wrong-event"),
        ("phase", OperatorPhase.LAYER_DRAINAGE),
        ("physical_transfer_id", "wrong-pipe"),
    ],
)
def test_event_authority_catches_systematic_generator_metadata_drift(
    field_name: str, wrong_value: object
) -> None:
    """A constructor-valid bug copied to every row must not self-validate."""
    state = _two_tank_state(source_stocks={ConservedEntity.NA: 20.0})
    event = _flow(physical_transfer_id="declared-pipe")
    result = _step(state, duration=0.25, water_flows=(event,))
    corrupted = tuple(
        replace(row, **{field_name: wrong_value}) for row in result.ledger
    )

    audit = audit_ledger(
        state,
        result.state,
        corrupted,
        expected_events=(event,),
    )

    assert audit.structural_errors
    assert not audit.balanced


def _single_flow_expectation(
    *,
    event_id: str = "irrigate",
    ordinal: int = 0,
    dt_hours: float = 0.25,
    water_mass_kg: float = 2.4925,
    na_mmol: float = 0.5,
) -> LedgerTransactionExpectation:
    return LedgerTransactionExpectation(
        transaction_id=f"tx:TEST:main:{ordinal:012d}",
        event_id=event_id,
        dt_hours=dt_hours,
        amounts={
            ConservedEntity.WATER: water_mass_kg,
            ConservedEntity.NA: na_mmol,
        },
    )


def test_audit_authority_orders_source_and_target_and_pins_event_rate() -> None:
    state = _two_tank_state(source_stocks={ConservedEntity.NA: 20.0})
    event = _flow()
    result = _step(state, duration=0.25, water_flows=(event,))
    expected = (_single_flow_expectation(),)

    reversed_endpoint = audit_ledger(
        state,
        result.state,
        result.ledger,
        expected_events=(replace(event, source="target", target="source"),),
        expected_transactions=expected,
    )
    wrong_rate = audit_ledger(
        state,
        result.state,
        result.ledger,
        expected_events=(replace(event, rate_l_per_hour=20.0),),
        expected_transactions=expected,
    )

    assert not reversed_endpoint.balanced
    assert not wrong_rate.balanced


def test_explicit_empty_authority_means_no_events_or_transactions() -> None:
    state = _two_tank_state(source_stocks={ConservedEntity.NA: 20.0})
    result = _step(state, duration=0.25, water_flows=(_flow(),))

    audit = audit_ledger(
        state,
        result.state,
        result.ledger,
        expected_events=(),
        expected_transactions=(),
    )

    assert any("unknown ledger event" in error for error in audit.structural_errors)
    assert any("unexpected transaction" in error for error in audit.structural_errors)
    assert not audit.balanced


def test_audit_rejects_systematic_row_evidence_drift_without_event_authority() -> None:
    state = _two_tank_state(source_stocks={ConservedEntity.NA: 20.0})
    result = _step(state, duration=0.25, water_flows=(_flow(),))
    corrupted = tuple(
        replace(row, evidence_label=EvidenceLabel.SYNTHETIC_ONLY)
        for row in result.ledger
    )

    audit = audit_ledger(state, result.state, corrupted)

    assert any("evidence disagrees" in error for error in audit.structural_errors)
    assert not audit.balanced


def test_audit_rejects_no_event_state_evidence_promotion() -> None:
    state = _two_tank_state(source_stocks={ConservedEntity.NA: 20.0})
    promoted = object.__new__(NetworkState)
    object.__setattr__(promoted, "compartments", state.compartments)
    object.__setattr__(promoted, "tracked_entities", state.tracked_entities)
    object.__setattr__(
        promoted,
        "evidence_label",
        EvidenceLabel.EMPIRICALLY_CALIBRATED,
    )

    audit = audit_ledger(
        state,
        promoted,
        (),
        expected_events=(),
        expected_transactions=(),
    )

    assert any("evidence" in error for error in audit.structural_errors)
    assert not audit.balanced


def test_literal_transaction_authority_rejects_swapped_event_quantities() -> None:
    state = _two_tank_state(source_stocks={ConservedEntity.NA: 100.0})
    first = _flow(event_id="a-flow", rate=2.0)
    second = _flow(event_id="b-flow", rate=1.0)
    result = _step(state, duration=0.25, water_flows=(first, second))
    rows = list(result.ledger)
    for index, row in enumerate(rows):
        if row.entity is not ConservedEntity.NA:
            continue
        magnitude = 0.25 if row.event_id == "a-flow" else 0.5
        rows[index] = replace(row, amount=-magnitude if row.amount < 0.0 else magnitude)
    expectations = (
        LedgerTransactionExpectation(
            transaction_id="tx:TEST:main:000000000000",
            event_id="a-flow",
            dt_hours=0.25,
            amounts={ConservedEntity.WATER: 0.4985, ConservedEntity.NA: 0.5},
        ),
        LedgerTransactionExpectation(
            transaction_id="tx:TEST:main:000000000001",
            event_id="b-flow",
            dt_hours=0.25,
            amounts={ConservedEntity.WATER: 0.24925, ConservedEntity.NA: 0.25},
        ),
    )

    audit = audit_ledger(
        state,
        result.state,
        tuple(rows),
        expected_events=(first, second),
        expected_transactions=expectations,
    )

    assert any("literal authority" in error for error in audit.structural_errors)
    assert not audit.balanced


def test_literal_transaction_authority_covers_external_rows_and_zero_events() -> None:
    state = _two_tank_state(source_stocks={ConservedEntity.NA: 20.0})
    feed = ExternalBoundaryFlux(
        event_id="feed",
        compartment="source",
        boundary_id="measured-feed",
        category=ExternalBoundaryCategory.SOURCE_FEED,
        material_mode=MaterialTransferMode.ADVECTIVE_AQUEOUS,
        volume_rate_l_per_hour=2.0,
        water_density_kg_l=0.997,
        entity_rates_per_hour={ConservedEntity.NA: 6.0},
        current_mixture_advection=False,
        phase=OperatorPhase.EXTERNAL_FEED_AMENDMENT,
        evidence_label=PHYSICS,
    )
    measured_zero = ExternalBoundaryFlux(
        event_id="measured-zero",
        compartment="source",
        boundary_id="measured-amendment",
        category=ExternalBoundaryCategory.AMENDMENT,
        material_mode=MaterialTransferMode.ENTITY_ONLY,
        volume_rate_l_per_hour=0.0,
        entity_rates_per_hour={ConservedEntity.NA: 0.0},
        current_mixture_advection=False,
        phase=OperatorPhase.EXTERNAL_FEED_AMENDMENT,
        evidence_label=PHYSICS,
    )
    result = _step(
        state,
        duration=0.25,
        boundary_fluxes=(feed, measured_zero),
    )
    expectations = (
        LedgerTransactionExpectation(
            transaction_id="tx:TEST:main:000000000000",
            event_id="feed",
            dt_hours=0.25,
            amounts={ConservedEntity.WATER: 0.4985, ConservedEntity.NA: 1.5},
        ),
        LedgerTransactionExpectation(
            transaction_id="tx:TEST:main:000000000001",
            event_id="measured-zero",
            dt_hours=0.25,
            amounts={ConservedEntity.NA: 0.0},
        ),
    )

    audit = audit_ledger(
        state,
        result.state,
        result.ledger,
        expected_events=(feed, measured_zero),
        expected_transactions=expectations,
    )

    assert audit.balanced, audit.structural_errors


def test_literal_transaction_authority_is_deeply_immutable() -> None:
    amounts = {ConservedEntity.NA: 0.5}
    expectation = LedgerTransactionExpectation(
        transaction_id="tx:TEST:main:000000000000",
        event_id="transfer",
        dt_hours=0.25,
        amounts=amounts,
    )
    amounts[ConservedEntity.NA] = 99.0

    assert expectation.amounts[ConservedEntity.NA] == 0.5
    with pytest.raises(TypeError):
        expectation.amounts[ConservedEntity.NA] = 1.0  # type: ignore[index]
    with pytest.raises(FrozenInstanceError):
        expectation.dt_hours = 1.0  # type: ignore[misc]


def test_audit_rejects_complete_internal_ledger_deletion_by_compartment() -> None:
    state = _two_tank_state(source_stocks={ConservedEntity.NA: 20.0})
    event = _flow()
    result = _step(state, duration=0.25, water_flows=(event,))

    audit = audit_ledger(
        state, result.state, (), expected_events=(event,)
    )

    assert audit.relative_residual(ConservedEntity.WATER) <= 1e-10
    assert audit.relative_residual(ConservedEntity.NA) <= 1e-10
    assert any(
        audit.relative_compartment_residual(compartment, ConservedEntity.NA)
        > 1e-10
        for compartment in state.compartments
    )
    assert not audit.balanced


def test_audit_rejects_same_count_wrong_quantity_redistribution() -> None:
    state = _two_tank_state(
        entities=frozenset({ConservedEntity.NA, ConservedEntity.CL}),
        source_stocks={ConservedEntity.NA: 20.0, ConservedEntity.CL: 30.0},
    )
    event = _flow()
    result = _step(state, duration=0.25, water_flows=(event,))
    corrupted = tuple(
        replace(row, entity=ConservedEntity.CL, unit=StockUnit.MMOL)
        if row.entity is ConservedEntity.NA
        else row
        for row in result.ledger
    )

    audit = audit_ledger(
        state, result.state, corrupted, expected_events=(event,)
    )

    assert audit.structural_errors
    assert not audit.balanced


def test_contract_rejects_mode_flow_kind_boundary_sign_and_carrier_corruption() -> None:
    state = _two_tank_state(source_stocks={ConservedEntity.NA: 20.0})
    event = _flow()
    result = _step(state, duration=0.25, water_flows=(event,))
    water = next(row for row in result.ledger if row.entity is ConservedEntity.WATER)
    solute = next(row for row in result.ledger if row.entity is ConservedEntity.NA)
    with pytest.raises(AlmondLabError) as mode:
        replace(solute, transfer_mode=MaterialTransferMode.ENTITY_ONLY)
    assert mode.value.code == "LEDGER_ENTITY_ONLY_PROVENANCE_REQUIRED"
    with pytest.raises(AlmondLabError) as flow_kind:
        replace(water, internal_water_flow_kind=None)
    assert flow_kind.value.code == "LEDGER_INTERNAL_WATER_FLOW_KIND_REQUIRED"
    with pytest.raises(AlmondLabError) as carrier:
        replace(water, carrier_volume_l=water.carrier_volume_l + 0.1)
    assert carrier.value.code == "LEDGER_WATER_IDENTITY_MISMATCH"

    feed = ExternalBoundaryFlux(
        event_id="feed",
        compartment="source",
        boundary_id="measured-feed",
        category=ExternalBoundaryCategory.SOURCE_FEED,
        material_mode=MaterialTransferMode.ADVECTIVE_AQUEOUS,
        volume_rate_l_per_hour=2.0,
        water_density_kg_l=0.997,
        entity_rates_per_hour={ConservedEntity.NA: 6.0},
        current_mixture_advection=False,
        phase=OperatorPhase.EXTERNAL_FEED_AMENDMENT,
        evidence_label=PHYSICS,
    )
    feed_result = _step(state, duration=0.25, boundary_fluxes=(feed,))
    positive = next(row for row in feed_result.ledger if row.amount > 0.0)
    with pytest.raises(AlmondLabError) as sign:
        replace(positive, amount=-positive.amount)
    assert sign.value.code == "LEDGER_BOUNDARY_DIRECTION_MISMATCH"


def test_audit_rejects_coordinated_density_and_carrier_mutation() -> None:
    state = _two_tank_state(source_stocks={ConservedEntity.NA: 20.0})
    event = _flow()
    result = _step(state, duration=0.25, water_flows=(event,))
    rows = list(result.ledger)
    water_index = next(
        index
        for index, row in enumerate(rows)
        if row.entity is ConservedEntity.WATER and row.amount > 0.0
    )
    row = rows[water_index]
    rows[water_index] = replace(
        row,
        carrier_volume_l=row.carrier_volume_l * 2.0,
        water_density_kg_l=row.water_density_kg_l / 2.0,
    )

    audit = audit_ledger(
        state, result.state, tuple(rows), expected_events=(event,)
    )

    assert audit.structural_errors
    assert not audit.balanced


def test_audit_rejects_coordinated_cap_metadata_mutation() -> None:
    state = _state(
        {
            "symplast": _compartment(
                "symplast",
                CompartmentKind.ROOT_SYMPLAST,
                volume_l=1.0,
                water_mass_kg=1.0,
                stocks={ConservedEntity.NA: 1.0},
            ),
            "vacuole": _compartment(
                "vacuole",
                CompartmentKind.ROOT_VACUOLE,
                volume_l=1.0,
                water_mass_kg=1.0,
                stocks={ConservedEntity.NA: 0.0},
            ),
        },
        frozenset({ConservedEntity.NA}),
    )
    event = InternalEntityFlux(
        event_id="sequester",
        source="symplast",
        target="vacuole",
        kind=InternalEntityFluxKind.SEQUESTRATION,
        entity=ConservedEntity.NA,
        rate_per_hour=2.0,
        phase=OperatorPhase.PLANT_ION_TRANSITIONS,
        evidence_label=EvidenceLabel.HYPOTHESIS_PRIOR,
    )
    result = _step(state, duration=0.25, entity_fluxes=(event,))
    rows = list(result.ledger)
    rows = [
        replace(
            row,
            requested_amount=1.0,
            applied_amount=0.5,
            cap_fraction=0.5,
        )
        for row in rows
    ]
    expectation = LedgerTransactionExpectation(
        transaction_id="tx:TEST:main:000000000000",
        event_id="sequester",
        dt_hours=0.25,
        amounts={ConservedEntity.NA: 0.5},
    )

    audit = audit_ledger(
        state,
        result.state,
        tuple(rows),
        expected_events=(event,),
        expected_transactions=(expectation,),
    )

    assert audit.structural_errors
    assert not audit.balanced


def test_external_boundary_id_cannot_launder_an_internal_compartment() -> None:
    state = _two_tank_state(source_stocks={ConservedEntity.NA: 1.0})
    flux = ExternalBoundaryFlux(
        event_id="laundered-amendment",
        compartment="source",
        boundary_id="target",
        category=ExternalBoundaryCategory.AMENDMENT,
        material_mode=MaterialTransferMode.ENTITY_ONLY,
        volume_rate_l_per_hour=0.0,
        entity_rates_per_hour={ConservedEntity.NA: 1.0},
        current_mixture_advection=False,
        phase=OperatorPhase.EXTERNAL_FEED_AMENDMENT,
        evidence_label=PHYSICS,
    )

    with pytest.raises(AlmondLabError) as exc_info:
        _step(state, duration=0.25, boundary_fluxes=(flux,))

    assert exc_info.value.code == "EXTERNAL_BOUNDARY_NAMESPACE_COLLISION"
    assert exc_info.value.field_path == "boundary_fluxes.0.boundary_id"


def test_cross_loop_plant_transfer_generates_a_self_auditing_ledger() -> None:
    state = _state(
        {
            "root-zone": _compartment(
                "root-zone",
                CompartmentKind.ROOT_ZONE,
                volume_l=1.0,
                water_mass_kg=1.0,
                stocks={ConservedEntity.NA: 1.0},
                loop_id="hydraulic-loop",
            ),
            "symplast": _compartment(
                "symplast",
                CompartmentKind.ROOT_SYMPLAST,
                volume_l=1.0,
                water_mass_kg=1.0,
                stocks={ConservedEntity.NA: 0.0},
                loop_id="plant-loop",
            ),
        },
        frozenset({ConservedEntity.NA}),
    )
    event = InternalEntityFlux(
        event_id="uptake",
        source="root-zone",
        target="symplast",
        kind=InternalEntityFluxKind.PLANT_UPTAKE,
        entity=ConservedEntity.NA,
        rate_per_hour=1.0,
        phase=OperatorPhase.PLANT_ION_TRANSITIONS,
        evidence_label=EvidenceLabel.HYPOTHESIS_PRIOR,
    )
    result = _step(state, duration=0.25, entity_fluxes=(event,))
    expectation = LedgerTransactionExpectation(
        transaction_id="tx:TEST:main:000000000000",
        event_id="uptake",
        dt_hours=0.25,
        amounts={ConservedEntity.NA: 0.25},
    )

    audit = audit_ledger(
        state,
        result.state,
        result.ledger,
        expected_events=(event,),
        expected_transactions=(expectation,),
    )

    assert audit.balanced, audit.structural_errors


def test_event_authority_rejects_constructor_valid_water_flow_kind_mutation() -> None:
    state = _two_tank_state(
        source_stocks={ConservedEntity.NA: 20.0},
        target_kind=CompartmentKind.GREENHOUSE_AIR,
    )
    event = _flow(
        event_id="evaporate",
        rate=1.0,
        phase=OperatorPhase.EVAPORATION_TRANSPIRATION,
        flow_kind=InternalWaterFlowKind.EVAPORATION,
    )
    result = _step(state, duration=0.25, water_flows=(event,))
    corrupted = tuple(
        replace(
            row,
            internal_water_flow_kind=InternalWaterFlowKind.TRANSPIRATION,
        )
        for row in result.ledger
    )

    audit = audit_ledger(
        state, result.state, corrupted, expected_events=(event,)
    )

    assert audit.structural_errors
    assert not audit.balanced


def test_phase_start_inventory_cannot_be_reused_by_same_phase_transfer() -> None:
    state = _state(
        {
            "symplast": _compartment(
                "symplast",
                CompartmentKind.ROOT_SYMPLAST,
                volume_l=1.0,
                water_mass_kg=1.0,
                stocks={ConservedEntity.NA: 1.0},
            ),
            "vacuole": _compartment(
                "vacuole",
                CompartmentKind.ROOT_VACUOLE,
                volume_l=1.0,
                water_mass_kg=1.0,
                stocks={ConservedEntity.NA: 0.0},
            ),
        },
        frozenset({ConservedEntity.NA}),
    )
    sequester = InternalEntityFlux(
        event_id="a-sequester",
        source="symplast",
        target="vacuole",
        kind=InternalEntityFluxKind.SEQUESTRATION,
        entity=ConservedEntity.NA,
        rate_per_hour=4.0,
        phase=OperatorPhase.PLANT_ION_TRANSITIONS,
        evidence_label=EvidenceLabel.HYPOTHESIS_PRIOR,
    )
    release = InternalEntityFlux(
        event_id="b-release",
        source="vacuole",
        target="symplast",
        kind=InternalEntityFluxKind.VACUOLE_RELEASE,
        entity=ConservedEntity.NA,
        rate_per_hour=4.0,
        phase=OperatorPhase.PLANT_ION_TRANSITIONS,
        evidence_label=EvidenceLabel.HYPOTHESIS_PRIOR,
    )

    result = _step(
        state,
        duration=0.25,
        entity_fluxes=(release, sequester),
    )

    outcomes = {item.event_id: item for item in result.internal_flux_outcomes}
    assert outcomes["a-sequester"].applied_amount == pytest.approx(1.0)
    assert outcomes["b-release"].applied_amount == pytest.approx(0.0)
    assert result.state.compartments["vacuole"].stocks[ConservedEntity.NA] == pytest.approx(1.0)


def test_fixed_phase_schedule_and_event_sorting_ignore_input_order() -> None:
    state = _two_tank_state(source_stocks={ConservedEntity.NA: 20.0})
    first = _flow(event_id="b-flow", rate=2.0)
    second = InternalWaterFlow(
        event_id="a-flow",
        source="source",
        target="target",
        rate_l_per_hour=3.0,
        flow_kind=InternalWaterFlowKind.AQUEOUS_TRANSFER,
        phase=OperatorPhase.IRRIGATION,
        evidence_label=PHYSICS,
    )

    forward = _step(state, duration=0.25, water_flows=(first, second))
    reversed_result = _step(
        state, duration=0.25, water_flows=(second, first)
    )

    assert forward == reversed_result


def test_later_phase_can_use_water_delivered_by_earlier_phase() -> None:
    tracked = frozenset({ConservedEntity.NA})
    state = _state(
        {
            "source": _compartment(
                "source",
                CompartmentKind.IRRIGATION_TANK,
                volume_l=100.0,
                water_mass_kg=99.7,
                stocks={ConservedEntity.NA: 100.0},
            ),
            "root": _compartment(
                "root",
                CompartmentKind.ROOT_ZONE,
                volume_l=0.0,
                water_mass_kg=0.0,
                stocks={ConservedEntity.NA: 0.0},
            ),
            "drainage": _compartment(
                "drainage",
                CompartmentKind.DRAINAGE,
                volume_l=0.0,
                water_mass_kg=0.0,
                stocks={ConservedEntity.NA: 0.0},
            ),
        },
        tracked,
    )
    irrigate = InternalWaterFlow(
        event_id="irrigate",
        source="source",
        target="root",
        rate_l_per_hour=10.0,
        flow_kind=InternalWaterFlowKind.AQUEOUS_TRANSFER,
        phase=OperatorPhase.IRRIGATION,
        evidence_label=PHYSICS,
    )
    drain = InternalWaterFlow(
        event_id="drain",
        source="root",
        target="drainage",
        rate_l_per_hour=1.0,
        flow_kind=InternalWaterFlowKind.AQUEOUS_TRANSFER,
        phase=OperatorPhase.LAYER_DRAINAGE,
        evidence_label=PHYSICS,
    )

    result = _step(
        state,
        duration=0.25,
        water_flows=(drain, irrigate),
    )

    assert result.substeps == 1
    assert result.state.compartments["root"].volume_l == pytest.approx(2.25)
    assert result.state.compartments["drainage"].volume_l == pytest.approx(0.25)
    assert audit_ledger(
        state,
        result.state,
        result.ledger,
        expected_events=(irrigate, drain),
    ).balanced


def test_tiny_positive_stock_is_not_numerically_erased() -> None:
    state = _two_tank_state(
        source_volume_l=1.0,
        source_stocks={ConservedEntity.NA: 1e-6},
    )
    event = _flow(rate=1e-6)

    result = _step(state, duration=1.0, water_flows=(event,))

    assert result.state.compartments["target"].stocks[ConservedEntity.NA] > 0.0
    assert audit_ledger(
        state, result.state, result.ledger, expected_events=(event,)
    ).balanced


def test_internal_water_kind_rejects_endpoint_mismatch() -> None:
    state = _two_tank_state(source_stocks={ConservedEntity.NA: 20.0})
    evaporation = _flow(
        event_id="evaporate",
        rate=1.0,
        phase=OperatorPhase.EVAPORATION_TRANSPIRATION,
        flow_kind=InternalWaterFlowKind.EVAPORATION,
    )
    with pytest.raises(AlmondLabError) as exc_info:
        _step(state, duration=0.25, water_flows=(evaporation,))
    assert exc_info.value.code == "INTERNAL_WATER_ENDPOINT_MISMATCH"


def test_depleted_water_source_fails_without_clipping_total_requested_duration() -> None:
    state = _two_tank_state(
        source_volume_l=10.0,
        source_stocks={ConservedEntity.NA: 1.0},
    )
    with pytest.raises(AlmondLabError) as exc_info:
        _step(state, duration=1.0, water_flows=(_flow(rate=20.0),))
    assert exc_info.value.code == "FLOW_EXCEEDS_SOURCE"


@pytest.mark.parametrize("bad", [True, "1.0", object(), float("nan"), float("inf"), 1e309])
def test_public_numeric_boundaries_reject_coercive_and_nonfinite_values(bad: object) -> None:
    with pytest.raises(AlmondLabError):
        _compartment(
            "tank",
            CompartmentKind.BLEND_TANK,
            volume_l=bad,  # type: ignore[arg-type]
            water_mass_kg=1.0,
            stocks={ConservedEntity.NA: 0.0},
        )
    with pytest.raises(AlmondLabError):
        InternalWaterFlow(
            event_id="flow",
            source="source",
            target="target",
            rate_l_per_hour=bad,  # type: ignore[arg-type]
            flow_kind=InternalWaterFlowKind.AQUEOUS_TRANSFER,
            phase=OperatorPhase.IRRIGATION,
            evidence_label=PHYSICS,
        )
    with pytest.raises(AlmondLabError):
        closed_form_tank_concentration(1.0, 1.0, 0.0, bad, 0.0, 1.0)  # type: ignore[arg-type]


@pytest.mark.parametrize("bad", [True, "1.0", object(), float("nan"), float("inf"), 1e309])
def test_every_event_and_step_numeric_boundary_is_strict(bad: object) -> None:
    with pytest.raises(AlmondLabError):
        ExternalBoundaryFlux(
            event_id="amend",
            compartment="source",
            boundary_id="measured-amendment",
            category=ExternalBoundaryCategory.AMENDMENT,
            material_mode=MaterialTransferMode.ENTITY_ONLY,
            volume_rate_l_per_hour=0.0,
            entity_rates_per_hour={ConservedEntity.NA: bad},  # type: ignore[dict-item]
            current_mixture_advection=False,
            phase=OperatorPhase.EXTERNAL_FEED_AMENDMENT,
            evidence_label=PHYSICS,
        )
    with pytest.raises(AlmondLabError):
        InternalEntityFlux(
            event_id="sequester",
            source="source",
            target="target",
            kind=InternalEntityFluxKind.SEQUESTRATION,
            entity=ConservedEntity.NA,
            rate_per_hour=bad,  # type: ignore[arg-type]
            phase=OperatorPhase.PLANT_ION_TRANSITIONS,
            evidence_label=EvidenceLabel.HYPOTHESIS_PRIOR,
        )
    adapter = ValidatedAdapterRef(
        adapter_id="adapter",
        version="1.0",
        sha256="a" * 64,
        domain_id="future-domain",
    )
    with pytest.raises(AlmondLabError):
        ReactionFlux(
            event_id="reaction",
            source="source",
            target="target",
            entity=ConservedEntity.NA,
            rate_per_hour=bad,  # type: ignore[arg-type]
            adapter=adapter,
            phase=OperatorPhase.REACTION_ADAPTERS,
            evidence_label=EvidenceLabel.EMPIRICALLY_CALIBRATED,
        )
    state = _two_tank_state(source_stocks={ConservedEntity.NA: 1.0})
    with pytest.raises(AlmondLabError):
        step_state(
            state,
            dt_hours=bad,  # type: ignore[arg-type]
            cursor=LedgerCursor("STRICT", "main"),
        )
    with pytest.raises(AlmondLabError):
        step_state(
            state,
            dt_hours=0.25,
            cursor=LedgerCursor("STRICT", "main"),
            max_substep_hours=bad,  # type: ignore[arg-type]
        )


def _assert_mass_numeric_error(
    exc_info: pytest.ExceptionInfo[AlmondLabError], field_path: str
) -> None:
    assert exc_info.value.code == "MASS_NUMERIC_INVALID"
    assert exc_info.value.field_path == field_path


@pytest.mark.parametrize(
    ("quantity", "field_path"),
    [
        ("density", "density_kg_l"),
        ("concentration", "stocks.na.concentration"),
    ],
)
def test_nonfinite_derived_compartment_quantities_fail_structurally(
    quantity: str, field_path: str
) -> None:
    with pytest.raises(AlmondLabError) as exc_info:
        _compartment(
            "tank",
            CompartmentKind.BLEND_TANK,
            volume_l=1e-320,
            water_mass_kg=1e308 if quantity == "density" else 1e-320,
            stocks={
                ConservedEntity.NA: 0.0 if quantity == "density" else 1e308
            },
        )

    _assert_mass_numeric_error(exc_info, field_path)


@pytest.mark.parametrize(
    ("quantity", "field_path"),
    [
        ("volume", "total_volume_l"),
        ("water", "total_water_mass_kg"),
        ("stock", "total_stock.na"),
    ],
)
def test_network_totals_map_fsum_overflow_to_structured_errors(
    quantity: str, field_path: str
) -> None:
    compartments = {
        compartment_id: _compartment(
            compartment_id,
            CompartmentKind.BLEND_TANK,
            volume_l=1e308,
            water_mass_kg=1e308,
            stocks={ConservedEntity.NA: 1e308},
        )
        for compartment_id in ("a", "b")
    }
    state = _state(compartments, frozenset({ConservedEntity.NA}))

    with pytest.raises(AlmondLabError) as exc_info:
        if quantity == "volume":
            state.total_volume_l()
        elif quantity == "water":
            state.total_water_mass_kg()
        else:
            state.total_stock(ConservedEntity.NA)

    _assert_mass_numeric_error(exc_info, field_path)


def test_boundary_volume_density_overflow_fails_at_the_derived_water_quantity() -> None:
    state = _state(
        {
            "tank": _compartment(
                "tank",
                CompartmentKind.BLEND_TANK,
                volume_l=1e308,
                water_mass_kg=1e308,
                stocks={ConservedEntity.NA: 0.0},
            )
        },
        frozenset({ConservedEntity.NA}),
    )
    feed = ExternalBoundaryFlux(
        event_id="feed",
        compartment="tank",
        boundary_id="source",
        category=ExternalBoundaryCategory.SOURCE_FEED,
        material_mode=MaterialTransferMode.ADVECTIVE_AQUEOUS,
        volume_rate_l_per_hour=1e308,
        water_density_kg_l=1e308,
        entity_rates_per_hour={ConservedEntity.NA: 0.0},
        current_mixture_advection=False,
        phase=OperatorPhase.EXTERNAL_FEED_AMENDMENT,
        evidence_label=PHYSICS,
    )

    with pytest.raises(AlmondLabError) as exc_info:
        _step(state, duration=0.25, boundary_fluxes=(feed,))

    _assert_mass_numeric_error(exc_info, "boundary_fluxes.feed.water_mass_kg")


def test_advective_concentration_product_preserves_a_finite_mathematical_result() -> None:
    state = _two_tank_state(
        source_volume_l=100.0,
        source_density=1.0,
        source_stocks={ConservedEntity.NA: 1e308},
    )

    result = _step(state, duration=0.25, water_flows=(_flow(rate=40.0),))

    assert result.state.compartments["target"].stocks[ConservedEntity.NA] == pytest.approx(
        1e307
    )


def test_competing_request_sum_overflow_fails_structurally() -> None:
    tracked = frozenset({ConservedEntity.NA})
    state = _state(
        {
            "symplast": _compartment(
                "symplast",
                CompartmentKind.ROOT_SYMPLAST,
                volume_l=1.0,
                water_mass_kg=1.0,
                stocks={ConservedEntity.NA: 1e308},
            ),
            "root": _compartment(
                "root",
                CompartmentKind.ROOT_ZONE,
                volume_l=1.0,
                water_mass_kg=1.0,
                stocks={ConservedEntity.NA: 0.0},
            ),
        },
        tracked,
    )
    events = tuple(
        InternalEntityFlux(
            event_id=f"efflux-{index}",
            source="symplast",
            target="root",
            kind=InternalEntityFluxKind.PLANT_EFFLUX,
            entity=ConservedEntity.NA,
            rate_per_hour=1e308,
            phase=OperatorPhase.PLANT_ION_TRANSITIONS,
            evidence_label=EvidenceLabel.HYPOTHESIS_PRIOR,
        )
        for index in range(8)
    )

    with pytest.raises(AlmondLabError) as exc_info:
        _step(state, duration=0.25, entity_fluxes=events)

    _assert_mass_numeric_error(
        exc_info, "compartments.symplast.requested_stock.na"
    )


def test_rate_duration_accumulation_overflow_fails_at_the_state_delta() -> None:
    state = _state(
        {
            "tank": _compartment(
                "tank",
                CompartmentKind.BLEND_TANK,
                volume_l=1.0,
                water_mass_kg=1.0,
                stocks={ConservedEntity.NA: 1e308},
            )
        },
        frozenset({ConservedEntity.NA}),
    )
    amendment = ExternalBoundaryFlux(
        event_id="amend",
        compartment="tank",
        boundary_id="measured-amendment",
        category=ExternalBoundaryCategory.AMENDMENT,
        material_mode=MaterialTransferMode.ENTITY_ONLY,
        volume_rate_l_per_hour=0.0,
        entity_rates_per_hour={ConservedEntity.NA: 1e308},
        current_mixture_advection=False,
        phase=OperatorPhase.EXTERNAL_FEED_AMENDMENT,
        evidence_label=PHYSICS,
    )

    with pytest.raises(AlmondLabError) as exc_info:
        _step(state, duration=1.0, boundary_fluxes=(amendment,))

    _assert_mass_numeric_error(exc_info, "compartments.tank.stocks.na")


def test_audit_ledger_total_overflow_fails_structurally() -> None:
    state = _state(
        {
            "tank": _compartment(
                "tank",
                CompartmentKind.BLEND_TANK,
                volume_l=1.0,
                water_mass_kg=1.0,
                stocks={ConservedEntity.NA: 0.0},
            )
        },
        frozenset({ConservedEntity.NA}),
    )
    rows = tuple(
        LedgerEntry(
            transaction_id=f"tx:AUDIT:main:{index:012d}",
            event_id=f"amend-{index}",
            kind=LedgerEntryKind.EXTERNAL,
            phase=OperatorPhase.EXTERNAL_FEED_AMENDMENT,
            transfer_mode=MaterialTransferMode.ENTITY_ONLY,
            compartment="tank",
            counterparty="measured-amendment",
            entity=ConservedEntity.NA,
            amount=1e308,
            unit=StockUnit.MMOL,
            evidence_label=PHYSICS,
            boundary_category=ExternalBoundaryCategory.AMENDMENT,
        )
        for index in range(2)
    )

    with pytest.raises(AlmondLabError) as exc_info:
        audit_ledger(state, state, rows)

    _assert_mass_numeric_error(exc_info, "audit.ledger.na")


def test_closed_form_overflow_fails_structurally() -> None:
    with pytest.raises(AlmondLabError) as exc_info:
        closed_form_tank_concentration(0.0, 0.0, 1e308, 1.0, 0.0, 1e308)

    _assert_mass_numeric_error(exc_info, "closed_form_tank_concentration")


def test_finite_extremes_remain_supported() -> None:
    tank = _compartment(
        "tank",
        CompartmentKind.BLEND_TANK,
        volume_l=1e308,
        water_mass_kg=1e308,
        stocks={ConservedEntity.NA: 1e308},
    )
    state = _state({"tank": tank}, frozenset({ConservedEntity.NA}))

    assert tank.density_kg_l == 1.0
    assert tank.concentration(ConservedEntity.NA) == 1.0
    assert state.total_volume_l() == 1e308
    assert state.total_water_mass_kg() == 1e308
    assert state.total_stock(ConservedEntity.NA) == 1e308
    assert closed_form_tank_concentration(
        1.0, 0.0, 1e308, 1.0, 0.0, 1e-308
    ) == pytest.approx(2.0)


def test_fixture_authoring_and_packaged_copies_are_byte_identical() -> None:
    for name in (
        "entity_units_density.yaml",
        "internal_plant_flux_cap.yaml",
        "chained_transaction_ids.yaml",
        "no_purge.yaml",
        "sufficient_purge.yaml",
    ):
        authored = (FIXTURES / name).read_bytes()
        packaged = (PACKAGED_FIXTURES / name).read_bytes()
        assert sha256(authored).hexdigest() == sha256(packaged).hexdigest()
        assert authored == packaged


def _analytic_state(initial: dict[str, object]) -> NetworkState:
    tank = initial["tank"]
    return _state(
        {
            "tank": _compartment(
                "tank",
                CompartmentKind.BLEND_TANK,
                volume_l=tank["volume_l"],
                water_mass_kg=tank["water_mass_kg"],
                stocks={ConservedEntity.NA: tank["stocks"]["na"]},
                empty_reference_density_kg_l=tank["empty_reference_density_kg_l"],
            )
        },
        frozenset({ConservedEntity.NA}),
    )


def test_no_purge_fixture_reaches_hand_derived_physical_stop() -> None:
    case = _fixture("no_purge.yaml")
    state = _analytic_state(case["initial"])
    source = case["source_flux"]
    flux = ExternalBoundaryFlux(
        event_id=source["event_id"],
        compartment="tank",
        boundary_id=source["boundary_id"],
        category=ExternalBoundaryCategory(source["category"]),
        material_mode=MaterialTransferMode(source["material_mode"]),
        volume_rate_l_per_hour=0.0,
        entity_rates_per_hour={ConservedEntity.NA: source["na_mmol_per_hour"]},
        current_mixture_advection=False,
        phase=OperatorPhase(source["phase"]),
        evidence_label=PHYSICS,
    )
    elapsed = 0.0
    cursor = LedgerCursor("NO_PURGE", "main")
    while state.concentration("tank", ConservedEntity.NA) < case["stop_concentration_mmol_l"]:
        result = _step(
            state,
            duration=case["sample_hours"],
            boundary_fluxes=(flux,),
            cursor=cursor,
        )
        state = result.state
        cursor = result.next_cursor
        elapsed += case["sample_hours"]

    assert elapsed == pytest.approx(case["expected_stop_hours"], rel=1e-12)
    expected = closed_form_tank_concentration(
        case["c0"], case["c_in"], case["m_dot"], case["volume"], 0.0, elapsed
    )
    assert state.concentration("tank", ConservedEntity.NA) == pytest.approx(expected)


def test_sufficient_purge_fixture_converges_to_closed_form_trajectory() -> None:
    case = _fixture("sufficient_purge.yaml")
    state = _analytic_state(case["initial"])
    source = case["influx"]
    purge_data = case["purge_flux"]
    influx = ExternalBoundaryFlux(
        event_id=source["event_id"],
        compartment="tank",
        boundary_id=source["boundary_id"],
        category=ExternalBoundaryCategory(source["category"]),
        material_mode=MaterialTransferMode.ADVECTIVE_AQUEOUS,
        volume_rate_l_per_hour=source["volume_l_per_hour"],
        water_density_kg_l=source["water_density_kg_l"],
        entity_rates_per_hour={ConservedEntity.NA: source["na_mmol_per_hour"]},
        current_mixture_advection=False,
        phase=OperatorPhase.EXTERNAL_FEED_AMENDMENT,
        evidence_label=PHYSICS,
    )
    purge = ExternalBoundaryFlux(
        event_id=purge_data["event_id"],
        compartment="tank",
        boundary_id=purge_data["boundary_id"],
        category=ExternalBoundaryCategory.PURGE_OR_DISCHARGE,
        material_mode=MaterialTransferMode.ADVECTIVE_AQUEOUS,
        volume_rate_l_per_hour=purge_data["volume_l_per_hour"],
        entity_rates_per_hour={},
        current_mixture_advection=True,
        phase=OperatorPhase.PURGE_DISPOSAL,
        evidence_label=PHYSICS,
    )
    cursor = LedgerCursor("PURGE", "main")
    observed = []
    elapsed = 0.0
    for _ in range(case["samples"]):
        result = _step(
            state,
            duration=case["sample_hours"],
            boundary_fluxes=(influx, purge),
            cursor=cursor,
            max_substep_hours=case["max_substep_hours"],
        )
        state = result.state
        cursor = result.next_cursor
        elapsed += case["sample_hours"]
        observed.append((elapsed, state.concentration("tank", ConservedEntity.NA)))

    for time, concentration in observed:
        expected = closed_form_tank_concentration(
            case["c0"], case["c_in"], case["m_dot"], case["volume"], case["purge"], time
        )
        assert concentration == pytest.approx(expected, rel=case["relative_tolerance"], abs=1e-8)
    steady_state = case["c_in"] + case["m_dot"] / case["purge"]
    expected_distance = abs(case["c0"] - steady_state) * exp(-12.0)
    assert abs(observed[-1][1] - steady_state) == pytest.approx(
        expected_distance, abs=case["terminal_absolute_tolerance"]
    )


def test_step_halving_reduces_split_phase_purge_error() -> None:
    case = _fixture("sufficient_purge.yaml")
    state = _analytic_state(case["initial"])
    influx_data = case["influx"]
    purge_data = case["purge_flux"]
    influx = ExternalBoundaryFlux(
        event_id="feed",
        compartment="tank",
        boundary_id="feed-water",
        category=ExternalBoundaryCategory.SOURCE_FEED,
        material_mode=MaterialTransferMode.ADVECTIVE_AQUEOUS,
        volume_rate_l_per_hour=2.0,
        water_density_kg_l=0.997,
        entity_rates_per_hour={ConservedEntity.NA: 6.0},
        current_mixture_advection=False,
        phase=OperatorPhase.EXTERNAL_FEED_AMENDMENT,
        evidence_label=PHYSICS,
    )
    purge = ExternalBoundaryFlux(
        event_id="purge",
        compartment="tank",
        boundary_id="purge-water",
        category=ExternalBoundaryCategory.PURGE_OR_DISCHARGE,
        material_mode=MaterialTransferMode.ADVECTIVE_AQUEOUS,
        volume_rate_l_per_hour=2.0,
        entity_rates_per_hour={},
        current_mixture_advection=True,
        phase=OperatorPhase.PURGE_DISPOSAL,
        evidence_label=PHYSICS,
    )
    oracle = closed_form_tank_concentration(5.0, 3.0, 0.0, 10.0, 2.0, 1.0)
    coarse = _step(
        state,
        duration=1.0,
        boundary_fluxes=(influx, purge),
        max_substep_hours=0.25,
    )
    fine = _step(
        state,
        duration=1.0,
        boundary_fluxes=(influx, purge),
        max_substep_hours=0.125,
    )
    assert abs(fine.state.concentration("tank", ConservedEntity.NA) - oracle) < abs(
        coarse.state.concentration("tank", ConservedEntity.NA) - oracle
    )


@given(
    volume=st.floats(min_value=1.0, max_value=1e5, allow_nan=False, allow_infinity=False),
    stock=st.floats(min_value=0.0, max_value=1e8, allow_nan=False, allow_infinity=False),
    fraction=st.floats(min_value=1e-6, max_value=0.9, allow_nan=False, allow_infinity=False),
)
def test_property_internal_transfer_preserves_nonnegativity_and_both_carriers(
    volume: float, stock: float, fraction: float
) -> None:
    state = _two_tank_state(
        source_volume_l=volume,
        source_density=0.997,
        source_stocks={ConservedEntity.NA: stock},
    )
    result = _step(
        state,
        duration=1.0,
        water_flows=(_flow(rate=volume * fraction),),
    )
    assert min(result.state.all_values()) >= -1e-12
    assert result.state.total_stock(ConservedEntity.NA) == pytest.approx(stock, rel=1e-10, abs=1e-10)
    assert result.state.total_water_mass_kg() == pytest.approx(0.997 * volume, rel=1e-10)
    assert result.state.total_volume_l() == pytest.approx(volume, rel=1e-10)
    assert audit_ledger(state, result.state, result.ledger).balanced


@pytest.mark.parametrize(
    "values",
    [
        (0.0, 0.0, 1.0, 10.0, 0.0, 5.0, 0.5),
        (1.0, 2.0, 3.0, 4.0, 0.0, 8.0, 7.0),
        (5.0, 3.0, 0.0, 10.0, 2.0, 5.0, 3.7357588823428847),
    ],
)
def test_closed_form_oracle_uses_hand_derived_literals(values: tuple[float, ...]) -> None:
    *arguments, expected = values
    assert closed_form_tank_concentration(*arguments) == pytest.approx(expected)


def test_mass_balance_reexports_shared_ledger_entry() -> None:
    from almondlab.mass_balance import LedgerEntry as MassLedgerEntry

    assert MassLedgerEntry is LedgerEntry
    assert isinstance(MappingProxyType({}), MappingProxyType)
