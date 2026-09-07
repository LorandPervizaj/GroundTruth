"""Geocode quality and neighborhood boundary sanity checks."""

from __future__ import annotations

import math
from typing import Any

import pandas as pd
from sqlalchemy import text
from sqlalchemy.orm import Session

# Prishtina neighborhoods are compact — coords far from NH centroid are suspect.
DEFAULT_MAX_DISTANCE_KM = 3.0


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlon / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def load_listing_coordinates(
    session: Session,
    neighborhood_ids: list[int],
) -> pd.DataFrame:
    if not neighborhood_ids:
        return pd.DataFrame()
    sql = text(
        """
        SELECT
            nl.latitude::float AS latitude,
            nl.longitude::float AS longitude,
            nl.geocode_precision,
            nl.neighborhood_id
        FROM normalized_listings nl
        WHERE nl.neighborhood_id = ANY(:neighborhood_ids)
          AND nl.latitude IS NOT NULL
          AND nl.longitude IS NOT NULL
          AND nl.is_active IS NOT FALSE
        """
    )
    return pd.DataFrame(
        session.execute(sql, {"neighborhood_ids": neighborhood_ids}).mappings().all()
    )


def neighborhood_geocode_summary(
    session: Session,
    neighborhood_ids: list[int],
    *,
    centroid_lat: float | None,
    centroid_lng: float | None,
    max_distance_km: float = DEFAULT_MAX_DISTANCE_KM,
) -> dict[str, Any]:
    df = load_listing_coordinates(session, neighborhood_ids)
    if df.empty:
        return {
            "centroid_lat": centroid_lat,
            "centroid_lng": centroid_lng,
            "listings_with_coords": 0,
            "source_coords_count": 0,
            "boundary_mismatch_count": 0,
            "median_distance_km": None,
            "max_distance_km": None,
        }

    distances: list[float] = []
    mismatches = 0
    source_coords = 0
    if centroid_lat is not None and centroid_lng is not None:
        for row in df.itertuples(index=False):
            if str(row.geocode_precision or "") == "source_coords":
                source_coords += 1
            dist = haversine_km(
                float(row.latitude),
                float(row.longitude),
                centroid_lat,
                centroid_lng,
            )
            distances.append(dist)
            if dist > max_distance_km:
                mismatches += 1

    dist_series = pd.Series(distances) if distances else pd.Series(dtype=float)
    return {
        "centroid_lat": centroid_lat,
        "centroid_lng": centroid_lng,
        "listings_with_coords": int(len(df)),
        "source_coords_count": source_coords,
        "boundary_mismatch_count": mismatches,
        "median_distance_km": round(float(dist_series.median()), 2)
        if not dist_series.empty
        else None,
        "max_distance_km": round(float(dist_series.max()), 2) if not dist_series.empty else None,
    }


def corpus_geocode_stats(session: Session) -> dict[str, float | int | None]:
    """Active listing coordinate coverage and neighborhood-centroid mismatch rate."""
    sql = text(
        """
        SELECT
            COUNT(*)::int AS total,
            COUNT(*) FILTER (
                WHERE latitude IS NOT NULL AND longitude IS NOT NULL
            )::int AS with_coords,
            COUNT(*) FILTER (
                WHERE geocode_precision = 'source_coords'
            )::int AS source_coords
        FROM normalized_listings
        WHERE is_active IS NOT FALSE
          AND listing_type IN ('rent', 'sale')
        """
    )
    row = session.execute(sql).mappings().first()
    if not row or not row["total"]:
        return {"coverage_pct": None, "mismatch_pct": None, "with_coords": 0, "total": 0}
    total = int(row["total"])
    with_coords = int(row["with_coords"])
    source_coords = int(row["source_coords"])
    coverage = round(100.0 * with_coords / total, 1) if total else None
    # Listings on centroid fallback vs source-reported coords (proxy for reconciliation).
    mismatch = round(100.0 * max(0, with_coords - source_coords) / total, 1) if total else None
    return {
        "coverage_pct": coverage,
        "mismatch_pct": mismatch,
        "with_coords": with_coords,
        "total": total,
    }
