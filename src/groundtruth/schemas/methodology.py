"""Public methodology metadata for citation and transparency."""

from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, Field


class MethodologyPublic(BaseModel):
    version: str
    released: date
    summary: str
    canonical_path: str = "/methodology"
    corpus_updated_at: datetime | None = None
    active_listings: int = 0
    raw_listings: int = 0
    data_sources: list[str] = Field(default_factory=list)
    parser_versions: list[str] = Field(default_factory=list)
    dataset_version: str = "live"
    dataset_frozen_at: datetime | None = None
    dataset_fingerprint: str | None = None
    invalid_pct: float | None = None
    golden_accuracy_pct: float | None = None
    cross_portal_dedup_note: str = (
        "Cross-portal dedup v1 — analytics-layer canonical primaries; "
        "review register at data/deduplication/cross_portal_groups.csv"
    )
    public_product_scope: str = "rent_and_sale"
