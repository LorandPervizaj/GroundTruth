"""Slice-level dataset confidence — complements per-listing parser confidence."""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class DatasetConfidence:
    """Confidence that an analytic slice supports reliable inference."""

    n: int
    parser_accuracy: float
    coverage_factor: float
    source_diversity_factor: float
    completeness_factor: float
    sample_reliability: float
    score: float
    tier: str

    def as_dict(self) -> dict:
        return {
            "n": self.n,
            "parser_accuracy": round(self.parser_accuracy, 3),
            "coverage_factor": round(self.coverage_factor, 3),
            "source_diversity_factor": round(self.source_diversity_factor, 3),
            "completeness_factor": round(self.completeness_factor, 3),
            "sample_reliability": round(self.sample_reliability, 3),
            "score": round(self.score, 3),
            "tier": self.tier,
        }


def sample_reliability(n: int) -> float:
    """Smooth effective sample size: min(1, sqrt(n/100))."""
    if n <= 0:
        return 0.0
    return min(1.0, math.sqrt(n / 100.0))


def _tier(score: float) -> str:
    if score < 0.25:
        return "insufficient"
    if score < 0.45:
        return "exploratory"
    if score < 0.65:
        return "moderate"
    return "high"


def compute_dataset_confidence(
    *,
    n: int,
    parser_accuracy: float = 0.97,
    critical_field_missing_rate: float = 0.0,
    n_sources: int = 1,
) -> DatasetConfidence:
    """
    Estimate reliability of an analytic slice.

    score = parser × coverage × diversity × completeness × sample_reliability

    critical_field_missing_rate: fraction of rows missing fields used in the analysis (0–1).
    n_sources: number of independent data sources contributing to the slice.
    """
    coverage_factor = 1.0
    completeness_factor = max(0.0, 1.0 - critical_field_missing_rate)
    source_diversity_factor = min(1.0, n_sources / 2.0)
    reliability = sample_reliability(n)
    score = (
        parser_accuracy
        * coverage_factor
        * source_diversity_factor
        * completeness_factor
        * reliability
    )
    return DatasetConfidence(
        n=n,
        parser_accuracy=parser_accuracy,
        coverage_factor=coverage_factor,
        source_diversity_factor=source_diversity_factor,
        completeness_factor=completeness_factor,
        sample_reliability=reliability,
        score=score,
        tier=_tier(score),
    )
