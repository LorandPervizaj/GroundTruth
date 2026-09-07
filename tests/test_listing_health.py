"""Tests for listing health signals."""

from groundtruth.analytics.listing_health import listing_health_signals, segment_health_summary


class TestListingHealth:
    def test_stale_and_price_reduced(self) -> None:
        signals = listing_health_signals(days_on_market=75, price_changed=True)
        assert "stale" in signals
        assert "price_reduced" in signals

    def test_long_dom_only(self) -> None:
        signals = listing_health_signals(days_on_market=50, price_changed=False)
        assert signals == ["long_dom"]

    def test_segment_summary(self) -> None:
        entries = [
            {"days_on_market": 10, "price_changed": False},
            {"days_on_market": 70, "price_changed": True},
        ]
        summary = segment_health_summary(entries)
        assert summary["stale_count"] == 1
        assert summary["price_reduced_count"] == 1
        assert summary["median_days_on_market"] == 70
