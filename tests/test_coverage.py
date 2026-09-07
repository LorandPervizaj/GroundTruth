"""Tests for neighborhood coverage analytics."""

import pandas as pd

from groundtruth.analytics.coverage import _clean_apartment_comps, _counts_by_neighborhood


class TestCoverageHelpers:
    def test_clean_apartment_comps_excludes_commercial(self) -> None:
        df = pd.DataFrame(
            {
                "property_type": ["APARTMENT", "APARTMENT", "HOUSE"],
                "is_commercial": [False, True, False],
                "neighborhood_name": ["Ulpiana", "Ulpiana", "Ulpiana"],
            }
        )
        clean = _clean_apartment_comps(df)
        assert len(clean) == 1

    def test_counts_by_neighborhood(self) -> None:
        df = pd.DataFrame({"neighborhood_name": ["A", "A", "B"]})
        assert _counts_by_neighborhood(df) == {"A": 2, "B": 1}
