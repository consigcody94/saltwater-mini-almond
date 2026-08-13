"""Conservative, non-promoting evidence-label policy."""

from __future__ import annotations

import re

from pydantic import BaseModel, ConfigDict, Field, model_validator

from almondlab.contracts import EvidenceLabel


_SHA256 = re.compile(r"^[0-9a-fA-F]{64}$")
_STRONG_LABELS = frozenset(
    {
        EvidenceLabel.PHYSICS_CONSTRAINED,
        EvidenceLabel.EMPIRICALLY_CALIBRATED,
    }
)
_ALLOWED_CLAIMS = {
    EvidenceLabel.PHYSICS_CONSTRAINED: frozenset(
        {
            EvidenceLabel.PHYSICS_CONSTRAINED,
            EvidenceLabel.HYPOTHESIS_PRIOR,
            EvidenceLabel.SYNTHETIC_ONLY,
        }
    ),
    EvidenceLabel.EMPIRICALLY_CALIBRATED: frozenset(
        {
            EvidenceLabel.EMPIRICALLY_CALIBRATED,
            EvidenceLabel.HYPOTHESIS_PRIOR,
            EvidenceLabel.SYNTHETIC_ONLY,
        }
    ),
    EvidenceLabel.HYPOTHESIS_PRIOR: frozenset(
        {EvidenceLabel.HYPOTHESIS_PRIOR, EvidenceLabel.SYNTHETIC_ONLY}
    ),
    EvidenceLabel.SYNTHETIC_ONLY: frozenset({EvidenceLabel.SYNTHETIC_ONLY}),
}


class EvidenceAdapter(BaseModel):
    """Explicitly justified bridge for otherwise incomparable strong evidence."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    source_labels: frozenset[EvidenceLabel]
    justified_label: EvidenceLabel
    justification: str = Field(min_length=1)
    validation_reference_sha256: str

    @model_validator(mode="after")
    def validate_bridge(self) -> "EvidenceAdapter":
        if self.source_labels != _STRONG_LABELS:
            raise ValueError(
                "an evidence adapter must bridge exactly physics and empirical inputs"
            )
        if self.justified_label not in _STRONG_LABELS:
            raise ValueError("an adapter's justified label must be a strong label")
        if not _SHA256.fullmatch(self.validation_reference_sha256):
            raise ValueError("validation_reference_sha256 must be a SHA-256 digest")
        return self


def evidence_label_is_allowed(
    permitted_label: EvidenceLabel, requested_label: EvidenceLabel
) -> bool:
    """Return whether a model may retain, rather than mint, the requested claim."""
    return (
        isinstance(permitted_label, EvidenceLabel)
        and isinstance(requested_label, EvidenceLabel)
        and requested_label in _ALLOWED_CLAIMS[permitted_label]
    )


def compose_evidence_labels(
    *labels: EvidenceLabel,
    adapter: EvidenceAdapter | None = None,
) -> EvidenceLabel:
    """Compose dependencies without promoting incompatible or weak evidence.

    Synthetic evidence dominates, followed by hypothesis-prior evidence.
    Homogeneous strong inputs retain their label. Mixed physics and empirical
    inputs conservatively resolve to ``hypothesis_prior`` unless a validated,
    explicitly supplied adapter justifies one strong result.
    """
    if not labels:
        raise ValueError("at least one evidence label is required")
    if any(not isinstance(label, EvidenceLabel) for label in labels):
        raise TypeError("every evidence input must be an EvidenceLabel")
    label_set = frozenset(labels)
    if EvidenceLabel.SYNTHETIC_ONLY in label_set:
        return EvidenceLabel.SYNTHETIC_ONLY
    if EvidenceLabel.HYPOTHESIS_PRIOR in label_set:
        return EvidenceLabel.HYPOTHESIS_PRIOR
    if len(label_set) == 1:
        return next(iter(label_set))
    if adapter is not None:
        if not isinstance(adapter, EvidenceAdapter) or adapter.source_labels != label_set:
            raise ValueError("adapter does not validate the supplied evidence inputs")
        return adapter.justified_label
    return EvidenceLabel.HYPOTHESIS_PRIOR
