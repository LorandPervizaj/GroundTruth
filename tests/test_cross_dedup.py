"""Tests for cross-portal deduplication."""

import pandas as pd

from groundtruth.analytics.cross_dedup import (
    apply_cross_dedupe,
    canonical_corpus_dataframe,
    cross_dedup_stats,
)


def _row(
    source: str,
    lid: str,
    *,
    nh: int = 1,
    area: float = 65.0,
    beds: int = 2,
    sale: float = 92_000.0,
    conf: float = 0.9,
) -> dict:
    return {
        "normalized_id": hash(f"{source}:{lid}") % 10_000,
        "source_website": source,
        "source_listing_id": lid,
        "original_url": f"https://example.com/{lid}",
        "listing_type": "sale",
        "property_type": "APARTMENT",
        "sale_price": sale,
        "rent_price": None,
        "price_per_sqm": sale / area,
        "area_sqm": area,
        "bedrooms": beds,
        "bathrooms": 1,
        "neighborhood_id": nh,
        "street_id": None,
        "building_id": None,
        "neighborhood": "Dardania",
        "confidence_score": conf,
        "listing_price": sale,
    }


def test_merges_cross_portal_duplicates() -> None:
    df = pd.DataFrame(
        [
            _row("gjirafa", "g1"),
            _row("merrjep", "m1"),
            _row("gjirafa", "g2", nh=2, area=80.0, beds=3, sale=120_000.0),
        ]
    )
    stats = cross_dedup_stats(df, threshold=85.0)
    assert stats.raw_listings == 3
    assert stats.canonical_listings == 2
    assert stats.duplicates_removed == 1

    canonical = canonical_corpus_dataframe(df, threshold=85.0)
    assert len(canonical) == 2
    assert (
        "canonical_group_id" not in canonical.columns
        or canonical["canonical_group_id"].nunique() == 2
    )


def test_single_source_rows_stay_separate() -> None:
    df = pd.DataFrame([_row("gjirafa", "g1"), _row("gjirafa", "g2", sale=93_000.0)])
    tagged = apply_cross_dedupe(df, threshold=85.0)
    assert tagged["group_size"].max() == 1
    assert cross_dedup_stats(df).duplicates_removed == 0
