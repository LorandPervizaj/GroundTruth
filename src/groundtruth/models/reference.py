"""Reference / gazetteer tables for geographic entities."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import Float, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from groundtruth.models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from groundtruth.models.canonical import CanonicalProperty
    from groundtruth.models.pipeline import NormalizedListing, ParsedListing


class District(Base, TimestampMixin):
    """Micro-market within a neighborhood (street corridor, landmark area, etc.)."""

    __tablename__ = "districts"
    __table_args__ = (
        UniqueConstraint("neighborhood_id", "slug", name="uq_district_neighborhood_slug"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    neighborhood_id: Mapped[int] = mapped_column(
        ForeignKey("neighborhoods.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    aliases: Mapped[list[str] | None] = mapped_column(JSONB, nullable=True)
    district_type: Mapped[str | None] = mapped_column(String(50), nullable=True)

    neighborhood: Mapped[Neighborhood] = relationship(back_populates="districts")
    complexes: Mapped[list[Complex]] = relationship(back_populates="district")
    parsed_listings: Mapped[list[ParsedListing]] = relationship(back_populates="district")
    normalized_listings: Mapped[list[NormalizedListing]] = relationship(back_populates="district")


class Neighborhood(Base, TimestampMixin):
    """Canonical neighborhood with centroid for geocoding fallback."""

    __tablename__ = "neighborhoods"
    __table_args__ = (UniqueConstraint("city", "slug", name="uq_neighborhood_city_slug"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    city: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    centroid_lat: Mapped[float | None] = mapped_column(Float, nullable=True)
    centroid_lng: Mapped[float | None] = mapped_column(Float, nullable=True)
    aliases: Mapped[list[str] | None] = mapped_column(JSONB, nullable=True)

    districts: Mapped[list[District]] = relationship(back_populates="neighborhood")
    streets: Mapped[list[Street]] = relationship(back_populates="neighborhood")
    complexes: Mapped[list[Complex]] = relationship(back_populates="neighborhood")
    buildings: Mapped[list[Building]] = relationship(back_populates="neighborhood")
    parsed_listings: Mapped[list[ParsedListing]] = relationship(back_populates="neighborhood")
    normalized_listings: Mapped[list[NormalizedListing]] = relationship(
        back_populates="neighborhood"
    )
    canonical_properties: Mapped[list[CanonicalProperty]] = relationship(
        back_populates="neighborhood"
    )


class Street(Base, TimestampMixin):
    """Street within a neighborhood."""

    __tablename__ = "streets"
    __table_args__ = (
        UniqueConstraint("neighborhood_id", "slug", name="uq_street_neighborhood_slug"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    neighborhood_id: Mapped[int] = mapped_column(
        ForeignKey("neighborhoods.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    aliases: Mapped[list[str] | None] = mapped_column(JSONB, nullable=True)

    neighborhood: Mapped[Neighborhood] = relationship(back_populates="streets")
    parsed_listings: Mapped[list[ParsedListing]] = relationship(back_populates="street")
    normalized_listings: Mapped[list[NormalizedListing]] = relationship(back_populates="street")
    canonical_properties: Mapped[list[CanonicalProperty]] = relationship(back_populates="street")


class Complex(Base, TimestampMixin):
    """Residential complex (e.g. Mati 1, BS Group)."""

    __tablename__ = "complexes"
    __table_args__ = (
        UniqueConstraint("neighborhood_id", "slug", name="uq_complex_neighborhood_slug"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    neighborhood_id: Mapped[int | None] = mapped_column(
        ForeignKey("neighborhoods.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    district_id: Mapped[int | None] = mapped_column(
        ForeignKey("districts.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    aliases: Mapped[list[str] | None] = mapped_column(JSONB, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    neighborhood: Mapped[Neighborhood | None] = relationship(back_populates="complexes")
    district: Mapped[District | None] = relationship(back_populates="complexes")
    buildings: Mapped[list[Building]] = relationship(back_populates="complex")
    parsed_listings: Mapped[list[ParsedListing]] = relationship(back_populates="complex")
    normalized_listings: Mapped[list[NormalizedListing]] = relationship(back_populates="complex")
    canonical_properties: Mapped[list[CanonicalProperty]] = relationship(back_populates="complex")


class Building(Base, TimestampMixin):
    """Named building within a complex or neighborhood."""

    __tablename__ = "buildings"
    __table_args__ = (UniqueConstraint("slug", name="uq_building_slug"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    complex_id: Mapped[int | None] = mapped_column(
        ForeignKey("complexes.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    neighborhood_id: Mapped[int | None] = mapped_column(
        ForeignKey("neighborhoods.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    aliases: Mapped[list[str] | None] = mapped_column(JSONB, nullable=True)

    complex: Mapped[Complex | None] = relationship(back_populates="buildings")
    neighborhood: Mapped[Neighborhood | None] = relationship(back_populates="buildings")
    parsed_listings: Mapped[list[ParsedListing]] = relationship(back_populates="building")
    normalized_listings: Mapped[list[NormalizedListing]] = relationship(back_populates="building")
    canonical_properties: Mapped[list[CanonicalProperty]] = relationship(back_populates="building")
