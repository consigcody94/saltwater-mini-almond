from math import isclose, sqrt
from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from almondlab.chemistry import (
    BlendMeasurement,
    blend_by_volume,
    charge_balance_error,
    sodium_adsorption_ratio,
    sodium_adsorption_ratio_for_water,
)
from almondlab.contracts import DataOrigin, ECKind, EvidenceLabel
from almondlab.errors import AlmondLabError
from almondlab.schemas import WaterBatch, WaterChemistry


FIXTURE_PATH = Path(__file__).parent / "fixtures" / "chemistry_handcheck.yaml"


def _fixture() -> dict[str, object]:
    return yaml.safe_load(FIXTURE_PATH.read_text())


def _batch(
    chemistry: dict[str, object],
    *,
    batch_id: str,
    origin: DataOrigin,
    label: EvidenceLabel,
) -> WaterBatch:
    return WaterBatch(
        water_batch_id=batch_id,
        chemistry=WaterChemistry(**chemistry),
        data_origin=origin,
        evidence_label=label,
        schema_version="1.0.0",
    )


def _measurement() -> BlendMeasurement:
    return BlendMeasurement(
        measurement_id="blend-observation-001",
        ec_kind=ECKind.ECW,
        ec_ds_m=7.2,
        temperature_k=298.15,
        measured_osmolality_osmol_kg=0.185,
        ph=7.5,
        data_origin=DataOrigin.EMPIRICAL,
        evidence_label=EvidenceLabel.EMPIRICALLY_CALIBRATED,
    )


def test_sar_hand_oracle_uses_charge_concentrations() -> None:
    assert isclose(
        sodium_adsorption_ratio(10.0, 4.0, 2.0),
        10.0 / sqrt(3.0),
        rel_tol=1e-12,
    )


def test_sar_water_wrapper_applies_divalent_ca_and_mg() -> None:
    payload = _fixture()["blend"]["source_a"]
    water = WaterChemistry(**payload)

    assert isclose(
        sodium_adsorption_ratio_for_water(water),
        10.0 / sqrt(3.0),
        rel_tol=1e-12,
    )


def test_sar_refuses_zero_divalent_charge() -> None:
    with pytest.raises(AlmondLabError) as exc_info:
        sodium_adsorption_ratio(10.0, 0.0, 0.0)

    assert exc_info.value.code == "SAR_ZERO_DENOMINATOR"


@pytest.mark.parametrize(
    ("field", "values", "expected_path"),
    [
        ("na", (True, 4.0, 2.0), "na_mmol_c_l"),
        ("ca", (10.0, "4.0", 2.0), "ca_mmol_c_l"),
        ("mg_nan", (10.0, 4.0, float("nan")), "mg_mmol_c_l"),
        ("mg_inf", (10.0, 4.0, float("inf")), "mg_mmol_c_l"),
        ("na_overflow", (10**10000, 4.0, 2.0), "na_mmol_c_l"),
        ("missing", (10.0, None, 2.0), "ca_mmol_c_l"),
    ],
    ids=["bool", "numeric-string", "nan", "infinity", "overflow", "missing"],
)
def test_sar_public_boundary_returns_stable_structured_number_errors(
    field: str, values: tuple[object, object, object], expected_path: str
) -> None:
    del field
    with pytest.raises(AlmondLabError) as exc_info:
        sodium_adsorption_ratio(*values)

    assert exc_info.value.to_dict() == {
        "code": "SAR_INVALID_CONCENTRATION",
        "message": "value must be a finite real number",
        "field_path": expected_path,
        "details": {"received_type": type(values[("na_mmol_c_l", "ca_mmol_c_l", "mg_mmol_c_l").index(expected_path)]).__name__},
    }


def test_sar_rejects_finite_inputs_whose_intermediate_sum_overflows() -> None:
    with pytest.raises(AlmondLabError) as exc_info:
        sodium_adsorption_ratio(1.0, 1e308, 1e308)

    assert exc_info.value.to_dict() == {
        "code": "SAR_NONFINITE_RESULT",
        "message": "SAR arithmetic overflowed",
        "field_path": "sar",
    }


def test_blend_sums_every_registered_analyte_and_alkalinity_by_mass() -> None:
    record = _fixture()["blend"]
    sources = [
        _batch(
            record["source_a"],
            batch_id="source-a",
            origin=DataOrigin.EMPIRICAL,
            label=EvidenceLabel.EMPIRICALLY_CALIBRATED,
        ),
        _batch(
            record["source_b"],
            batch_id="source-b",
            origin=DataOrigin.LITERATURE_DERIVED,
            label=EvidenceLabel.HYPOTHESIS_PRIOR,
        ),
    ]

    result = blend_by_volume(
        sources,
        record["volumes_l"],
        measurement=_measurement(),
    )

    for field, expected in record["expected"].items():
        assert getattr(result.chemistry, field) == pytest.approx(expected)
    assert result.total_volume_l == 8.0
    assert result.chemistry.ec_ds_m == 7.2
    assert result.source_data_origins == (
        DataOrigin.EMPIRICAL,
        DataOrigin.LITERATURE_DERIVED,
    )
    assert result.measurement_data_origin is DataOrigin.EMPIRICAL
    assert result.evidence_label is EvidenceLabel.HYPOTHESIS_PRIOR


def test_blend_mixed_physics_and_empirical_evidence_is_not_promoted() -> None:
    record = _fixture()["blend"]
    sources = [
        _batch(
            record["source_a"],
            batch_id="source-a",
            origin=DataOrigin.MODEL_DERIVED,
            label=EvidenceLabel.PHYSICS_CONSTRAINED,
        )
    ]

    result = blend_by_volume(sources, [1], measurement=_measurement())

    assert result.evidence_label is EvidenceLabel.HYPOTHESIS_PRIOR


@pytest.mark.parametrize(
    "bad_volume",
    [True, "1.0", float("nan"), float("inf"), pytest.param(10**10000, id="overflow"), None],
)
def test_blend_volume_boundary_returns_stable_path_for_malformed_numbers(
    bad_volume: object,
) -> None:
    record = _fixture()["blend"]
    source = _batch(
        record["source_a"],
        batch_id="source-a",
        origin=DataOrigin.EMPIRICAL,
        label=EvidenceLabel.EMPIRICALLY_CALIBRATED,
    )

    with pytest.raises(AlmondLabError) as exc_info:
        blend_by_volume([source], [bad_volume], measurement=_measurement())

    assert exc_info.value.to_dict() == {
        "code": "BLEND_INVALID_VOLUME",
        "message": "value must be a finite real number",
        "field_path": "volumes_l.0",
        "details": {"received_type": type(bad_volume).__name__},
    }


@pytest.mark.parametrize(
    "bad_value",
    [True, "7.2", float("nan"), float("inf"), pytest.param(10**10000, id="overflow")],
)
def test_blend_measurement_schema_rejects_coercive_or_nonfinite_numbers(
    bad_value: object,
) -> None:
    with pytest.raises(ValidationError) as exc_info:
        _measurement().model_copy(update={"ec_ds_m": bad_value}, deep=True).model_validate(
            {**_measurement().model_dump(), "ec_ds_m": bad_value}
        )

    assert exc_info.value.errors()[0]["loc"] == ("ec_ds_m",)


def test_blend_refuses_to_average_ec_without_validated_measurement() -> None:
    record = _fixture()["blend"]
    sources = [
        _batch(
            record["source_a"],
            batch_id="source-a",
            origin=DataOrigin.EMPIRICAL,
            label=EvidenceLabel.EMPIRICALLY_CALIBRATED,
        ),
        _batch(
            record["source_b"],
            batch_id="source-b",
            origin=DataOrigin.EMPIRICAL,
            label=EvidenceLabel.EMPIRICALLY_CALIBRATED,
        ),
    ]

    with pytest.raises(AlmondLabError) as exc_info:
        blend_by_volume(sources, record["volumes_l"])

    assert exc_info.value.code == "EC_MEASUREMENT_REQUIRED"


def test_blend_refuses_mixed_ec_kinds_even_with_measurement() -> None:
    record = _fixture()["blend"]
    mixed = dict(record["source_b"])
    mixed["ec_kind"] = ECKind.ECE
    sources = [
        _batch(
            record["source_a"],
            batch_id="source-a",
            origin=DataOrigin.EMPIRICAL,
            label=EvidenceLabel.EMPIRICALLY_CALIBRATED,
        ),
        _batch(
            mixed,
            batch_id="source-b",
            origin=DataOrigin.EMPIRICAL,
            label=EvidenceLabel.EMPIRICALLY_CALIBRATED,
        ),
    ]

    with pytest.raises(AlmondLabError) as exc_info:
        blend_by_volume(sources, record["volumes_l"], measurement=_measurement())

    assert exc_info.value.code == "EC_TYPE_MISMATCH"


def test_blend_refuses_measurement_of_different_ec_kind() -> None:
    record = _fixture()["blend"]
    source = _batch(
        record["source_a"],
        batch_id="source-a",
        origin=DataOrigin.EMPIRICAL,
        label=EvidenceLabel.PHYSICS_CONSTRAINED,
    )
    measurement = _measurement().model_copy(update={"ec_kind": ECKind.PORE_WATER})

    with pytest.raises(AlmondLabError) as exc_info:
        blend_by_volume([source], [2.0], measurement=measurement)

    assert exc_info.value.code == "EC_TYPE_MISMATCH"


def test_charge_balance_uses_explicit_valence_and_measured_alkalinity() -> None:
    payload = dict(_fixture()["blend"]["source_a"])
    payload.update(
        na_mmol_l=10.0,
        k_mmol_l=1.0,
        ca_mmol_l=2.0,
        mg_mmol_l=1.0,
        cl_mmol_l=8.0,
        sulfate_mmol_l=2.0,
        alkalinity_mmol_c_l=2.0,
        bicarbonate_mmol_l=100.0,
        nitrate_mmol_l=1.0,
        phosphate_mmol_l=20.0,
    )

    assert charge_balance_error(WaterChemistry(**payload)) == pytest.approx(6.25)


@pytest.mark.parametrize("bad_water", [True, "water", None])
def test_charge_balance_public_boundary_rejects_missing_or_wrong_water_object(
    bad_water: object,
) -> None:
    with pytest.raises(AlmondLabError) as exc_info:
        charge_balance_error(bad_water)

    assert exc_info.value.to_dict() == {
        "code": "CHARGE_BALANCE_INVALID_WATER",
        "message": "water must be validated WaterChemistry",
        "field_path": "water",
        "details": {"received_type": type(bad_water).__name__},
    }


LABELS = tuple(EvidenceLabel)
PAIR_EXPECTATIONS = {
    (EvidenceLabel.PHYSICS_CONSTRAINED, EvidenceLabel.PHYSICS_CONSTRAINED): EvidenceLabel.PHYSICS_CONSTRAINED,
    (EvidenceLabel.PHYSICS_CONSTRAINED, EvidenceLabel.EMPIRICALLY_CALIBRATED): EvidenceLabel.HYPOTHESIS_PRIOR,
    (EvidenceLabel.PHYSICS_CONSTRAINED, EvidenceLabel.HYPOTHESIS_PRIOR): EvidenceLabel.HYPOTHESIS_PRIOR,
    (EvidenceLabel.PHYSICS_CONSTRAINED, EvidenceLabel.SYNTHETIC_ONLY): EvidenceLabel.SYNTHETIC_ONLY,
    (EvidenceLabel.EMPIRICALLY_CALIBRATED, EvidenceLabel.PHYSICS_CONSTRAINED): EvidenceLabel.HYPOTHESIS_PRIOR,
    (EvidenceLabel.EMPIRICALLY_CALIBRATED, EvidenceLabel.EMPIRICALLY_CALIBRATED): EvidenceLabel.EMPIRICALLY_CALIBRATED,
    (EvidenceLabel.EMPIRICALLY_CALIBRATED, EvidenceLabel.HYPOTHESIS_PRIOR): EvidenceLabel.HYPOTHESIS_PRIOR,
    (EvidenceLabel.EMPIRICALLY_CALIBRATED, EvidenceLabel.SYNTHETIC_ONLY): EvidenceLabel.SYNTHETIC_ONLY,
    (EvidenceLabel.HYPOTHESIS_PRIOR, EvidenceLabel.PHYSICS_CONSTRAINED): EvidenceLabel.HYPOTHESIS_PRIOR,
    (EvidenceLabel.HYPOTHESIS_PRIOR, EvidenceLabel.EMPIRICALLY_CALIBRATED): EvidenceLabel.HYPOTHESIS_PRIOR,
    (EvidenceLabel.HYPOTHESIS_PRIOR, EvidenceLabel.HYPOTHESIS_PRIOR): EvidenceLabel.HYPOTHESIS_PRIOR,
    (EvidenceLabel.HYPOTHESIS_PRIOR, EvidenceLabel.SYNTHETIC_ONLY): EvidenceLabel.SYNTHETIC_ONLY,
    (EvidenceLabel.SYNTHETIC_ONLY, EvidenceLabel.PHYSICS_CONSTRAINED): EvidenceLabel.SYNTHETIC_ONLY,
    (EvidenceLabel.SYNTHETIC_ONLY, EvidenceLabel.EMPIRICALLY_CALIBRATED): EvidenceLabel.SYNTHETIC_ONLY,
    (EvidenceLabel.SYNTHETIC_ONLY, EvidenceLabel.HYPOTHESIS_PRIOR): EvidenceLabel.SYNTHETIC_ONLY,
    (EvidenceLabel.SYNTHETIC_ONLY, EvidenceLabel.SYNTHETIC_ONLY): EvidenceLabel.SYNTHETIC_ONLY,
}


@pytest.mark.parametrize(("left", "right"), PAIR_EXPECTATIONS)
def test_evidence_composition_truth_table_covers_all_sixteen_pairs(
    left: EvidenceLabel, right: EvidenceLabel
) -> None:
    from almondlab.evidence_policy import compose_evidence_labels

    assert compose_evidence_labels(left, right) is PAIR_EXPECTATIONS[(left, right)]


def test_evidence_composition_is_order_invariant_and_associative() -> None:
    from almondlab.evidence_policy import compose_evidence_labels

    for left in LABELS:
        for middle in LABELS:
            assert compose_evidence_labels(left, middle) is compose_evidence_labels(middle, left)
            for right in LABELS:
                assert compose_evidence_labels(
                    compose_evidence_labels(left, middle), right
                ) is compose_evidence_labels(
                    left, compose_evidence_labels(middle, right)
                )
