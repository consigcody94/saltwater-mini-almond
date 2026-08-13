import math
from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from almondlab.contracts import DataOrigin, ECKind, EvidenceLabel
from almondlab.schemas import ModelDomain, ObservationRecord, WaterBatch, WaterChemistry
from almondlab.units import canonical_quantity


def chemistry_payload() -> dict[str, object]:
    return {
        "ec_kind": ECKind.ECW,
        "ec_ds_m": 6.0,
        "temperature_k": 298.15,
        "measured_osmolality_osmol_kg": 0.15,
        "ph": 7.2,
        "alkalinity_mmol_c_l": 2.1,
        "na_mmol_l": 45.0,
        "cl_mmol_l": 50.0,
        "ca_mmol_l": 4.0,
        "mg_mmol_l": 3.0,
        "k_mmol_l": 2.0,
        "total_b_mmol_l": 0.1,
        "sulfate_mmol_l": 2.0,
        "bicarbonate_mmol_l": 2.1,
        "nitrate_mmol_l": 1.0,
        "phosphate_mmol_l": 0.5,
    }


def domain_payload() -> dict[str, object]:
    return {
        "model_id": "core_v1",
        "version": "1.0.0",
        "permitted_evidence_label": EvidenceLabel.PHYSICS_CONSTRAINED,
        "ec_ds_m_min": 0.7,
        "ec_ds_m_max": 15.0,
        "osmolality_min": 0.02,
        "osmolality_max": 0.30,
        "temperature_k_min": 291.15,
        "temperature_k_max": 303.15,
        "required_chemistry_fields": [
            {
                "field_name": "ec_ds_m",
                "observation_kind": "measured",
                "ec_kind": "ECw",
            },
            {"field_name": "ph", "observation_kind": "measured"},
            {
                "field_name": "measured_osmolality_osmol_kg",
                "observation_kind": "measured",
            },
            {
                "field_name": "alkalinity_mmol_c_l",
                "observation_kind": "measured",
            },
            {"field_name": "temperature_k", "observation_kind": "measured"},
            {"field_name": "sar", "observation_kind": "computed"},
        ],
        "required_analytes": [
            "na",
            "cl",
            "ca",
            "mg",
            "k",
            "total_b",
            "sulfate",
            "bicarbonate",
            "nitrate",
            "phosphate",
        ],
        "allowed_chassis": ["Vairo"],
        "allowed_life_stages": ["juvenile"],
        "calibration_datasets": [],
        "extrapolation_policy": "deny",
    }


def test_water_requires_complete_registered_chemistry() -> None:
    with pytest.raises(ValidationError):
        WaterChemistry(ec_kind=ECKind.ECW, ec_ds_m=6.0, temperature_k=298.15)


def test_water_rejects_nonfinite_values() -> None:
    payload = chemistry_payload()
    payload["ph"] = math.nan

    with pytest.raises(ValidationError):
        WaterChemistry(**payload)


@pytest.mark.parametrize(
    "bad_value",
    [True, False, "6.0", math.inf, -math.inf, pytest.param(10**10000, id="overflow")],
)
def test_water_rejects_non_real_or_nonfinite_numeric_inputs(bad_value: object) -> None:
    payload = chemistry_payload()
    payload["ec_ds_m"] = bad_value

    with pytest.raises(ValidationError) as exc_info:
        WaterChemistry(**payload)

    assert exc_info.value.errors()[0]["loc"] == ("ec_ds_m",)


def test_water_normalizes_ordinary_yaml_integer_literals_to_finite_float() -> None:
    payload = chemistry_payload()
    payload["ec_ds_m"] = 6

    water = WaterChemistry(**payload)

    assert water.ec_ds_m == 6.0
    assert isinstance(water.ec_ds_m, float)


def test_water_rejects_negative_solute_stock() -> None:
    payload = chemistry_payload()
    payload["na_mmol_l"] = -0.01

    with pytest.raises(ValidationError):
        WaterChemistry(**payload)


def test_water_rejects_negative_alkalinity() -> None:
    payload = chemistry_payload()
    payload["alkalinity_mmol_c_l"] = -0.01

    with pytest.raises(ValidationError) as exc_info:
        WaterChemistry(**payload)

    assert any(error["loc"] == ("alkalinity_mmol_c_l",) for error in exc_info.value.errors())


def test_water_from_celsius_stores_only_kelvin() -> None:
    payload = chemistry_payload()
    payload.pop("temperature_k")

    water = WaterChemistry.from_celsius(**payload, temperature_c=25.0)

    assert water.temperature_k == pytest.approx(298.15)
    assert "temperature_c" not in water.model_dump()


def test_water_rejects_unknown_fields() -> None:
    payload = chemistry_payload()
    payload["unregistered_analyte"] = 1.0

    with pytest.raises(ValidationError):
        WaterChemistry(**payload)


def test_water_instances_are_immutable() -> None:
    water = WaterChemistry(**chemistry_payload())

    with pytest.raises(ValidationError):
        water.ph = 7.0


def test_domain_bounds_are_ordered() -> None:
    payload = domain_payload()
    payload["ec_ds_m_min"] = 15.0
    payload["ec_ds_m_max"] = 0.7

    with pytest.raises(ValidationError):
        ModelDomain(**payload)


def test_domain_requires_explicit_chemistry_field_policy() -> None:
    payload = domain_payload()
    payload.pop("required_chemistry_fields")

    with pytest.raises(ValidationError) as exc_info:
        ModelDomain(**payload)

    assert exc_info.value.errors()[0]["loc"] == ("required_chemistry_fields",)


@pytest.mark.parametrize(
    "field_name",
    [
        "ec_ds_m_min",
        "ec_ds_m_max",
        "osmolality_min",
        "osmolality_max",
        "temperature_k_min",
        "temperature_k_max",
    ],
)
def test_domain_rejects_negative_physical_bounds(field_name: str) -> None:
    payload = domain_payload()
    payload[field_name] = -0.01

    with pytest.raises(ValidationError) as exc_info:
        ModelDomain(**payload)

    assert any(error["loc"] == (field_name,) for error in exc_info.value.errors())


@pytest.mark.parametrize(
    "bad_value",
    [True, "0.7", math.nan, math.inf, pytest.param(10**10000, id="overflow")],
)
def test_domain_rejects_coercive_or_nonfinite_bounds(bad_value: object) -> None:
    payload = domain_payload()
    payload["ec_ds_m_min"] = bad_value

    with pytest.raises(ValidationError) as exc_info:
        ModelDomain(**payload)

    assert exc_info.value.errors()[0]["loc"] == ("ec_ds_m_min",)


def test_domain_rejects_malformed_dataset_hash() -> None:
    payload = domain_payload()
    payload["calibration_datasets"] = [
        {"provenance_id": "dataset_1", "sha256": "not-a-sha256"}
    ]

    with pytest.raises(ValidationError):
        ModelDomain(**payload)


def test_empirical_domain_requires_calibration_data() -> None:
    payload = domain_payload()
    payload["permitted_evidence_label"] = EvidenceLabel.EMPIRICALLY_CALIBRATED

    with pytest.raises(ValidationError):
        ModelDomain(**payload)


@pytest.mark.parametrize(
    ("model_id", "label"),
    [
        ("alternate_core", EvidenceLabel.PHYSICS_CONSTRAINED),
        ("hypothesis_v1", EvidenceLabel.HYPOTHESIS_PRIOR),
        ("synthetic_v1", EvidenceLabel.SYNTHETIC_ONLY),
    ],
)
def test_only_conservation_core_allows_empty_calibration_data(
    model_id: str, label: EvidenceLabel
) -> None:
    payload = domain_payload()
    payload["model_id"] = model_id
    payload["permitted_evidence_label"] = label

    with pytest.raises(ValidationError) as exc_info:
        ModelDomain(**payload)

    assert "empty calibration datasets are reserved for core_v1" in str(exc_info.value)


def test_core_domain_yaml_loads_with_exact_scope() -> None:
    config_path = Path(__file__).parents[1] / "configs" / "model_domains.yaml"
    record = yaml.safe_load(config_path.read_text())["core_v1"]
    domain = ModelDomain(**record)

    assert domain.ec_kind is ECKind.ECW
    assert (domain.ec_ds_m_min, domain.ec_ds_m_max) == (0.7, 15.0)
    assert (domain.osmolality_min, domain.osmolality_max) == (0.02, 0.30)
    assert (domain.temperature_k_min, domain.temperature_k_max) == (291.15, 303.15)
    assert domain.permitted_evidence_label is EvidenceLabel.PHYSICS_CONSTRAINED
    assert tuple(field.field_name for field in domain.required_chemistry_fields) == (
        "ec_ds_m",
        "ph",
        "measured_osmolality_osmol_kg",
        "alkalinity_mmol_c_l",
        "temperature_k",
        "sar",
    )
    assert domain.required_analytes == (
        "na",
        "cl",
        "ca",
        "mg",
        "k",
        "total_b",
        "sulfate",
        "bicarbonate",
        "nitrate",
        "phosphate",
    )
    assert domain.allowed_chassis == ("Vairo",)
    assert domain.allowed_life_stages == ("juvenile",)
    assert domain.calibration_datasets == ()
    assert domain.extrapolation_policy == "deny"
    assert hash(domain)


def test_canonical_quantity_converts_to_requested_unit() -> None:
    assert canonical_quantity(1.0, "liter", "milliliter") == 1000.0


def test_records_keep_data_origin_distinct_from_evidence_label() -> None:
    batch = WaterBatch(
        water_batch_id="SYN_water_001",
        chemistry=WaterChemistry(**chemistry_payload()),
        data_origin=DataOrigin.SYNTHETIC,
        evidence_label=EvidenceLabel.PHYSICS_CONSTRAINED,
        schema_version="1.0.0",
    )
    record = ObservationRecord(
        record_id="SYN_observation_001",
        observation_type="water_ec",
        observed_at="2026-08-12T12:00:00Z",
        value=6.0,
        unit="dS/m",
        data_origin=DataOrigin.SYNTHETIC,
        evidence_label=EvidenceLabel.PHYSICS_CONSTRAINED,
        schema_version="1.0.0",
        water_batch_id=batch.water_batch_id,
    )

    assert record.data_origin is DataOrigin.SYNTHETIC
    assert record.evidence_label is EvidenceLabel.PHYSICS_CONSTRAINED
