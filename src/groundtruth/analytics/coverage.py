"""Neighborhood data coverage — rent and sale comparable counts per gazetteer NH."""

from __future__ import annotations

import pandas as pd
from sqlalchemy.orm import Session

from groundtruth.analytics.valuation import (
    MIN_COMPARABLES,
    rent_comparables_dataframe,
    sale_comparables_dataframe,
)
from groundtruth.models.reference import Neighborhood


def _clean_apartment_comps(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    apt = df["property_type"].fillna("APARTMENT").str.upper() == "APARTMENT"
    commercial = df["is_commercial"] if "is_commercial" in df.columns else False
    return df[apt & ~commercial].copy()


def _counts_by_neighborhood(
    df: pd.DataFrame, name_col: str = "neighborhood_name"
) -> dict[str, int]:
    if df.empty or name_col not in df.columns:
        return {}
    counts: dict[str, int] = {}
    for name, count in df.groupby(name_col).size().items():
        if name:
            counts[str(name)] = int(count)
    return counts


def build_neighborhood_coverage_table(session: Session) -> pd.DataFrame:
    """
      Full gazetteer coverage: rent comps, sale comps, estimate-ready flags.

    Columns: neighborhood, rent_comps, sale_comps, rent_estimate_ready,
             sale_estimate_ready, rent_pct_of_city, sale_pct_of_city
    """
    neighborhoods = session.query(Neighborhood).order_by(Neighborhood.name).all()
    rent_df = _clean_apartment_comps(rent_comparables_dataframe(session))
    sale_df = _clean_apartment_comps(sale_comparables_dataframe(session))

    rent_counts = _counts_by_neighborhood(rent_df)
    sale_counts = _counts_by_neighborhood(sale_df)
    total_rent = sum(rent_counts.values())
    total_sale = sum(sale_counts.values())

    rows = []
    for nh in neighborhoods:
        rent_n = rent_counts.get(nh.name, 0)
        sale_n = sale_counts.get(nh.name, 0)
        rows.append(
            {
                "neighborhood_id": nh.id,
                "neighborhood": nh.name,
                "rent_comps": rent_n,
                "sale_comps": sale_n,
                "rent_estimate_ready": rent_n >= MIN_COMPARABLES,
                "sale_estimate_ready": sale_n >= MIN_COMPARABLES,
                "rent_pct_of_city": round(100.0 * rent_n / total_rent, 1) if total_rent else 0.0,
                "sale_pct_of_city": round(100.0 * sale_n / total_sale, 1) if total_sale else 0.0,
            }
        )

    table = pd.DataFrame(rows)
    return table.sort_values(
        ["rent_estimate_ready", "rent_comps", "sale_comps"], ascending=[False, False, False]
    )
