"""Pydantic schemas for pipeline stages and API boundaries."""

from groundtruth.schemas.canonical import CanonicalPropertySchema, ListingSourceSchema
from groundtruth.schemas.deduplication import DuplicateMatchResult, DuplicateScoreBreakdown
from groundtruth.schemas.pipeline import (
    NormalizedListingSchema,
    ParsedListingSchema,
    RawListingSchema,
)
from groundtruth.schemas.reference import (
    BuildingSchema,
    ComplexSchema,
    NeighborhoodSchema,
    StreetSchema,
)

__all__ = [
    "BuildingSchema",
    "CanonicalPropertySchema",
    "ComplexSchema",
    "DuplicateMatchResult",
    "DuplicateScoreBreakdown",
    "ListingSourceSchema",
    "NeighborhoodSchema",
    "NormalizedListingSchema",
    "ParsedListingSchema",
    "RawListingSchema",
    "StreetSchema",
]
