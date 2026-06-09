"""Per-listing lifecycle observations — one row per listing per ETL day."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Boolean, Date, DateTime, Enum, Float, ForeignKey, Numeric, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from groundtruth.models.base import Base
from groundtruth.models.enums import ListingType


class ListingObservation(Base):
    """Snapshot of a source listing at a point in time for trend analysis."""

    __tablename__ = "listing_observations"
    __table_args__ = (
        UniqueConstraint(
            "source_website",
            "source_listing_id",
            "observed_date",
            name="uq_listing_observation_day",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    source_website: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    source_listing_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    normalized_listing_id: Mapped[int | None] = mapped_column(
        ForeignKey("normalized_listings.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    observed_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    observed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    listing_type: Mapped[ListingType | None] = mapped_column(
        Enum(ListingType, name="listing_type_observation", native_enum=False),
        nullable=True,
    )
    sale_price: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    rent_price: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    area_sqm: Mapped[float | None] = mapped_column(Float, nullable=True)
    is_active: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    confidence_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    parser_version: Mapped[str | None] = mapped_column(String(20), nullable=True)
    original_url: Mapped[str | None] = mapped_column(Text, nullable=True)
