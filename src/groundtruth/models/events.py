"""Property lifecycle event tracking."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from sqlalchemy import DateTime, Enum, ForeignKey, Numeric, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from groundtruth.models.base import Base
from groundtruth.models.enums import PropertyEventType

if TYPE_CHECKING:
    from groundtruth.models.canonical import CanonicalProperty
    from groundtruth.models.scrape_run import ScrapeRun


class PropertyEvent(Base):
    """
    Lifecycle event for a canonical property.

    Enables: days on market, discount before sale, price reductions, price velocity.
    """

    __tablename__ = "property_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    canonical_property_id: Mapped[int] = mapped_column(
        ForeignKey("canonical_properties.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    scrape_run_id: Mapped[int | None] = mapped_column(
        ForeignKey("scrape_runs.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    event_type: Mapped[PropertyEventType] = mapped_column(
        Enum(PropertyEventType, name="property_event_type", native_enum=False),
        nullable=False,
        index=True,
    )

    old_sale_price: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    new_sale_price: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    old_rent_price: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    new_rent_price: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    price_change_pct: Mapped[float | None] = mapped_column(nullable=True)

    source_website: Mapped[str | None] = mapped_column(String(100), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_: Mapped[dict[str, Any] | None] = mapped_column("metadata", JSONB, nullable=True)

    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True,
    )

    canonical_property: Mapped[CanonicalProperty] = relationship(back_populates="property_events")
    scrape_run: Mapped[ScrapeRun | None] = relationship()
