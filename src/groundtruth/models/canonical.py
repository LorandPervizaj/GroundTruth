"""Canonical properties, source provenance, and price history."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import TYPE_CHECKING

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
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from groundtruth.models.base import Base, TimestampMixin
from groundtruth.models.enums import (
    BuildingAgeCategory,
    Currency,
    HeatingType,
    ListingType,
    PropertyType,
)

if TYPE_CHECKING:
    from groundtruth.models.events import PropertyEvent
    from groundtruth.models.pipeline import NormalizedListing, ParsedListing
    from groundtruth.models.reference import Building, Complex, Neighborhood, Street


class CanonicalProperty(Base, TimestampMixin):
    """Deduplicated canonical property record. Best-known field values."""

    __tablename__ = "canonical_properties"

    id: Mapped[int] = mapped_column(primary_key=True)
    duplicate_group_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)

    listing_type: Mapped[ListingType | None] = mapped_column(
        Enum(ListingType, name="listing_type_canonical", native_enum=False),
        nullable=True,
    )
    property_type: Mapped[PropertyType | None] = mapped_column(
        Enum(PropertyType, name="property_type_canonical", native_enum=False),
        nullable=True,
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    sale_price: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    rent_price: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    currency: Mapped[Currency] = mapped_column(
        Enum(Currency, name="currency_canonical", native_enum=False),
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
        Enum(BuildingAgeCategory, name="building_age_category_canonical", native_enum=False),
        nullable=True,
    )
    is_new_construction: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    is_furnished: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    heating_type: Mapped[HeatingType | None] = mapped_column(
        Enum(HeatingType, name="heating_type_canonical", native_enum=False),
        nullable=True,
    )
    has_elevator: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    has_parking: Mapped[bool | None] = mapped_column(Boolean, nullable=True)

    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    longitude: Mapped[float | None] = mapped_column(Float, nullable=True)

    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    neighborhood: Mapped[Neighborhood | None] = relationship(
        back_populates="canonical_properties"
    )
    street: Mapped[Street | None] = relationship(back_populates="canonical_properties")
    complex: Mapped[Complex | None] = relationship(back_populates="canonical_properties")
    building: Mapped[Building | None] = relationship(back_populates="canonical_properties")
    listing_sources: Mapped[list[ListingSource]] = relationship(back_populates="canonical_property")
    price_history: Mapped[list[PriceHistory]] = relationship(back_populates="canonical_property")
    property_events: Mapped[list[PropertyEvent]] = relationship(back_populates="canonical_property")


class ListingSource(Base):
    """Provenance link between a canonical property and a source listing."""

    __tablename__ = "listing_sources"

    id: Mapped[int] = mapped_column(primary_key=True)
    canonical_property_id: Mapped[int] = mapped_column(
        ForeignKey("canonical_properties.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    normalized_listing_id: Mapped[int] = mapped_column(
        ForeignKey("normalized_listings.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    parsed_listing_id: Mapped[int] = mapped_column(
        ForeignKey("parsed_listings.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    source_website: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    source_listing_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    original_url: Mapped[str] = mapped_column(Text, nullable=False)
    is_primary_source: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    duplicate_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    duplicate_match_fields: Mapped[list[str] | None] = mapped_column(JSONB, nullable=True)

    linked_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    canonical_property: Mapped[CanonicalProperty] = relationship(back_populates="listing_sources")
    normalized_listing: Mapped[NormalizedListing] = relationship(back_populates="listing_sources")
    parsed_listing: Mapped[ParsedListing] = relationship(back_populates="listing_sources")


class PriceHistory(Base):
    """Historical price snapshots for trend analysis."""

    __tablename__ = "price_history"

    id: Mapped[int] = mapped_column(primary_key=True)
    canonical_property_id: Mapped[int] = mapped_column(
        ForeignKey("canonical_properties.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    listing_source_id: Mapped[int | None] = mapped_column(
        ForeignKey("listing_sources.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    sale_price: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    rent_price: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    currency: Mapped[Currency] = mapped_column(
        Enum(Currency, name="currency_history", native_enum=False),
        nullable=False,
        default=Currency.EUR,
    )
    price_per_sqm: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    source_website: Mapped[str] = mapped_column(String(100), nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True,
    )
    listing_date: Mapped[date | None] = mapped_column(Date, nullable=True)

    canonical_property: Mapped[CanonicalProperty] = relationship(back_populates="price_history")
    listing_source: Mapped[ListingSource | None] = relationship()
