"""Tests for Evidence Conversion Rate."""

from groundtruth.analytics.ecr import evidence_conversion_rate


def test_ecr_basic() -> None:
    assert evidence_conversion_rate(2, 100) == 0.02
    assert evidence_conversion_rate(2, 20) == 0.1
    assert evidence_conversion_rate(0, 100) == 0.0
    assert evidence_conversion_rate(1, 0) is None
