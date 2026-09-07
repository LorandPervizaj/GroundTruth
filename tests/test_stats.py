"""Tests for robust statistics helpers."""

import pandas as pd

from groundtruth.analytics.dataset_confidence import compute_dataset_confidence, sample_reliability
from groundtruth.analytics.stability import MetricSnapshot, assess_stability
from groundtruth.analytics.stats import (
    bootstrap_median_ci,
    bootstrap_weighted_mean_ci,
    comparable_area_weights,
    compare_medians,
    summarize,
    weighted_average,
)
from groundtruth.claims.registry import Claim, load_claims, register_claim, supersede_claim


class TestStats:
    def test_summarize_basic(self) -> None:
        stats = summarize(pd.Series([100, 200, 300, 400, 500]))
        assert stats is not None
        assert stats.n == 5
        assert stats.median == 300.0
        assert stats.iqr == 200.0

    def test_bootstrap_median_ci(self) -> None:
        result = bootstrap_median_ci([10, 20, 30, 40, 50], n_resamples=1000, seed=1)
        assert result is not None
        median, lo, hi = result
        assert lo <= median <= hi

    def test_area_weights_favor_closer_listings(self) -> None:
        weights = comparable_area_weights([90, 110, 110], 110.0, bandwidth_m2=10.0)
        assert weights[1] == weights[2]
        assert weights[1] > weights[0]

    def test_weighted_average_ignores_distant_outlier(self) -> None:
        values = [5.0, 5.0, 10.0]
        weights = comparable_area_weights([110, 110, 90], 110.0, bandwidth_m2=10.0)
        assert weighted_average(values, weights) < 6.0

    def test_bootstrap_weighted_mean_ci(self) -> None:
        values = [4.0, 4.5, 5.0, 5.5]
        weights = comparable_area_weights([108, 109, 110, 111], 110.0)
        result = bootstrap_weighted_mean_ci(values, weights, n_resamples=500, seed=1)
        assert result is not None
        mean, lo, hi = result
        assert lo <= mean <= hi

    def test_compare_medians_detects_difference(self) -> None:
        a = [10, 11, 12, 13, 14] * 10
        b = [20, 21, 22, 23, 24] * 10
        result = compare_medians(a, b, n_resamples=2000, seed=1)
        assert result["significant_at_95"] is True
        assert result["median_difference"] < 0


class TestDatasetConfidence:
    def test_sample_reliability_curve(self) -> None:
        assert sample_reliability(4) == 0.2
        assert sample_reliability(25) == 0.5
        assert sample_reliability(100) == 1.0

    def test_large_sample_scores_higher(self) -> None:
        small = compute_dataset_confidence(n=8, critical_field_missing_rate=0.1, n_sources=1)
        large = compute_dataset_confidence(n=350, critical_field_missing_rate=0.03, n_sources=2)
        assert large.score > small.score
        assert large.sample_reliability > small.sample_reliability


class TestStability:
    def test_overlapping_cis_are_stable(self) -> None:
        prev = MetricSnapshot(520, 505, 535, 400)
        curr = MetricSnapshot(527, 510, 541, 420)
        result = assess_stability(curr, prev)
        assert result.classification == "stable"
        assert result.ci_overlap is True


class TestClaimRegistry:
    def test_supersede_marks_old_claim(self, tmp_path) -> None:
        path = tmp_path / "registry.csv"
        old = Claim(claim_id="GT-900", statement="old fact", status="published")
        register_claim(old, path=path)
        new = Claim(claim_id="GT-901", statement="updated fact", status="published")
        supersede_claim("GT-900", new, path=path)
        claims = load_claims(path)
        by_id = {c.claim_id: c for c in claims}
        assert by_id["GT-900"].status == "superseded"
        assert by_id["GT-900"].superseded_by == "GT-901"
