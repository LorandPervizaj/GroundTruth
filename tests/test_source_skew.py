"""Source skew and confidence diversity penalty tests."""

from __future__ import annotations

from groundtruth.analytics.sample_confidence import confidence_level, sample_meta
from groundtruth.analytics.source_skew import source_diversity_penalty


def test_source_diversity_penalty_balanced() -> None:
    assert source_diversity_penalty({"gjirafa": 0.5, "merrjep": 0.5}) == 1.0


def test_source_diversity_penalty_dominant() -> None:
    penalty = source_diversity_penalty({"gjirafa": 0.8, "merrjep": 0.2})
    assert 0.85 <= penalty < 1.0


def test_confidence_downgraded_by_skew() -> None:
    assert confidence_level(50, source_diversity=1.0) == "medium"
    assert confidence_level(35, source_diversity=0.85) == "low"


def test_sample_meta_includes_skew() -> None:
    meta = sample_meta(120, source_diversity=0.9)
    assert meta["n"] == 120
    assert meta["confidence"] in ("high", "medium", "low", "insufficient")
