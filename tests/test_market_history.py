"""Tests for biweekly market history aggregation."""

import pandas as pd

from groundtruth.analytics.market_history import biweekly_points_from_observations


class TestBiweeklyHistory:
    def test_aggregates_sale_and_rent_medians(self) -> None:
        # Two listings in the same biweekly bucket (early January 2026).
        df = pd.DataFrame(
            {
                "observed_date": ["2026-01-05", "2026-01-06", "2026-01-07", "2026-01-08"],
                "source_website": ["gjirafa"] * 4,
                "source_listing_id": ["s1", "s1", "s2", "r1"],
                "listing_type": ["sale", "sale", "sale", "rent"],
                "sale_price": [100_000.0, 110_000.0, 120_000.0, None],
                "rent_price": [None, None, None, 600.0],
                "area_sqm": [100.0, 100.0, 80.0, 75.0],
                "property_type": ["APARTMENT"] * 4,
            }
        )
        points = biweekly_points_from_observations(df, min_listings=2)
        assert len(points) == 1
        point = points[0]
        assert point["median_sale_psm_eur"] == 1300
        assert point["median_rent_eur"] is None
        assert point["sale_n"] == 2

    def test_dedupes_listing_within_period(self) -> None:
        df = pd.DataFrame(
            {
                "observed_date": ["2026-03-02", "2026-03-05", "2026-03-08"],
                "source_website": ["gjirafa", "gjirafa", "gjirafa"],
                "source_listing_id": ["s1", "s1", "s1"],
                "listing_type": ["sale", "sale", "sale"],
                "sale_price": [90_000.0, 95_000.0, 100_000.0],
                "rent_price": [None, None, None],
                "area_sqm": [90.0, 90.0, 90.0],
                "property_type": ["APARTMENT"] * 3,
            }
        )
        points = biweekly_points_from_observations(df, min_listings=1)
        assert len(points) == 1
        assert points[0]["median_sale_psm_eur"] == 1110
        assert points[0]["sale_n"] == 1

    def test_empty_without_apartments(self) -> None:
        df = pd.DataFrame(
            {
                "observed_date": ["2026-01-01"],
                "source_website": ["gjirafa"],
                "source_listing_id": ["l1"],
                "listing_type": ["sale"],
                "sale_price": [50_000.0],
                "rent_price": [None],
                "area_sqm": [500.0],
                "property_type": ["LAND"],
            }
        )
        assert biweekly_points_from_observations(df) == []
