"""Luxury property concentration metrics."""

import pandas as pd

# Top decile threshold for €/m² in Prishtina market (configurable later)
DEFAULT_LUXURY_THRESHOLD_PSQM = 2000.0


def luxury_concentration(
    df: pd.DataFrame,
    group_col: str = "neighborhood_id",
    threshold_psqm: float = DEFAULT_LUXURY_THRESHOLD_PSQM,
) -> pd.DataFrame:
    """Percentage of listings above luxury €/m² threshold by group."""
    sale_df = df[df["listing_type"] == "sale"].dropna(subset=["price_per_sqm"])
    if sale_df.empty:
        return pd.DataFrame()

    def _luxury_pct(group: pd.DataFrame) -> float:
        if len(group) == 0:
            return 0.0
        return (group["price_per_sqm"] >= threshold_psqm).sum() / len(group) * 100

    result = sale_df.groupby(group_col).apply(_luxury_pct, include_groups=False)
    return result.reset_index(name="luxury_percentage")
