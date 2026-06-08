"""Precomputed market snapshots for fast dashboard and reporting."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import Date, Float, ForeignKey, Integer, Numeric, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from groundtruth.models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from groundtruth.models.reference import Neighborhood


class MarketSnapshot(Base, TimestampMixin):
    """
    Nightly precomputed neighborhood market metrics.

    Dashboard reads from here instead of recalculating millions of rows.
    """

    __tablename__ = "market_snapshots"
    __table_args__ = (
        UniqueConstraint("snapshot_date", "neighborhood_id", name="uq_snapshot_date_neighborhood"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    snapshot_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    neighborhood_id: Mapped[int] = mapped_column(
        ForeignKey("neighborhoods.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Price metrics
    median_price: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    mean_price: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    median_price_per_sqm: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    mean_price_per_sqm: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)

    # Inventory
    inventory: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    median_size_sqm: Mapped[float | None] = mapped_column(Float, nullable=True)
    mean_size_sqm: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Rental
    median_rent: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    gross_yield_pct: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Composition
    luxury_percentage: Mapped[float | None] = mapped_column(Float, nullable=True)
    new_build_percentage: Mapped[float | None] = mapped_column(Float, nullable=True)
    median_building_age: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Composite scores (0–100)
    market_health_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    price_stability_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    construction_activity_score: Mapped[float | None] = mapped_column(Float, nullable=True)

    neighborhood: Mapped[Neighborhood] = relationship()
