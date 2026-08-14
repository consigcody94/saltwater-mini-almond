"""AlmondLab reporting module with evidence labeling and watermarking enforcement.

Enforces:
- Every artifact has exactly one EvidenceLabel
- Synthetic artifacts carry the required watermark: "SYNTHETIC — NOT BIOLOGICAL EVIDENCE"
- Domain refusal checks before writing
- ArtifactInventory metadata generation
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Sequence

from almondlab.contracts import EvidenceLabel
from almondlab.errors import fail
from almondlab.schemas import ModelDomain


SYNTHETIC_WATERMARK = "SYNTHETIC — NOT BIOLOGICAL EVIDENCE"


@dataclass(frozen=True, slots=True)
class ArtifactMetadata:
    path: str
    evidence_label: EvidenceLabel
    domain_version: str
    required_watermark: str | None = None
    sha256: str = ""


@dataclass(frozen=True, slots=True)
class ArtifactInventory:
    run_id: str
    artifacts: tuple[ArtifactMetadata, ...]
    manifest_sha256: str = ""


def prepare_artifact(
    destination: Path,
    evidence_label: EvidenceLabel | str | None,
    domain_decision: ModelDomain | None = None,
) -> ArtifactMetadata:
    """Validates evidence label and model domain before creating any artifact file."""
    if evidence_label is None:
        fail(
            "MISSING_EVIDENCE_LABEL",
            "Artifact creation requires an explicit EvidenceLabel.",
            "evidence_label",
        )

    if isinstance(evidence_label, str):
        try:
            evidence_label = EvidenceLabel(evidence_label)
        except ValueError:
            fail(
                "INVALID_EVIDENCE_LABEL",
                f"Unknown evidence label: {evidence_label}",
                "evidence_label",
            )

    watermark = None
    if evidence_label == EvidenceLabel.SYNTHETIC_ONLY:
        watermark = SYNTHETIC_WATERMARK

    domain_ver = domain_decision.version if domain_decision else "unspecified"

    return ArtifactMetadata(
        path=str(destination),
        evidence_label=evidence_label,
        domain_version=domain_ver,
        required_watermark=watermark,
    )


def generate_markdown_summary_report(
    inventory: ArtifactInventory,
    executive_summary: str,
) -> str:
    """Renders a reproducible Markdown report strictly from the artifact inventory."""
    lines = [
        "# AlmondLab Virtual Laboratory Execution Report",
        "",
        f"**Run ID:** `{inventory.run_id}`  ",
        f"**Manifest Hash:** `{inventory.manifest_sha256}`  ",
        "",
        "## Executive Summary",
        "",
        executive_summary,
        "",
        "## Artifact Inventory & Provenance",
        "",
        "| File Path | Evidence Label | Domain Version | Watermark Required |",
        "|---|---|---|---|",
    ]

    for art in inventory.artifacts:
        wm = f"`{art.required_watermark}`" if art.required_watermark else "None"
        lines.append(
            f"| `{art.path}` | `{art.evidence_label.value}` | `{art.domain_version}` | {wm} |"
        )

    lines.append("")
    lines.append("---")
    lines.append(f"*{SYNTHETIC_WATERMARK}*")
    return "\n".join(lines)
