"""Named analytical corpus populations (Stage 5 authority)."""

from __future__ import annotations

from datetime import date
from typing import Any

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from groundtruth.analytics.corpus import (
    _query_deduped_corpus_dataframe,
    active_corpus_dataframe,
)
from groundtruth.analytics.cross_dedup import apply_cross_dedupe
from groundtruth.analytics.valuation import rent_comparables_dataframe, sale_comparables_dataframe
from groundtruth.models.lifecycle import ListingLifecycleState

PRICING_WINDOW_CANDIDATE_DAYS = (30, 90, 180, 365)
DEFAULT_RECENT_PRICING_DAYS = 365


def _canonical(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df.copy()
    tagged = apply_cross_dedupe(df)
    return tagged[tagged["is_canonical_primary"]].copy()


def current_inventory_dataframe(session: Session) -> pd.DataFrame:
    """Valid listings with lifecycle ACTIVE; no publication-age proxy."""
    keys = set(
        session.execute(
            select(
                ListingLifecycleState.source_website,
                ListingLifecycleState.source_listing_id,
            ).where(ListingLifecycleState.status == "ACTIVE")
        ).all()
    )
    if not keys:
        return pd.DataFrame()
    valid = _query_deduped_corpus_dataframe(session, validity_only=True)
    if valid.empty:
        return valid
    mask = [
        (str(source), str(listing_id)) in keys
        for source, listing_id in zip(
            valid["source_website"], valid["source_listing_id"], strict=True
        )
    ]
    return _canonical(valid[pd.Series(mask, index=valid.index)])


def recent_pricing_dataframe(
    session: Session,
    *,
    window_days: int = DEFAULT_RECENT_PRICING_DAYS,
) -> pd.DataFrame:
    """Cross-deduped recent pricing corpus with an explicit shared window."""
    if window_days <= 0:
        raise ValueError("window_days must be positive")
    return (
        active_corpus_dataframe(session, max_age_months=12, cross_dedupe=True)
        .loc[
            lambda frame: (
                pd.to_datetime(frame["listing_date"]).dt.date
                >= date.fromordinal(date.today().toordinal() - window_days + 1)
            )
        ]
        .copy()
    )


def valuation_comparables_dataframe(session: Session, *, transaction_type: str) -> pd.DataFrame:
    if transaction_type == "rent":
        return rent_comparables_dataframe(session)
    if transaction_type == "sale":
        return sale_comparables_dataframe(session)
    raise ValueError(f"unsupported valuation transaction type: {transaction_type}")


def historical_observations_dataframe(session: Session) -> pd.DataFrame:
    from groundtruth.analytics.listing_lifecycle import observation_lifecycle_dataframe

    return observation_lifecycle_dataframe(session)


def pricing_window_coverage(session: Session) -> dict[str, Any]:
    """Evidence used to select one system-wide recent-pricing window."""
    rows: list[dict[str, Any]] = []
    for days in PRICING_WINDOW_CANDIDATE_DAYS:
        df = recent_pricing_dataframe(session, window_days=days)
        counts = df.groupby("neighborhood_id").size() if not df.empty else pd.Series(dtype=int)
        source_counts = (
            df.groupby("neighborhood_id")["source_website"].nunique()
            if not df.empty
            else pd.Series(dtype=int)
        )
        rows.append(
            {
                "window_days": days,
                "markets_n_ge_10": int((counts >= 10).sum()),
                "markets_n_ge_30": int((counts >= 30).sum()),
                "markets_n_ge_100": int((counts >= 100).sum()),
                "median_observations_per_market": float(counts.median()) if len(counts) else 0.0,
                "median_sources_per_market": float(source_counts.median())
                if len(source_counts)
                else 0.0,
            }
        )
    return {
        "selected_window_days": DEFAULT_RECENT_PRICING_DAYS,
        "selection_rule": "widest candidate preserving one standard window and maximum market coverage",
        "candidates": rows,
    }
