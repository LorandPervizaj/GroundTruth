"""Scrape run tracking."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import DateTime, Enum, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from groundtruth.models.base import Base
from groundtruth.models.enums import ScrapeRunStatus

if TYPE_CHECKING:
    from groundtruth.models.etl import EtlMetrics, InvalidListing
    from groundtruth.models.pipeline import NormalizedListing, ParsedListing, RawListing


class ScrapeRun(Base):
    """Metadata for a single spider execution."""

    __tablename__ = "scrape_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    spider_name: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    spider_version: Mapped[str] = mapped_column(String(20), nullable=False, default="1.0.0")
    status: Mapped[ScrapeRunStatus] = mapped_column(
        Enum(ScrapeRunStatus, name="scrape_run_status", native_enum=False),
        nullable=False,
        default=ScrapeRunStatus.PENDING,
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    listings_found: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    listings_stored: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    errors_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_: Mapped[dict[str, Any] | None] = mapped_column("metadata", JSONB, nullable=True)

    raw_listings: Mapped[list[RawListing]] = relationship(back_populates="scrape_run")
    parsed_listings: Mapped[list[ParsedListing]] = relationship(back_populates="scrape_run")
    normalized_listings: Mapped[list[NormalizedListing]] = relationship(
        back_populates="scrape_run"
    )
    etl_metrics: Mapped[list[EtlMetrics]] = relationship(back_populates="scrape_run")
    invalid_listings: Mapped[list[InvalidListing]] = relationship(back_populates="scrape_run")
