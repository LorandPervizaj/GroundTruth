"""Request/response schemas for rent valuation v1.0."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

ValuationType = Literal["rent", "sale"]


class ValuationRequest(BaseModel):
    """Inputs for a fair-market rent or sale estimate."""

    valuation_type: ValuationType = "rent"
    neighborhood: str = Field(
        min_length=1,
        max_length=120,
        description="Neighborhood name (e.g. Ulpiana) or numeric id",
    )
    area_sqm: float = Field(gt=0, le=500)
    bedrooms: int | None = Field(default=None, ge=0, le=10)
    listing_rent_eur: float | None = Field(
        default=None, gt=0, le=50_000, description="Listed rent to assess"
    )
    listing_sale_eur: float | None = Field(
        default=None, gt=0, le=10_000_000, description="Listed sale price to assess"
    )
    area_tolerance_pct: float = Field(default=0.20, ge=0.05, le=0.50)
    area_match_tolerance_m2: float = Field(default=5.0, ge=1.0, le=15.0)


class NeighborhoodOption(BaseModel):
    name: str
    slug: str
    rent_listings: int
    sale_listings: int = 0
    estimate_ready: bool
    sale_estimate_ready: bool = False


class ExcludedFactor(BaseModel):
    factor: str
    reason: str
    claim_id: str | None = None


class ComparableListing(BaseModel):
    """One observed listing used in the estimate."""

    source_listing_id: str
    area_sqm: float
    bedrooms: int | None
    rent_eur: float
    rent_per_sqm: float


class NegotiationAid(BaseModel):
    """Actionable rent figures for negotiation (not percentages)."""

    comparable_median_rent_eur: float
    negotiation_lo_eur: float
    negotiation_hi_eur: float
    listing_rent_eur: float
    monthly_difference_eur: float


class ValuationExplanation(BaseModel):
    """Machine- and human-readable reasoning trace."""

    estimate: float
    confidence: str
    sample_size: int
    top_factors: list[str]
    excluded: list[str]
    dataset_version: str
    comparable_method: str


class ValuationResult(BaseModel):
    """Fair-market rent or sale estimate with explicit limitations."""

    valuation_type: ValuationType = "rent"
    model_id: str = "DM-002"
    model_version: str = "1.0.0"
    dataset_version: str = "v1.0"
    product_version: str = "1.0"

    neighborhood_id: int
    neighborhood_name: str
    area_sqm: float
    area_bucket_sqm: float
    area_match_lo_sqm: float
    area_match_hi_sqm: float
    bedrooms: int | None

    point_estimate_eur: float
    lower_ci_eur: float
    upper_ci_eur: float
    median_rent_per_sqm: float
    comparable_median_rent_eur: float

    comparable_count: int
    comparable_method: str
    bedroom_adjustment_applied: bool
    comparables: list[ComparableListing]
    why_checks: list[str]

    listing_rent_eur: float | None = None
    assessment: Literal["above_comparables", "within_comparables", "below_comparables"] | None = (
        None
    )
    vs_median_pct: float | None = None
    assessment_summary: str | None = None
    negotiation: NegotiationAid | None = None

    confidence_label: Literal["Low", "Medium", "High"]
    confidence_score: float
    confidence_notes: list[str]

    excluded_factors: list[ExcludedFactor]
    method_summary: str
    explanation: ValuationExplanation
