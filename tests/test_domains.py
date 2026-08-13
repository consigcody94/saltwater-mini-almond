import hashlib
from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from almondlab.chemistry import sodium_adsorption_ratio_for_water
from almondlab.contracts import DataOrigin, ECKind, EvidenceLabel
from almondlab.domains import DomainRequest, validate_domain
from almondlab.errors import AlmondLabError
from almondlab.schemas import ModelDomain, WaterChemistry


DIGEST_A = "a" * 64
DIGEST_B = "b" * 64
SOURCE_ID = "chemistry-record"


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


def _requirements() -> tuple[dict[str, object], ...]:
    return (
        {"field_name": "ec_ds_m", "observation_kind": "measured", "ec_kind": "ECw"},
        {"field_name": "ph", "observation_kind": "measured"},
        {
            "field_name": "measured_osmolality_osmol_kg",
            "observation_kind": "measured",
        },
        {"field_name": "alkalinity_mmol_c_l", "observation_kind": "measured"},
        {"field_name": "temperature_k", "observation_kind": "measured"},
        {"field_name": "sar", "observation_kind": "computed"},
    )


def _domain(
    *,
    policy: str = "deny",
    permitted_label: EvidenceLabel = EvidenceLabel.EMPIRICALLY_CALIBRATED,
) -> ModelDomain:
    calibration = (
        [{"provenance_id": "dataset-a", "sha256": DIGEST_A}]
        if permitted_label is EvidenceLabel.EMPIRICALLY_CALIBRATED
        else []
    )
    model_id = (
        "calibrated_v1"
        if permitted_label is EvidenceLabel.EMPIRICALLY_CALIBRATED
        else "core_v1"
    )
    return ModelDomain(
        model_id=model_id,
        version="1.0.0",
        permitted_evidence_label=permitted_label,
        ec_kind=ECKind.ECW,
        ec_ds_m_min=1.0,
        ec_ds_m_max=10.0,
        osmolality_min=0.05,
        osmolality_max=0.25,
        temperature_k_min=290.0,
        temperature_k_max=305.0,
        required_chemistry_fields=_requirements(),
        required_analytes=("na", "cl", "ca", "mg"),
        allowed_chassis=("Vairo",),
        allowed_life_stages=("juvenile",),
        calibration_datasets=calibration,
        extrapolation_policy=policy,
    )


def _observations(
    water: WaterChemistry,
    *,
    label: EvidenceLabel,
    omitted: frozenset[str] = frozenset(),
    kind_updates: dict[str, str] | None = None,
    ec_kind: ECKind = ECKind.ECW,
    provenance_sha256: str = DIGEST_A,
) -> tuple[dict[str, object], ...]:
    kinds = {field["field_name"]: field["observation_kind"] for field in _requirements()}
    kinds.update(kind_updates or {})
    analytes = ("na", "cl", "ca", "mg", "k", "total_b", "sulfate", "bicarbonate", "nitrate", "phosphate")
    fields = (*kinds, *(f"{analyte}_mmol_l" for analyte in analytes))
    rows: list[dict[str, object]] = []
    for field_name in fields:
        if field_name in omitted:
            continue
        value = (
            sodium_adsorption_ratio_for_water(water)
            if field_name == "sar"
            else getattr(water, field_name)
        )
        row: dict[str, object] = {
            "field_name": field_name,
            "value": value,
            "observation_kind": kinds.get(field_name, "measured"),
            "data_origin": DataOrigin.SYNTHETIC,
            "evidence_label": label,
            "provenance_id": SOURCE_ID,
            "provenance_sha256": provenance_sha256,
        }
        if field_name == "ec_ds_m":
            row["ec_kind"] = ec_kind
        rows.append(row)
    return tuple(rows)


def _request(**updates: object) -> DomainRequest:
    water = updates.pop("water", _water())
    label = updates.get("requested_label", EvidenceLabel.EMPIRICALLY_CALIBRATED)
    payload: dict[str, object] = {
        "water": water,
        "chemistry_observations": _observations(water, label=label),
        "provenance_sources": (
            {"provenance_id": SOURCE_ID, "sha256": DIGEST_A},
        ),
        "chassis": "Vairo",
        "life_stage": "juvenile",
        "calibration_datasets": (
            {"provenance_id": "dataset-a", "sha256": DIGEST_A},
        ),
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
    water = _water(**{field: value})
    result = validate_domain(
        _domain(),
        _request(water=water, chemistry_observations=_observations(water, label=EvidenceLabel.EMPIRICALLY_CALIBRATED)),
    )

    assert result.evidence_label is EvidenceLabel.EMPIRICALLY_CALIBRATED
    assert result.violations == ()


@pytest.mark.parametrize(
    "requested_label",
    [EvidenceLabel.PHYSICS_CONSTRAINED, EvidenceLabel.HYPOTHESIS_PRIOR, EvidenceLabel.SYNTHETIC_ONLY],
)
def test_physics_domain_accepts_in_domain_claim_at_or_below_its_label(
    requested_label: EvidenceLabel,
) -> None:
    water = _water()
    request = _request(
        water=water,
        requested_label=requested_label,
        chemistry_observations=_observations(water, label=requested_label),
        calibration_datasets=(),
    )

    result = validate_domain(_domain(permitted_label=EvidenceLabel.PHYSICS_CONSTRAINED), request)

    assert result.evidence_label is requested_label
    assert result.violations == ()


def test_physics_domain_cannot_mint_empirical_claim() -> None:
    with pytest.raises(AlmondLabError) as exc_info:
        validate_domain(
            _domain(permitted_label=EvidenceLabel.PHYSICS_CONSTRAINED),
            _request(calibration_datasets=()),
        )

    assert exc_info.value.code == "DOMAIN_VIOLATION"
    assert exc_info.value.details["violations"][-1]["reason"] == "evidence_label_incompatible"


def test_empirical_domain_cannot_mint_physics_claim() -> None:
    water = _water()
    with pytest.raises(AlmondLabError) as exc_info:
        validate_domain(
            _domain(),
            _request(
                water=water,
                requested_label=EvidenceLabel.PHYSICS_CONSTRAINED,
                chemistry_observations=_observations(water, label=EvidenceLabel.PHYSICS_CONSTRAINED),
            ),
        )

    assert exc_info.value.details["violations"][-1]["reason"] == "evidence_label_incompatible"


@pytest.mark.parametrize(
    ("missing_field", "expected_path"),
    [
        ("ph", "request.chemistry_observations.ph"),
        ("measured_osmolality_osmol_kg", "request.chemistry_observations.measured_osmolality_osmol_kg"),
        ("alkalinity_mmol_c_l", "request.chemistry_observations.alkalinity_mmol_c_l"),
        ("temperature_k", "request.chemistry_observations.temperature_k"),
        ("sar", "request.chemistry_observations.sar"),
        ("cl_mmol_l", "request.chemistry_observations.cl_mmol_l"),
    ],
)
def test_missing_required_chemistry_or_analyte_observation_is_hard_violation(
    missing_field: str, expected_path: str
) -> None:
    water = _water(ec_ds_m=20.0)
    request = _request(
        water=water,
        requested_label=EvidenceLabel.SYNTHETIC_ONLY,
        chemistry_observations=_observations(
            water,
            label=EvidenceLabel.SYNTHETIC_ONLY,
            omitted=frozenset({missing_field}),
        ),
    )

    with pytest.raises(AlmondLabError) as exc_info:
        validate_domain(_domain(policy="synthetic_only"), request)

    assert expected_path in {
        violation["field"] for violation in exc_info.value.details["violations"]
    }


def test_hard_chemistry_failure_stops_before_evidence_label_resolution() -> None:
    water = _water()
    request = _request(
        water=water,
        chemistry_observations=_observations(
            water,
            label=EvidenceLabel.EMPIRICALLY_CALIBRATED,
            omitted=frozenset({"ph"}),
        ),
        calibration_datasets=(),
    )

    with pytest.raises(AlmondLabError) as exc_info:
        validate_domain(
            _domain(permitted_label=EvidenceLabel.PHYSICS_CONSTRAINED),
            request,
        )

    assert [item["field"] for item in exc_info.value.details["violations"]] == [
        "request.chemistry_observations.ph"
    ]


def test_wrong_ec_observation_kind_is_hard_violation() -> None:
    water = _water()
    request = _request(
        water=water,
        chemistry_observations=_observations(
            water,
            label=EvidenceLabel.EMPIRICALLY_CALIBRATED,
            kind_updates={"ec_ds_m": "computed"},
        ),
    )

    with pytest.raises(AlmondLabError) as exc_info:
        validate_domain(_domain(), request)

    assert exc_info.value.details["violations"][0]["reason"] == "observation_kind_mismatch"


def test_wrong_ec_type_is_hard_violation() -> None:
    water = _water()
    request = _request(
        water=water,
        chemistry_observations=_observations(
            water,
            label=EvidenceLabel.EMPIRICALLY_CALIBRATED,
            ec_kind=ECKind.ECE,
        ),
    )

    with pytest.raises(AlmondLabError) as exc_info:
        validate_domain(_domain(), request)

    assert "request.chemistry_observations.ec_ds_m.ec_kind" in {
        item["field"] for item in exc_info.value.details["violations"]
    }


def test_derived_value_is_rejected_when_measurement_is_required() -> None:
    water = _water()
    request = _request(
        water=water,
        chemistry_observations=_observations(
            water,
            label=EvidenceLabel.EMPIRICALLY_CALIBRATED,
            kind_updates={"ph": "computed"},
        ),
    )

    with pytest.raises(AlmondLabError) as exc_info:
        validate_domain(_domain(), request)

    assert exc_info.value.details["violations"][0]["field"] == "request.chemistry_observations.ph.observation_kind"


def test_provenance_hash_mismatch_is_hard_violation() -> None:
    water = _water()
    request = _request(
        water=water,
        chemistry_observations=_observations(
            water,
            label=EvidenceLabel.EMPIRICALLY_CALIBRATED,
            provenance_sha256=DIGEST_B,
        ),
    )

    with pytest.raises(AlmondLabError) as exc_info:
        validate_domain(_domain(), request)

    assert exc_info.value.details["violations"][0]["reason"] == "provenance_hash_mismatch"


def test_dataset_hash_mismatch_is_refused_before_label_resolution() -> None:
    request = _request(
        calibration_datasets=(
            {"provenance_id": "dataset-a", "sha256": DIGEST_B},
        )
    )

    with pytest.raises(AlmondLabError) as exc_info:
        validate_domain(_domain(), request)

    assert exc_info.value.details["violations"][-1] == {
        "field": "request.calibration_datasets.dataset-a",
        "reason": "hash_mismatch",
        "expected": DIGEST_A,
        "received": DIGEST_B,
    }


@pytest.mark.parametrize(
    ("policy", "requested_label"),
    [
        ("hypothesis_prior", EvidenceLabel.HYPOTHESIS_PRIOR),
        ("synthetic_only", EvidenceLabel.SYNTHETIC_ONLY),
    ],
)
def test_exact_weak_extrapolation_retains_every_range_and_scope_violation(
    policy: str, requested_label: EvidenceLabel
) -> None:
    water = _water(ec_ds_m=20.0)
    request = _request(
        water=water,
        chemistry_observations=_observations(water, label=requested_label),
        chassis="Other",
        life_stage="mature",
        requested_label=requested_label,
    )

    result = validate_domain(_domain(policy=policy), request)

    assert result.evidence_label is requested_label
    assert {item["field"] for item in result.violations} == {
        "request.water.ec_ds_m",
        "request.chassis",
        "request.life_stage",
    }


@pytest.mark.parametrize(
    ("policy", "requested_label"),
    [
        ("hypothesis_prior", EvidenceLabel.SYNTHETIC_ONLY),
        ("synthetic_only", EvidenceLabel.HYPOTHESIS_PRIOR),
        ("synthetic_only", EvidenceLabel.EMPIRICALLY_CALIBRATED),
    ],
)
def test_out_of_domain_request_requires_exact_authorized_weak_label(
    policy: str, requested_label: EvidenceLabel
) -> None:
    water = _water(ec_ds_m=20.0)
    with pytest.raises(AlmondLabError) as exc_info:
        validate_domain(
            _domain(policy=policy),
            _request(
                water=water,
                chemistry_observations=_observations(water, label=requested_label),
                requested_label=requested_label,
            ),
        )

    assert exc_info.value.code == "DOMAIN_VIOLATION"


def test_actual_paper1_hypothesis_water_validates_in_core_domain_and_stays_weak() -> None:
    from almondlab.domains import load_model_domains

    repo = Path(__file__).parents[1]
    registry = load_model_domains(repo / "configs" / "model_domains.yaml")
    core = registry.get("core_v1")
    paper_path = repo / "configs" / "experiment_paper1.yaml"
    paper = yaml.safe_load(paper_path.read_text())
    paper_digest = hashlib.sha256(paper_path.read_bytes()).hexdigest()
    record = paper["water_conditions"][1]
    water = WaterChemistry(**record["chemistry"])
    label = EvidenceLabel(record["evidence_label"])
    observations = _observations(
        water,
        label=label,
        provenance_sha256=paper_digest,
    )
    request = DomainRequest(
        water=water,
        chemistry_observations=observations,
        provenance_sources=(
            {"provenance_id": SOURCE_ID, "sha256": paper_digest},
        ),
        chassis="Vairo",
        life_stage="juvenile",
        calibration_datasets=(),
        requested_label=label,
    )

    result = validate_domain(core, request)

    assert result.evidence_label is EvidenceLabel.HYPOTHESIS_PRIOR
    assert result.violations == ()
    assert hash(registry)


def test_model_domain_loader_uses_identical_packaged_authority_and_is_strict(
    tmp_path: Path,
) -> None:
    from almondlab.domains import load_model_domains

    repo = Path(__file__).parents[1]
    source = repo / "configs" / "model_domains.yaml"
    registry = load_model_domains(source)
    packaged = load_model_domains()

    assert registry.sha256 == packaged.sha256
    assert registry.domains == packaged.domains
    malformed = tmp_path / "model_domains.yaml"
    malformed.write_text(source.read_text().replace("version: 1.0.0", "version: 1.0.0\n  unknown: true"))
    with pytest.raises(ValidationError):
        load_model_domains(malformed)
