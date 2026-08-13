"""Exact model-domain refusal and explicit weak-extrapolation policy."""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from dataclasses import dataclass
from importlib import resources
from math import isclose
from pathlib import Path

import yaml
from pydantic import Field, ValidationError, model_validator

from almondlab.chemistry import sodium_adsorption_ratio_for_water
from almondlab.contracts import EvidenceLabel
from almondlab.evidence_policy import (
    compose_evidence_labels,
    evidence_label_is_allowed,
)
from almondlab.errors import AlmondLabError, fail
from almondlab.schemas import (
    ChemistryObservation,
    ModelDomain,
    ProvenanceReference,
    StrictScientificModel,
    WaterChemistry,
)


class DomainRequest(StrictScientificModel):
    """Chemistry observations, scope, and provenance facts for one request."""

    water: WaterChemistry
    chemistry_observations: tuple[ChemistryObservation, ...] = Field(min_length=1)
    provenance_sources: tuple[ProvenanceReference, ...] = Field(min_length=1)
    chassis: str = Field(min_length=1)
    life_stage: str = Field(min_length=1)
    calibration_datasets: tuple[ProvenanceReference, ...]
    requested_label: EvidenceLabel

    @model_validator(mode="after")
    def validate_unique_identifiers(self) -> "DomainRequest":
        observation_fields = tuple(row.field_name for row in self.chemistry_observations)
        if len(set(observation_fields)) != len(observation_fields):
            raise ValueError("chemistry observation fields must be unique")
        for name, rows in (
            ("provenance sources", self.provenance_sources),
            ("calibration datasets", self.calibration_datasets),
        ):
            identifiers = tuple(row.provenance_id for row in rows)
            if len(set(identifiers)) != len(identifiers):
                raise ValueError(f"{name} must have unique identifiers")
        return self


@dataclass(frozen=True)
class DomainValidationResult:
    """Resolved label plus the complete, auditable set of domain violations."""

    evidence_label: EvidenceLabel
    requested_label: EvidenceLabel
    violations: tuple[dict[str, object], ...]


@dataclass(frozen=True)
class ModelDomainRegistry:
    """Hash-addressed, immutable collection loaded from one strict policy file."""

    domains: tuple[ModelDomain, ...]
    sha256: str

    def get(self, model_id: str) -> ModelDomain:
        for domain in self.domains:
            if domain.model_id == model_id:
                return domain
        raise KeyError(model_id)


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


def _raise_domain_violation(
    domain: ModelDomain,
    request: DomainRequest,
    violations: list[dict[str, object]],
) -> None:
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


def _required_value(field_name: str, water: WaterChemistry) -> float:
    if field_name == "sar":
        return sodium_adsorption_ratio_for_water(water)
    return getattr(water, field_name)


def _validation_path(root: str, error: Exception) -> str:
    """Return a stable dotted path for the first Pydantic validation error."""

    if isinstance(error, ValidationError):
        errors = error.errors(include_url=False, include_context=False)
        if errors:
            return ".".join((root, *(str(item) for item in errors[0]["loc"])))
    return root


def _canonical_domain(domain: ModelDomain) -> ModelDomain:
    """Revalidate a possibly copied policy, including its hidden instance state."""

    try:
        return ModelDomain.model_validate(domain)
    except Exception as error:
        fail(
            "DOMAIN_INVALID_POLICY",
            "domain failed canonical policy validation",
            _validation_path("domain", error),
            {"validation_error_type": type(error).__name__},
        )


def _canonical_request(request: DomainRequest) -> DomainRequest:
    """Revalidate copied requests and all nested scientific records."""

    try:
        return DomainRequest.model_validate(request)
    except Exception as error:
        fail(
            "DOMAIN_INVALID_REQUEST",
            "request failed canonical scientific-input validation",
            _validation_path("request", error),
            {"validation_error_type": type(error).__name__},
        )


def validate_domain(
    domain: ModelDomain,
    request: DomainRequest,
) -> DomainValidationResult:
    """Validate availability first, then resolve evidence and extrapolation."""
    if not isinstance(domain, ModelDomain):
        fail(
            "DOMAIN_INVALID_POLICY",
            "domain must be validated ModelDomain",
            "domain",
            {"received_type": type(domain).__name__},
        )
    if not isinstance(request, DomainRequest):
        fail(
            "DOMAIN_INVALID_REQUEST",
            "request must be validated DomainRequest",
            "request",
            {"received_type": type(request).__name__},
        )
    domain = _canonical_domain(domain)
    request = _canonical_request(request)

    hard_violations: list[dict[str, object]] = []
    extrapolatable_violations: list[dict[str, object]] = []
    observations = {row.field_name: row for row in request.chemistry_observations}
    provenance = {row.provenance_id: row.sha256 for row in request.provenance_sources}

    if request.water.ec_kind is not domain.ec_kind:
        hard_violations.append(
            _violation(
                "request.water.ec_kind",
                "ec_kind_mismatch",
                domain.ec_kind.value,
                request.water.ec_kind.value,
            )
        )
    _outside_inclusive_range(
        extrapolatable_violations,
        "ec_ds_m",
        request.water.ec_ds_m,
        domain.ec_ds_m_min,
        domain.ec_ds_m_max,
    )
    _outside_inclusive_range(
        extrapolatable_violations,
        "measured_osmolality_osmol_kg",
        request.water.measured_osmolality_osmol_kg,
        domain.osmolality_min,
        domain.osmolality_max,
    )
    _outside_inclusive_range(
        extrapolatable_violations,
        "temperature_k",
        request.water.temperature_k,
        domain.temperature_k_min,
        domain.temperature_k_max,
    )

    required_kinds = {
        requirement.field_name: requirement for requirement in domain.required_chemistry_fields
    }
    analyte_fields = {
        "alkalinity_mmol_c_l" if analyte == "alkalinity" else f"{analyte}_mmol_l"
        for analyte in domain.required_analytes
    }
    for field_name in (*required_kinds, *sorted(analyte_fields)):
        observation = observations.get(field_name)
        path = f"request.chemistry_observations.{field_name}"
        if observation is None:
            hard_violations.append(
                _violation(path, "required_observation_missing", "present", "missing")
            )
            continue
        expected_value: float | None = None
        try:
            expected_value = _required_value(field_name, request.water)
        except AlmondLabError as error:
            hard_violations.append(
                _violation(
                    f"{path}.value",
                    "required_computation_failed",
                    "computable from validated water chemistry",
                    {"code": error.code, "field_path": error.field_path},
                )
            )
        except (AttributeError, TypeError, ValueError, OverflowError) as error:
            hard_violations.append(
                _violation(
                    f"{path}.value",
                    "required_computation_failed",
                    "computable from validated water chemistry",
                    {"code": type(error).__name__, "field_path": field_name},
                )
            )
        if expected_value is not None and not isclose(
            observation.value, expected_value, rel_tol=1e-12, abs_tol=1e-12
        ):
            hard_violations.append(
                _violation(
                    f"{path}.value",
                    "observation_value_mismatch",
                    expected_value,
                    observation.value,
                )
            )
        requirement = required_kinds.get(field_name)
        if requirement is not None:
            if observation.observation_kind != requirement.observation_kind:
                hard_violations.append(
                    _violation(
                        f"{path}.observation_kind",
                        "observation_kind_mismatch",
                        requirement.observation_kind,
                        observation.observation_kind,
                    )
                )
            if requirement.ec_kind is not None and observation.ec_kind is not requirement.ec_kind:
                hard_violations.append(
                    _violation(
                        f"{path}.ec_kind",
                        "ec_kind_mismatch",
                        requirement.ec_kind.value,
                        observation.ec_kind.value if observation.ec_kind else None,
                    )
                )
        expected_hash = provenance.get(observation.provenance_id)
        if expected_hash is None:
            hard_violations.append(
                _violation(
                    f"{path}.provenance_id",
                    "provenance_source_missing",
                    "registered source",
                    observation.provenance_id,
                )
            )
        elif expected_hash != observation.provenance_sha256:
            hard_violations.append(
                _violation(
                    f"{path}.provenance_sha256",
                    "provenance_hash_mismatch",
                    expected_hash,
                    observation.provenance_sha256,
                )
            )

    if request.chassis not in domain.allowed_chassis:
        extrapolatable_violations.append(
            _violation(
                "request.chassis",
                "chassis_not_allowed",
                list(domain.allowed_chassis),
                request.chassis,
            )
        )
    if request.life_stage not in domain.allowed_life_stages:
        extrapolatable_violations.append(
            _violation(
                "request.life_stage",
                "life_stage_not_allowed",
                list(domain.allowed_life_stages),
                request.life_stage,
            )
        )

    expected_datasets = {
        row.provenance_id: row.sha256 for row in domain.calibration_datasets
    }
    received_datasets = {
        row.provenance_id: row.sha256 for row in request.calibration_datasets
    }
    for dataset_id, expected_hash in expected_datasets.items():
        received_hash = received_datasets.get(dataset_id)
        if received_hash is None:
            hard_violations.append(
                _violation(
                    f"request.calibration_datasets.{dataset_id}",
                    "required_dataset_missing",
                    expected_hash,
                    None,
                )
            )
        elif received_hash != expected_hash:
            hard_violations.append(
                _violation(
                    f"request.calibration_datasets.{dataset_id}",
                    "hash_mismatch",
                    expected_hash,
                    received_hash,
                )
            )
    for dataset_id in sorted(set(received_datasets) - set(expected_datasets)):
        hard_violations.append(
            _violation(
                f"request.calibration_datasets.{dataset_id}",
                "unexpected_dataset",
                None,
                received_datasets[dataset_id],
            )
        )

    if hard_violations:
        _raise_domain_violation(
            domain,
            request,
            [*hard_violations, *extrapolatable_violations],
        )

    dependency_label = compose_evidence_labels(
        *(row.evidence_label for row in request.chemistry_observations)
    )
    resolved_dependency_label = compose_evidence_labels(
        request.requested_label, dependency_label
    )
    if resolved_dependency_label is not request.requested_label:
        hard_violations.append(
            _violation(
                "request.requested_label",
                "evidence_dependency_mismatch",
                resolved_dependency_label.value,
                request.requested_label.value,
            )
        )
    if not evidence_label_is_allowed(
        domain.permitted_evidence_label, request.requested_label
    ):
        hard_violations.append(
            _violation(
                "request.requested_label",
                "evidence_label_incompatible",
                domain.permitted_evidence_label.value,
                request.requested_label.value,
            )
        )

    if hard_violations:
        _raise_domain_violation(
            domain,
            request,
            [*hard_violations, *extrapolatable_violations],
        )
    if not extrapolatable_violations:
        return DomainValidationResult(
            evidence_label=request.requested_label,
            requested_label=request.requested_label,
            violations=(),
        )
    if (
        domain.extrapolation_policy == "deny"
        or request.requested_label.value != domain.extrapolation_policy
    ):
        _raise_domain_violation(domain, request, extrapolatable_violations)
    return DomainValidationResult(
        evidence_label=request.requested_label,
        requested_label=request.requested_label,
        violations=tuple(extrapolatable_violations),
    )


def load_model_domains(path: str | Path | None = None) -> ModelDomainRegistry:
    """Load the authoritative strict domain registry and retain its content hash."""
    if path is None:
        raw = (
            resources.files("almondlab.resources")
            .joinpath("configs/model_domains.yaml")
            .read_bytes()
        )
    else:
        raw = Path(path).read_bytes()
    payload = yaml.safe_load(raw)
    if not isinstance(payload, Mapping) or not payload:
        raise ValueError("model domain policy must be a nonempty mapping")
    domains: list[ModelDomain] = []
    for registry_id, record in payload.items():
        if not isinstance(registry_id, str) or not isinstance(record, Mapping):
            raise ValueError("model domain entries must be named mappings")
        domain = ModelDomain(**dict(record))
        if domain.model_id != registry_id:
            raise ValueError("registry key must match model_id")
        domains.append(domain)
    if len({domain.model_id for domain in domains}) != len(domains):
        raise ValueError("model domain identifiers must be unique")
    return ModelDomainRegistry(
        domains=tuple(domains),
        sha256=hashlib.sha256(raw).hexdigest(),
    )
