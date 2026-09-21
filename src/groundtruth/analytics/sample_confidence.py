"""Sample-size confidence tiers for public-facing metrics."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Literal, TypedDict

# Product confidence thresholds for public market metrics.
CONFIDENCE_HIGH_MIN = 100
CONFIDENCE_MEDIUM_MIN = 30
CONFIDENCE_LOW_MIN = 10

ConfidenceLevel = Literal["high", "medium", "low", "insufficient"]


class SampleMeta(TypedDict):
    n: int
    confidence: ConfidenceLevel


@dataclass(frozen=True)
class MetricEvidence:
    sample_n: int
    source_count: int
    freshness_days: int
    largest_source_share_pct: float | None = None


_TIER_RANK: dict[ConfidenceLevel, int] = {
    "insufficient": 0,
    "low": 1,
    "medium": 2,
    "high": 3,
}


def _cap(level: ConfidenceLevel, maximum: ConfidenceLevel) -> ConfidenceLevel:
    return level if _TIER_RANK[level] <= _TIER_RANK[maximum] else maximum


def metric_confidence(evidence: MetricEvidence) -> ConfidenceLevel:
    """Transparent deterministic v1 confidence: sample, sources, freshness."""
    level = confidence_level(evidence.sample_n)
    if evidence.source_count <= 1:
        level = _cap(level, "low")
    elif evidence.source_count <= 2:
        level = _cap(level, "medium")
    if evidence.largest_source_share_pct is not None and evidence.largest_source_share_pct >= 80:
        level = _cap(level, "low")
    if evidence.freshness_days > 365:
        return "insufficient"
    if evidence.freshness_days > 180:
        level = _cap(level, "low")
    return level


def metric_evidence_payload(evidence: MetricEvidence) -> dict[str, int | float | None]:
    return asdict(evidence)


def confidence_level(n: int, *, source_diversity: float = 1.0) -> ConfidenceLevel:
    """Map observation count to a visual confidence tier.

    ``source_diversity`` is a multiplier in (0, 1] from source_skew analysis;
    it downgrades tiers when one portal dominates the sample (structural skew).
    """
    effective_n = int(n * source_diversity)
    if effective_n < CONFIDENCE_LOW_MIN:
        return "insufficient"
    if effective_n >= CONFIDENCE_HIGH_MIN:
        return "high"
    if effective_n >= CONFIDENCE_MEDIUM_MIN:
        return "medium"
    return "low"


def sample_meta(n: int, *, source_diversity: float = 1.0) -> SampleMeta:
    return {"n": int(n), "confidence": confidence_level(n, source_diversity=source_diversity)}
