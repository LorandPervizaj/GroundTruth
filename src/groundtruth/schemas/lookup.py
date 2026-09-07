"""Schemas for market lookup API."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

EntityType = Literal["neighborhood", "district", "street", "complex"]
ConfidenceLevel = Literal["high", "medium", "low", "insufficient"]
PriceTier = Literal["$", "$$", "$$$", "$$$$"]


class MetricSample(BaseModel):
    """Sample size backing a displayed aggregate."""

    n: int = 0
    confidence: ConfidenceLevel = "insufficient"


PropertyTypeKey = Literal["apartment", "house", "land", "commercial", "other"]


class PropertyTypeMarket(BaseModel):
    """Sale market stats for one property segment (apartments, houses, land, …)."""

    property_type: PropertyTypeKey
    label: str
    average_sale_psm_eur: float | None = None
    median_sale_eur: float | None = None
    median_area_sqm: float | None = None
    listings: int = 0
    confidence: ConfidenceLevel = "insufficient"


class MarketPulse(BaseModel):
    average_sale_psm_eur: float | None = None
    average_rent_psm_eur: float | None = None
    median_sale_eur: float | None = None
    median_rent_eur: float | None = None
    typical_area_sqm: float | None = None
    typical_bedrooms: int | None = None
    active_listings: int = 0
    observations: int = 0
    data_sources: list[str] = Field(default_factory=list)
    confidence: ConfidenceLevel = "insufficient"
    sale_psm_sample: MetricSample = Field(default_factory=MetricSample)
    rent_psm_sample: MetricSample = Field(default_factory=MetricSample)
    median_sale_sample: MetricSample = Field(default_factory=MetricSample)
    median_rent_sample: MetricSample = Field(default_factory=MetricSample)
    median_days_on_market: int | None = None
    days_on_market_sample: MetricSample = Field(default_factory=MetricSample)
    last_updated: datetime | None = None


class PricePercentiles(BaseModel):
    """Sale €/m² distribution at key percentile breakpoints."""

    p10_sale_psm: float | None = None
    p50_sale_psm: float | None = None
    p90_sale_psm: float | None = None
    n: int = 0


class CityComparison(BaseModel):
    """Neighborhood price level relative to city-wide baseline."""

    city_median_sale_psm: float | None = None
    city_median_rent: float | None = None
    neighborhood_sale_psm: float | None = None
    neighborhood_rent: float | None = None
    premium_pct: float | None = None
    price_tier: PriceTier = "$$"


class BedroomBreakdown(BaseModel):
    bedrooms: int
    label: str
    average_sale_psm_eur: float | None = None
    average_rent_psm_eur: float | None = None
    median_sale_eur: float | None = None
    median_rent_eur: float | None = None
    listings: int = 0
    confidence: ConfidenceLevel = "insufficient"


class SizeBreakdown(BaseModel):
    size_band: str
    label: str
    average_sale_psm_eur: float | None = None
    average_rent_psm_eur: float | None = None
    median_sale_eur: float | None = None
    median_rent_eur: float | None = None
    listings: int = 0
    confidence: ConfidenceLevel = "insufficient"


class RecentListing(BaseModel):
    source: str
    source_listing_id: str
    url: str
    listing_type: str
    property_type: str | None = None
    price_eur: float
    price_per_sqm_eur: float | None = None
    area_sqm: float | None = None
    bedrooms: int | None = None
    first_seen: str | None = None
    last_seen: str | None = None
    days_on_market: int | None = None
    observation_count: int | None = None
    price_changed: bool | None = None
    health_signals: list[str] = Field(default_factory=list)


class GeoSummary(BaseModel):
    centroid_lat: float | None = None
    centroid_lng: float | None = None
    listings_with_coords: int = 0
    source_coords_count: int = 0
    boundary_mismatch_count: int = 0
    median_distance_km: float | None = None
    max_distance_km: float | None = None


class PriceHistogramBin(BaseModel):
    bin_start: int
    bin_end: int
    count: int


class PriceDistribution(BaseModel):
    listing_type: Literal["sale", "rent"]
    bins: list[PriceHistogramBin] = Field(default_factory=list)
    n: int = 0
    confidence: ConfidenceLevel = "insufficient"


class ListingHealthSummary(BaseModel):
    median_days_on_market: int | None = None
    stale_count: int = 0
    price_reduced_count: int = 0
    tracked_listings: int = 0


class RelatedEntity(BaseModel):
    entity_type: EntityType
    slug: str
    display_name: str
    listings: int = 0


class ParentEntity(BaseModel):
    entity_type: Literal["neighborhood", "district"] = "neighborhood"
    slug: str
    display_name: str


class ChildEntity(BaseModel):
    entity_type: EntityType
    slug: str
    display_name: str
    listings: int = 0


class CorpusMeta(BaseModel):
    corpus_updated_at: datetime | None = None
    active_listings: int = 0
    active_listings_confidence: ConfidenceLevel = "insufficient"
    raw_listings: int = 0
    cross_portal_duplicates_removed: int = 0
    cross_portal_duplicate_groups: int = 0
    median_days_on_market: int | None = None
    data_sources: list[str] = Field(default_factory=list)
    source_count: int = 0
    geocode_coverage_pct: float | None = None
    geocode_mismatch_pct: float | None = None
    dataset_version: str = "live"
    dataset_frozen_at: datetime | None = None
    dataset_fingerprint: str | None = None
    invalid_pct: float | None = None
    golden_accuracy_pct: float | None = None
    public_product_scope: str = "rent_and_sale"


class MapMarketPoint(BaseModel):
    slug: str
    name: str
    latitude: float
    longitude: float
    listings: int = 0
    confidence: ConfidenceLevel = "insufficient"
    density_weight: float = 0.0
    median_rent_psm_eur: float | None = None


class MapMarketsResponse(BaseModel):
    points: list[MapMarketPoint] = Field(default_factory=list)
    corpus_updated_at: datetime | None = None
    geocode_note: str = ""


class MarketLookup(BaseModel):
    entity_type: EntityType
    slug: str
    display_name: str
    also_known_as: list[str] = Field(default_factory=list)
    requested_slug: str | None = None
    city: str = "Prishtina"
    corpus_updated_at: datetime | None = None
    pulse: MarketPulse
    price_percentiles: PricePercentiles | None = None
    city_comparison: CityComparison | None = None
    sale_by_property_type: list[PropertyTypeMarket] = Field(default_factory=list)
    bedroom_breakdown: list[BedroomBreakdown] = Field(default_factory=list)
    size_breakdown: list[SizeBreakdown] = Field(default_factory=list)
    recent_listings: list[RecentListing] = Field(default_factory=list)
    parent: ParentEntity | None = None
    breadcrumb: list[ParentEntity] = Field(default_factory=list)
    children: list[ChildEntity] = Field(default_factory=list)
    related: list[RelatedEntity] = Field(default_factory=list)
    geo: GeoSummary | None = None
    sale_price_distribution: PriceDistribution | None = None
    rent_price_distribution: PriceDistribution | None = None
    listing_health: ListingHealthSummary | None = None
    dataset_version: str = "live"
    total_listings: int = 0


class SearchResult(BaseModel):
    entity_type: EntityType
    slug: str
    display_name: str
    subtitle: str
    listings: int = 0
    match_reason: str


class SearchResponse(BaseModel):
    query: str
    results: list[SearchResult] = Field(default_factory=list)


class HistoryPoint(BaseModel):
    period_start: str
    period_end: str
    median_sale_psm_eur: int | None = None
    median_rent_eur: int | None = None
    median_rent_psm_eur: float | None = None
    sale_n: int = 0
    rent_n: int = 0
    inventory_n: int = 0
    sale_confidence: ConfidenceLevel = "insufficient"
    rent_confidence: ConfidenceLevel = "insufficient"


class MarketHistory(BaseModel):
    entity_type: EntityType
    slug: str
    display_name: str
    cadence: Literal["biweekly"] = "biweekly"
    months: int = 12
    points: list[HistoryPoint] = Field(default_factory=list)


class CompareNeighborhood(BaseModel):
    slug: str
    display_name: str
    pulse: MarketPulse


class CompareResponse(BaseModel):
    neighborhoods: list[CompareNeighborhood] = Field(default_factory=list)
    corpus_updated_at: datetime | None = None


class NeighborhoodMarketSummary(BaseModel):
    slug: str
    name: str
    rent_listings: int = 0
    sale_listings: int = 0
    median_rent_eur: float | None = None
    median_rent_psm_eur: float | None = None
    confidence: ConfidenceLevel = "insufficient"
    estimate_ready: bool = False
