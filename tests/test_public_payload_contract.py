"""Contract tests for public Metrik payloads (DATA_HANDLING allowlist)."""

from __future__ import annotations

import pytest

from groundtruth.schemas.lookup import MarketLookup, MarketPulse, RecentListing
from groundtruth.schemas.valuation import ComparableListing
from groundtruth.services.public_payload import (
    MARKET_LOOKUP_TOP_LEVEL_KEYS,
    assert_comparable_public,
    assert_market_lookup_public,
    assert_recent_listing_public,
)


def _sample_recent(**overrides) -> dict:
    base = {
        "source": "Portal A",
        "source_listing_id": "abc123",
        "url": "https://example.com/listing/1",
        "listing_type": "rent",
        "property_type": "apartment",
        "price_eur": 450.0,
        "price_per_sqm_eur": 7.5,
        "area_sqm": 60.0,
        "bedrooms": 2,
        "first_seen": "2026-01-01",
        "last_seen": "2026-02-01",
        "days_on_market": 30,
        "observation_count": 2,
        "price_changed": False,
        "health_signals": [],
    }
    base.update(overrides)
    return base


def _sample_lookup(**overrides) -> dict:
    pulse = MarketPulse(active_listings=12, confidence="medium")
    base = MarketLookup(
        entity_type="neighborhood",
        slug="ulpiana",
        display_name="Ulpiana",
        pulse=pulse,
        recent_listings=[RecentListing.model_validate(_sample_recent())],
        total_listings=12,
    ).model_dump(mode="json")
    base.update(overrides)
    return base


def test_recent_listing_allowlist_and_schema() -> None:
    payload = _sample_recent()
    assert_recent_listing_public(payload, context="fixture")
    for key in ("title", "description", "phone"):
        assert key not in payload


@pytest.mark.parametrize("forbidden", ["title", "description", "phone", "email", "agent"])
def test_recent_listing_rejects_forbidden_fields(forbidden: str) -> None:
    payload = _sample_recent(**{forbidden: "secret"})
    with pytest.raises(ValueError, match="forbidden"):
        assert_recent_listing_public(payload, context="bad")


def test_comparable_allowlist() -> None:
    payload = ComparableListing(
        source_listing_id="x1",
        area_sqm=55.0,
        bedrooms=2,
        rent_eur=400.0,
        rent_per_sqm=7.27,
    ).model_dump(mode="json")
    assert_comparable_public(payload, context="comp")
    with pytest.raises(ValueError, match="forbidden"):
        assert_comparable_public({**payload, "description": "nope"}, context="bad")


def test_market_lookup_top_level_keys_locked() -> None:
    """Detect accidental expansion of the MarketLookup public surface."""
    assert frozenset(MarketLookup.model_fields.keys()) == MARKET_LOOKUP_TOP_LEVEL_KEYS
    payload = _sample_lookup()
    assert set(payload.keys()) == MARKET_LOOKUP_TOP_LEVEL_KEYS
    assert_market_lookup_public(payload, context="lookup")


def test_market_lookup_rejects_forbidden_recent_fields() -> None:
    payload = _sample_lookup()
    payload["recent_listings"] = [_sample_recent(title="Hidden ad title")]
    with pytest.raises(ValueError, match="forbidden"):
        assert_market_lookup_public(payload, context="lookup")
