"""Schemas for informal Facebook Marketplace and group sampling."""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field

CaptureMethod = Literal["manual", "export"]
ListingTypeLit = Literal["sale", "rent", "unknown"]


class FacebookMarketplaceCapture(BaseModel):
    """Raw manual capture of a Marketplace listing (B1)."""

    title: str | None = None
    description: str | None = None
    price_text: str | None = None
    listing_type: ListingTypeLit = "unknown"
    url: str = Field(min_length=10, max_length=500)
    neighborhood_guess: str | None = Field(default=None, max_length=120)
    area_sqm: float | None = Field(default=None, ge=10, le=2000)
    bedrooms: int | None = Field(default=None, ge=0, le=10)
    captured_at: date | None = None
    capture_method: CaptureMethod = "manual"


class InformalListingRecord(BaseModel):
    """Normalized informal listing — quarantine tier, not in active corpus."""

    source_website: Literal["facebook"] = "facebook"
    parser_version: str = "0.1.0-facebook-informal"
    source_listing_id: str
    original_url: str
    title: str | None = None
    description: str | None = None
    listing_type: ListingTypeLit
    price_eur: int | None = None
    price_per_sqm_eur: int | None = None
    area_sqm: int | None = None
    bedrooms: int | None = None
    neighborhood_guess: str | None = None
    captured_at: str
    capture_method: CaptureMethod = "manual"
    confidence_tier: Literal["informal"] = "informal"


class FacebookGroupSample(BaseModel):
    """Manual observation from a Prishtina RE Facebook group (B3)."""

    group_id: str = Field(min_length=2, max_length=80)
    group_name: str | None = Field(default=None, max_length=200)
    post_url: str | None = Field(default=None, max_length=500)
    snippet: str = Field(min_length=5, max_length=2000)
    price_eur: int | None = Field(default=None, ge=50, le=5_000_000)
    listing_type: ListingTypeLit = "unknown"
    neighborhood_guess: str | None = Field(default=None, max_length=120)
    area_sqm: int | None = Field(default=None, ge=10, le=2000)
    bedrooms: int | None = Field(default=None, ge=0, le=10)
    sampled_at: datetime | None = None
    sampler: str = "manual"
