"""Tests for market price distribution histograms."""

import pandas as pd

from groundtruth.analytics.price_histogram import (
    MAX_HISTOGRAM_BINS,
    RENT_BIN_WIDTH_EUR,
    SALE_BIN_WIDTH_PSM,
    SALE_DISTRIBUTION_MAX_PSM,
    sale_psm_for_distribution,
    segment_price_distribution,
)


def _sale_segment(prices: list[float]) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "listing_type": ["sale"] * len(prices),
            "price_per_sqm": prices,
            "rent_price": [None] * len(prices),
            "area_sqm": [80.0] * len(prices),
        }
    )


def _rent_segment(rents: list[float], areas: list[float] | None = None) -> pd.DataFrame:
    areas = areas or [80.0] * len(rents)
    return pd.DataFrame(
        {
            "listing_type": ["rent"] * len(rents),
            "price_per_sqm": [5.0] * len(rents),
            "rent_price": rents,
            "area_sqm": areas,
        }
    )


class TestPriceHistogram:
    def test_sale_bins(self) -> None:
        segment = _sale_segment(
            [1200, 1300, 1400, 1500, 1600, 1700, 1800, 1900, 2000, 2100, 2200, 2300]
        )
        out = segment_price_distribution(segment, "sale")
        assert out["n"] == 12
        assert out["listing_type"] == "sale"
        assert out["max_psm_exclusive"] == int(SALE_DISTRIBUTION_MAX_PSM)
        assert out["excluded_n"] == 0
        assert len(out["bins"]) >= 3
        assert out["confidence"] in ("low", "medium", "high")
        assert all(
            b["bin_end"] - b["bin_start"] == SALE_BIN_WIDTH_PSM
            or b["bin_end"] == int(SALE_DISTRIBUTION_MAX_PSM)
            for b in out["bins"]
        )

    def test_rent_bins_use_monthly_rent(self) -> None:
        segment = _rent_segment([250, 300, 320, 350, 380, 400, 420, 450, 480, 500, 550, 600])
        out = segment_price_distribution(segment, "rent")
        assert out["n"] == 12
        assert out["listing_type"] == "rent"
        assert "max_psm_exclusive" not in out
        assert len(out["bins"]) >= 3
        # Monthly rent bands should be hundreds of euros, not single-digit €/m².
        assert out["bins"][0]["bin_start"] >= 100
        assert all(b["bin_end"] - b["bin_start"] == RENT_BIN_WIDTH_EUR for b in out["bins"])

    def test_insufficient_sample(self) -> None:
        segment = _sale_segment([1500.0, 1600.0])
        out = segment_price_distribution(segment, "sale")
        assert out["bins"] == []
        assert out["confidence"] == "insufficient"

    def test_sale_histogram_uses_validation_band_then_distribution_ceiling(self) -> None:
        """Below-band and ≥€4,000/m² rows are excluded; €3,999 stays."""
        segment = _sale_segment(
            [
                400,  # below validation band
                1200,
                1300,
                1400,
                1500,
                1600,
                1700,
                1800,
                1900,
                2000,
                3999,
                4000,  # exclusive ceiling
                4500,
                16000,  # above validation band
            ]
        )
        out = segment_price_distribution(segment, "sale")
        assert out["n"] == 10  # 400 and ≥4000 / 16000 out
        assert out["excluded_n"] == 2  # 4000 and 4500 (16000 already out of band)
        assert out["bins"]
        assert all(b["bin_end"] <= SALE_DISTRIBUTION_MAX_PSM for b in out["bins"])
        assert all(b["bin_start"] >= 500 for b in out["bins"])

    def test_sale_cutoff_boundary_is_exclusive(self) -> None:
        bulk = [1500.0 + i * 20 for i in range(20)]
        segment = _sale_segment(bulk + [3999.0, 4000.0, 4001.0])
        out = segment_price_distribution(segment, "sale")
        assert out["n"] == len(bulk) + 1
        assert out["excluded_n"] == 2
        assert max(b["bin_end"] for b in out["bins"]) <= 4000
        assert all(b["bin_start"] < 4000 for b in out["bins"])

    def test_sale_cutoff_helper_matches_segment_filter(self) -> None:
        series = pd.Series([3999.0, 4000.0, 4100.0, 2500.0])
        kept, excluded = sale_psm_for_distribution(series)
        assert list(kept.sort_values()) == [2500.0, 3999.0]
        assert excluded == 2

    def test_sale_cutoff_does_not_affect_rent(self) -> None:
        """High monthly rents stay when €/m²/mo is in band; sale ceiling is unused."""
        segment = _rent_segment(
            [400, 450, 500, 550, 600, 650, 700, 800, 900, 3200],
            areas=[100.0] * 9 + [400.0],
        )
        out = segment_price_distribution(segment, "rent")
        assert out["n"] == 10
        assert max(b["bin_end"] for b in out["bins"]) >= 3200
        assert "max_psm_exclusive" not in out

    def test_rent_histogram_uses_the_same_rows_as_the_rent_median(self) -> None:
        """Out-of-band €/m²/mo rows must not create a rent tail the median never sees."""
        segment = _rent_segment(
            [250, 300, 320, 350, 380, 400, 420, 450, 480, 500, 6300, 40],
            areas=[70.0] * 12,
        )
        out = segment_price_distribution(segment, "rent")
        assert out["n"] == 10
        assert max(b["bin_end"] for b in out["bins"]) <= 600

    def test_large_area_rentals_stay_in_the_distribution(self) -> None:
        """A €3,200/mo ask on 400 m² is €8/m²/mo — genuine, so it must not be dropped."""
        segment = _rent_segment(
            [400, 450, 500, 550, 600, 650, 700, 800, 900, 3200],
            areas=[100.0] * 9 + [400.0],
        )
        out = segment_price_distribution(segment, "rent")
        assert out["n"] == 10
        assert max(b["bin_end"] for b in out["bins"]) >= 3200

    def test_fixed_sale_width_is_fifty_psm(self) -> None:
        bulk = [900 + (i % 70) * 30 for i in range(140)]
        above_cutoff = [4500, 6000, 9000]
        segment = _sale_segment([float(v) for v in bulk + above_cutoff])
        out = segment_price_distribution(segment, "sale")
        assert out["n"] == len(bulk)
        assert out["excluded_n"] == len(above_cutoff)
        assert max(b["bin_end"] for b in out["bins"]) <= SALE_DISTRIBUTION_MAX_PSM
        widths = {b["bin_end"] - b["bin_start"] for b in out["bins"]}
        assert widths <= {SALE_BIN_WIDTH_PSM}
        assert len(out["bins"]) >= 8

    def test_bin_count_stays_within_declared_bounds(self) -> None:
        segment = _sale_segment([800.0 + i * 7 for i in range(400)])
        out = segment_price_distribution(segment, "sale")
        assert 1 <= len(out["bins"]) <= MAX_HISTOGRAM_BINS

    def test_sparse_bins_remain_in_payload_counts(self) -> None:
        """Backend still reports low-count bins; frontend draws every nonempty interval."""
        # Cluster around 1500 plus four isolated highs below the ceiling.
        prices = [1500.0 + (i % 10) * 15 for i in range(40)] + [3200.0, 3300.0, 3400.0, 3500.0]
        out = segment_price_distribution(_sale_segment(prices), "sale")
        assert out["n"] == 44
        sparse = [b for b in out["bins"] if 0 < b["count"] < 5]
        assert sparse, "expected at least one low-count upper bin in the payload"
        assert all(b["bin_end"] - b["bin_start"] == SALE_BIN_WIDTH_PSM for b in out["bins"])
