"""Public payload allowlists — shared by release verify and contract tests.

Mirrors docs/DATA_HANDLING.md: Metrik exposes aggregates and a narrow recent-listing
shape, never listing titles, descriptions, or contact fields.
"""

from __future__ import annotations

from typing import Any

from pydantic import ValidationError

from groundtruth.schemas.lookup import MarketLookup, RecentListing
from groundtruth.schemas.valuation import ComparableListing

# Listing-level keys that must never appear on public recent_listings / comparables.
FORBIDDEN_LISTING_FIELD_KEYS = frozenset(
    {
        "title",
        "description",
        "description_original",
        "phone",
        "email",
        "agent",
        "raw_html",
        "raw_payload",
        "photos",
        "images",
        "image_urls",
        "contact",
        "whatsapp",
        "viber",
        "messenger",
    }
)

RECENT_LISTING_ALLOWED_KEYS = frozenset(RecentListing.model_fields.keys())
COMPARABLE_ALLOWED_KEYS = frozenset(ComparableListing.model_fields.keys())
MARKET_LOOKUP_TOP_LEVEL_KEYS = frozenset(MarketLookup.model_fields.keys())


def assert_no_forbidden_listing_fields(payload: dict[str, Any], *, context: str) -> None:
    """Raise ValueError if a public listing-like dict contains forbidden keys."""
    bad = sorted(FORBIDDEN_LISTING_FIELD_KEYS.intersection(payload.keys()))
    if bad:
        raise ValueError(f"{context}: forbidden public fields present: {bad}")


def assert_recent_listing_public(payload: dict[str, Any], *, context: str) -> None:
    """Validate one recent_listings item against allowlist + RecentListing schema."""
    assert_no_forbidden_listing_fields(payload, context=context)
    unknown = sorted(set(payload.keys()) - RECENT_LISTING_ALLOWED_KEYS)
    if unknown:
        raise ValueError(f"{context}: unexpected recent listing fields: {unknown}")
    try:
        RecentListing.model_validate(payload)
    except ValidationError as exc:
        raise ValueError(f"{context}: invalid RecentListing: {exc}") from exc


def assert_comparable_public(payload: dict[str, Any], *, context: str) -> None:
    """Validate one valuation comparable against allowlist + ComparableListing schema."""
    assert_no_forbidden_listing_fields(payload, context=context)
    unknown = sorted(set(payload.keys()) - COMPARABLE_ALLOWED_KEYS)
    if unknown:
        raise ValueError(f"{context}: unexpected comparable fields: {unknown}")
    try:
        ComparableListing.model_validate(payload)
    except ValidationError as exc:
        raise ValueError(f"{context}: invalid ComparableListing: {exc}") from exc


def assert_market_lookup_public(payload: dict[str, Any], *, context: str) -> None:
    """Validate a lookup cache / API MarketLookup payload for public safety."""
    try:
        MarketLookup.model_validate(payload)
    except ValidationError as exc:
        raise ValueError(f"{context}: invalid MarketLookup: {exc}") from exc

    recent = payload.get("recent_listings") or []
    if not isinstance(recent, list):
        raise ValueError(f"{context}: recent_listings must be a list")
    for i, item in enumerate(recent):
        if not isinstance(item, dict):
            raise ValueError(f"{context}: recent_listings[{i}] must be an object")
        assert_recent_listing_public(item, context=f"{context}.recent_listings[{i}]")
