"""Data lineage — reproducible link from every listing to its ETL provenance."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from groundtruth.models.base import Base

if TYPE_CHECKING:
    from groundtruth.models.etl import EtlMetrics
    from groundtruth.models.pipeline import NormalizedListing, ParsedListing, RawListing


class DataLineage(Base):
    """
    Audit trail: every normalized listing traces back to raw input and parser versions.

    Enables reproducible reports — any statistic can be recomputed from lineage filters.
    """

    __tablename__ = "data_lineage"

    id: Mapped[int] = mapped_column(primary_key=True)
    normalized_listing_id: Mapped[int] = mapped_column(
        ForeignKey("normalized_listings.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    raw_listing_id: Mapped[int] = mapped_column(
        ForeignKey("raw_listings.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    parsed_listing_id: Mapped[int] = mapped_column(
        ForeignKey("parsed_listings.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    etl_metrics_id: Mapped[int | None] = mapped_column(
        ForeignKey("etl_metrics.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    parser_version: Mapped[str] = mapped_column(String(20), nullable=False)
    normalization_version: Mapped[str] = mapped_column(String(20), nullable=False)
    gazetteer_version: Mapped[str] = mapped_column(String(20), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    normalized_listing: Mapped[NormalizedListing] = relationship()
    raw_listing: Mapped[RawListing] = relationship()
    parsed_listing: Mapped[ParsedListing] = relationship()
    etl_metrics: Mapped[EtlMetrics | None] = relationship()
