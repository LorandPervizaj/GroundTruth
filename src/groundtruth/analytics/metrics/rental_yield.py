"""Rental yield calculations."""

import pandas as pd


def gross_rental_yield(
    sale_df: pd.DataFrame,
    rent_df: pd.DataFrame,
    group_col: str = "neighborhood_id",
) -> pd.DataFrame:
    """Estimate gross rental yield (%) by group."""
    sale_median = sale_df.groupby(group_col)["sale_price"].median()
    rent_median = rent_df.groupby(group_col)["rent_price"].median()
    combined = pd.DataFrame({"median_sale": sale_median, "median_rent": rent_median}).dropna()
    combined["gross_yield_pct"] = (combined["median_rent"] * 12 / combined["median_sale"]) * 100
    return combined.reset_index()
