from __future__ import annotations

from dataclasses import FrozenInstanceError, replace
from hashlib import sha256
from importlib import resources
from math import isclose
from pathlib import Path
from types import MappingProxyType

import pytest
import yaml
from hypothesis import given, strategies as st

import almondlab.treatment as treatment_module

from almondlab.contracts import (
    ConservedEntity,
    EvidenceLabel,
    ExternalBoundaryCategory,
    LedgerCursor,
    LedgerEntryKind,
    MaterialTransferMode,
    OperatorPhase,
    StockUnit,
)
from almondlab.errors import AlmondLabError
from almondlab.treatment import (
    FormulaResolvedAmendment,
    ROParameters,
    RORemovalResult,
    ROResult,
    RemineralizationResult,
    TreatmentStream,
    audit_ro_ledger,
    remineralize,
    ro_split,
)


FIXTURE_PATH = Path(__file__).parent / "fixtures" / "ro_remineralization.yaml"


def _fixture() -> dict[str, object]:
    return yaml.safe_load(FIXTURE_PATH.read_bytes())


def _stocks(values: dict[str, float]) -> dict[ConservedEntity, float]:
    return {ConservedEntity(key): value for key, value in values.items()}


def _feed(
    *,
    label: EvidenceLabel = EvidenceLabel.PHYSICS_CONSTRAINED,
    stocks: dict[ConservedEntity, float] | None = None,
) -> TreatmentStream:
    return TreatmentStream(
        stream_id="ro-feed",
        volume_l=100.0,
        water_mass_kg=99.7,
        stocks=stocks
        if stocks is not None
        else {
            ConservedEntity.NA: 5000.0,
            ConservedEntity.ALKALINITY: 100.0,
        },
        evidence_label=label,
    )


def _parameters(
    *,
    recovery: float = 0.60,
    label: EvidenceLabel = EvidenceLabel.PHYSICS_CONSTRAINED,
    rejection: dict[ConservedEntity, float] | None = None,
) -> ROParameters:
    return ROParameters(
        model_id="ro-bench",
        version="1.0.0",
        recovery=recovery,
        rejection=rejection
        if rejection is not None
        else {
            ConservedEntity.NA: 0.95,
            ConservedEntity.ALKALINITY: 0.50,
        },
        evidence_label=label,
    )


def _split(
    *,
    feed: TreatmentStream | None = None,
    parameters: ROParameters | None = None,
    cursor: LedgerCursor | None = None,
) -> ROResult:
    return ro_split(
        feed or _feed(),
        parameters or _parameters(),
        permeate_stream_id="ro-permeate",
        concentrate_stream_id="ro-concentrate",
        cursor=cursor or LedgerCursor("run-1", "treatment", 7),
    )


def _amendment(
    *, label: EvidenceLabel = EvidenceLabel.PHYSICS_CONSTRAINED
) -> FormulaResolvedAmendment:
    return FormulaResolvedAmendment(
        dose_id="mineral-dose",
        water_volume_l=2.0,
        water_density_kg_l=1.0,
        stock_additions={
            ConservedEntity.NA: 10.0,
            ConservedEntity.ALKALINITY: 6.0,
        },
        evidence_label=label,
    )


def test_exact_fixture_mirror_and_hand_oracle() -> None:
    test_bytes = FIXTURE_PATH.read_bytes()
    package_bytes = (
        resources.files("almondlab.resources")
        .joinpath("fixtures/ro_remineralization.yaml")
        .read_bytes()
    )
    assert test_bytes == package_bytes
    assert sha256(test_bytes).hexdigest() == sha256(package_bytes).hexdigest()

    fixture = _fixture()
    feed_data = fixture["feed"]
    parameter_data = fixture["parameters"]
    expected_ro = fixture["expected_ro"]
    amendment_data = fixture["amendment"]
    expected_final = fixture["expected_final"]
    assert isinstance(feed_data, dict)
    assert isinstance(parameter_data, dict)
    assert isinstance(expected_ro, dict)
    assert isinstance(amendment_data, dict)
    assert isinstance(expected_final, dict)
    assert feed_data == {
        "stream_id": "ro-feed",
        "volume_l": 100.0,
        "water_density_kg_l": 0.997,
        "water_mass_kg": 99.7,
        "stocks": {"na": 5000.0, "alkalinity": 100.0},
    }
    assert parameter_data == {
        "model_id": "ro-bench",
        "version": "1.0.0",
        "recovery": 0.60,
        "rejection": {"na": 0.95, "alkalinity": 0.50},
    }
    assert expected_ro == {
        "permeate": {
            "stream_id": "ro-permeate",
            "volume_l": 60.0,
            "water_mass_kg": 59.82,
            "stocks": {"na": 150.0, "alkalinity": 30.0},
        },
        "concentrate": {
            "stream_id": "ro-concentrate",
            "volume_l": 40.0,
            "water_mass_kg": 39.88,
            "stocks": {"na": 4850.0, "alkalinity": 70.0},
        },
        "selectively_rejected": {"na": 2850.0, "alkalinity": 30.0},
    }
    assert amendment_data == {
        "dose_id": "mineral-dose",
        "water_volume_l": 2.0,
        "water_density_kg_l": 1.0,
        "stock_additions": {"na": 10.0, "alkalinity": 6.0},
    }
    assert expected_final == {
        "stream_id": "final-product",
        "volume_l": 62.0,
        "water_mass_kg": 61.82,
        "density_kg_l": 0.9970967741935484,
        "stocks": {"na": 160.0, "alkalinity": 36.0},
    }
    feed = TreatmentStream(
        stream_id=feed_data["stream_id"],
        volume_l=feed_data["volume_l"],
        water_mass_kg=feed_data["water_mass_kg"],
        stocks=_stocks(feed_data["stocks"]),
        evidence_label=EvidenceLabel.PHYSICS_CONSTRAINED,
    )
    parameters = ROParameters(
        model_id=parameter_data["model_id"],
        version=parameter_data["version"],
        recovery=parameter_data["recovery"],
        rejection=_stocks(parameter_data["rejection"]),
        evidence_label=EvidenceLabel.PHYSICS_CONSTRAINED,
    )

    result = _split(feed=feed, parameters=parameters)

    assert feed.density_kg_l == feed_data["water_density_kg_l"] == 0.997
    assert result.permeate.stream_id == expected_ro["permeate"]["stream_id"]
    assert result.permeate.volume_l == expected_ro["permeate"]["volume_l"] == 60.0
    assert result.permeate.water_mass_kg == expected_ro["permeate"]["water_mass_kg"] == 59.82
    assert result.permeate.stocks == pytest.approx({
        ConservedEntity.NA: 150.0,
        ConservedEntity.ALKALINITY: 30.0,
    }, rel=1e-12, abs=1e-12)
    assert result.permeate.stocks == pytest.approx(
        _stocks(expected_ro["permeate"]["stocks"]), rel=1e-12, abs=1e-12
    )
    assert result.concentrate.stream_id == expected_ro["concentrate"]["stream_id"]
    assert result.concentrate.volume_l == expected_ro["concentrate"]["volume_l"] == 40.0
    assert result.concentrate.water_mass_kg == expected_ro["concentrate"]["water_mass_kg"] == 39.88
    assert result.concentrate.stocks == pytest.approx({
        ConservedEntity.NA: 4850.0,
        ConservedEntity.ALKALINITY: 70.0,
    }, rel=1e-12, abs=1e-12)
    assert result.concentrate.stocks == pytest.approx(
        _stocks(expected_ro["concentrate"]["stocks"]), rel=1e-12, abs=1e-12
    )
    assert result.removal.selectively_rejected_stock == pytest.approx({
        ConservedEntity.NA: 2850.0,
        ConservedEntity.ALKALINITY: 30.0,
    }, rel=1e-12, abs=1e-12)
    assert result.removal.selectively_rejected_stock == pytest.approx(
        _stocks(expected_ro["selectively_rejected"]), rel=1e-12, abs=1e-12
    )
    assert result.removal.destination_stream_id == "ro-concentrate"
    assert result.removal.destination_stock is result.concentrate.stocks
    assert result.next_cursor == LedgerCursor("run-1", "treatment", 9)

    dose = FormulaResolvedAmendment(
        dose_id=amendment_data["dose_id"],
        water_volume_l=amendment_data["water_volume_l"],
        water_density_kg_l=amendment_data["water_density_kg_l"],
        stock_additions=_stocks(amendment_data["stock_additions"]),
        evidence_label=EvidenceLabel.PHYSICS_CONSTRAINED,
    )
    final = remineralize(
        result.permeate,
        (dose,),
        output_stream_id=expected_final["stream_id"],
        cursor=result.next_cursor,
    )
    assert final.after.stream_id == expected_final["stream_id"] == "final-product"
    assert final.after.volume_l == expected_final["volume_l"] == 62.0
    assert final.after.water_mass_kg == expected_final["water_mass_kg"] == 61.82
    assert final.after.density_kg_l == expected_final["density_kg_l"] == 0.9970967741935484
    assert final.after.stocks == pytest.approx({
        ConservedEntity.NA: 160.0,
        ConservedEntity.ALKALINITY: 36.0,
    }, rel=1e-12, abs=1e-12)
    assert final.after.stocks == pytest.approx(
        _stocks(expected_final["stocks"]), rel=1e-12, abs=1e-12
    )
    assert final.next_cursor == LedgerCursor("run-1", "treatment", 10)


def test_ro_ledger_has_two_complete_paired_transactions_in_canonical_order() -> None:
    result = _split()

    assert len(result.ledger) == 12
    assert [row.transaction_id for row in result.ledger] == [
        *("tx:run-1:treatment:000000000007",) * 6,
        *("tx:run-1:treatment:000000000008",) * 6,
    ]
    for offset, destination in ((0, "ro-permeate"), (6, "ro-concentrate")):
        rows = result.ledger[offset : offset + 6]
        assert [(row.entity, row.compartment, row.counterparty) for row in rows] == [
            (ConservedEntity.WATER, "ro-feed", destination),
            (ConservedEntity.WATER, destination, "ro-feed"),
            (ConservedEntity.NA, "ro-feed", destination),
            (ConservedEntity.NA, destination, "ro-feed"),
            (ConservedEntity.ALKALINITY, "ro-feed", destination),
            (ConservedEntity.ALKALINITY, destination, "ro-feed"),
        ]
        assert [row.amount < 0.0 for row in rows] == [True, False, True, False, True, False]
        assert all(row.kind is LedgerEntryKind.INTERNAL for row in rows)
        assert all(row.phase is OperatorPhase.TREATMENT_BLENDING for row in rows)
        assert all(row.transfer_mode is MaterialTransferMode.ADVECTIVE_AQUEOUS for row in rows)
        assert all(row.treatment_model_id == "ro-bench" for row in rows)
        assert all(row.treatment_model_version == "1.0.0" for row in rows)
        assert rows[0].unit is StockUnit.KG
        assert rows[2].unit is StockUnit.MMOL
        assert rows[4].unit is StockUnit.MMOL_C
        assert rows[0].carrier_volume_l == rows[1].carrier_volume_l
        assert rows[0].water_density_kg_l == rows[1].water_density_kg_l
        assert rows[0].water_density_kg_l == pytest.approx(0.997, rel=1e-12)


@pytest.mark.parametrize("rejection", [0.0, 1.0])
@pytest.mark.parametrize("recovery", [1e-12, 1.0 - 1e-12])
def test_ro_accepts_rejection_endpoints_and_open_recovery_near_boundaries(
    rejection: float, recovery: float
) -> None:
    feed = _feed(stocks={ConservedEntity.NA: 37.0})
    parameters = _parameters(
        recovery=recovery,
        rejection={ConservedEntity.NA: rejection},
    )
    result = _split(feed=feed, parameters=parameters)

    expected_permeate = 37.0 * recovery * (1.0 - rejection)
    assert result.permeate.stocks[ConservedEntity.NA] == expected_permeate
    assert result.concentrate.stocks[ConservedEntity.NA] == 37.0 - expected_permeate
    assert result.removal.selectively_rejected_stock[ConservedEntity.NA] == (
        37.0 * recovery * rejection
    )


@given(
    stock=st.floats(min_value=0.0, max_value=1e12, allow_nan=False, allow_infinity=False),
    recovery=st.floats(min_value=1e-9, max_value=1.0 - 1e-9, allow_nan=False),
    rejection=st.floats(min_value=0.0, max_value=1.0, allow_nan=False),
)
def test_ro_uses_complementary_subtraction_for_represented_conservation(
    stock: float, recovery: float, rejection: float
) -> None:
    feed = _feed(stocks={ConservedEntity.NA: stock})
    result = _split(
        feed=feed,
        parameters=_parameters(
            recovery=recovery,
            rejection={ConservedEntity.NA: rejection},
        ),
    )

    permeate = result.permeate.stocks[ConservedEntity.NA]
    assert result.concentrate.stocks[ConservedEntity.NA] == stock - permeate
    assert result.concentrate.volume_l == 100.0 - result.permeate.volume_l
    assert result.concentrate.water_mass_kg == 99.7 - result.permeate.water_mass_kg
    assert result.permeate.volume_l + result.concentrate.volume_l == 100.0
    assert isclose(
        result.permeate.water_mass_kg + result.concentrate.water_mass_kg,
        99.7,
        rel_tol=1e-15,
    )


def test_ro_audit_detects_deletion_duplication_and_corruption() -> None:
    result = _split()
    candidates = (
        result.ledger[:-1],
        (*result.ledger, result.ledger[-1]),
        (*result.ledger[:2], replace(result.ledger[2], amount=-149.0), *result.ledger[3:]),
    )

    for candidate in candidates:
        with pytest.raises(AlmondLabError) as exc_info:
            audit_ro_ledger(result, candidate)
        assert exc_info.value.code == "RO_LEDGER_AUDIT_FAILED"

    audit_ro_ledger(result)


def test_ro_audit_is_independent_of_the_row_generator(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(treatment_module, "_ro_transfer_rows", lambda **_: ())

    with pytest.raises(AlmondLabError) as exc_info:
        _split()

    assert exc_info.value.code == "RO_LEDGER_AUDIT_FAILED"


def test_ro_replay_is_deterministic_and_cursor_continues_without_collisions() -> None:
    initial = LedgerCursor("same-run", "ro-chain", 41)
    first = _split(cursor=initial)
    replay = _split(cursor=initial)
    second = _split(cursor=first.next_cursor)

    assert first == replay
    assert {row.transaction_id for row in first.ledger} == {
        "tx:same-run:ro-chain:000000000041",
        "tx:same-run:ro-chain:000000000042",
    }
    assert {row.transaction_id for row in second.ledger} == {
        "tx:same-run:ro-chain:000000000043",
        "tx:same-run:ro-chain:000000000044",
    }
    assert not (
        {row.transaction_id for row in first.ledger}
        & {row.transaction_id for row in second.ledger}
    )


def test_remineralization_sorts_doses_uses_fsum_and_emits_one_transaction_per_dose() -> None:
    dose_z = FormulaResolvedAmendment(
        dose_id="z-dose",
        water_volume_l=0.2,
        water_density_kg_l=1.0,
        stock_additions={ConservedEntity.NA: 1e16},
        evidence_label=EvidenceLabel.PHYSICS_CONSTRAINED,
    )
    dose_a = FormulaResolvedAmendment(
        dose_id="a-dose",
        water_volume_l=0.1,
        water_density_kg_l=1.0,
        stock_additions={ConservedEntity.NA: 1.0},
        evidence_label=EvidenceLabel.PHYSICS_CONSTRAINED,
    )
    dose_m = FormulaResolvedAmendment(
        dose_id="m-dose",
        water_volume_l=0.3,
        water_density_kg_l=1.0,
        stock_additions={ConservedEntity.NA: 1.0},
        evidence_label=EvidenceLabel.PHYSICS_CONSTRAINED,
    )
    product = TreatmentStream(
        "product", 1.0, 1.0, {ConservedEntity.NA: 0.0}, EvidenceLabel.PHYSICS_CONSTRAINED
    )
    cursor = LedgerCursor("run", "dose", 3)

    forward = remineralize(
        product,
        (dose_z, dose_a, dose_m),
        output_stream_id="final",
        cursor=cursor,
    )
    reverse = remineralize(
        product,
        (dose_m, dose_a, dose_z),
        output_stream_id="final",
        cursor=cursor,
    )

    assert forward == reverse
    assert [dose.dose_id for dose in forward.doses] == ["a-dose", "m-dose", "z-dose"]
    assert forward.after.stocks[ConservedEntity.NA] == 1.0000000000000002e16
    assert forward.after.volume_l == 1.6
    assert forward.after.water_mass_kg == 1.6
    assert {row.transaction_id for row in forward.ledger} == {
        "tx:run:dose:000000000003",
        "tx:run:dose:000000000004",
        "tx:run:dose:000000000005",
    }
    assert forward.next_cursor == LedgerCursor("run", "dose", 6)
    assert all(row.kind is LedgerEntryKind.EXTERNAL for row in forward.ledger)
    assert all(row.boundary_category is ExternalBoundaryCategory.AMENDMENT for row in forward.ledger)
    assert all(row.phase is OperatorPhase.EXTERNAL_FEED_AMENDMENT for row in forward.ledger)


def test_remineralization_ledger_is_one_sided_and_uses_alkalinity_charge_units() -> None:
    ro = _split()
    result = remineralize(
        ro.permeate,
        (_amendment(),),
        output_stream_id="final-product",
        cursor=ro.next_cursor,
    )

    assert len(result.ledger) == 3
    assert {row.transaction_id for row in result.ledger} == {
        "tx:run-1:treatment:000000000009"
    }
    assert [(row.entity, row.amount, row.unit) for row in result.ledger] == [
        (ConservedEntity.WATER, 2.0, StockUnit.KG),
        (ConservedEntity.NA, 10.0, StockUnit.MMOL),
        (ConservedEntity.ALKALINITY, 6.0, StockUnit.MMOL_C),
    ]
    assert all(row.compartment == "final-product" for row in result.ledger)
    assert all(row.counterparty == "mineral-dose" for row in result.ledger)


def test_evidence_composition_never_promotes_dependencies() -> None:
    ro = _split(
        feed=_feed(label=EvidenceLabel.PHYSICS_CONSTRAINED),
        parameters=_parameters(label=EvidenceLabel.EMPIRICALLY_CALIBRATED),
    )
    assert ro.evidence_label is EvidenceLabel.HYPOTHESIS_PRIOR
    assert ro.permeate.evidence_label is EvidenceLabel.HYPOTHESIS_PRIOR
    assert all(row.evidence_label is EvidenceLabel.HYPOTHESIS_PRIOR for row in ro.ledger)

    final = remineralize(
        ro.permeate,
        (_amendment(label=EvidenceLabel.SYNTHETIC_ONLY),),
        output_stream_id="final-product",
        cursor=ro.next_cursor,
    )
    assert final.evidence_label is EvidenceLabel.SYNTHETIC_ONLY
    assert final.after.evidence_label is EvidenceLabel.SYNTHETIC_ONLY


def test_all_nested_records_and_mappings_are_deeply_immutable() -> None:
    source_stocks = {ConservedEntity.NA: 5.0}
    source_rejection = {ConservedEntity.NA: 0.9}
    source_additions = {ConservedEntity.NA: 1.0}
    feed = _feed(stocks=source_stocks)
    parameters = _parameters(rejection=source_rejection)
    dose = FormulaResolvedAmendment(
        "dose", 1.0, 1.0, source_additions, EvidenceLabel.PHYSICS_CONSTRAINED
    )
    result = _split(feed=feed, parameters=parameters)
    final = remineralize(
        result.permeate, (dose,), output_stream_id="final", cursor=result.next_cursor
    )

    source_stocks[ConservedEntity.NA] = 999.0
    source_rejection[ConservedEntity.NA] = 0.0
    source_additions[ConservedEntity.NA] = 999.0
    assert feed.stocks[ConservedEntity.NA] == 5.0
    assert parameters.rejection[ConservedEntity.NA] == 0.9
    assert dose.stock_additions[ConservedEntity.NA] == 1.0
    mappings = (
        feed.stocks,
        parameters.rejection,
        result.permeate.stocks,
        result.concentrate.stocks,
        result.removal.selectively_rejected_stock,
        result.removal.destination_stock,
        dose.stock_additions,
        final.after.stocks,
    )
    assert all(isinstance(mapping, MappingProxyType) for mapping in mappings)
    for mapping in mappings:
        with pytest.raises(TypeError):
            mapping[ConservedEntity.NA] = 7.0
    frozen_mutations = (
        (feed, "evidence_label", EvidenceLabel.SYNTHETIC_ONLY),
        (parameters, "evidence_label", EvidenceLabel.SYNTHETIC_ONLY),
        (result.removal, "destination_stream_id", "elsewhere"),
        (result, "evidence_label", EvidenceLabel.SYNTHETIC_ONLY),
        (dose, "evidence_label", EvidenceLabel.SYNTHETIC_ONLY),
        (final, "evidence_label", EvidenceLabel.SYNTHETIC_ONLY),
    )
    for record, field_name, value in frozen_mutations:
        with pytest.raises(FrozenInstanceError):
            setattr(record, field_name, value)
    assert isinstance(result.ledger, tuple)
    assert isinstance(final.doses, tuple)
    assert isinstance(final.ledger, tuple)


@pytest.mark.parametrize("recovery", [0.0, 1.0, -0.1, 1.1])
def test_ro_refuses_closed_or_outside_recovery(recovery: float) -> None:
    with pytest.raises(AlmondLabError) as exc_info:
        _parameters(recovery=recovery)
    assert exc_info.value.code == "RO_RECOVERY_OUT_OF_RANGE"
    assert exc_info.value.field_path == "recovery"


@pytest.mark.parametrize("rejection", [-0.01, 1.01])
def test_ro_refuses_nonphysical_ion_rejection(rejection: float) -> None:
    with pytest.raises(AlmondLabError) as exc_info:
        _parameters(rejection={ConservedEntity.NA: rejection})
    assert exc_info.value.code == "RO_REJECTION_OUT_OF_RANGE"


@pytest.mark.parametrize("ec_key", ["ec", "ECw", "ec_ds_m", "pore_water_EC", "ECe"])
def test_ro_refuses_ec_rejection_aliases(ec_key: str) -> None:
    with pytest.raises(AlmondLabError) as exc_info:
        ROParameters(
            "model",
            "1.0",
            0.5,
            {ConservedEntity.NA: 0.9, ec_key: 0.8},
            EvidenceLabel.PHYSICS_CONSTRAINED,
        )
    assert exc_info.value.code == "RO_EC_REJECTION_FORBIDDEN"


@pytest.mark.parametrize(
    "rejection",
    [
        {ConservedEntity.NA: 0.95},
        {
            ConservedEntity.NA: 0.95,
            ConservedEntity.ALKALINITY: 0.50,
            ConservedEntity.CL: 0.90,
        },
    ],
)
def test_ro_requires_exact_rejection_coverage(rejection: dict[ConservedEntity, float]) -> None:
    with pytest.raises(AlmondLabError) as exc_info:
        _split(parameters=_parameters(rejection=rejection))
    assert exc_info.value.code == "RO_REJECTION_KEYS_MISMATCH"


@pytest.mark.parametrize("bad_id", ["", "has space", "x" * 65, "a/b"])
def test_treatment_refuses_invalid_or_colliding_stream_ids(bad_id: str) -> None:
    with pytest.raises(AlmondLabError) as constructor_error:
        TreatmentStream(
            bad_id,
            1.0,
            1.0,
            {ConservedEntity.NA: 1.0},
            EvidenceLabel.PHYSICS_CONSTRAINED,
        )
    assert constructor_error.value.code == "TREATMENT_STREAM_ID_INVALID"

    with pytest.raises(AlmondLabError) as split_error:
        ro_split(
            _feed(),
            _parameters(),
            permeate_stream_id=bad_id,
            concentrate_stream_id="concentrate",
            cursor=LedgerCursor("run", "chain"),
        )
    assert split_error.value.code == "TREATMENT_STREAM_ID_INVALID"


@pytest.mark.parametrize(
    ("permeate_id", "concentrate_id"),
    [("ro-feed", "concentrate"), ("product", "ro-feed"), ("same", "same")],
)
def test_ro_refuses_stream_identity_collisions(
    permeate_id: str, concentrate_id: str
) -> None:
    with pytest.raises(AlmondLabError) as exc_info:
        ro_split(
            _feed(),
            _parameters(),
            permeate_stream_id=permeate_id,
            concentrate_stream_id=concentrate_id,
            cursor=LedgerCursor("run", "chain"),
        )
    assert exc_info.value.code == "RO_STREAM_IDS_NOT_UNIQUE"


def test_remineralization_refuses_duplicate_dose_ids_and_output_collision() -> None:
    dose = _amendment()
    with pytest.raises(AlmondLabError) as duplicate:
        remineralize(
            _split().permeate,
            (dose, dose),
            output_stream_id="final",
            cursor=LedgerCursor("run", "dose"),
        )
    assert duplicate.value.code == "AMENDMENT_DUPLICATE_DOSE_ID"

    with pytest.raises(AlmondLabError) as collision:
        remineralize(
            _split().permeate,
            (dose,),
            output_stream_id="ro-permeate",
            cursor=LedgerCursor("run", "dose"),
        )
    assert collision.value.code == "REMINERALIZATION_STREAM_ID_COLLISION"


@pytest.mark.parametrize(
    "value",
    [True, "1.0", object(), float("nan"), float("inf"), -float("inf"), 10**10_000],
    ids=[
        "bool",
        "string",
        "object",
        "nan",
        "positive-infinity",
        "negative-infinity",
        "float-overflow",
    ],
)
def test_treatment_numeric_boundaries_reject_coercive_nonfinite_and_overflow(
    value: object,
) -> None:
    factories = (
        lambda: TreatmentStream(
            "feed", value, 1.0, {ConservedEntity.NA: 1.0}, EvidenceLabel.PHYSICS_CONSTRAINED
        ),
        lambda: TreatmentStream(
            "feed", 1.0, value, {ConservedEntity.NA: 1.0}, EvidenceLabel.PHYSICS_CONSTRAINED
        ),
        lambda: TreatmentStream(
            "feed", 1.0, 1.0, {ConservedEntity.NA: value}, EvidenceLabel.PHYSICS_CONSTRAINED
        ),
        lambda: ROParameters(
            "model", "1.0", value, {ConservedEntity.NA: 0.5}, EvidenceLabel.PHYSICS_CONSTRAINED
        ),
        lambda: ROParameters(
            "model", "1.0", 0.5, {ConservedEntity.NA: value}, EvidenceLabel.PHYSICS_CONSTRAINED
        ),
        lambda: FormulaResolvedAmendment(
            "dose", value, 1.0, {ConservedEntity.NA: 1.0}, EvidenceLabel.PHYSICS_CONSTRAINED
        ),
        lambda: FormulaResolvedAmendment(
            "dose", 1.0, value, {ConservedEntity.NA: 1.0}, EvidenceLabel.PHYSICS_CONSTRAINED
        ),
        lambda: FormulaResolvedAmendment(
            "dose", 1.0, 1.0, {ConservedEntity.NA: value}, EvidenceLabel.PHYSICS_CONSTRAINED
        ),
    )
    for factory in factories:
        with pytest.raises(AlmondLabError) as exc_info:
            factory()
        assert exc_info.value.code == "TREATMENT_NUMERIC_INVALID"


def test_treatment_requires_typed_entities_labels_and_forbids_water_stock() -> None:
    with pytest.raises(AlmondLabError) as string_entity:
        TreatmentStream(
            "feed", 1.0, 1.0, {"na": 1.0}, EvidenceLabel.PHYSICS_CONSTRAINED
        )
    assert string_entity.value.code == "TREATMENT_ENTITY_TYPE_REQUIRED"

    with pytest.raises(AlmondLabError) as water:
        TreatmentStream(
            "feed", 1.0, 1.0, {ConservedEntity.WATER: 1.0}, EvidenceLabel.PHYSICS_CONSTRAINED
        )
    assert water.value.code == "TREATMENT_WATER_STOCK_FORBIDDEN"

    with pytest.raises(AlmondLabError) as label:
        TreatmentStream(
            "feed", 1.0, 1.0, {ConservedEntity.NA: 1.0}, "physics_constrained"
        )
    assert label.value.code == "TREATMENT_EVIDENCE_LABEL_INVALID"


def test_treatment_requires_positive_stream_mass_and_volume_and_nonnegative_stocks() -> None:
    for field, changes in (
        ("volume_l", {"volume_l": 0.0}),
        ("water_mass_kg", {"water_mass_kg": 0.0}),
        ("stocks.na", {"stocks": {ConservedEntity.NA: -0.1}}),
    ):
        values = {
            "stream_id": "feed",
            "volume_l": 1.0,
            "water_mass_kg": 1.0,
            "stocks": {ConservedEntity.NA: 1.0},
            "evidence_label": EvidenceLabel.PHYSICS_CONSTRAINED,
        }
        values.update(changes)
        with pytest.raises(AlmondLabError) as exc_info:
            TreatmentStream(**values)
        assert exc_info.value.code == "TREATMENT_NUMERIC_INVALID"
        assert exc_info.value.field_path == field


def test_treatment_refuses_nonfinite_derived_density_and_amendment_water_mass() -> None:
    with pytest.raises(AlmondLabError) as stream_error:
        TreatmentStream(
            "feed",
            1e-320,
            1e308,
            {ConservedEntity.NA: 1.0},
            EvidenceLabel.PHYSICS_CONSTRAINED,
        )
    assert stream_error.value.code == "TREATMENT_NUMERIC_INVALID"
    assert stream_error.value.field_path == "density_kg_l"

    with pytest.raises(AlmondLabError) as dose_error:
        FormulaResolvedAmendment(
            "dose",
            1e308,
            1e308,
            {ConservedEntity.NA: 1.0},
            EvidenceLabel.PHYSICS_CONSTRAINED,
        )
    assert dose_error.value.code == "TREATMENT_NUMERIC_INVALID"
    assert dose_error.value.field_path == "water_mass_kg"


def test_remineralization_refuses_nonfinite_stock_aggregate_instead_of_leaking_overflow() -> None:
    product = TreatmentStream(
        "product",
        1.0,
        1.0,
        {ConservedEntity.NA: 1e308},
        EvidenceLabel.PHYSICS_CONSTRAINED,
    )
    dose = FormulaResolvedAmendment(
        "dose",
        0.0,
        1.0,
        {ConservedEntity.NA: 1e308},
        EvidenceLabel.PHYSICS_CONSTRAINED,
    )

    with pytest.raises(AlmondLabError) as exc_info:
        remineralize(
            product,
            (dose,),
            output_stream_id="final",
            cursor=LedgerCursor("run", "dose"),
        )

    assert exc_info.value.code == "TREATMENT_NUMERIC_INVALID"
    assert exc_info.value.field_path == "after.stocks.na"


@pytest.mark.parametrize(
    ("product_volume", "product_water", "dose_volume", "dose_density", "field_path"),
    [
        (1e308, 1.0, 1e308, 1e-308, "after.volume_l"),
        (1.0, 1e308, 1e308, 1.0, "after.water_mass_kg"),
    ],
)
def test_remineralization_reports_the_exact_overflowing_water_field(
    product_volume: float,
    product_water: float,
    dose_volume: float,
    dose_density: float,
    field_path: str,
) -> None:
    product = TreatmentStream(
        "product",
        product_volume,
        product_water,
        {ConservedEntity.NA: 1.0},
        EvidenceLabel.PHYSICS_CONSTRAINED,
    )
    dose = FormulaResolvedAmendment(
        "dose",
        dose_volume,
        dose_density,
        {ConservedEntity.NA: 1.0},
        EvidenceLabel.PHYSICS_CONSTRAINED,
    )

    with pytest.raises(AlmondLabError) as exc_info:
        remineralize(
            product,
            (dose,),
            output_stream_id="final",
            cursor=LedgerCursor("run", "dose"),
        )

    assert exc_info.value.code == "TREATMENT_NUMERIC_INVALID"
    assert exc_info.value.field_path == field_path


def test_result_types_are_exact_public_records() -> None:
    ro = _split()
    final = remineralize(
        ro.permeate,
        (_amendment(),),
        output_stream_id="final",
        cursor=ro.next_cursor,
    )
    assert isinstance(ro, ROResult)
    assert isinstance(ro.removal, RORemovalResult)
    assert isinstance(final, RemineralizationResult)
    assert isclose(ro.feed.density_kg_l, 0.997, rel_tol=0.0, abs_tol=0.0)
