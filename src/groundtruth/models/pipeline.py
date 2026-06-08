"""Pipeline stage tables: raw → parsed → normalized."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from groundtruth.models.base import Base
from groundtruth.models.enums import (
    BuildingAgeCategory,
    Currency,
    HeatingType,
    ListingType,
    PropertyType,
)

if TYPE_CHECKING:
    from groundtruth.models.canonical import ListingSource
    from groundtruth.models.reference import Building, Complex, Neighborhood, Street
    from groundtruth.models.scrape_run import ScrapeRun


class RawListing(Base):
    """Immutable raw payload exactly as received from a source."""

    __tablename__ = "raw_listings"
    __table_args__ = (
        UniqueConstraint(
            "source_website",
            "source_listing_id",
            "content_hash",
            name="uq_raw_listing_source_hash",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    scrape_run_id: Mapped[int] = mapped_column(
        ForeignKey("scrape_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    source_website: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    source_listing_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    original_url: Mapped[str] = mapped_column(Text, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    raw_payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    raw_html: Mapped[str | None] = mapped_column(Text, nullable=True)
    spider_version: Mapped[str] = mapped_column(String(20), nullable=False, default="1.0.0")
    scraped_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    scrape_run: Mapped[ScrapeRun] = relationship(back_populates="raw_listings")
    parsed_listings: Mapped[list[ParsedListing]] = relationship(back_populates="raw_listing")


class ParsedListing(Base):
    """Structured extraction from a raw listing. Reproducible from raw data."""

    __tablename__ = "parsed_listings"

    id: Mapped[int] = mapped_column(primary_key=True)
    raw_listing_id: Mapped[int] = mapped_column(
        ForeignKey("raw_listings.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    scrape_run_id: Mapped[int] = mapped_column(
        ForeignKey("scrape_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    spider_version: Mapped[str] = mapped_column(String(20), nullable=False, default="1.0.0")
    parser_version: Mapped[str] = mapped_column(String(20), nullable=False, default="1.0.0")
    source_website: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    source_listing_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    original_url: Mapped[str] = mapped_column(Text, nullable=False)

    listing_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    property_type: Mapped[PropertyType | None] = mapped_column(
        Enum(PropertyType, name="property_type", native_enum=False),
        nullable=True,
    )
    listing_type: Mapped[ListingType | None] = mapped_column(
        Enum(ListingType, name="listing_type", native_enum=False),
        nullable=True,
    )
    is_active: Mapped[bool | None] = mapped_column(Boolean, nullable=True)

    sale_price: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    rent_price: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    currency: Mapped[Currency | None] = mapped_column(
        Enum(Currency, name="currency", native_enum=False),
        nullable=True,
    )

    city: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    neighborhood_raw: Mapped[str | None] = mapped_column(String(255), nullable=True)
    street_raw: Mapped[str | None] = mapped_column(String(255), nullable=True)
    complex_raw: Mapped[str | None] = mapped_column(String(255), nullable=True)
    building_raw: Mapped[str | None] = mapped_column(String(255), nullable=True)

    neighborhood_id: Mapped[int | None] = mapped_column(
        ForeignKey("neighborhoods.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    street_id: Mapped[int | None] = mapped_column(
        ForeignKey("streets.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    complex_id: Mapped[int | None] = mapped_column(
        ForeignKey("complexes.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    building_id: Mapped[int | None] = mapped_column(
        ForeignKey("buildings.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    area_sqm: Mapped[float | None] = mapped_column(Float, nullable=True)
    bedrooms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    bathrooms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    floor: Mapped[int | None] = mapped_column(Integer, nullable=True)
    total_floors: Mapped[int | None] = mapped_column(Integer, nullable=True)

    construction_year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    building_age_category: Mapped[BuildingAgeCategory | None] = mapped_column(
        Enum(BuildingAgeCategory, name="building_age_category", native_enum=False),
        nullable=True,
    )
    is_new_construction: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    is_under_construction: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    is_finished: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    is_furnished: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    heating_type: Mapped[HeatingType | None] = mapped_column(
        Enum(HeatingType, name="heating_type", native_enum=False),
        nullable=True,
    )
    has_elevator: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    has_parking: Mapped[bool | None] = mapped_column(Boolean, nullable=True)

    description_original: Mapped[str | None] = mapped_column(Text, nullable=True)
    description_cleaned: Mapped[str | None] = mapped_column(Text, nullable=True)
    image_urls: Mapped[list[str] | None] = mapped_column(JSONB, nullable=True)
    extra_fields: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)

    parsed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    raw_listing: Mapped[RawListing] = relationship(back_populates="parsed_listings")
    scrape_run: Mapped[ScrapeRun] = relationship(back_populates="parsed_listings")
    neighborhood: Mapped[Neighborhood | None] = relationship(back_populates="parsed_listings")
    street: Mapped[Street | None] = relationship(back_populates="parsed_listings")
    complex: Mapped[Complex | None] = relationship(back_populates="parsed_listings")
    building: Mapped[Building | None] = relationship(back_populates="parsed_listings")
    normalized_listings: Mapped[list[NormalizedListing]] = relationship(
        back_populates="parsed_listing"
    )
    listing_sources: Mapped[list[ListingSource]] = relationship(back_populates="parsed_listing")


class NormalizedListing(Base):
    """Cleaned, typed, gazetteer-matched listing ready for deduplication."""

    __tablename__ = "normalized_listings"

    id: Mapped[int] = mapped_column(primary_key=True)
    parsed_listing_id: Mapped[int] = mapped_column(
        ForeignKey("parsed_listings.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    scrape_run_id: Mapped[int] = mapped_column(
        ForeignKey("scrape_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    spider_version: Mapped[str] = mapped_column(String(20), nullable=False, default="1.0.0")
    parser_version: Mapped[str] = mapped_column(String(20), nullable=False, default="1.0.0")
    source_website: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    source_listing_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    original_url: Mapped[str] = mapped_column(Text, nullable=False)

    listing_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    property_type: Mapped[PropertyType | None] = mapped_column(
        Enum(PropertyType, name="property_type_norm", native_enum=False),
        nullable=True,
    )
    listing_type: Mapped[ListingType | None] = mapped_column(
        Enum(ListingType, name="listing_type_norm", native_enum=False),
        nullable=True,
    )
    is_active: Mapped[bool | None] = mapped_column(Boolean, nullable=True)

    sale_price: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    rent_price: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    currency: Mapped[Currency] = mapped_column(
        Enum(Currency, name="currency_norm", native_enum=False),
        nullable=False,
        default=Currency.EUR,
    )
    price_per_sqm: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)

    city: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    neighborhood_id: Mapped[int | None] = mapped_column(
        ForeignKey("neighborhoods.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    street_id: Mapped[int | None] = mapped_column(
        ForeignKey("streets.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    complex_id: Mapped[int | None] = mapped_column(
        ForeignKey("complexes.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    building_id: Mapped[int | None] = mapped_column(
        ForeignKey("buildings.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    area_sqm: Mapped[float | None] = mapped_column(Float, nullable=True)
    bedrooms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    bathrooms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    floor: Mapped[int | None] = mapped_column(Integer, nullable=True)
    total_floors: Mapped[int | None] = mapped_column(Integer, nullable=True)

    construction_year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    building_age_category: Mapped[BuildingAgeCategory | None] = mapped_column(
        Enum(BuildingAgeCategory, name="building_age_category_norm", native_enum=False),
        nullable=True,
    )
    is_new_construction: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    is_under_construction: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    is_finished: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    is_furnished: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    heating_type: Mapped[HeatingType | None] = mapped_column(
        Enum(HeatingType, name="heating_type_norm", native_enum=False),
        nullable=True,
    )
    has_elevator: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    has_parking: Mapped[bool | None] = mapped_column(Boolean, nullable=True)

    description_original: Mapped[str | None] = mapped_column(Text, nullable=True)
    description_cleaned: Mapped[str | None] = mapped_column(Text, nullable=True)
    image_urls: Mapped[list[str] | None] = mapped_column(JSONB, nullable=True)

    latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    longitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    geocode_precision: Mapped[str | None] = mapped_column(String(50), nullable=True)

    normalization_version: Mapped[str] = mapped_column(String(20), nullable=False, default="1.0.0")
    scraped_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    confidence_score: Mapped[float | None] = mapped_column(Float, nullable=True, index=True)
    confidence_details: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    normalized_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    parsed_listing: Mapped[ParsedListing] = relationship(back_populates="normalized_listings")
    scrape_run: Mapped[ScrapeRun] = relationship(back_populates="normalized_listings")
    neighborhood: Mapped[Neighborhood | None] = relationship(back_populates="normalized_listings")
    street: Mapped[Street | None] = relationship(back_populates="normalized_listings")
    complex: Mapped[Complex | None] = relationship(back_populates="normalized_listings")
    building: Mapped[Building | None] = relationship(back_populates="normalized_listings")
    listing_sources: Mapped[list[ListingSource]] = relationship(
        back_populates="normalized_listing"
    )
