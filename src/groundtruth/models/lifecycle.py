"""Durable source-listing lifecycle state."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from groundtruth.models.base import Base


class ListingLifecycleState(Base):
    __tablename__ = "listing_lifecycle_states"
    __table_args__ = (
        UniqueConstraint("source_website", "source_listing_id", name="uq_lifecycle_source_listing"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    source_website: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    source_listing_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_seen_run_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    consecutive_successful_misses: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="UNKNOWN", index=True)
    inactive_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reactivated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
