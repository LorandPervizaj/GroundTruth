from __future__ import annotations

import pandas as pd
import pytest

from groundtruth.analytics.market_integrity import (
    MarketEntity,
    MarketIntegrityError,
    _validate_size_bands,
    profile_market_entity,
)


def _rows() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "normalized_id": 1,
                "source_website": "a",
                "source_listing_id": "1",
                "listing_type": "sale",
                "property_type": "APARTMENT",
                "sale_price": 100_000.0,
                "rent_price": None,
                "price_per_sqm": 2_000.0,
                "listing_price": 100_000.0,
                "area_sqm": 50.0,
                "bedrooms": 1,
                "neighborhood_id": 7,
                "canonical_group_id": "g1",
                "group_size": 2,
                "is_canonical_primary": True,
            },
            {
                "normalized_id": 2,
                "source_website": "b",
                "source_listing_id": "2",
                "listing_type": "sale",
                "property_type": "APARTMENT",
                "sale_price": 100_000.0,
                "rent_price": None,
                "price_per_sqm": 2_000.0,
                "listing_price": 100_000.0,
                "area_sqm": 50.0,
                "bedrooms": 1,
                "neighborhood_id": 7,
                "canonical_group_id": "g1",
                "group_size": 2,
                "is_canonical_primary": False,
            },
            {
                "normalized_id": 3,
                "source_website": "b",
                "source_listing_id": "3",
                "listing_type": "rent",
                "property_type": "STUDIO",
                "sale_price": None,
                "rent_price": 400.0,
                "price_per_sqm": None,
                "listing_price": 400.0,
                "area_sqm": 40.0,
                "bedrooms": 0,
                "neighborhood_id": 7,
                "canonical_group_id": "g2",
                "group_size": 1,
                "is_canonical_primary": True,
            },
        ]
    )


def test_entity_profile_reconciles_metric_populations() -> None:
    tagged = _rows()
    canonical = tagged[tagged["is_canonical_primary"]].copy()
    result = profile_market_entity(
        MarketEntity("neighborhood", "test", "Test", "neighborhood_id", (7,)),
        tagged,
        canonical,
    )

    assert result["dedup"] == {
        "pre_cross_dedup_n": 3,
        "post_cross_dedup_n": 2,
        "duplicate_groups": 1,
        "dedup_removal_pct": 33.33,
    }
    assert result["reconciliation"] == {
        "headline_inventory_n": 2,
        "apartment_n": 2,
        "sale_metric_n": 1,
        "rent_metric_n": 1,
        "bedroom_union_n": 2,
        "size_union_n": 2,
    }
    assert result["bedroom_buckets"][0]["rent_n"] == 1
    assert result["bedroom_buckets"][1]["sale_n"] == 1


def test_frozen_lookup_drift_is_reported() -> None:
    tagged = _rows()
    canonical = tagged[tagged["is_canonical_primary"]].copy()
    entity = MarketEntity(
        "neighborhood",
        "test",
        "Test",
        "neighborhood_id",
        (7,),
        {"headline_inventory_n": 999, "sale_metric_n": 1, "rent_metric_n": 1},
    )
    result = profile_market_entity(entity, tagged, canonical)
    assert result["warnings"][0] == {
        "code": "FROZEN_LOOKUP_DRIFT",
        "metric": "headline_inventory_n",
        "baseline": 2,
        "frozen_lookup": 999,
    }


def test_ulpiana_frozen_lookup_drift_is_a_hard_failure() -> None:
    tagged = _rows()
    canonical = tagged[tagged["is_canonical_primary"]].copy()
    entity = MarketEntity(
        "neighborhood",
        "ulpiana",
        "Ulpiana",
        "neighborhood_id",
        (7,),
        {"headline_inventory_n": 999},
    )
    with pytest.raises(MarketIntegrityError, match="Ulpiana frozen lookup"):
        profile_market_entity(entity, tagged, canonical)


def test_metric_n_cannot_exceed_parent(monkeypatch: pytest.MonkeyPatch) -> None:
    tagged = _rows().iloc[[0]].copy()
    monkeypatch.setattr(
        "groundtruth.analytics.market_integrity.sale_psm_series",
        lambda _: pd.Series([1.0, 2.0]),
    )
    with pytest.raises(MarketIntegrityError, match="sale metric N"):
        profile_market_entity(
            MarketEntity("neighborhood", "test", "Test", "neighborhood_id", (7,)),
            tagged,
            tagged,
        )


def test_production_size_bands_do_not_overlap() -> None:
    _validate_size_bands()
