"""Pydantic schemas for pipeline stage data transfer."""

from datetime import date, datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, HttpUrl

from groundtruth.models.enums import (
    BuildingAgeCategory,
    Currency,
    HeatingType,
    ListingType,
    PropertyType,
)


class RawListingSchema(BaseModel):
    """Immutable raw listing as received from a spider."""

    model_config = ConfigDict(from_attributes=True)

    source_website: str
    source_listing_id: str
    original_url: str
    content_hash: str
    raw_payload: dict[str, Any]
    raw_html: str | None = None
    spider_version: str = "1.0.0"
    scraped_at: datetime | None = None
    scrape_run_id: int | None = None


class ParsedListingSchema(BaseModel):
    """Structured listing after parsing raw content."""

    model_config = ConfigDict(from_attributes=True)

    raw_listing_id: int | None = None
    scrape_run_id: int | None = None
    spider_version: str = "1.0.0"
    parser_version: str = "1.0.0"
    source_website: str
    source_listing_id: str
    original_url: str

    listing_date: date | None = None
    property_type: PropertyType | None = None
    listing_type: ListingType | None = None
    is_active: bool | None = True

    sale_price: Decimal | None = None
    rent_price: Decimal | None = None
    currency: Currency | None = None

    city: str | None = None
    neighborhood_raw: str | None = None
    street_raw: str | None = None
    complex_raw: str | None = None
    building_raw: str | None = None

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
    is_under_construction: bool | None = None
    is_finished: bool | None = None
    is_furnished: bool | None = None
    heating_type: HeatingType | None = None
    has_elevator: bool | None = None
    has_parking: bool | None = None

    description_original: str | None = None
    description_cleaned: str | None = None
    image_urls: list[str] = Field(default_factory=list)
    extra_fields: dict[str, Any] = Field(default_factory=dict)


class NormalizedListingSchema(BaseModel):
    """Cleaned listing ready for deduplication and analytics."""

    model_config = ConfigDict(from_attributes=True)

    parsed_listing_id: int | None = None
    scrape_run_id: int | None = None
    spider_version: str = "1.0.0"
    parser_version: str = "1.0.0"
    source_website: str
    source_listing_id: str
    original_url: str

    listing_date: date | None = None
    property_type: PropertyType | None = None
    listing_type: ListingType | None = None
    is_active: bool | None = True

    sale_price: Decimal | None = None
    rent_price: Decimal | None = None
    currency: Currency = Currency.EUR
    price_per_sqm: Decimal | None = None
    scraped_at: datetime | None = None

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
    is_under_construction: bool | None = None
    is_finished: bool | None = None
    is_furnished: bool | None = None
    heating_type: HeatingType | None = None
    has_elevator: bool | None = None
    has_parking: bool | None = None

    description_original: str | None = None
    description_cleaned: str | None = None
    image_urls: list[HttpUrl | str] = Field(default_factory=list)

    latitude: float | None = None
    longitude: float | None = None
    geocode_precision: str | None = None

    normalization_version: str = "1.0.0"
    gazetteer_version: str = "unknown"
    confidence_score: float | None = None
    confidence_details: dict[str, Any] | None = None
