"""Tests for market lookup service."""

import pandas as pd

from groundtruth.analytics.listing_health import listing_health_signals
from groundtruth.analytics.sample_confidence import confidence_level
from groundtruth.schemas.lookup import RecentListing
from groundtruth.services.lookup import (
    _assign_size_band,
    _build_pulse,
    _pick_diverse_recent,
    _sale_by_property_type_breakdown,
)


class TestLookupHelpers:
    def test_build_pulse_rent_averages(self) -> None:
        segment = pd.DataFrame(
            {
                "listing_type": ["rent", "rent", "sale"],
                "property_type": ["APARTMENT", "APARTMENT", "APARTMENT"],
                "rent_price": [300.0, 400.0, None],
                "sale_price": [None, None, 120_000.0],
                "area_sqm": [60.0, 80.0, 75.0],
                "price_per_sqm": [None, None, 1600.0],
                "bedrooms": [2, 2, 2],
                "source_website": ["gjirafa", "merrjep", "gjirafa"],
                "source_listing_id": ["1", "2", "3"],
            }
        )
        pulse = _build_pulse(segment, observations=3)
        assert pulse.median_rent_eur == 350
        assert pulse.average_rent_psm_eur == 5
        assert pulse.confidence == "insufficient"  # confidence uses rent count (2)
        assert pulse.median_rent_sample.n == 2
        assert pulse.median_rent_sample.confidence == "insufficient"
        assert pulse.active_listings == 3

    def test_build_pulse_inventory_count_all_types(self) -> None:
        segment = pd.DataFrame(
            {
                "listing_type": ["rent", "sale"],
                "property_type": ["APARTMENT", "APARTMENT"],
                "rent_price": [300.0, None],
                "sale_price": [None, 120_000.0],
                "area_sqm": [60.0, 75.0],
                "price_per_sqm": [None, 1600.0],
                "bedrooms": [2, 2],
                "source_website": ["gjirafa", "gjirafa"],
                "source_listing_id": ["1", "2"],
            }
        )
        pulse = _build_pulse(segment, observations=2, inventory_count=23)
        assert pulse.active_listings == 23
        assert pulse.confidence == "insufficient"

    def test_build_pulse_uppercase_listing_type(self) -> None:
        segment = pd.DataFrame(
            {
                "listing_type": ["RENT", "RENT"],
                "property_type": ["APARTMENT", "APARTMENT"],
                "rent_price": [300.0, 500.0],
                "sale_price": [None, None],
                "area_sqm": [60.0, 100.0],
                "price_per_sqm": [None, None],
                "bedrooms": [2, 3],
                "source_website": ["merrjep", "merrjep"],
                "source_listing_id": ["1", "2"],
            }
        )
        segment["listing_type"] = segment["listing_type"].str.lower()
        pulse = _build_pulse(segment, observations=2)
        assert pulse.median_rent_eur == 400

    def test_build_pulse_days_on_market(self) -> None:
        segment = pd.DataFrame(
            {
                "listing_type": ["rent", "rent"],
                "property_type": ["APARTMENT", "APARTMENT"],
                "rent_price": [300.0, 500.0],
                "sale_price": [None, None],
                "area_sqm": [60.0, 100.0],
                "price_per_sqm": [None, None],
                "bedrooms": [2, 3],
                "source_website": ["gjirafa", "merrjep"],
                "source_listing_id": ["a", "b"],
            }
        )
        lifecycle_map = {
            ("gjirafa", "a"): {"days_on_market": 10},
            ("merrjep", "b"): {"days_on_market": 30},
        }
        pulse = _build_pulse(segment, observations=2, lifecycle_map=lifecycle_map)
        assert pulse.median_days_on_market == 20
        assert pulse.days_on_market_sample.n == 2

    def test_sale_by_property_type_breakdown(self) -> None:
        segment = pd.DataFrame(
            {
                "listing_type": ["sale", "sale", "sale", "rent"],
                "property_type": ["APARTMENT", "HOUSE", "LAND", "APARTMENT"],
                "sale_price": [100_000.0, 250_000.0, 50_000.0, None],
                "rent_price": [None, None, None, 400.0],
                "area_sqm": [80.0, 200.0, 500.0, 70.0],
                "price_per_sqm": [1250.0, 1250.0, 600.0, None],
            }
        )
        rows = _sale_by_property_type_breakdown(segment)
        by_label = {r.label: r for r in rows}
        assert by_label["Apartments"].median_sale_eur == 100_000
        assert by_label["Houses"].listings == 1
        assert by_label["Land"].average_sale_psm_eur == 600
        assert "Commercial" not in by_label

    def test_size_bands(self) -> None:
        assert _assign_size_band(45) == "0-50"
        assert _assign_size_band(65) == "50-70"
        assert _assign_size_band(82) == "70-90"
        assert _assign_size_band(100) == "90-120"
        assert _assign_size_band(150) == "120+"

    def test_confidence_tiers(self) -> None:
        assert confidence_level(150) == "high"
        assert confidence_level(50) == "medium"
        assert confidence_level(15) == "low"
        assert confidence_level(3) == "insufficient"

    def test_pick_diverse_recent_balances_sources(self) -> None:
        def row(
            source: str,
            listing_type: str,
            ptype: str,
            area: float,
            lid: str,
        ) -> RecentListing:
            return RecentListing(
                source=source,
                source_listing_id=lid,
                url=f"https://example.com/{lid}",
                listing_type=listing_type,
                property_type=ptype,
                price_eur=1000.0,
                area_sqm=area,
                bedrooms=2,
            )

        candidates = []
        for i in range(12):
            candidates.append(row("pro-rks", "rent", "apartment", 50 + i, f"p{i}"))
        for i in range(4):
            candidates.append(row("merrjep", "rent", "apartment", 60 + i, f"m{i}"))
            candidates.append(row("gjirafa", "sale", "apartment", 70 + i, f"g{i}"))

        picked = _pick_diverse_recent(candidates, limit=9)
        counts = {source: 0 for source in ("gjirafa", "merrjep", "pro-rks")}
        for item in picked:
            counts[item.source] += 1

        assert len(picked) == 9
        assert counts["gjirafa"] == 3
        assert counts["merrjep"] == 3
        assert counts["pro-rks"] == 3

    def test_listing_health_signals(self) -> None:
        signals = listing_health_signals(days_on_market=80, price_changed=True, observation_count=5)
        assert "stale" in signals
        assert "price_reduced" in signals
