"""Metric stability classification — avoid overinterpreting noise."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

StabilityClass = Literal["stable", "moderately_stable", "volatile"]


@dataclass(frozen=True)
class MetricSnapshot:
    """Point-in-time metric with uncertainty."""

    value: float
    ci_lo: float
    ci_hi: float
    n: int


@dataclass(frozen=True)
class StabilityAssessment:
    """Comparison of two metric snapshots."""

    classification: StabilityClass
    ci_overlap: bool
    relative_change: float
    relative_ci_width: float
    score: float

    def as_dict(self) -> dict:
        return {
            "classification": self.classification,
            "ci_overlap": self.ci_overlap,
            "relative_change": round(self.relative_change, 4),
            "relative_ci_width": round(self.relative_ci_width, 4),
            "score": round(self.score, 3),
        }


def _ci_width(snapshot: MetricSnapshot) -> float:
    return max(snapshot.ci_hi - snapshot.ci_lo, 1e-9)


def assess_stability(
    current: MetricSnapshot,
    previous: MetricSnapshot | None = None,
) -> StabilityAssessment:
    """
    Classify whether a metric change is meaningful.

    Without history, uses CI width relative to value and sample size only.
    With history, requires CI overlap and relative change.
    """
    rel_ci = _ci_width(current) / max(abs(current.value), 1e-9)

    if previous is None:
        score = (1.0 - min(rel_ci, 1.0)) * min(1.0, (current.n / 100) ** 0.5)
        if score >= 0.6:
            klass: StabilityClass = "stable"
        elif score >= 0.35:
            klass = "moderately_stable"
        else:
            klass = "volatile"
        return StabilityAssessment(
            classification=klass,
            ci_overlap=True,
            relative_change=0.0,
            relative_ci_width=rel_ci,
            score=score,
        )

    overlap = not (current.ci_hi < previous.ci_lo or current.ci_lo > previous.ci_hi)
    rel_change = abs(current.value - previous.value) / max(abs(previous.value), 1e-9)
    prev_rel_ci = _ci_width(previous) / max(abs(previous.value), 1e-9)
    avg_rel_ci = (rel_ci + prev_rel_ci) / 2

    if overlap and rel_change < avg_rel_ci:
        klass = "stable"
        score = 0.8
    elif overlap or rel_change < 2 * avg_rel_ci:
        klass = "moderately_stable"
        score = 0.5
    else:
        klass = "volatile"
        score = 0.2

    score *= min(1.0, (min(current.n, previous.n) / 100) ** 0.5)

    return StabilityAssessment(
        classification=klass,
        ci_overlap=overlap,
        relative_change=rel_change,
        relative_ci_width=rel_ci,
        score=score,
    )
