"""Tests for €/m² price distribution histograms."""

import pandas as pd

from groundtruth.analytics.price_histogram import segment_price_distribution


class TestPriceHistogram:
    def test_sale_bins(self) -> None:
        segment = pd.DataFrame(
            {
                "listing_type": ["sale"] * 12,
                "price_per_sqm": [
                    1200,
                    1300,
                    1400,
                    1500,
                    1600,
                    1700,
                    1800,
                    1900,
                    2000,
                    2100,
                    2200,
                    2300,
                ],
                "rent_price": [None] * 12,
                "area_sqm": [80.0] * 12,
            }
        )
        out = segment_price_distribution(segment, "sale")
        assert out["n"] == 12
        assert out["listing_type"] == "sale"
        assert len(out["bins"]) >= 3
        assert out["confidence"] in ("low", "medium", "high")

    def test_insufficient_sample(self) -> None:
        segment = pd.DataFrame(
            {
                "listing_type": ["sale", "sale"],
                "price_per_sqm": [1500.0, 1600.0],
                "rent_price": [None, None],
                "area_sqm": [80.0, 90.0],
            }
        )
        out = segment_price_distribution(segment, "sale")
        assert out["bins"] == []
        assert out["confidence"] == "insufficient"
