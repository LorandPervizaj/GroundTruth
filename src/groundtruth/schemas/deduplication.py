"""Pydantic schemas for duplicate detection results."""

from pydantic import BaseModel, Field


class DuplicateScoreBreakdown(BaseModel):
    """Per-field similarity scores contributing to duplicate confidence."""

    price_score: float = 0.0
    area_score: float = 0.0
    bedrooms_score: float = 0.0
    bathrooms_score: float = 0.0
    building_score: float = 0.0
    street_score: float = 0.0
    neighborhood_score: float = 0.0
    description_score: float = 0.0


class DuplicateMatchResult(BaseModel):
    """Duplicate confidence between two listings. Scoring only — no auto-merge."""

    candidate_listing_id: int
    reference_listing_id: int
    confidence: float = Field(ge=0.0, le=100.0)
    breakdown: DuplicateScoreBreakdown
    matched_fields: list[str] = Field(default_factory=list)
    is_likely_duplicate: bool = False
