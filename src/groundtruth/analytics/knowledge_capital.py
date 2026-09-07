"""Knowledge Capital — enduring value of the claim corpus."""

from __future__ import annotations

from groundtruth.analytics.voi import IMPACT_SCORES
from groundtruth.claims.registry import Claim

EVIDENCE_STRENGTH: dict[str, float] = {
    "A": 1.0,
    "B": 0.85,
    "C": 0.65,
    "D": 0.4,
    "E": 0.2,
}

MATURITY_STRENGTH: dict[str, float] = {
    "M0": 0.25,
    "M1": 0.5,
    "M2": 0.75,
    "M3": 0.9,
    "M4": 1.0,
}

STRUCTURE_MULTIPLIER: dict[str, float] = {
    "structural": 1.5,
    "descriptive": 1.0,
    "method": 0.8,
}


def claim_quality_score(claim: Claim, *, replicated: bool = False) -> float:
    """Single-claim contribution to Knowledge Capital."""
    impact = IMPACT_SCORES.get(claim.impact or "medium", 3.0) / 5.0
    evidence = EVIDENCE_STRENGTH.get(claim.evidence_grade or "C", 0.65)
    maturity = MATURITY_STRENGTH.get(getattr(claim, "maturity", "M0") or "M0", 0.25)
    structure = STRUCTURE_MULTIPLIER.get(
        getattr(claim, "claim_structure", "descriptive") or "descriptive", 1.0
    )
    persistence = 1.2 if replicated else 1.0
    if claim.status == "superseded":
        return 0.0
    if claim.status != "published":
        return 0.0
    return round(impact * evidence * maturity * structure * persistence, 4)


def knowledge_capital(claims: list[Claim], *, replicated_ids: set[str] | None = None) -> float:
    """Sum of published claim quality scores."""
    replicated_ids = replicated_ids or set()
    return round(
        sum(
            claim_quality_score(claim, replicated=claim.claim_id in replicated_ids)
            for claim in claims
        ),
        4,
    )
