"""Cross-time listing lifecycle from observation history."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

import pandas as pd
from sqlalchemy import text
from sqlalchemy.orm import Session

from groundtruth.analytics.listing_fingerprint import active_price, area_bucket, price_bucket
from groundtruth.analytics.sample_confidence import confidence_level

ListingLifecycleKey = tuple[str, str]


def observation_lifecycle_dataframe(
    session: Session,
    listing_keys: Iterable[ListingLifecycleKey] | None = None,
) -> pd.DataFrame:
    """Per source listing: first/last seen, observation count, price changes."""
    keys = list(listing_keys) if listing_keys is not None else None
    if keys is not None and not keys:
        return pd.DataFrame(
            columns=[
                "source_website",
                "source_listing_id",
                "first_seen",
                "last_seen",
                "observation_count",
                "distinct_prices",
                "area_sqm",
                "listing_type",
                "days_on_market",
                "price_changed",
            ]
        )

    if keys is None:
        sql = text(
            """
            SELECT
                lo.source_website,
                lo.source_listing_id,
                MIN(lo.observed_date) AS first_seen,
                MAX(lo.observed_date) AS last_seen,
                COUNT(*) AS observation_count,
                COUNT(DISTINCT COALESCE(lo.sale_price, lo.rent_price)) AS distinct_prices,
                MAX(lo.area_sqm) AS area_sqm,
                MAX(lo.listing_type::text) AS listing_type
            FROM listing_observations lo
            GROUP BY lo.source_website, lo.source_listing_id
            """
        )
        df = pd.DataFrame(session.execute(sql).mappings().all())
    else:
        rows: list[dict[str, Any]] = []
        chunk = 400
        for start in range(0, len(keys), chunk):
            batch = keys[start : start + chunk]
            values = ", ".join(f"(:sw{i}, :id{i})" for i in range(len(batch)))
            params: dict[str, Any] = {}
            for i, (website, listing_id) in enumerate(batch):
                params[f"sw{i}"] = website
                params[f"id{i}"] = listing_id
            sql = text(
                f"""
                SELECT
                    lo.source_website,
                    lo.source_listing_id,
                    MIN(lo.observed_date) AS first_seen,
                    MAX(lo.observed_date) AS last_seen,
                    COUNT(*) AS observation_count,
                    COUNT(DISTINCT COALESCE(lo.sale_price, lo.rent_price)) AS distinct_prices,
                    MAX(lo.area_sqm) AS area_sqm,
                    MAX(lo.listing_type::text) AS listing_type
                FROM listing_observations lo
                INNER JOIN (VALUES {values}) AS k(source_website, source_listing_id)
                    ON lo.source_website = k.source_website
                    AND lo.source_listing_id = k.source_listing_id
                GROUP BY lo.source_website, lo.source_listing_id
                """
            )
            rows.extend(session.execute(sql, params).mappings().all())
        df = pd.DataFrame(rows)
    if df.empty:
        return df
    df["days_on_market"] = (
        pd.to_datetime(df["last_seen"]) - pd.to_datetime(df["first_seen"])
    ).dt.days
    df["days_on_market"] = df["days_on_market"].clip(lower=0)
    df["price_changed"] = df["distinct_prices"] > 1
    return df


def median_days_on_market(session: Session) -> int | None:
    """Corpus-wide median days on market without loading full observation history."""
    row = (
        session.execute(
            text(
                """
            SELECT percentile_cont(0.5) WITHIN GROUP (ORDER BY days_on_market) AS median_dom
            FROM (
                SELECT GREATEST(
                    0,
                    (MAX(observed_date) - MIN(observed_date))
                ) AS days_on_market
                FROM listing_observations
                GROUP BY source_website, source_listing_id
            ) tracked
            """
            )
        )
        .mappings()
        .first()
    )
    if not row or row["median_dom"] is None:
        return None
    return int(row["median_dom"])


def lifecycle_lookup_map(
    session: Session,
    listing_keys: Iterable[ListingLifecycleKey] | None = None,
) -> dict[ListingLifecycleKey, dict[str, Any]]:
    """Fast lookup of lifecycle fields by (source_website, source_listing_id)."""
    df = observation_lifecycle_dataframe(session, listing_keys=listing_keys)
    if df.empty:
        return {}
    out: dict[ListingLifecycleKey, dict[str, Any]] = {}
    for row in df.itertuples(index=False):
        key = (str(row.source_website), str(row.source_listing_id))
        first = row.first_seen
        last = row.last_seen
        out[key] = {
            "first_seen": first.isoformat() if hasattr(first, "isoformat") else str(first),
            "last_seen": last.isoformat() if hasattr(last, "isoformat") else str(last),
            "days_on_market": int(row.days_on_market) if row.days_on_market is not None else None,
            "observation_count": int(row.observation_count),
            "price_changed": bool(row.price_changed),
        }
    return out


def segment_days_on_market(
    segment: pd.DataFrame,
    lifecycle_map: dict[ListingLifecycleKey, dict[str, Any]],
) -> tuple[int | None, int, str]:
    """Median days on market for listings in a segment with observation history."""
    if segment.empty or not lifecycle_map:
        return None, 0, "insufficient"
    values: list[int] = []
    for row in segment.itertuples(index=False):
        key = (str(row.source_website), str(row.source_listing_id))
        entry = lifecycle_map.get(key)
        if entry and entry.get("days_on_market") is not None:
            values.append(int(entry["days_on_market"]))
    if not values:
        return None, 0, "insufficient"
    n = len(values)
    return int(pd.Series(values).median()), n, confidence_level(n)


def cross_time_relist_candidates(session: Session, *, min_ids: int = 2) -> pd.DataFrame:
    """
    Fingerprints seen under multiple source_listing_ids — likely relists, not new supply.
    """
    sql = text(
        """
        SELECT
            lo.source_website,
            lo.source_listing_id,
            lo.observed_date,
            lo.listing_type::text AS listing_type,
            lo.sale_price::float AS sale_price,
            lo.rent_price::float AS rent_price,
            lo.area_sqm,
            nl.bedrooms,
            nl.neighborhood_id
        FROM listing_observations lo
        LEFT JOIN normalized_listings nl ON nl.id = lo.normalized_listing_id
        """
    )
    obs = pd.DataFrame(session.execute(sql).mappings().all())
    if obs.empty:
        return pd.DataFrame(
            columns=[
                "fingerprint",
                "listing_type",
                "neighborhood_id",
                "area_bucket",
                "price_bucket",
                "bedrooms",
                "distinct_listing_ids",
                "sources",
                "first_seen",
                "last_seen",
            ]
        )

    obs["listing_type"] = obs["listing_type"].astype(str).str.lower()
    obs["listing_price"] = obs.apply(active_price, axis=1)

    def _fp(row: pd.Series) -> tuple[Any, ...] | None:
        if row.get("neighborhood_id") is None or pd.isna(row["neighborhood_id"]):
            return None
        area = area_bucket(row.get("area_sqm"))
        price = price_bucket(row.get("listing_price"))
        if area is None or price is None:
            return None
        beds = row.get("bedrooms")
        beds_key = int(beds) if beds is not None and not pd.isna(beds) else None
        return (
            str(row.get("listing_type", "")),
            int(row["neighborhood_id"]),
            area,
            beds_key,
            price,
        )

    obs["fingerprint"] = obs.apply(_fp, axis=1)
    obs = obs[obs["fingerprint"].notna()].copy()
    if obs.empty:
        return pd.DataFrame()

    grouped = (
        obs.groupby("fingerprint", dropna=True)
        .agg(
            listing_type=("listing_type", "first"),
            neighborhood_id=("neighborhood_id", "first"),
            area_bucket=("area_sqm", lambda s: area_bucket(s.iloc[0])),
            price_bucket=("listing_price", lambda s: price_bucket(s.iloc[0])),
            bedrooms=("bedrooms", "first"),
            distinct_listing_ids=("source_listing_id", "nunique"),
            sources=("source_website", lambda s: ", ".join(sorted(s.astype(str).unique()))),
            first_seen=("observed_date", "min"),
            last_seen=("observed_date", "max"),
        )
        .reset_index()
    )
    relists = grouped[grouped["distinct_listing_ids"] >= min_ids].copy()
    relists["fingerprint"] = relists["fingerprint"].astype(str)
    return relists.sort_values("distinct_listing_ids", ascending=False)


def lifecycle_summary(session: Session, *, include_relists: bool = False) -> dict[str, Any]:
    lifecycle = observation_lifecycle_dataframe(session)
    if lifecycle.empty:
        return {
            "tracked_listings": 0,
            "median_days_on_market": None,
            "price_changed_count": 0,
            "relist_fingerprints": 0,
        }
    relists = cross_time_relist_candidates(session) if include_relists else pd.DataFrame()
    dom = lifecycle["days_on_market"].dropna()
    return {
        "tracked_listings": int(len(lifecycle)),
        "median_days_on_market": int(dom.median()) if not dom.empty else None,
        "price_changed_count": int(lifecycle["price_changed"].sum()),
        "relist_fingerprints": int(len(relists)),
    }
