from dataclasses import FrozenInstanceError, replace
from fractions import Fraction

import pytest

from almondlab.contracts import (
    CORE_V1_OPERATOR_SCHEDULE,
    ENTITY_SPECS,
    CompartmentKind,
    ConcentrationUnit,
    ConservedEntity,
    DataOrigin,
    ECKind,
    EntitySpec,
    EvidenceLabel,
    ExternalBoundaryCategory,
    GateState,
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


def test_public_enums_preserve_existing_values() -> None:
    assert EvidenceLabel.PHYSICS_CONSTRAINED.value == "physics_constrained"
    assert DataOrigin.SYNTHETIC.value == "synthetic"
    assert ECKind.ECW.value == "ECw"
    assert ConservedEntity.TOTAL_B.value == "total_b"
    assert GateState.NOT_EVALUABLE.value == "not_evaluable"


def test_conservation_enum_values_are_exact() -> None:
    assert [member.value for member in StockUnit] == ["kg", "mmol", "mmol_c"]
    assert [member.value for member in ConcentrationUnit] == [
        "mmol/L",
        "mmol_c/L",
    ]
    assert [member.value for member in ExternalBoundaryCategory] == [
        "source_feed",
        "external_makeup",
        "amendment",
        "disposed_concentrate",
        "purge_or_discharge",
        "sampling",
        "leak",
        "vented_vapor",
        "harvested_tissue",
        "removed_solid",
        "treatment_loss",
        "other_measured_output",
    ]
    assert [member.value for member in InternalEntityFluxKind] == [
        "plant_uptake",
        "plant_efflux",
        "xylem_retrieval",
        "sequestration",
        "vacuole_release",
        "xylem_loading",
        "tissue_deposition",
    ]
    assert [member.value for member in OperatorPhase] == [
        "external_feed_amendment",
        "treatment_blending",
        "irrigation",
        "evaporation_transpiration",
        "layer_drainage",
        "plant_ion_transitions",
        "reaction_adapters",
        "drainage_condensate_return",
        "purge_disposal",
        "numerical_closure",
    ]
    assert [member.value for member in LedgerEntryKind] == ["internal", "external"]
    assert [member.value for member in MaterialTransferMode] == [
        "advective_aqueous",
        "water_only",
        "entity_only",
    ]
    assert [member.value for member in InternalWaterFlowKind] == [
        "aqueous_transfer",
        "evaporation",
        "transpiration",
        "condensate_return",
    ]


def test_compartment_kinds_cover_water_treatment_and_plant_systems() -> None:
    required = {
        "source_water",
        "treatment_feed",
        "treatment_product",
        "treatment_concentrate",
        "blend_tank",
        "irrigation_tank",
        "root_zone",
        "root_apoplast",
        "root_symplast",
        "root_vacuole",
        "xylem",
        "shoot_tissue",
        "drainage",
        "condensate",
    }

    assert required <= {member.value for member in CompartmentKind}


def test_entity_registry_is_exhaustive_and_uses_canonical_units() -> None:
    assert set(ENTITY_SPECS) == set(ConservedEntity)
    assert len(ENTITY_SPECS) == len(ConservedEntity)
    assert all(key is spec.entity for key, spec in ENTITY_SPECS.items())

    water = entity_spec(ConservedEntity.WATER)
    assert water.stock_unit is StockUnit.KG
    assert water.concentration_unit is None
    assert water.basis == "reserved water carrier mass"

    alkalinity = entity_spec(ConservedEntity.ALKALINITY)
    assert alkalinity.stock_unit is StockUnit.MMOL_C
    assert alkalinity.concentration_unit is ConcentrationUnit.MMOL_C_PER_L
    assert "charge" in alkalinity.basis

    for entity in ConservedEntity:
        if entity in {ConservedEntity.WATER, ConservedEntity.ALKALINITY}:
            continue
        spec = entity_spec(entity)
        assert spec.stock_unit is StockUnit.MMOL
        assert spec.concentration_unit is ConcentrationUnit.MMOL_PER_L
        assert spec.basis


def test_entity_registry_and_specs_are_deeply_immutable() -> None:
    with pytest.raises(TypeError):
        ENTITY_SPECS[ConservedEntity.NA] = ENTITY_SPECS[ConservedEntity.CL]  # type: ignore[index]
    with pytest.raises(FrozenInstanceError):
        ENTITY_SPECS[ConservedEntity.NA].basis = "changed"  # type: ignore[misc]


def test_entity_accessor_is_strict() -> None:
    with pytest.raises(AlmondLabError) as exc_info:
        entity_spec("na")  # type: ignore[arg-type]

    assert exc_info.value.to_dict() == {
        "code": "ENTITY_TYPE_REQUIRED",
        "message": "entity must be a ConservedEntity",
        "field_path": "entity",
    }


def test_core_operator_schedule_is_exact_and_immutable() -> None:
    assert CORE_V1_OPERATOR_SCHEDULE.schedule_id == "core_v1"
    assert CORE_V1_OPERATOR_SCHEDULE.phases == tuple(OperatorPhase)
    with pytest.raises(FrozenInstanceError):
        CORE_V1_OPERATOR_SCHEDULE.schedule_id = "changed"  # type: ignore[misc]


@pytest.mark.parametrize(
    ("phases", "code"),
    [
        (tuple(OperatorPhase)[:-1], "OPERATOR_SCHEDULE_MISSING_PHASE"),
        (
            tuple(OperatorPhase) + (OperatorPhase.NUMERICAL_CLOSURE,),
            "OPERATOR_SCHEDULE_DUPLICATE_PHASE",
        ),
        (tuple(reversed(tuple(OperatorPhase))), "OPERATOR_SCHEDULE_ORDER_INVALID"),
        (
            tuple(OperatorPhase) + ("invented_phase",),
            "OPERATOR_SCHEDULE_EXTRA_PHASE",
        ),
    ],
)
def test_operator_schedule_rejects_missing_duplicate_reordered_and_extra_phases(
    phases: tuple[object, ...], code: str
) -> None:
    with pytest.raises(AlmondLabError) as exc_info:
        OperatorSchedule("invalid", phases)  # type: ignore[arg-type]

    assert exc_info.value.code == code
    assert exc_info.value.field_path == "phases"


def test_operator_schedule_copies_mutable_phase_input_before_validation() -> None:
    mutable = list(OperatorPhase)
    schedule = OperatorSchedule("copy-test", mutable)  # type: ignore[arg-type]
    mutable.reverse()

    assert schedule.phases == tuple(OperatorPhase)


def test_ledger_cursor_issues_exact_ids_without_mutation() -> None:
    cursor = LedgerCursor("run-2026_08_12", "irrigation.a")

    first_id, after_first = cursor.issue()
    second_id, after_second = after_first.issue()

    assert first_id == "tx:run-2026_08_12:irrigation.a:000000000000"
    assert second_id == "tx:run-2026_08_12:irrigation.a:000000000001"
    assert cursor.next_ordinal == 0
    assert after_second.next_ordinal == 2


def test_ledger_cursor_replays_deterministically_and_namespaces_are_disjoint() -> None:
    a1, _ = LedgerCursor("run-a", "chain-1", 42).issue()
    a2, _ = LedgerCursor("run-a", "chain-1", 42).issue()
    other_run, _ = LedgerCursor("run-b", "chain-1", 42).issue()
    other_chain, _ = LedgerCursor("run-a", "chain-2", 42).issue()

    assert a1 == a2 == "tx:run-a:chain-1:000000000042"
    assert len({a1, other_run, other_chain}) == 3


@pytest.mark.parametrize(
    ("kwargs", "code", "field_path"),
    [
        ({"run_id": "", "chain_id": "chain"}, "LEDGER_ID_INVALID", "run_id"),
        (
            {"run_id": "bad:id", "chain_id": "chain"},
            "LEDGER_ID_INVALID",
            "run_id",
        ),
        (
            {"run_id": "rün", "chain_id": "chain"},
            "LEDGER_ID_INVALID",
            "run_id",
        ),
        (
            {"run_id": "run", "chain_id": "two words"},
            "LEDGER_ID_INVALID",
            "chain_id",
        ),
        (
            {"run_id": "run", "chain_id": "chain", "next_ordinal": True},
            "LEDGER_ORDINAL_INVALID",
            "next_ordinal",
        ),
        (
            {"run_id": "run", "chain_id": "chain", "next_ordinal": 1.5},
            "LEDGER_ORDINAL_INVALID",
            "next_ordinal",
        ),
        (
            {"run_id": "run", "chain_id": "chain", "next_ordinal": -1},
            "LEDGER_ORDINAL_INVALID",
            "next_ordinal",
        ),
        (
            {
                "run_id": "run",
                "chain_id": "chain",
                "next_ordinal": 1_000_000_000_001,
            },
            "LEDGER_ORDINAL_OVERFLOW",
            "next_ordinal",
        ),
    ],
)
def test_ledger_cursor_rejects_invalid_namespaces_and_ordinals(
    kwargs: dict[str, object], code: str, field_path: str
) -> None:
    with pytest.raises(AlmondLabError) as exc_info:
        LedgerCursor(**kwargs)  # type: ignore[arg-type]

    assert exc_info.value.code == code
    assert exc_info.value.field_path == field_path


def test_ledger_cursor_refuses_to_issue_beyond_fixed_width() -> None:
    last_id, exhausted = LedgerCursor("run", "chain", 999_999_999_999).issue()

    assert last_id == "tx:run:chain:999999999999"

    with pytest.raises(AlmondLabError) as exc_info:
        exhausted.issue()

    assert exc_info.value.code == "LEDGER_ORDINAL_OVERFLOW"
    assert exc_info.value.field_path == "next_ordinal"


def _water_entry(**changes: object) -> LedgerEntry:
    transaction_id, _ = LedgerCursor("run", "water").issue()
    values: dict[str, object] = {
        "transaction_id": transaction_id,
        "event_id": "pipe-a",
        "kind": LedgerEntryKind.INTERNAL,
        "phase": OperatorPhase.IRRIGATION,
        "transfer_mode": MaterialTransferMode.ADVECTIVE_AQUEOUS,
        "compartment": "tank-a",
        "counterparty": "tank-b",
        "entity": ConservedEntity.WATER,
        "amount": -19.94,
        "unit": StockUnit.KG,
        "evidence_label": EvidenceLabel.PHYSICS_CONSTRAINED,
        "physical_transfer_id": "pipe-a",
        "carrier_volume_l": 20.0,
        "water_density_kg_l": 0.997,
    }
    values.update(changes)
    return LedgerEntry(**values)  # type: ignore[arg-type]


def _ion_entry(**changes: object) -> LedgerEntry:
    transaction_id, _ = LedgerCursor("run", "ions").issue()
    values: dict[str, object] = {
        "transaction_id": transaction_id,
        "event_id": "na-uptake",
        "kind": LedgerEntryKind.INTERNAL,
        "phase": OperatorPhase.PLANT_ION_TRANSITIONS,
        "transfer_mode": MaterialTransferMode.ENTITY_ONLY,
        "compartment": "root-zone",
        "counterparty": "root-apoplast",
        "entity": ConservedEntity.NA,
        "amount": -0.5,
        "unit": StockUnit.MMOL,
        "evidence_label": EvidenceLabel.HYPOTHESIS_PRIOR,
        "internal_flux_kind": InternalEntityFluxKind.PLANT_UPTAKE,
        "requested_amount": 1.0,
        "applied_amount": 0.5,
        "cap_fraction": 0.5,
    }
    values.update(changes)
    return LedgerEntry(**values)  # type: ignore[arg-type]


def test_ledger_entry_is_frozen_typed_and_supports_capped_flux_metadata() -> None:
    water = _water_entry()
    ion = _ion_entry()

    assert water.entity is ConservedEntity.WATER
    assert water.unit is StockUnit.KG
    assert water.carrier_volume_l * water.water_density_kg_l == pytest.approx(
        abs(water.amount)
    )
    assert ion.internal_flux_kind is InternalEntityFluxKind.PLANT_UPTAKE
    assert ion.applied_amount == abs(ion.amount)
    with pytest.raises(FrozenInstanceError):
        ion.amount = 4.0  # type: ignore[misc]


@pytest.mark.parametrize(
    ("entry_factory", "changes", "code", "field_path"),
    [
        (_ion_entry, {"unit": StockUnit.KG}, "LEDGER_UNIT_MISMATCH", "unit"),
        (
            _water_entry,
            {"carrier_volume_l": None},
            "LEDGER_WATER_CARRIER_REQUIRED",
            "carrier_volume_l",
        ),
        (
            _water_entry,
            {"water_density_kg_l": None},
            "LEDGER_WATER_CARRIER_REQUIRED",
            "water_density_kg_l",
        ),
        (
            _water_entry,
            {"amount": -20.0},
            "LEDGER_WATER_IDENTITY_MISMATCH",
            "amount",
        ),
        (
            _ion_entry,
            {"carrier_volume_l": 1.0},
            "LEDGER_SOLUTE_CARRIER_FORBIDDEN",
            "carrier_volume_l",
        ),
        (
            _ion_entry,
            {"transfer_mode": MaterialTransferMode.WATER_ONLY},
            "LEDGER_TRANSFER_MODE_MISMATCH",
            "transfer_mode",
        ),
        (
            _water_entry,
            {"transfer_mode": MaterialTransferMode.ENTITY_ONLY},
            "LEDGER_TRANSFER_MODE_MISMATCH",
            "transfer_mode",
        ),
        (
            _ion_entry,
            {"boundary_category": ExternalBoundaryCategory.AMENDMENT},
            "LEDGER_BOUNDARY_KIND_MISMATCH",
            "boundary_category",
        ),
        (
            _ion_entry,
            {"applied_amount": 1.5},
            "LEDGER_APPLIED_EXCEEDS_REQUESTED",
            "applied_amount",
        ),
        (
            _ion_entry,
            {"cap_fraction": 0.2},
            "LEDGER_CAP_IDENTITY_MISMATCH",
            "cap_fraction",
        ),
    ],
)
def test_ledger_entry_rejects_incoherent_units_modes_and_metadata(
    entry_factory: object,
    changes: dict[str, object],
    code: str,
    field_path: str,
) -> None:
    with pytest.raises(AlmondLabError) as exc_info:
        entry_factory(**changes)  # type: ignore[operator]

    assert exc_info.value.code == code
    assert exc_info.value.field_path == field_path


@pytest.mark.parametrize(
    "changes",
    [
        {"amount": float("nan")},
        {"carrier_volume_l": float("inf")},
        {"requested_amount": float("nan")},
        {"cap_fraction": float("inf")},
    ],
)
def test_ledger_entry_rejects_nonfinite_numeric_metadata(changes: dict[str, object]) -> None:
    with pytest.raises(AlmondLabError) as exc_info:
        _water_entry(**changes)

    assert exc_info.value.code == "LEDGER_NUMERIC_INVALID"


def test_reaction_adapter_metadata_is_all_or_none_and_sha256_typed() -> None:
    reaction = replace(
        _ion_entry(),
        phase=OperatorPhase.REACTION_ADAPTERS,
        internal_flux_kind=None,
        event_id="reaction-1",
        adapter_id="carbonate-v1",
        adapter_version="1.0.0",
        adapter_hash="a" * 64,
    )
    assert reaction.adapter_hash == "a" * 64

    with pytest.raises(AlmondLabError) as incomplete:
        _ion_entry(
            phase=OperatorPhase.REACTION_ADAPTERS,
            internal_flux_kind=None,
            adapter_id="carbonate-v1",
        )
    assert incomplete.value.code == "LEDGER_ADAPTER_REFERENCE_INVALID"

    with pytest.raises(AlmondLabError) as wrong_phase:
        _ion_entry(
            adapter_id="carbonate-v1",
            adapter_version="1.0.0",
            adapter_hash="a" * 64,
        )
    assert wrong_phase.value.code == "LEDGER_ADAPTER_PHASE_MISMATCH"


@pytest.mark.parametrize("value", [0, 1, -2, 0.5, Fraction(1, 4)])
def test_finite_float_accepts_genuine_real_numbers(value: object) -> None:
    assert finite_float(value, code="NUMBER_INVALID", field_path="case.value") == float(
        value
    )


@pytest.mark.parametrize(
    "value",
    [True, False, "1.0", object(), float("nan"), float("inf"), -float("inf"), 10**10_000],
    ids=[
        "true",
        "false",
        "string",
        "object",
        "nan",
        "positive-infinity",
        "negative-infinity",
        "float-conversion-overflow",
    ],
)
def test_finite_float_rejects_non_real_nonfinite_and_overflowing_values(
    value: object,
) -> None:
    with pytest.raises(AlmondLabError) as exc_info:
        finite_float(value, code="NUMBER_INVALID", field_path="case.value")

    assert exc_info.value.code == "NUMBER_INVALID"
    assert exc_info.value.field_path == "case.value"


def test_finite_float_enforces_requested_bounds() -> None:
    with pytest.raises(AlmondLabError) as zero:
        finite_float(
            0,
            code="STRICTLY_POSITIVE_REQUIRED",
            field_path="density",
            positive=True,
        )
    assert zero.value.to_dict() == {
        "code": "STRICTLY_POSITIVE_REQUIRED",
        "message": "value must be greater than zero",
        "field_path": "density",
    }

    with pytest.raises(AlmondLabError) as negative:
        finite_float(
            -0.1,
            code="NONNEGATIVE_REQUIRED",
            field_path="stock",
            nonnegative=True,
        )
    assert negative.value.to_dict() == {
        "code": "NONNEGATIVE_REQUIRED",
        "message": "value must be nonnegative",
        "field_path": "stock",
    }


def test_fail_and_error_serialize_structured_fields() -> None:
    with pytest.raises(AlmondLabError) as raised:
        fail("EC_TYPE_MISMATCH", "wrong EC kind", "water.ec_kind")
    assert raised.value.code == "EC_TYPE_MISMATCH"
    assert raised.value.field_path == "water.ec_kind"

    error = AlmondLabError(
        "EC_TYPE_MISMATCH",
        "wrong EC kind",
        "water.ec_kind",
        {"expected": "ECw", "received": "ECe"},
    )
    assert error.to_dict() == {
        "code": "EC_TYPE_MISMATCH",
        "message": "wrong EC kind",
        "field_path": "water.ec_kind",
        "details": {"expected": "ECw", "received": "ECe"},
    }
