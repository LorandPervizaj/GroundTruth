"""Budget-based neighborhood matching."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from groundtruth.schemas.lookup import ConfidenceLevel

ListingType = Literal["rent", "sale"]
FitTier = Literal["best", "good", "stretch"]


class BudgetMatchRequest(BaseModel):
    listing_type: ListingType = "rent"
    max_budget_eur: float = Field(gt=0, le=10_000_000)
    min_area_sqm: float | None = Field(default=None, ge=15, le=500)
    max_area_sqm: float | None = Field(default=None, ge=15, le=500)
    min_price_psm_eur: float | None = Field(default=None, ge=0, le=50_000)
    max_price_psm_eur: float | None = Field(default=None, ge=0, le=50_000)
    bedrooms: int | None = Field(default=None, ge=0, le=10)
    top_n: int = Field(default=8, ge=1, le=20)


class BudgetMatchNeighborhood(BaseModel):
    slug: str
    name: str
    match_count: int = 0
    sample_count: int = 0
    afford_pct: float = 0.0
    median_price_eur: float | None = None
    median_area_sqm: float | None = None
    median_price_psm: float | None = None
    gross_yield_pct: float | None = None
    confidence: ConfidenceLevel = "insufficient"
    fit_score: float = 0.0
    fit_tier: FitTier = "good"
    budget_headroom_eur: float | None = None
    budget_headroom_pct: float | None = None
    area_fit_pct: float | None = None
    estimated_target_sqm: float | None = None
    estimated_price_eur: float | None = None
    rank: int = 0
    summary_key: str = "budget_match_summary_default"


class BudgetMatchResponse(BaseModel):
    listing_type: ListingType
    max_budget_eur: float
    min_area_sqm: float | None = None
    max_area_sqm: float | None = None
    min_price_psm_eur: float | None = None
    max_price_psm_eur: float | None = None
    bedrooms: int | None = None
    neighborhoods: list[BudgetMatchNeighborhood] = Field(default_factory=list)
    total_matches: int = 0
    cached: bool = False
    degraded: bool = False
    degradation_reason: str | None = None
