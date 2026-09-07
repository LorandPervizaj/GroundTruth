"""Coarse listing fingerprints for duplicate blocking."""

from __future__ import annotations

from typing import Any

import pandas as pd

AREA_BUCKET_M2 = 5
PRICE_BUCKET_EUR = 50


def price_bucket(price: float | None, *, step: int = PRICE_BUCKET_EUR) -> int | None:
    if price is None or (isinstance(price, float) and pd.isna(price)):
        return None
    return int(float(price) // step) * step


def area_bucket(area_sqm: float | None, *, step: int = AREA_BUCKET_M2) -> int | None:
    if area_sqm is None or (isinstance(area_sqm, float) and pd.isna(area_sqm)):
        return None
    return int(round(float(area_sqm) / step) * step)


def active_price(row: pd.Series | dict[str, Any]) -> float | None:
    if isinstance(row, pd.Series):
        listing_type = str(row.get("listing_type", "")).lower()
        price = row.get("rent_price") if listing_type == "rent" else row.get("sale_price")
    else:
        listing_type = str(row.get("listing_type", "")).lower()
        price = row.get("rent_price") if listing_type == "rent" else row.get("sale_price")
    if price is None or (isinstance(price, float) and pd.isna(price)):
        return None
    return float(price)


def coarse_block_key(row: pd.Series) -> tuple[Any, ...] | None:
    """Blocking key for cross-portal candidate generation."""
    if row.get("neighborhood_id") is None or pd.isna(row["neighborhood_id"]):
        return None
    area = area_bucket(row.get("area_sqm"))
    price = price_bucket(active_price(row))
    if area is None or price is None:
        return None
    beds = row.get("bedrooms")
    beds_key = int(beds) if beds is not None and not pd.isna(beds) else None
    return (
        str(row.get("listing_type", "")).lower(),
        int(row["neighborhood_id"]),
        area,
        beds_key,
        price,
    )
