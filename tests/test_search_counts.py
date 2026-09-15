"""Unit tests for search listing counts and minimum-inventory filter."""

from __future__ import annotations

from unittest.mock import MagicMock

from groundtruth.services.search import _MIN_SEARCH_LISTINGS, _listing_counts, search_market


class TestListingCounts:
    def test_cache_uses_active_listings_and_merges_canonical_slugs(self, monkeypatch) -> None:
        monkeypatch.setattr(
            "groundtruth.services.lookup_cache.cache_is_loaded",
            lambda: True,
        )
        monkeypatch.setattr(
            "groundtruth.services.lookup_cache.get_cached_listing_counts",
            lambda: {
                "neighborhood/dragodan": 42,
                "neighborhood/arberia": 42,
                "neighborhood/mati": 25,
                "neighborhood/matiqan": 25,
            },
        )
        counts = _listing_counts(MagicMock())
        assert counts[("neighborhood", "arberia")] == 42
        assert counts[("neighborhood", "matiqan")] == 25

    def test_uncached_merges_neighborhood_slugs(self, monkeypatch) -> None:
        import pandas as pd

        monkeypatch.setattr(
            "groundtruth.services.lookup_cache.cache_is_loaded",
            lambda: False,
        )

        df = pd.DataFrame(
            {
                "neighborhood_id": [1, 1, 2, 2, 2, 3],
                "district_id": [None] * 6,
                "street_id": [None] * 6,
                "complex_id": [None] * 6,
                "property_type": ["APARTMENT"] * 6,
                "listing_type": ["rent"] * 6,
            }
        )
        monkeypatch.setattr(
            "groundtruth.services.search.active_corpus_dataframe",
            lambda _session: df,
        )

        session = MagicMock()
        dragodan = MagicMock(id=1, slug="dragodan")
        arberia = MagicMock(id=2, slug="arberia")
        kolovice = MagicMock(id=3, slug="kolovice")
        session.query.return_value.all.side_effect = [
            [dragodan, arberia, kolovice],
            [],
            [],
            [],
        ]

        counts = _listing_counts(session)
        assert counts[("neighborhood", "arberia")] == 5
        assert counts[("neighborhood", "kolovice")] == 1


class TestSearchMinimumListings:
    def test_hides_locations_below_threshold(self, monkeypatch) -> None:
        session = MagicMock()
        monkeypatch.setattr(
            "groundtruth.services.search._listing_counts",
            lambda _session: {
                ("neighborhood", "kolovice"): 25,
                ("neighborhood", "tinyville"): _MIN_SEARCH_LISTINGS - 1,
            },
        )
        monkeypatch.setattr(
            "groundtruth.services.search._load_aliases",
            lambda: {
                "kolovice": [("neighborhood", "kolovice", "Kolovice", "Prishtina")],
                "tinyville": [("neighborhood", "tinyville", "Tinyville", "Prishtina")],
            },
        )
        monkeypatch.setattr(
            "groundtruth.services.lookup_cache.cache_is_loaded",
            lambda: True,
        )

        result = search_market(session, "kol")
        slugs = [r.slug for r in result.results]
        assert "kolovice" in slugs
        assert "tinyville" not in slugs
        kolovice = next(r for r in result.results if r.slug == "kolovice")
        assert kolovice.listings == 25
