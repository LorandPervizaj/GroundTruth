"""Schemas for public rent-yield API."""

from __future__ import annotations

from pydantic import BaseModel, Field


class RentYieldRow(BaseModel):
    """One neighborhood gross rent-yield row."""

    neighborhood_name: str
    slug: str | None = None
    neighborhood_id: int | None = None
    median_rent_eur: float | None = None
    median_sale_eur: float | None = None
    median_rent_psm: float | None = None
    median_sale_psm: float | None = None
    gross_yield_pct: float | None = None
    rent_listings: int = 0
    sale_listings: int = 0
    estimate_ready: bool = False


class RentYieldResponse(BaseModel):
    """Public rent-yield payload."""

    rows: list[RentYieldRow] = Field(default_factory=list)
    cached: bool | None = None
