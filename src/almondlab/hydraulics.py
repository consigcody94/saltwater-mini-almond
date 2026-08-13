"""Physics-constrained osmotic and hydraulic uptake calculations."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from math import isfinite
from numbers import Real
from typing import Literal

from pydantic import Field, ValidationError, model_validator

from almondlab.contracts import EvidenceLabel
from almondlab.evidence_policy import (
    compose_evidence_labels,
    evidence_label_is_allowed,
)
from almondlab.errors import fail
from almondlab.schemas import FiniteFloat, StrictScientificModel


GAS_CONSTANT_MPA_L_MOL_K = 0.008314462618


def _finite(value: object, field_path: str) -> float:
    if isinstance(value, bool) or not isinstance(value, Real):
        fail(
            "HYDRAULIC_INVALID_NUMBER",
            "value must be a finite real number",
            field_path,
            {"received_type": type(value).__name__},
        )
    try:
        converted = float(value)
    except (TypeError, ValueError, OverflowError):
        fail(
            "HYDRAULIC_INVALID_NUMBER",
            "value must be a finite real number",
            field_path,
            {"received_type": type(value).__name__},
        )
    if not isfinite(converted):
        fail(
            "HYDRAULIC_INVALID_NUMBER",
            "value must be a finite real number",
            field_path,
            {"received_type": type(value).__name__},
        )
    return converted


def osmotic_potential_mpa(
    osmolality_osmol_kg: object = None,
    temperature_k: object = None,
    density_kg_l: object = None,
) -> float:
    """Return bulk osmotic potential from measured osmolality in MPa."""
    osmolality = _finite(osmolality_osmol_kg, "osmolality_osmol_kg")
    temperature = _finite(temperature_k, "temperature_k")
    density = _finite(density_kg_l, "density_kg_l")
    if osmolality < 0.0:
        fail(
            "HYDRAULIC_INVALID_OSMOLALITY",
            "osmolality must be nonnegative",
            "osmolality_osmol_kg",
        )
    if temperature <= 0.0:
        fail(
            "HYDRAULIC_INVALID_TEMPERATURE",
            "temperature must be positive Kelvin",
            "temperature_k",
        )
    if density <= 0.0:
        fail(
            "HYDRAULIC_INVALID_DENSITY",
            "density must be positive",
            "density_kg_l",
        )
    result = -GAS_CONSTANT_MPA_L_MOL_K * temperature * density * osmolality
    if not isfinite(result):
        fail(
            "HYDRAULIC_NONFINITE_RESULT",
            "osmotic-potential arithmetic overflowed",
            "osmotic_potential_mpa",
        )
    return result


class HydraulicInputs(StrictScientificModel):
    """All explicitly unit-bearing inputs to the hydraulic uptake gate."""

    osmolality_osmol_kg: FiniteFloat
    temperature_k: FiniteFloat
    water_density_kg_l: FiniteFloat
    matric_mpa: FiniteFloat
    leaf_critical_mpa: FiniteFloat
    adjustment_mpa: FiniteFloat
    root_conductance_l_day_mpa: FiniteFloat
    potential_transpiration_l_day: FiniteFloat
    specific_ion_factor: FiniteFloat
    evidence_label: EvidenceLabel


class HydraulicDomain(StrictScientificModel):
    """Hash-addressed applicability policy for one hydraulic calculation."""

    model_id: str = Field(min_length=1)
    version: str = Field(min_length=1)
    purpose: Literal["model_applicability", "analytic_verification"]
    osmolality_min: FiniteFloat
    osmolality_max: FiniteFloat
    temperature_k_min: FiniteFloat
    temperature_k_max: FiniteFloat
    permitted_evidence_label: EvidenceLabel
    extrapolation_policy: Literal["deny", "hypothesis_prior", "synthetic_only"]

    @model_validator(mode="before")
    @classmethod
    def normalize_legacy_fixture_key(cls, value: object) -> object:
        """Read version-1 analytic fixtures while emitting only canonical names."""

        if isinstance(value, Mapping) and "permitted_label" in value:
            normalized = dict(value)
            if "permitted_evidence_label" in normalized:
                raise ValueError(
                    "permitted_label and permitted_evidence_label cannot both be supplied"
                )
            normalized["permitted_evidence_label"] = normalized.pop("permitted_label")
            return normalized
        return value

    @model_validator(mode="after")
    def validate_bounds(self) -> "HydraulicDomain":
        if self.osmolality_min < 0.0:
            raise ValueError("osmolality_min must be nonnegative")
        if self.temperature_k_min <= 0.0:
            raise ValueError("temperature_k_min must be positive")
        if self.osmolality_min > self.osmolality_max:
            raise ValueError("osmolality_min must not exceed osmolality_max")
        if self.temperature_k_min > self.temperature_k_max:
            raise ValueError("temperature_k_min must not exceed temperature_k_max")
        return self

    @property
    def sha256(self) -> str:
        canonical = json.dumps(
            self.model_dump(mode="json"), sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
        return hashlib.sha256(canonical).hexdigest()


class HydraulicDomainViolation(StrictScientificModel):
    """One immutable hydraulic-domain decision fact."""

    field: str = Field(min_length=1)
    reason: str = Field(min_length=1)
    expected_minimum: FiniteFloat | None = None
    expected_maximum: FiniteFloat | None = None
    expected_label: EvidenceLabel | None = None
    received_value: FiniteFloat | None = None
    received_label: EvidenceLabel | None = None


class HydraulicDomainDecision(StrictScientificModel):
    """Auditable resolution of one requested label under one domain policy."""

    model_id: str
    version: str
    purpose: Literal["model_applicability", "analytic_verification"]
    domain_sha256: str
    permitted_evidence_label: EvidenceLabel
    requested_label: EvidenceLabel
    resolved_label: EvidenceLabel
    extrapolated: bool
    violations: tuple[HydraulicDomainViolation, ...]


class HydraulicUptake(StrictScientificModel):
    """Immutable hydraulic cap with evidence and complete domain decision."""

    osmotic_potential_mpa: FiniteFloat
    soil_potential_mpa: FiniteFloat
    leaf_limit_mpa: FiniteFloat
    hydraulic_capacity_l_day: FiniteFloat
    ion_limited_demand_l_day: FiniteFloat
    actual_l_day: FiniteFloat
    evidence_label: EvidenceLabel
    domain_decision: HydraulicDomainDecision


def _domain_violation(
    field: str, reason: str, expected: object, received: object
) -> dict[str, object]:
    return {
        "field": field,
        "reason": reason,
        "expected": expected,
        "received": received,
    }


def _immutable_violation(item: dict[str, object]) -> HydraulicDomainViolation:
    if item["reason"] == "outside_inclusive_range":
        expected = item["expected"]
        if not isinstance(expected, dict):
            raise TypeError("range violation requires structured bounds")
        return HydraulicDomainViolation(
            field=str(item["field"]),
            reason=str(item["reason"]),
            expected_minimum=expected["minimum"],
            expected_maximum=expected["maximum"],
            received_value=item["received"],
        )
    return HydraulicDomainViolation(
        field=str(item["field"]),
        reason=str(item["reason"]),
        expected_label=EvidenceLabel(str(item["expected"])),
        received_label=EvidenceLabel(str(item["received"])),
    )


def _validate_domain(
    params: HydraulicInputs,
    domain: HydraulicDomain,
    *,
    osmolality: float,
    temperature_k: float,
) -> HydraulicDomainDecision:
    violations: list[dict[str, object]] = []
    for name, lower, upper, value in (
        (
            "osmolality_osmol_kg",
            domain.osmolality_min,
            domain.osmolality_max,
            osmolality,
        ),
        (
            "temperature_k",
            domain.temperature_k_min,
            domain.temperature_k_max,
            temperature_k,
        ),
    ):
        if value < lower or value > upper:
            violations.append(
                _domain_violation(
                    name,
                    "outside_inclusive_range",
                    {"minimum": lower, "maximum": upper},
                    value,
                )
            )
    label_compatible = evidence_label_is_allowed(
        domain.permitted_evidence_label, params.evidence_label
    )
    if not label_compatible:
        violations.append(
            _domain_violation(
                "evidence_label",
                "evidence_label_incompatible",
                domain.permitted_evidence_label.value,
                params.evidence_label.value,
            )
        )
    extrapolated = bool(violations)
    exact_weak_extrapolation = (
        label_compatible
        and domain.extrapolation_policy != "deny"
        and params.evidence_label.value == domain.extrapolation_policy
        and all(item["reason"] == "outside_inclusive_range" for item in violations)
    )
    if violations and not exact_weak_extrapolation:
        fail(
            "HYDRAULIC_DOMAIN_VIOLATION",
            "input is outside the hydraulic domain",
            "domain",
            {
                "model_id": domain.model_id,
                "version": domain.version,
                "requested_label": params.evidence_label.value,
                "violations": violations,
            },
        )
    resolved = compose_evidence_labels(
        params.evidence_label, domain.permitted_evidence_label
    )
    return HydraulicDomainDecision(
        model_id=domain.model_id,
        version=domain.version,
        purpose=domain.purpose,
        domain_sha256=domain.sha256,
        permitted_evidence_label=domain.permitted_evidence_label,
        requested_label=params.evidence_label,
        resolved_label=resolved,
        extrapolated=extrapolated,
        violations=tuple(_immutable_violation(item) for item in violations),
    )


def _validation_path(root: str, error: Exception) -> str:
    if isinstance(error, ValidationError):
        errors = error.errors(include_url=False, include_context=False)
        if errors:
            return ".".join((root, *(str(item) for item in errors[0]["loc"])))
    return root


def _canonical_inputs(params: HydraulicInputs) -> HydraulicInputs:
    try:
        return HydraulicInputs.model_validate(params)
    except Exception as error:
        fail(
            "HYDRAULIC_INVALID_INPUTS",
            "params failed canonical hydraulic-input validation",
            _validation_path("params", error),
            {"validation_error_type": type(error).__name__},
        )


def _canonical_domain(domain: HydraulicDomain) -> HydraulicDomain:
    try:
        return HydraulicDomain.model_validate(domain)
    except Exception as error:
        fail(
            "HYDRAULIC_INVALID_DOMAIN",
            "domain failed canonical hydraulic-policy validation",
            _validation_path("domain", error),
            {"validation_error_type": type(error).__name__},
        )


def hydraulic_uptake(
    params: object = None, *, domain: object = None
) -> HydraulicUptake:
    """Cap potential transpiration after explicit evidence/domain validation."""
    if not isinstance(params, HydraulicInputs):
        fail(
            "HYDRAULIC_INVALID_INPUTS",
            "params must be validated HydraulicInputs",
            "params",
            {"received_type": type(params).__name__},
        )
    if domain is None:
        fail(
            "HYDRAULIC_DOMAIN_REQUIRED",
            "an explicit validated hydraulic domain is required",
            "domain",
        )
    if not isinstance(domain, HydraulicDomain):
        fail(
            "HYDRAULIC_INVALID_DOMAIN",
            "domain must be validated HydraulicDomain",
            "domain",
            {"received_type": type(domain).__name__},
        )
    params = _canonical_inputs(params)
    domain = _canonical_domain(domain)
    values = {
        name: _finite(getattr(params, name), name)
        for name in (
            "osmolality_osmol_kg",
            "temperature_k",
            "water_density_kg_l",
            "matric_mpa",
            "leaf_critical_mpa",
            "adjustment_mpa",
            "root_conductance_l_day_mpa",
            "potential_transpiration_l_day",
            "specific_ion_factor",
        )
    }
    decision = _validate_domain(
        params,
        domain,
        osmolality=values["osmolality_osmol_kg"],
        temperature_k=values["temperature_k"],
    )
    if values["root_conductance_l_day_mpa"] < 0.0:
        fail(
            "HYDRAULIC_INVALID_CONDUCTANCE",
            "root conductance must be nonnegative",
            "root_conductance_l_day_mpa",
        )
    if values["potential_transpiration_l_day"] < 0.0:
        fail(
            "HYDRAULIC_INVALID_TRANSPIRATION",
            "potential transpiration must be nonnegative",
            "potential_transpiration_l_day",
        )
    if not 0.0 <= values["specific_ion_factor"] <= 1.0:
        fail(
            "HYDRAULIC_INVALID_ION_FACTOR",
            "specific ion factor must be in [0, 1]",
            "specific_ion_factor",
        )
    osmotic = osmotic_potential_mpa(
        values["osmolality_osmol_kg"],
        values["temperature_k"],
        values["water_density_kg_l"],
    )
    soil = values["matric_mpa"] + osmotic
    leaf_limit = values["leaf_critical_mpa"] - values["adjustment_mpa"]
    hydraulic_capacity = max(
        0.0,
        values["root_conductance_l_day_mpa"] * (soil - leaf_limit),
    )
    ion_limited_demand = (
        values["potential_transpiration_l_day"] * values["specific_ion_factor"]
    )
    outputs = (soil, leaf_limit, hydraulic_capacity, ion_limited_demand)
    if not all(isfinite(value) for value in outputs):
        fail(
            "HYDRAULIC_NONFINITE_RESULT",
            "hydraulic arithmetic overflowed",
            "hydraulic_uptake",
        )
    return HydraulicUptake(
        osmotic_potential_mpa=osmotic,
        soil_potential_mpa=soil,
        leaf_limit_mpa=leaf_limit,
        hydraulic_capacity_l_day=hydraulic_capacity,
        ion_limited_demand_l_day=ion_limited_demand,
        actual_l_day=min(ion_limited_demand, hydraulic_capacity),
        evidence_label=decision.resolved_label,
        domain_decision=decision,
    )
