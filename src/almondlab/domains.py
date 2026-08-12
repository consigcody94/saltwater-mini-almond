"""Exact model-domain refusal and explicit weak-extrapolation policy."""

from dataclasses import dataclass

from pydantic import Field

from almondlab.contracts import EvidenceLabel
from almondlab.errors import fail
from almondlab.schemas import ModelDomain, StrictScientificModel, WaterChemistry


class DomainRequest(StrictScientificModel):
    """All chemistry, biological scope, and calibration facts for one request."""

    water: WaterChemistry
    available_analytes: frozenset[str]
    chassis: str = Field(min_length=1)
    life_stage: str = Field(min_length=1)
    calibration_datasets: dict[str, str]
    requested_label: EvidenceLabel


@dataclass(frozen=True)
class DomainValidationResult:
    """Resolved label plus the complete, auditable set of domain violations."""

    evidence_label: EvidenceLabel
    requested_label: EvidenceLabel
    violations: tuple[dict[str, object], ...]


def _violation(
    field: str,
    reason: str,
    expected: object,
    received: object,
) -> dict[str, object]:
    return {
        "field": field,
        "reason": reason,
        "expected": expected,
        "received": received,
    }


def _outside_inclusive_range(
    violations: list[dict[str, object]],
    field: str,
    value: float,
    lower: float,
    upper: float,
) -> None:
    if value < lower or value > upper:
        violations.append(
            _violation(
                f"request.water.{field}",
                "outside_inclusive_range",
                {"minimum": lower, "maximum": upper},
                value,
            )
        )


def validate_domain(
    domain: ModelDomain,
    request: DomainRequest,
) -> DomainValidationResult:
    """Validate every domain dimension, refusing or explicitly weakening output."""
    violations: list[dict[str, object]] = []

    if request.water.ec_kind is not domain.ec_kind:
        violations.append(
            _violation(
                "request.water.ec_kind",
                "ec_kind_mismatch",
                domain.ec_kind.value,
                request.water.ec_kind.value,
            )
        )
    _outside_inclusive_range(
        violations,
        "ec_ds_m",
        request.water.ec_ds_m,
        domain.ec_ds_m_min,
        domain.ec_ds_m_max,
    )
    _outside_inclusive_range(
        violations,
        "measured_osmolality_osmol_kg",
        request.water.measured_osmolality_osmol_kg,
        domain.osmolality_min,
        domain.osmolality_max,
    )
    _outside_inclusive_range(
        violations,
        "temperature_k",
        request.water.temperature_k,
        domain.temperature_k_min,
        domain.temperature_k_max,
    )

    for analyte in domain.required_analytes:
        if analyte not in request.available_analytes:
            violations.append(
                _violation(
                    f"request.available_analytes.{analyte}",
                    "required_analyte_missing",
                    "present",
                    "missing",
                )
            )
            continue
        chemistry_field = (
            "alkalinity_mmol_c_l"
            if analyte == "alkalinity"
            else f"{analyte}_mmol_l"
        )
        if not hasattr(request.water, chemistry_field):
            violations.append(
                _violation(
                    f"request.water.{chemistry_field}",
                    "chemistry_field_missing",
                    "registered chemistry value",
                    "missing",
                )
            )

    if request.chassis not in domain.allowed_chassis:
        violations.append(
            _violation(
                "request.chassis",
                "chassis_not_allowed",
                list(domain.allowed_chassis),
                request.chassis,
            )
        )
    if request.life_stage not in domain.allowed_life_stages:
        violations.append(
            _violation(
                "request.life_stage",
                "life_stage_not_allowed",
                list(domain.allowed_life_stages),
                request.life_stage,
            )
        )

    for dataset_id, expected_hash in domain.calibration_datasets.items():
        received_hash = request.calibration_datasets.get(dataset_id)
        if received_hash is None:
            violations.append(
                _violation(
                    f"request.calibration_datasets.{dataset_id}",
                    "required_dataset_missing",
                    expected_hash,
                    None,
                )
            )
        elif received_hash != expected_hash:
            violations.append(
                _violation(
                    f"request.calibration_datasets.{dataset_id}",
                    "hash_mismatch",
                    expected_hash,
                    received_hash,
                )
            )
    for dataset_id in sorted(
        set(request.calibration_datasets) - set(domain.calibration_datasets)
    ):
        violations.append(
            _violation(
                f"request.calibration_datasets.{dataset_id}",
                "unexpected_dataset",
                None,
                request.calibration_datasets[dataset_id],
            )
        )

    if request.requested_label is not domain.permitted_label:
        violations.append(
            _violation(
                "request.requested_label",
                "evidence_label_mismatch",
                domain.permitted_label.value,
                request.requested_label.value,
            )
        )

    if not violations:
        return DomainValidationResult(
            evidence_label=request.requested_label,
            requested_label=request.requested_label,
            violations=(),
        )
    if (
        domain.extrapolation_policy == "deny"
        or request.requested_label.value != domain.extrapolation_policy
    ):
        fail(
            "DOMAIN_VIOLATION",
            "request is outside the model domain",
            "request",
            {
                "model_id": domain.model_id,
                "version": domain.version,
                "requested_label": request.requested_label.value,
                "violations": violations,
            },
        )

    return DomainValidationResult(
        evidence_label=request.requested_label,
        requested_label=request.requested_label,
        violations=tuple(violations),
    )
