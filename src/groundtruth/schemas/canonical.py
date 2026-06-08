"""Pydantic schemas for canonical properties and provenance."""

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from groundtruth.models.enums import (
    BuildingAgeCategory,
    Currency,
    HeatingType,
    ListingType,
    PropertyType,
)


class CanonicalPropertySchema(BaseModel):
    """Deduplicated canonical property."""

    model_config = ConfigDict(from_attributes=True)

    id: int | None = None
    duplicate_group_id: str | None = None

    listing_type: ListingType | None = None
    property_type: PropertyType | None = None
    is_active: bool = True

    sale_price: Decimal | None = None
    rent_price: Decimal | None = None
    currency: Currency = Currency.EUR
    price_per_sqm: Decimal | None = None

    city: str | None = None
    neighborhood_id: int | None = None
    street_id: int | None = None
    complex_id: int | None = None
    building_id: int | None = None

    area_sqm: float | None = None
    bedrooms: int | None = None
    bathrooms: int | None = None
    floor: int | None = None
    total_floors: int | None = None

    construction_year: int | None = None
    building_age_category: BuildingAgeCategory | None = None
    is_new_construction: bool | None = None
    is_furnished: bool | None = None
    heating_type: HeatingType | None = None
    has_elevator: bool | None = None
    has_parking: bool | None = None

    description: str | None = None
    latitude: float | None = None
    longitude: float | None = None

    first_seen_at: datetime | None = None
    last_seen_at: datetime | None = None


class ListingSourceSchema(BaseModel):
    """Source provenance for a canonical property."""

    model_config = ConfigDict(from_attributes=True)

    canonical_property_id: int | None = None
    normalized_listing_id: int
    parsed_listing_id: int

    source_website: str
    source_listing_id: str
    original_url: str
    is_primary_source: bool = False

    duplicate_confidence: float | None = None
    duplicate_match_fields: list[str] = Field(default_factory=list)
