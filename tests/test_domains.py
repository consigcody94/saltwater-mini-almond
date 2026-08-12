import pytest

from almondlab.contracts import ECKind, EvidenceLabel
from almondlab.domains import DomainRequest, validate_domain
from almondlab.errors import AlmondLabError
from almondlab.schemas import ModelDomain, WaterChemistry


DIGEST_A = "a" * 64
DIGEST_B = "b" * 64


def _water(**updates: object) -> WaterChemistry:
    payload: dict[str, object] = {
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
    payload.update(updates)
    return WaterChemistry(**payload)


def _domain(
    *,
    policy: str = "deny",
    permitted_label: EvidenceLabel = EvidenceLabel.EMPIRICALLY_CALIBRATED,
) -> ModelDomain:
    return ModelDomain(
        model_id="calibrated_v1",
        version="1.0.0",
        permitted_label=permitted_label,
        ec_kind=ECKind.ECW,
        ec_ds_m_min=1.0,
        ec_ds_m_max=10.0,
        osmolality_min=0.05,
        osmolality_max=0.25,
        temperature_k_min=290.0,
        temperature_k_max=305.0,
        required_analytes=("na", "cl", "ca", "mg"),
        allowed_chassis=("Vairo",),
        allowed_life_stages=("juvenile",),
        calibration_datasets={"dataset-a": DIGEST_A},
        extrapolation_policy=policy,
    )


def _request(**updates: object) -> DomainRequest:
    payload: dict[str, object] = {
        "water": _water(),
        "available_analytes": frozenset(
            {
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
            }
        ),
        "chassis": "Vairo",
        "life_stage": "juvenile",
        "calibration_datasets": {"dataset-a": DIGEST_A},
        "requested_label": EvidenceLabel.EMPIRICALLY_CALIBRATED,
    }
    payload.update(updates)
    return DomainRequest(**payload)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("ec_ds_m", 1.0),
        ("ec_ds_m", 10.0),
        ("measured_osmolality_osmol_kg", 0.05),
        ("measured_osmolality_osmol_kg", 0.25),
        ("temperature_k", 290.0),
        ("temperature_k", 305.0),
    ],
)
def test_domain_boundaries_are_inclusive(field: str, value: float) -> None:
    result = validate_domain(_domain(), _request(water=_water(**{field: value})))

    assert result.evidence_label is EvidenceLabel.EMPIRICALLY_CALIBRATED
    assert result.violations == ()


def test_denied_domain_reports_every_violation_in_structured_error() -> None:
    request = _request(
        water=_water(ec_kind=ECKind.ECE, ec_ds_m=20.0, temperature_k=310.0),
        available_analytes=frozenset({"na", "ca"}),
        chassis="Other",
        life_stage="mature",
        calibration_datasets={"dataset-a": DIGEST_B, "unexpected": DIGEST_A},
        requested_label=EvidenceLabel.PHYSICS_CONSTRAINED,
    )

    with pytest.raises(AlmondLabError) as exc_info:
        validate_domain(_domain(), request)

    error = exc_info.value
    fields = {item["field"] for item in error.details["violations"]}
    assert error.code == "DOMAIN_VIOLATION"
    assert fields == {
        "request.water.ec_kind",
        "request.water.ec_ds_m",
        "request.water.temperature_k",
        "request.available_analytes.cl",
        "request.available_analytes.mg",
        "request.chassis",
        "request.life_stage",
        "request.calibration_datasets.dataset-a",
        "request.calibration_datasets.unexpected",
        "request.requested_label",
    }


def test_missing_analyte_is_refused() -> None:
    request = _request(available_analytes=frozenset({"na", "ca", "mg"}))

    with pytest.raises(AlmondLabError) as exc_info:
        validate_domain(_domain(), request)

    assert exc_info.value.code == "DOMAIN_VIOLATION"
    assert exc_info.value.details["violations"][0]["field"] == (
        "request.available_analytes.cl"
    )


def test_dataset_hash_mismatch_is_refused() -> None:
    request = _request(calibration_datasets={"dataset-a": DIGEST_B})

    with pytest.raises(AlmondLabError) as exc_info:
        validate_domain(_domain(), request)

    assert exc_info.value.details["violations"] == [
        {
            "field": "request.calibration_datasets.dataset-a",
            "reason": "hash_mismatch",
            "expected": DIGEST_A,
            "received": DIGEST_B,
        }
    ]


@pytest.mark.parametrize(
    ("policy", "expected_label"),
    [
        ("hypothesis_prior", EvidenceLabel.HYPOTHESIS_PRIOR),
        ("synthetic_only", EvidenceLabel.SYNTHETIC_ONLY),
    ],
)
def test_allowed_extrapolation_returns_weak_label_and_all_violations(
    policy: str,
    expected_label: EvidenceLabel,
) -> None:
    request = _request(
        water=_water(ec_ds_m=20.0),
        available_analytes=frozenset({"na"}),
        chassis="Other",
    )

    result = validate_domain(_domain(policy=policy), request)

    assert result.evidence_label is expected_label
    assert {item["field"] for item in result.violations} == {
        "request.water.ec_ds_m",
        "request.available_analytes.cl",
        "request.available_analytes.ca",
        "request.available_analytes.mg",
        "request.chassis",
    }


def test_allowed_extrapolation_never_preserves_strong_requested_label() -> None:
    result = validate_domain(
        _domain(policy="hypothesis_prior"),
        _request(water=_water(ec_ds_m=20.0)),
    )

    assert result.evidence_label is EvidenceLabel.HYPOTHESIS_PRIOR
    assert result.requested_label is EvidenceLabel.EMPIRICALLY_CALIBRATED


def test_allowed_extrapolation_reports_every_analyte_when_none_are_available() -> None:
    result = validate_domain(
        _domain(policy="synthetic_only"),
        _request(available_analytes=frozenset()),
    )

    assert [item["field"] for item in result.violations] == [
        "request.available_analytes.na",
        "request.available_analytes.cl",
        "request.available_analytes.ca",
        "request.available_analytes.mg",
    ]
