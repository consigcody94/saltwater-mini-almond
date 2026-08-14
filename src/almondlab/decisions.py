"""AlmondLab Paper 1 scientific decision rules, candidate ranking, and slot allocation.

Implements the registered decision criteria:
- H1 Efficacy: posterior probability P(delta_k >= log(1.20)) >= 0.90
- H2 Guardrail: posterior probability P(penalty_k > 0.10) <= 0.10
- H3 Mechanism: candidate-specific directional assay passes
- Advancement score: A[k] = min(p_H1[k], p_H2_good[k], p_H3[k]) (never multiplied)
- Leader-relative ties: A_max - A[k] <= 0.02
- Finalist cap: at most 4 candidates advance to confirmation
- Scientific labels: inconclusive, provisional_leader, co-leading, not_evaluable
- Candidate states: discovery_eligible, confirmation_passed, fully_advanceable
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from math import isclose, log
from typing import Mapping, Sequence

from almondlab.contracts import EvidenceLabel
from almondlab.errors import fail
from almondlab.paper1_contracts import (
    CandidateState,
    DecisionThresholds,
    ScientificLabel,
)


@dataclass(frozen=True, slots=True)
class CandidateDiscoveryScore:
    candidate_id: str
    p_h1_efficacy: float
    p_h2_good: float
    p_h2_bad_penalty: float
    p_h3_mechanism: float
    advancement_score: float  # min(p_h1, p_h2_good, p_h3)
    is_eligible: bool
    scientific_label: ScientificLabel
    rank: int | None = None
    allocated_confirmation_slot: bool = False
    evidence_label: EvidenceLabel = EvidenceLabel.SYNTHETIC_ONLY


@dataclass(frozen=True, slots=True)
class DiscoveryDecisionResult:
    scores: Mapping[str, CandidateDiscoveryScore]
    eligible_candidate_ids: tuple[str, ...]
    finalist_candidate_ids: tuple[str, ...]
    leader_relative_tie_set: tuple[str, ...]
    a_max: float
    scientific_summary: str
    evidence_label: EvidenceLabel = EvidenceLabel.SYNTHETIC_ONLY


def compute_advancement_score(
    p_h1: float,
    p_h2_good: float,
    p_h3: float,
) -> float:
    """Computes the conservative weakest-gate score A[k] = min(p_H1, p_H2_good, p_H3).

    Marginal gate probabilities are never multiplied.
    """
    return min(p_h1, p_h2_good, p_h3)


def evaluate_discovery_candidates(
    candidate_probabilities: Mapping[str, Mapping[str, float]],
    thresholds: DecisionThresholds | None = None,
) -> DiscoveryDecisionResult:
    """Evaluates candidates against the prospective Paper 1 discovery decision rules."""
    h1_min_p = 0.90
    h2_max_bad_p = 0.10
    h3_min_p = 0.90
    tie_margin = 0.02
    finalist_cap = thresholds.finalist_cap if thresholds else 4

    scores: dict[str, CandidateDiscoveryScore] = {}
    eligible: list[tuple[str, float, float, str]] = []  # (id, a_k, p_h2_bad, id)

    for cid, probs in candidate_probabilities.items():
        p_h1 = probs.get("p_h1", 0.0)
        p_h2_good = probs.get("p_h2_good", probs.get("p_h2", 0.0))
        p_h2_bad = probs.get("p_h2_bad", 1.0 - p_h2_good)
        p_h3 = probs.get("p_h3", 0.0)

        a_k = compute_advancement_score(p_h1, p_h2_good, p_h3)
        is_elig = (p_h1 >= h1_min_p) and (p_h2_bad <= h2_max_bad_p) and (p_h3 >= h3_min_p)

        if is_elig:
            eligible.append((cid, a_k, p_h2_bad, cid))

        scores[cid] = CandidateDiscoveryScore(
            candidate_id=cid,
            p_h1_efficacy=p_h1,
            p_h2_good=p_h2_good,
            p_h2_bad_penalty=p_h2_bad,
            p_h3_mechanism=p_h3,
            advancement_score=a_k,
            is_eligible=is_elig,
            scientific_label=ScientificLabel.INCONCLUSIVE,
        )

    if not eligible:
        return DiscoveryDecisionResult(
            scores=scores,
            eligible_candidate_ids=(),
            finalist_candidate_ids=(),
            leader_relative_tie_set=(),
            a_max=0.0,
            scientific_summary="No candidates met the registered discovery eligibility thresholds.",
        )

    # Sort eligible by A_k descending, then lowest p_h2_bad, then ID
    eligible.sort(key=lambda x: (-x[1], x[2], x[3]))
    a_max = eligible[0][1]

    # Leader-relative tie set: A_max - A[k] <= 0.02
    tie_set = tuple(x[0] for x in eligible if (a_max - x[1]) <= tie_margin + 1e-9)

    # Assign scientific labels
    final_scores: dict[str, CandidateDiscoveryScore] = dict(scores)
    for rank_idx, (cid, a_k, p_h2_bad, _) in enumerate(eligible, start=1):
        if len(tie_set) == 1 and cid == tie_set[0]:
            label = ScientificLabel.PROVISIONAL_LEADER
        elif cid in tie_set:
            label = ScientificLabel.CO_LEADING
        else:
            label = ScientificLabel.INCONCLUSIVE

        allocated = rank_idx <= finalist_cap
        old = scores[cid]
        final_scores[cid] = CandidateDiscoveryScore(
            candidate_id=cid,
            p_h1_efficacy=old.p_h1_efficacy,
            p_h2_good=old.p_h2_good,
            p_h2_bad_penalty=old.p_h2_bad_penalty,
            p_h3_mechanism=old.p_h3_mechanism,
            advancement_score=a_k,
            is_eligible=True,
            scientific_label=label,
            rank=rank_idx,
            allocated_confirmation_slot=allocated,
        )

    finalist_ids = tuple(x[0] for x in eligible[:finalist_cap])
    eligible_ids = tuple(x[0] for x in eligible)

    summary = (
        f"{len(eligible)} candidates discovery_eligible; {len(tie_set)} in leader-relative tie set "
        f"(A_max={a_max:.4f}); {len(finalist_ids)} allocated confirmation capacity (cap={finalist_cap})."
    )

    return DiscoveryDecisionResult(
        scores=final_scores,
        eligible_candidate_ids=eligible_ids,
        finalist_candidate_ids=finalist_ids,
        leader_relative_tie_set=tie_set,
        a_max=a_max,
        scientific_summary=summary,
    )
