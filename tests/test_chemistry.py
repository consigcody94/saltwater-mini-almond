from math import isclose, sqrt
from pathlib import Path

import pytest
import yaml

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
