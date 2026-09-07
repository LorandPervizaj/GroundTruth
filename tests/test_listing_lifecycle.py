"""Tests for observation-based listing lifecycle metrics."""

import pandas as pd

from groundtruth.analytics.listing_lifecycle import segment_days_on_market


class TestSegmentDaysOnMarket:
    def test_median_from_lifecycle_map(self) -> None:
        segment = pd.DataFrame(
            {
                "source_website": ["gjirafa", "merrjep", "gjirafa"],
                "source_listing_id": ["a", "b", "c"],
            }
        )
        lifecycle_map = {
            ("gjirafa", "a"): {"days_on_market": 10},
            ("merrjep", "b"): {"days_on_market": 30},
            ("gjirafa", "c"): {"days_on_market": 20},
        }
        median, n, conf = segment_days_on_market(segment, lifecycle_map)
        assert median == 20
        assert n == 3
        assert conf == "insufficient"

    def test_skips_listings_without_history(self) -> None:
        segment = pd.DataFrame(
            {
                "source_website": ["gjirafa", "merrjep"],
                "source_listing_id": ["a", "missing"],
            }
        )
        lifecycle_map = {("gjirafa", "a"): {"days_on_market": 14}}
        median, n, conf = segment_days_on_market(segment, lifecycle_map)
        assert median == 14
        assert n == 1
        assert conf == "insufficient"

    def test_empty_when_no_matches(self) -> None:
        segment = pd.DataFrame({"source_website": ["gjirafa"], "source_listing_id": ["x"]})
        median, n, conf = segment_days_on_market(segment, {})
        assert median is None
        assert n == 0
        assert conf == "insufficient"
