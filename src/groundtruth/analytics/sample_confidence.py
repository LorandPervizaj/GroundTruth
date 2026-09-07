"""Sample-size confidence tiers for public-facing metrics."""

from __future__ import annotations

from typing import Literal, TypedDict

# Product confidence thresholds for public market metrics.
CONFIDENCE_HIGH_MIN = 100
CONFIDENCE_MEDIUM_MIN = 30
CONFIDENCE_LOW_MIN = 10

ConfidenceLevel = Literal["high", "medium", "low", "insufficient"]


class SampleMeta(TypedDict):
    n: int
    confidence: ConfidenceLevel


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
