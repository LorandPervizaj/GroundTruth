"""Product analytics event schema and dashboard snapshot."""

from __future__ import annotations

from pydantic import BaseModel, Field


class ProductEvent(BaseModel):
    """Anonymous product instrumentation event."""

    event: str = Field(min_length=1, max_length=64)
    visitor_id: str | None = Field(default=None, max_length=64)
    municipality: str | None = Field(default=None, max_length=80)
    neighborhood: str | None = Field(default=None, max_length=120)
    entity_type: str | None = Field(default=None, max_length=32)
    slug: str | None = Field(default=None, max_length=80)
    property_type: str | None = Field(default=None, max_length=32)
    listing_type: str | None = Field(default=None, max_length=16)
    valuation_type: str | None = Field(default=None, max_length=16)
    area_sqm: float | None = Field(default=None, ge=0, le=500)
    bedrooms: int | None = Field(default=None, ge=0, le=10)
    had_listing_rent: bool | None = None
    had_asking: bool | None = None
    success: bool | None = None
    confidence: str | None = Field(default=None, max_length=32)
    confidence_tier: str | None = Field(default=None, max_length=32)
    section: str | None = Field(default=None, max_length=64)
    query: str | None = Field(default=None, max_length=80)
    query_length: int | None = Field(default=None, ge=0, le=200)
    results_count: int | None = Field(default=None, ge=0)
    response_time_ms: float | None = Field(default=None, ge=0)
    report_type: str | None = Field(default=None, max_length=64)


class TopNeighborhoodRow(BaseModel):
    neighborhood: str
    events: int


class ProductAnalyticsSnapshot(BaseModel):
    """Aggregated product metrics for a rolling window."""

    window_days: int
    event_count: int
    dau: int
    wau: int
    repeat_visitor_rate_pct: float | None
    valuations_per_day: dict[str, int]
    valuations_requested: int
    valuations_completed: int
    valuation_success_rate_pct: float | None
    market_page_views: int
    searches_performed: int
    zero_result_searches: int
    zero_result_rate_pct: float | None
    rent_yield_views: int
    report_downloads: int
    top_neighborhoods: list[TopNeighborhoodRow]
    confidence_tier_counts: dict[str, int]
    avg_valuation_response_ms: float | None
    listing_type_counts: dict[str, int]
