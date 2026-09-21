from __future__ import annotations

import pytest

from groundtruth.analytics.sample_confidence import MetricEvidence, metric_confidence


@pytest.mark.parametrize(
    ("n", "expected"),
    [(9, "insufficient"), (10, "low"), (29, "low"), (30, "medium"), (99, "medium"), (100, "high")],
)
def test_sample_boundaries(n: int, expected: str) -> None:
    assert metric_confidence(MetricEvidence(n, 6, 0)) == expected


def test_source_diversity_changes_metric_confidence() -> None:
    assert metric_confidence(MetricEvidence(100, 1, 0)) == "low"
    assert metric_confidence(MetricEvidence(100, 6, 0)) == "high"


def test_freshness_caps_confidence() -> None:
    assert metric_confidence(MetricEvidence(100, 6, 181)) == "low"
    assert metric_confidence(MetricEvidence(100, 6, 366)) == "insufficient"


def test_confidence_is_deterministic() -> None:
    evidence = MetricEvidence(100, 6, 10, 25.0)
    assert metric_confidence(evidence) == metric_confidence(evidence)
