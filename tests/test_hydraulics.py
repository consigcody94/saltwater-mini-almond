from math import isclose

import pytest
from pydantic import ValidationError

from almondlab.contracts import EvidenceLabel
from almondlab.errors import AlmondLabError
from almondlab.hydraulics import (
    HydraulicDomain,
    HydraulicInputs,
    HydraulicUptake,
    hydraulic_uptake,
    osmotic_potential_mpa,
)


def _domain(**updates: object) -> HydraulicDomain:
    values: dict[str, object] = {
        "model_id": "hydraulic-core-v1",
        "version": "1.0.0",
        "purpose": "model_applicability",
        "osmolality_min": 0.01,
        "osmolality_max": 0.40,
        "temperature_k_min": 290.0,
        "temperature_k_max": 305.0,
        "permitted_evidence_label": EvidenceLabel.PHYSICS_CONSTRAINED,
        "extrapolation_policy": "deny",
    }
    values.update(updates)
    return HydraulicDomain(**values)


def _inputs(**updates: object) -> HydraulicInputs:
    values: dict[str, object] = {
        "osmolality_osmol_kg": 0.05,
        "temperature_k": 298.15,
        "water_density_kg_l": 0.997,
        "matric_mpa": -0.10,
        "leaf_critical_mpa": -2.00,
        "adjustment_mpa": 0.0,
        "root_conductance_l_day_mpa": 0.50,
        "potential_transpiration_l_day": 1.00,
        "specific_ion_factor": 1.00,
        "evidence_label": EvidenceLabel.PHYSICS_CONSTRAINED,
    }
    values.update(updates)
    return HydraulicInputs(**values)


def test_perfect_na_exclusion_keeps_osmotic_penalty_with_explicit_domain() -> None:
    """An ion-specific factor cannot erase the bulk osmotic potential."""
    domain = _domain()
    fresh = hydraulic_uptake(_inputs(osmolality_osmol_kg=0.05), domain=domain)
    saline = hydraulic_uptake(_inputs(osmolality_osmol_kg=0.40), domain=domain)

    assert isclose(fresh.actual_l_day, 0.888212, abs_tol=1e-6)
    assert isclose(saline.actual_l_day, 0.455696, abs_tol=1e-6)
    assert isclose(saline.actual_l_day / fresh.actual_l_day, 0.513049, abs_tol=1e-6)
    assert saline.evidence_label is EvidenceLabel.PHYSICS_CONSTRAINED
    assert saline.domain_decision.model_id == "hydraulic-core-v1"
    assert saline.domain_decision.violations == ()


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("osmolality_osmol_kg", True),
        ("temperature_k", "298.15"),
        ("water_density_kg_l", float("nan")),
        ("matric_mpa", float("inf")),
        ("leaf_critical_mpa", float("-inf")),
        ("specific_ion_factor", 10**10000),
    ],
    ids=["bool", "numeric-string", "nan", "infinity", "negative-infinity", "overflow"],
)
def test_hydraulic_input_schema_rejects_bool_strings_nonfinite_and_overflow(
    field: str, value: object
) -> None:
    with pytest.raises(ValidationError) as exc_info:
        _inputs(**{field: value})

    assert exc_info.value.errors()[0]["loc"] == (field,)


def test_hydraulic_inputs_require_explicit_evidence_label() -> None:
    values = _inputs().model_dump()
    values.pop("evidence_label")

    with pytest.raises(ValidationError) as exc_info:
        HydraulicInputs(**values)

    assert exc_info.value.errors()[0]["loc"] == ("evidence_label",)


def test_hydraulic_inputs_require_every_numeric_field() -> None:
    values = _inputs().model_dump()
    values.pop("matric_mpa")

    with pytest.raises(ValidationError) as exc_info:
        HydraulicInputs(**values)

    assert exc_info.value.errors()[0]["loc"] == ("matric_mpa",)


@pytest.mark.parametrize(
    "bad_value",
    [True, "0.05", float("nan"), float("inf"), pytest.param(10**10000, id="overflow"), None],
)
def test_osmotic_public_function_returns_stable_structured_number_error(
    bad_value: object,
) -> None:
    with pytest.raises(AlmondLabError) as exc_info:
        osmotic_potential_mpa(bad_value, 298.15, 0.997)

    assert exc_info.value.to_dict()["code"] == "HYDRAULIC_INVALID_NUMBER"
    assert exc_info.value.to_dict()["field_path"] == "osmolality_osmol_kg"


@pytest.mark.parametrize(
    "bad_value",
    [True, "0.01", float("nan"), float("inf"), pytest.param(10**10000, id="overflow")],
)
def test_hydraulic_domain_rejects_coercive_or_nonfinite_bounds(bad_value: object) -> None:
    with pytest.raises(ValidationError) as exc_info:
        _domain(osmolality_min=bad_value)

    assert exc_info.value.errors()[0]["loc"] == ("osmolality_min",)


def test_hydraulic_domain_legacy_fixture_key_normalizes_to_canonical_vocabulary() -> None:
    payload = _domain().model_dump()
    payload["permitted_label"] = payload.pop("permitted_evidence_label")

    domain = HydraulicDomain(**payload)

    assert domain.permitted_evidence_label is EvidenceLabel.PHYSICS_CONSTRAINED
    assert "permitted_label" not in domain.model_dump()


def test_hydraulic_uptake_requires_validated_explicit_domain() -> None:
    with pytest.raises(AlmondLabError) as exc_info:
        hydraulic_uptake(_inputs(), domain=None)

    assert exc_info.value.to_dict()["code"] == "HYDRAULIC_DOMAIN_REQUIRED"
    assert exc_info.value.to_dict()["field_path"] == "domain"


def test_hydraulic_result_cannot_be_constructed_without_label_or_domain_decision() -> None:
    with pytest.raises(ValidationError) as exc_info:
        HydraulicUptake(
            osmotic_potential_mpa=-0.1,
            soil_potential_mpa=-0.2,
            leaf_limit_mpa=-2.0,
            hydraulic_capacity_l_day=0.9,
            ion_limited_demand_l_day=1.0,
            actual_l_day=0.9,
        )

    assert {error["loc"] for error in exc_info.value.errors()} == {
        ("evidence_label",),
        ("domain_decision",),
    }


@pytest.mark.parametrize(
    "requested_label",
    [EvidenceLabel.HYPOTHESIS_PRIOR, EvidenceLabel.SYNTHETIC_ONLY],
)
def test_in_domain_weak_hydraulic_input_stays_weak(
    requested_label: EvidenceLabel,
) -> None:
    result = hydraulic_uptake(
        _inputs(evidence_label=requested_label),
        domain=_domain(),
    )

    assert result.evidence_label is requested_label
    assert result.domain_decision.requested_label is requested_label
    assert result.domain_decision.violations == ()


@pytest.mark.parametrize(
    ("permitted", "requested"),
    [
        (EvidenceLabel.PHYSICS_CONSTRAINED, EvidenceLabel.EMPIRICALLY_CALIBRATED),
        (EvidenceLabel.EMPIRICALLY_CALIBRATED, EvidenceLabel.PHYSICS_CONSTRAINED),
    ],
)
def test_hydraulic_strong_label_mismatch_fails(
    permitted: EvidenceLabel, requested: EvidenceLabel
) -> None:
    with pytest.raises(AlmondLabError) as exc_info:
        hydraulic_uptake(
            _inputs(evidence_label=requested),
            domain=_domain(permitted_evidence_label=permitted),
        )

    assert exc_info.value.code == "HYDRAULIC_DOMAIN_VIOLATION"
    assert exc_info.value.details["violations"][-1]["reason"] == "evidence_label_incompatible"


def test_hydraulic_exact_weak_extrapolation_retains_all_violations() -> None:
    result = hydraulic_uptake(
        _inputs(
            osmolality_osmol_kg=0.50,
            temperature_k=310.0,
            evidence_label=EvidenceLabel.SYNTHETIC_ONLY,
        ),
        domain=_domain(extrapolation_policy="synthetic_only"),
    )

    assert result.evidence_label is EvidenceLabel.SYNTHETIC_ONLY
    assert result.domain_decision.extrapolated is True
    assert {violation.field for violation in result.domain_decision.violations} == {
        "osmolality_osmol_kg",
        "temperature_k",
    }
    osmolality = next(
        item
        for item in result.domain_decision.violations
        if item.field == "osmolality_osmol_kg"
    )
    assert (osmolality.expected_minimum, osmolality.expected_maximum) == (
        0.01,
        0.40,
    )
    assert osmolality.received_value == 0.50


def test_hydraulic_output_and_nested_domain_decision_are_immutable() -> None:
    result = hydraulic_uptake(_inputs(), domain=_domain())

    with pytest.raises(ValidationError):
        result.actual_l_day = 0.0
    with pytest.raises(ValidationError):
        result.domain_decision.extrapolated = True


@pytest.mark.parametrize(
    ("field", "bad_value"),
    [
        ("osmolality_osmol_kg", "0.1"),
        ("temperature_k", True),
        ("water_density_kg_l", float("nan")),
        ("evidence_label", "invented_label"),
    ],
    ids=["numeric-string", "bool", "nonfinite", "invalid-label"],
)
def test_hydraulic_uptake_revalidates_malformed_copied_inputs(
    field: str, bad_value: object
) -> None:
    malformed = _inputs().model_copy(update={field: bad_value})

    with pytest.raises(AlmondLabError) as exc_info:
        hydraulic_uptake(malformed, domain=_domain())

    assert exc_info.value.code == "HYDRAULIC_INVALID_INPUTS"
    assert exc_info.value.field_path == f"params.{field}"


@pytest.mark.parametrize(
    ("field", "bad_value"),
    [
        ("osmolality_min", "0.01"),
        ("temperature_k_max", True),
        ("osmolality_max", float("inf")),
        ("permitted_evidence_label", "invented_label"),
    ],
    ids=["numeric-string", "bool", "nonfinite", "invalid-label"],
)
def test_hydraulic_uptake_revalidates_malformed_copied_domain(
    field: str, bad_value: object
) -> None:
    malformed = _domain().model_copy(update={field: bad_value})

    with pytest.raises(AlmondLabError) as exc_info:
        hydraulic_uptake(_inputs(), domain=malformed)

    assert exc_info.value.code == "HYDRAULIC_INVALID_DOMAIN"
    assert exc_info.value.field_path == f"domain.{field}"


@pytest.mark.parametrize(
    "requested_label",
    [EvidenceLabel.PHYSICS_CONSTRAINED, EvidenceLabel.HYPOTHESIS_PRIOR],
)
def test_hydraulic_out_of_domain_rejects_strong_or_wrong_weak_label(
    requested_label: EvidenceLabel,
) -> None:
    with pytest.raises(AlmondLabError) as exc_info:
        hydraulic_uptake(
            _inputs(osmolality_osmol_kg=0.50, evidence_label=requested_label),
            domain=_domain(extrapolation_policy="synthetic_only"),
        )

    assert exc_info.value.code == "HYDRAULIC_DOMAIN_VIOLATION"


def test_adjustment_has_no_unregistered_global_bound() -> None:
    result = hydraulic_uptake(_inputs(adjustment_mpa=0.51), domain=_domain())

    assert result.leaf_limit_mpa == pytest.approx(-2.51)
