"""Biweekly market history from listing observations."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any, Literal

import pandas as pd
from sqlalchemy import text
from sqlalchemy.orm import Session

from groundtruth.analytics.display_rounding import round_rent_eur, round_rent_psm, round_sale_psm
from groundtruth.analytics.sample_confidence import confidence_level

DEFAULT_HISTORY_MONTHS = 12
MIN_HISTORY_MONTHS = 6
MAX_HISTORY_MONTHS = 12
MIN_PERIOD_LISTINGS = 5

_APARTMENT_TYPES = frozenset({"APARTMENT", "STUDIO"})

EntityTypeLit = Literal["neighborhood", "district", "street", "complex"]

_ENTITY_COL: dict[EntityTypeLit, str] = {
    "neighborhood": "neighborhood_id",
    "district": "district_id",
    "street": "street_id",
    "complex": "complex_id",
}


def load_entity_observations(
    session: Session,
    entity_type: EntityTypeLit,
    entity_id: int,
    *,
    months: int = DEFAULT_HISTORY_MONTHS,
) -> pd.DataFrame:
    """Observation rows for an entity segment over the lookback window."""
    months = max(MIN_HISTORY_MONTHS, min(months, MAX_HISTORY_MONTHS))
    col = _ENTITY_COL[entity_type]
    since = date.today() - timedelta(days=months * 31)
    sql = text(
        f"""
        SELECT
            lo.observed_date,
            lo.source_website,
            lo.source_listing_id,
            lower(lo.listing_type::text) AS listing_type,
            lo.sale_price::float AS sale_price,
            lo.rent_price::float AS rent_price,
            lo.area_sqm,
            upper(coalesce(nl.property_type::text, 'APARTMENT')) AS property_type
        FROM listing_observations lo
        JOIN normalized_listings nl ON nl.id = lo.normalized_listing_id
        WHERE nl.{col} = :entity_id
          AND lo.observed_date >= :since
          AND coalesce(lo.is_active, true) = true
        ORDER BY lo.observed_date
        """
    )
    rows = session.execute(sql, {"entity_id": entity_id, "since": since}).mappings().all()
    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows)


def biweekly_points_from_observations(
    df: pd.DataFrame,
    *,
    min_listings: int = MIN_PERIOD_LISTINGS,
) -> list[dict[str, Any]]:
    """
    Aggregate apartment observations into biweekly periods.

    Uses the last observation per listing within each period, then computes medians.
    """
    if df.empty:
        return []

    apt = df[df["property_type"].isin(_APARTMENT_TYPES)].copy()
    if apt.empty:
        return []

    apt["observed_date"] = pd.to_datetime(apt["observed_date"])
    apt["period_end"] = (
        apt["observed_date"].dt.to_period("2W-SUN").apply(lambda p: p.end_time.date())
    )
    apt = apt.sort_values("observed_date")
    apt = apt.drop_duplicates(
        subset=["period_end", "source_website", "source_listing_id"],
        keep="last",
    )

    sale_mask = apt["listing_type"] == "sale"
    rent_mask = apt["listing_type"] == "rent"
    apt.loc[sale_mask, "sale_psm"] = (
        apt.loc[sale_mask, "sale_price"] / apt.loc[sale_mask, "area_sqm"]
    )
    apt.loc[rent_mask, "rent_psm"] = (
        apt.loc[rent_mask, "rent_price"] / apt.loc[rent_mask, "area_sqm"]
    )

    points: list[dict[str, Any]] = []
    for period_end, group in apt.groupby("period_end", sort=True):
        sale = group[group["listing_type"] == "sale"]
        rent = group[group["listing_type"] == "rent"]
        sale_psm = sale["sale_psm"].dropna()
        rent_prices = rent["rent_price"].dropna()
        rent_psm = rent["rent_psm"].dropna()
        sale_n = int(len(sale_psm))
        rent_n = int(len(rent_prices))
        inv_n = int(len(group))

        period_start = (pd.Timestamp(period_end) - pd.Timedelta(days=13)).date()
        end_iso = period_end.isoformat() if hasattr(period_end, "isoformat") else str(period_end)

        points.append(
            {
                "period_start": period_start.isoformat(),
                "period_end": end_iso,
                "median_sale_psm_eur": round_sale_psm(sale_psm.median())
                if sale_n >= min_listings
                else None,
                "median_rent_eur": round_rent_eur(rent_prices.median())
                if rent_n >= min_listings
                else None,
                "median_rent_psm_eur": round_rent_psm(rent_psm.median())
                if rent_n >= min_listings
                else None,
                "sale_n": sale_n,
                "rent_n": rent_n,
                "inventory_n": inv_n,
                "sale_confidence": confidence_level(sale_n),
                "rent_confidence": confidence_level(rent_n),
            }
        )

    return points
