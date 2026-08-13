from dataclasses import FrozenInstanceError, replace
from math import exp, isclose
from pathlib import Path

import pytest
import yaml
from hypothesis import given, strategies as st

from almondlab.errors import AlmondLabError
from almondlab.contracts import ConservedEntity, EvidenceLabel
from almondlab.mass_balance import (
    ExternalFlux,
    Flow,
    LedgerEntry,
    NetworkState,
    audit_ledger,
    closed_form_tank_concentration,
    step_state,
)


FIXTURES = Path(__file__).parent / "fixtures"


def _fixture(name: str) -> dict[str, object]:
    return yaml.safe_load((FIXTURES / name).read_text())


def test_internal_flow_is_equal_debit_and_credit() -> None:
    state = NetworkState.from_dict(
        volumes_l={"source": 10.0, "product": 0.0},
        stocks_mmol={"source": {"na": 100.0}, "product": {"na": 0.0}},
    )

    result = step_state(state, [Flow("source", "product", 1.0)], [], 1.0)

    assert isclose(result.state.total_stock("na"), 100.0, rel_tol=1e-12)
    assert result.state.volumes_l == {"source": 9.0, "product": 1.0}
    internal = [row for row in result.ledger if row.kind == "internal"]
    for transaction_id in {row.transaction_id for row in internal}:
        rows = [row for row in internal if row.transaction_id == transaction_id]
        for quantity in {row.quantity for row in rows}:
            pair = [row for row in rows if row.quantity == quantity]
            assert len(pair) == 2
            assert pair[0].amount + pair[1].amount == pytest.approx(0.0, abs=1e-14)
    audit = audit_ledger(state, result.state, result.ledger)
    assert audit.relative_residual("water") <= 1e-10
    assert audit.relative_residual("na") <= 1e-10


def test_state_is_immutable_including_nested_input_mappings() -> None:
    volumes = {"tank": 5.0}
    stocks = {"tank": {"na": 2.0}}
    state = NetworkState.from_dict(volumes, stocks, {"tank": "loop-a"})
    volumes["tank"] = 99.0
    stocks["tank"]["na"] = 99.0

    assert state.volumes_l["tank"] == 5.0
    assert state.stocks_mmol["tank"]["na"] == 2.0
    with pytest.raises(TypeError):
        state.stocks_mmol["tank"]["na"] = 3.0  # type: ignore[index]
    with pytest.raises(FrozenInstanceError):
        state.volumes_l = {}  # type: ignore[misc]


def test_cross_loop_flow_requires_physical_transfer_identifier() -> None:
    state = NetworkState.from_dict(
        {"well": 10.0, "plant": 0.0},
        {"well": {"na": 10.0}, "plant": {"na": 0.0}},
        {"well": "source-loop", "plant": "treatment-loop"},
    )

    with pytest.raises(AlmondLabError) as exc_info:
        step_state(state, [Flow("well", "plant", 1.0)], [], 0.25)

    assert exc_info.value.code == "CROSS_LOOP_TRANSFER"
    recorded = step_state(
        state,
        [Flow("well", "plant", 1.0, physical_transfer_id="pipe-7")],
        [],
        0.25,
    )
    assert recorded.state.volumes_l["plant"] == pytest.approx(0.25)


def test_external_flux_requires_named_boundary() -> None:
    state = NetworkState.from_dict({"tank": 1.0}, {"tank": {"na": 1.0}})
    with pytest.raises(AlmondLabError) as exc_info:
        step_state(state, [], [ExternalFlux("tank", "", 1.0)], 0.25)
    assert exc_info.value.code == "EXTERNAL_BOUNDARY_REQUIRED"


def test_one_day_water_fixture_is_a_hand_literal() -> None:
    case = _fixture("water_one_day.yaml")
    state = NetworkState.from_dict(**case["initial"])
    flow = Flow(**case["flow"])

    result = step_state(state, [flow], [], case["duration_hours"])

    assert dict(result.state.volumes_l) == pytest.approx(case["expected_volumes_l"])
    assert result.substeps >= 96
    assert audit_ledger(state, result.state, result.ledger).balanced


def test_every_registered_entity_is_advected_at_source_concentration() -> None:
    case = _fixture("ions_conservative.yaml")
    state = NetworkState.from_dict(**case["initial"])

    result = step_state(state, [Flow(**case["flow"])], [], case["duration_hours"])

    for compartment, expected in case["expected_stocks_mmol"].items():
        assert dict(result.state.stocks_mmol[compartment]) == pytest.approx(expected)
    audit = audit_ledger(state, result.state, result.ledger)
    assert audit.quantities == frozenset(entity.value for entity in ConservedEntity)
    assert all(audit.relative_residual(item) <= 1e-10 for item in audit.quantities)


def test_excessive_fraction_is_subdivided_and_not_clipped() -> None:
    state = NetworkState.from_dict(
        {"source": 10.0, "target": 0.0},
        {"source": {"na": 20.0}, "target": {"na": 0.0}},
    )

    result = step_state(state, [Flow("source", "target", 8.0)], [], 1.0)

    assert result.substeps > 4
    assert result.state.volumes_l["source"] == pytest.approx(2.0)
    assert result.state.volumes_l["target"] == pytest.approx(8.0)
    assert result.state.total_stock("na") == pytest.approx(20.0)


def test_nonfinite_and_materially_negative_states_are_rejected() -> None:
    with pytest.raises(AlmondLabError) as nonfinite:
        NetworkState.from_dict({"tank": float("nan")}, {"tank": {"na": 0.0}})
    assert nonfinite.value.code == "NONFINITE_STATE"
    with pytest.raises(AlmondLabError) as negative:
        NetworkState.from_dict({"tank": 1.0}, {"tank": {"na": -2e-12}})
    assert negative.value.code == "NEGATIVE_STATE"


def test_corrupted_ledger_is_detected_independently_for_one_entity() -> None:
    state = NetworkState.from_dict(
        {"a": 10.0, "b": 0.0},
        {"a": {"na": 20.0, "cl": 30.0}, "b": {"na": 0.0, "cl": 0.0}},
    )
    result = step_state(state, [Flow("a", "b", 1.0)], [], 0.25)
    ledger = list(result.ledger)
    index = next(i for i, row in enumerate(ledger) if row.quantity == "na")
    ledger[index] = replace(ledger[index], amount=ledger[index].amount + 0.01)

    audit = audit_ledger(state, result.state, ledger)

    assert audit.relative_residual("na") > 1e-10
    assert audit.relative_residual("cl") <= 1e-10
    assert audit.relative_residual("water") <= 1e-10
    assert not audit.balanced


def test_audit_rejects_internal_transaction_with_both_entity_rows_deleted() -> None:
    state = NetworkState.from_dict(
        {"a": 10.0, "b": 0.0},
        {"a": {"na": 20.0}, "b": {"na": 0.0}},
    )
    result = step_state(state, [Flow("a", "b", 1.0)], [], 0.25)
    ledger = [row for row in result.ledger if row.quantity != "na"]

    audit = audit_ledger(state, result.state, ledger)

    assert audit.relative_residual("na") <= 1e-10
    assert audit.internal_transaction_errors
    assert not audit.balanced


def test_audit_reconciles_complete_internal_deletion_by_compartment() -> None:
    state = NetworkState.from_dict(
        {"z_source": 10.0, "a_target": 0.0},
        {
            "z_source": {"na": 20.0},
            "a_target": {"na": 0.0},
        },
    )
    result = step_state(state, [Flow("z_source", "a_target", 1.0)], [], 0.25)

    audit = audit_ledger(state, result.state, [])

    assert audit.relative_residual("water") <= 1e-10
    assert audit.relative_residual("na") <= 1e-10
    assert audit.relative_compartment_residual("z_source", "water") > 1e-10
    assert audit.relative_compartment_residual("a_target", "na") > 1e-10
    assert not audit.balanced


@pytest.mark.parametrize("corruption", ["amount", "endpoints"])
def test_audit_rejects_consistent_paired_corruption_by_compartment(
    corruption: str,
) -> None:
    state = NetworkState.from_dict(
        {"source": 10.0, "target": 0.0, "decoy": 0.0},
        {
            "source": {"na": 20.0},
            "target": {"na": 0.0},
            "decoy": {"na": 0.0},
        },
    )
    result = step_state(state, [Flow("source", "target", 1.0)], [], 0.25)
    ledger = list(result.ledger)
    for index, row in enumerate(ledger):
        if corruption == "amount":
            ledger[index] = replace(row, amount=row.amount / 2.0)
        elif row.compartment == "source":
            ledger[index] = replace(row, counterparty="decoy")
        else:
            ledger[index] = replace(
                row,
                compartment="decoy",
                counterparty="source",
            )

    audit = audit_ledger(state, result.state, ledger)

    assert audit.relative_residual("water") <= 1e-10
    assert audit.relative_residual("na") <= 1e-10
    assert audit.internal_transaction_errors == ()
    assert any(
        audit.relative_compartment_residual(compartment, quantity) > 1e-10
        for compartment in state.volumes_l
        for quantity in ("water", "na")
    )
    assert not audit.balanced


@pytest.mark.parametrize("corruption", ["transaction_id", "counterparty", "unit"])
def test_audit_rejects_corrupted_internal_pair_metadata(corruption: str) -> None:
    state = NetworkState.from_dict(
        {"a": 10.0, "b": 0.0, "c": 0.0},
        {"a": {"na": 20.0}, "b": {"na": 0.0}, "c": {"na": 0.0}},
    )
    result = step_state(state, [Flow("a", "b", 1.0)], [], 0.25)
    ledger = list(result.ledger)
    index = next(i for i, row in enumerate(ledger) if row.quantity == "na" and row.amount > 0)
    changes: dict[str, object]
    if corruption == "transaction_id":
        changes = {"transaction_id": "internal:99:99"}
    elif corruption == "counterparty":
        changes = {"counterparty": "c"}
    else:
        changes = {"unit": "L"}
    ledger[index] = replace(ledger[index], **changes)

    audit = audit_ledger(state, result.state, ledger)

    assert audit.internal_transaction_errors
    assert not audit.balanced


@pytest.mark.parametrize("field", ["compartment", "counterparty"])
def test_audit_rejects_unknown_internal_endpoint(field: str) -> None:
    state = NetworkState.from_dict(
        {"source": 10.0, "target": 0.0},
        {"source": {"na": 20.0}, "target": {"na": 0.0}},
    )
    result = step_state(state, [Flow("source", "target", 1.0)], [], 0.25)
    ledger = list(result.ledger)
    ledger[0] = replace(ledger[0], **{field: "ghost"})

    with pytest.raises(AlmondLabError) as exc_info:
        audit_ledger(state, result.state, ledger)

    assert exc_info.value.code == "LEDGER_UNKNOWN_COMPARTMENT"


def test_audit_rejects_unknown_external_owning_compartment() -> None:
    state = NetworkState.from_dict({"tank": 10.0}, {"tank": {"na": 20.0}})
    result = step_state(
        state,
        [],
        [ExternalFlux("tank", "rain", 1.0, {"na": 2.0})],
        0.25,
    )
    ledger = [replace(row, compartment="ghost") for row in result.ledger]

    with pytest.raises(AlmondLabError) as exc_info:
        audit_ledger(state, result.state, ledger)

    assert exc_info.value.code == "LEDGER_UNKNOWN_COMPARTMENT"


def test_audit_accepts_valid_internal_pairs_and_explicit_evidence() -> None:
    state = NetworkState.from_dict(
        {"a": 10.0, "b": 0.0},
        {"a": {"na": 20.0}, "b": {"na": 0.0}},
    )
    result = step_state(
        state,
        [Flow("a", "b", 1.0, physical_transfer_id="pipe-a")],
        [ExternalFlux("a", "rain", 0.0, {"na": 0.1})],
        0.25,
    )

    assert all(
        row.evidence_label is EvidenceLabel.PHYSICS_CONSTRAINED
        for row in result.ledger
    )
    audit = audit_ledger(state, result.state, result.ledger)
    assert audit.internal_transaction_errors == ()
    assert audit.balanced


@pytest.mark.parametrize("corruption", ["direction", "physical_transfer_id"])
def test_audit_requires_consistent_metadata_across_transaction_quantities(
    corruption: str,
) -> None:
    state = NetworkState.from_dict(
        {"a": 10.0, "b": 0.0},
        {"a": {"na": 20.0}, "b": {"na": 0.0}},
        {"a": "loop-a", "b": "loop-b"},
    )
    result = step_state(
        state,
        [Flow("a", "b", 1.0, physical_transfer_id="pipe-a")],
        [],
        0.25,
    )
    ledger = list(result.ledger)
    for index, row in enumerate(ledger):
        if row.quantity != "na":
            continue
        if corruption == "direction":
            ledger[index] = replace(
                row,
                compartment=row.counterparty,
                counterparty=row.compartment,
            )
        else:
            ledger[index] = replace(row, physical_transfer_id="pipe-b")

    audit = audit_ledger(state, result.state, ledger)

    assert audit.internal_transaction_errors
    assert not audit.balanced


def test_zero_stock_pair_inherits_water_direction_without_lexical_inference() -> None:
    state = NetworkState.from_dict(
        {"z_source": 10.0, "a_target": 0.0},
        {
            "z_source": {"na": 0.0},
            "a_target": {"na": 0.0},
        },
    )
    result = step_state(state, [Flow("z_source", "a_target", 1.0)], [], 0.25)

    audit = audit_ledger(state, result.state, result.ledger)

    assert audit.internal_transaction_errors == ()
    assert audit.relative_compartment_residual("z_source", "na") <= 1e-10
    assert audit.balanced


def test_ledger_entry_requires_explicit_evidence_label() -> None:
    with pytest.raises(TypeError):
        # Missing provenance is a construction error, not a physics default.
        LedgerEntry("tx", "a", "b", "water", -1.0, "L", "internal")  # type: ignore[call-arg]

    row = LedgerEntry(
        "tx",
        "a",
        "b",
        "water",
        -1.0,
        "L",
        "internal",
        EvidenceLabel.PHYSICS_CONSTRAINED,
    )
    assert row.evidence_label is EvidenceLabel.PHYSICS_CONSTRAINED


def test_no_purge_fixture_reaches_physical_censored_stop() -> None:
    case = _fixture("no_purge.yaml")
    state = NetworkState.from_dict(**case["initial"])
    flux = ExternalFlux(**case["source_flux"])
    elapsed = 0.0
    while state.concentration("tank", "na") < case["stop_concentration_mmol_l"]:
        result = step_state(state, [], [flux], case["sample_hours"])
        state = result.state
        elapsed += case["sample_hours"]

    assert elapsed == pytest.approx(case["expected_stop_hours"], rel=1e-6)
    expected = closed_form_tank_concentration(
        case["c0"], case["c_in"], case["m_dot"], case["volume"], 0.0, elapsed
    )
    assert state.concentration("tank", "na") == pytest.approx(expected, rel=1e-12)
    assert state.concentration("tank", "na") == pytest.approx(2.0 * case["c0"])


def test_sufficient_purge_fixture_matches_closed_form_trajectory() -> None:
    case = _fixture("sufficient_purge.yaml")
    state = NetworkState.from_dict(**case["initial"])
    influx = ExternalFlux(**case["influx"])
    purge = ExternalFlux(**case["purge_flux"])
    concentrations = []
    elapsed = 0.0
    for _ in range(case["samples"]):
        result = step_state(state, [], [influx, purge], case["sample_hours"])
        state = result.state
        elapsed += case["sample_hours"]
        concentrations.append((elapsed, state.concentration("tank", "na")))

    for time, observed in concentrations:
        expected = closed_form_tank_concentration(
            case["c0"],
            case["c_in"],
            case["m_dot"],
            case["volume"],
            case["purge"],
            time,
        )
        assert observed == pytest.approx(expected, rel=1e-5, abs=1e-8)
    c_ss = case["c_in"] + case["m_dot"] / case["purge"]
    terminal_distance = abs(concentrations[-1][1] - c_ss)
    expected_distance = abs(case["c0"] - c_ss) * exp(-12.0)
    assert terminal_distance == pytest.approx(expected_distance, abs=1e-6)


def test_step_halving_converges_toward_purge_oracle() -> None:
    state = NetworkState.from_dict({"tank": 10.0}, {"tank": {"na": 50.0}})
    fluxes = [
        ExternalFlux("tank", "feed", 2.0, {"na": 6.0}),
        ExternalFlux("tank", "discharge", -2.0),
    ]
    oracle = closed_form_tank_concentration(5.0, 3.0, 0.0, 10.0, 2.0, 1.0)

    coarse = step_state(state, [], fluxes, 1.0, max_substep_hours=0.25)
    fine = step_state(state, [], fluxes, 1.0, max_substep_hours=0.125)

    coarse_error = abs(coarse.state.concentration("tank", "na") - oracle)
    fine_error = abs(fine.state.concentration("tank", "na") - oracle)
    assert fine_error < coarse_error


@given(
    volume=st.floats(min_value=1.0, max_value=1e5, allow_nan=False, allow_infinity=False),
    stock=st.floats(min_value=0.0, max_value=1e8, allow_nan=False, allow_infinity=False),
    fraction=st.floats(min_value=0.0, max_value=0.9, allow_nan=False, allow_infinity=False),
)
def test_property_internal_transfer_preserves_positivity_and_stock(
    volume: float, stock: float, fraction: float
) -> None:
    state = NetworkState.from_dict(
        {"source": volume, "target": 0.0},
        {"source": {"na": stock}, "target": {"na": 0.0}},
    )

    result = step_state(state, [Flow("source", "target", volume * fraction)], [], 1.0)

    assert min(result.state.all_values()) >= -1e-12
    assert result.state.total_stock("na") == pytest.approx(stock, rel=1e-10, abs=1e-10)
    for transaction_id in {row.transaction_id for row in result.ledger}:
        rows = [row for row in result.ledger if row.transaction_id == transaction_id]
        for quantity in {row.quantity for row in rows}:
            assert sum(row.amount for row in rows if row.quantity == quantity) == pytest.approx(
                0.0, abs=1e-10
            )


def test_external_reaction_sink_is_capped_by_available_stock() -> None:
    state = NetworkState.from_dict({"tank": 10.0}, {"tank": {"na": 1.0}})
    sink = ExternalFlux("tank", "uptake", 0.0, {"na": -100.0})

    result = step_state(state, [], [sink], 1.0)

    assert result.state.stocks_mmol["tank"]["na"] == pytest.approx(0.0)
    assert min(result.state.all_values()) >= -1e-12


def test_one_boundary_flux_audits_advective_loss_and_declared_source_once() -> None:
    state = NetworkState.from_dict({"tank": 10.0}, {"tank": {"na": 50.0}})
    combined = ExternalFlux("tank", "process", -1.0, {"na": 2.0})

    result = step_state(state, [], [combined], 0.25)
    entity_rows = [row for row in result.ledger if row.quantity == "na"]

    assert len(entity_rows) == 2
    assert {1 if row.amount > 0.0 else -1 for row in entity_rows} == {-1, 1}
    assert audit_ledger(state, result.state, result.ledger).relative_residual("na") <= 1e-10


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
