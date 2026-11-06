"""Offline historical price projections; never promotes rejected records or writes data."""

from __future__ import annotations

import pandas as pd


def latest_active(rows: pd.DataFrame) -> pd.DataFrame:
    """Match SQL filtering before DISTINCT ON, including older eligible fallbacks."""
    return (
        rows[rows["currently_active"].fillna(False)]
        .sort_values("normalized_id")
        .drop_duplicates(["source_website", "source_listing_id"], keep="last")
        .reset_index(drop=True)
    )


def project_prices(rows: pd.DataFrame, decisions: list[dict]) -> pd.DataFrame:
    """Change only approved projection fields, preserving existing exclusion state."""
    result = rows.copy(deep=True)
    ids = [d["normalized_id"] for d in decisions]
    if len(ids) != len(set(ids)):
        raise ValueError("Duplicate normalized projection target")
    for decision in decisions:
        if not decision["projectable"]:
            continue
        selected = result["normalized_id"] == decision["normalized_id"]
        if selected.sum() != 1:
            raise ValueError("Missing or ambiguous normalized projection target")
        result.loc[selected, "sale_price"] = decision["new_sale_price"]
        result.loc[selected, "price_per_sqm"] = decision["new_price_per_sqm"]
        if decision["introduced_validation_codes"]:
            result.loc[selected, ["currently_active", "currently_valid"]] = False
    return result


def neighborhood_medians(frame: pd.DataFrame) -> pd.DataFrame:
    """Asking-price diagnostics, separately by transaction and property category."""
    work = frame.copy()
    work["asking_price"] = work["sale_price"].where(
        work["listing_type"] == "sale", work["rent_price"]
    )
    return (
        work.groupby(
            ["neighborhood_id", "neighborhood", "listing_type", "property_type"], dropna=False
        )
        .agg(
            listings=("normalized_id", "count"),
            median_asking_eur=("asking_price", "median"),
            median_asking_eur_m2=("price_per_sqm", "median"),
        )
        .reset_index()
    )
