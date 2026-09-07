"""Tests for sample-size confidence tiers."""

from groundtruth.analytics.sample_confidence import (
    CONFIDENCE_HIGH_MIN,
    CONFIDENCE_LOW_MIN,
    CONFIDENCE_MEDIUM_MIN,
    confidence_level,
    sample_meta,
)


def test_threshold_constants() -> None:
    assert CONFIDENCE_HIGH_MIN == 100
    assert CONFIDENCE_MEDIUM_MIN == 30
    assert CONFIDENCE_LOW_MIN == 10


def test_confidence_level_tiers() -> None:
    assert confidence_level(150) == "high"
    assert confidence_level(100) == "high"
    assert confidence_level(50) == "medium"
    assert confidence_level(30) == "medium"
    assert confidence_level(15) == "low"
    assert confidence_level(10) == "low"
    assert confidence_level(3) == "insufficient"


def test_sample_meta_shape() -> None:
    meta = sample_meta(42)
    assert meta == {"n": 42, "confidence": "medium"}
