"""ETL quality tracking: run metrics and invalid listing records."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import DateTime, Enum, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from groundtruth.models.base import Base
from groundtruth.models.enums import PipelineStage

if TYPE_CHECKING:
    from groundtruth.models.pipeline import NormalizedListing, ParsedListing, RawListing
    from groundtruth.models.scrape_run import ScrapeRun


class EtlMetrics(Base):
    """Per-run ETL quality and throughput metrics."""

    __tablename__ = "etl_metrics"

    id: Mapped[int] = mapped_column(primary_key=True)
    scrape_run_id: Mapped[int | None] = mapped_column(
        ForeignKey("scrape_runs.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    source: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    parser_version: Mapped[str] = mapped_column(String(20), nullable=False)
    normalization_version: Mapped[str] = mapped_column(String(20), nullable=False)
    gazetteer_version: Mapped[str] = mapped_column(String(20), nullable=False, default="unknown")

    total_scraped: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    parsed_success: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    parsed_failed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    normalized_success: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    normalized_failed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    validation_failed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    duplicate_candidates: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    duration_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    field_rates: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    scrape_run: Mapped[ScrapeRun | None] = relationship(back_populates="etl_metrics")


class InvalidListing(Base):
    """Listings that failed parsing, normalization, or validation — kept for inspection."""

    __tablename__ = "invalid_listings"

    id: Mapped[int] = mapped_column(primary_key=True)
    scrape_run_id: Mapped[int | None] = mapped_column(
        ForeignKey("scrape_runs.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    raw_listing_id: Mapped[int | None] = mapped_column(
        ForeignKey("raw_listings.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    parsed_listing_id: Mapped[int | None] = mapped_column(
        ForeignKey("parsed_listings.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    normalized_listing_id: Mapped[int | None] = mapped_column(
        ForeignKey("normalized_listings.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    stage: Mapped[PipelineStage] = mapped_column(
        Enum(PipelineStage, name="pipeline_stage", native_enum=False),
        nullable=False,
    )
    error_codes: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    field_errors: Mapped[dict[str, str] | None] = mapped_column(JSONB, nullable=True)
    message: Mapped[str | None] = mapped_column(Text, nullable=True)
    snapshot: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    scrape_run: Mapped[ScrapeRun | None] = relationship(back_populates="invalid_listings")
    raw_listing: Mapped[RawListing | None] = relationship()
    parsed_listing: Mapped[ParsedListing | None] = relationship()
    normalized_listing: Mapped[NormalizedListing | None] = relationship()
