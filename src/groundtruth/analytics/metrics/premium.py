"""Premium analysis: complexes vs neighborhoods, new build vs existing."""

import pandas as pd


def complex_premium(
    df: pd.DataFrame,
    group_col: str = "complex_id",
    baseline_col: str = "neighborhood_id",
) -> pd.DataFrame:
    """Premium of complex €/m² over surrounding neighborhood average."""
    sale_df = df[df["listing_type"] == "sale"].dropna(subset=["price_per_sqm"])
    if sale_df.empty:
        return pd.DataFrame()

    neighborhood_avg = sale_df.groupby(baseline_col)["price_per_sqm"].median()
    complex_avg = sale_df.groupby([baseline_col, group_col])["price_per_sqm"].median()

    rows = []
    for (nh_id, complex_id), complex_median in complex_avg.items():
        nh_median = neighborhood_avg.get(nh_id)
        if nh_median and nh_median > 0:
            premium_pct = ((complex_median - nh_median) / nh_median) * 100
            rows.append(
                {
                    "neighborhood_id": nh_id,
                    "complex_id": complex_id,
                    "complex_median_psqm": complex_median,
                    "neighborhood_median_psqm": nh_median,
                    "premium_pct": premium_pct,
                }
            )
    return pd.DataFrame(rows)


def neighborhood_premium(
    df: pd.DataFrame,
    target_neighborhood: str | int,
    city_baseline: str | int,
    group_col: str = "neighborhood_id",
) -> float | None:
    """Premium of one neighborhood over city-wide median €/m²."""
    sale_df = df[df["listing_type"] == "sale"].dropna(subset=["price_per_sqm"])
    city_median = sale_df[sale_df[group_col] != target_neighborhood]["price_per_sqm"].median()
    nh_median = sale_df[sale_df[group_col] == target_neighborhood]["price_per_sqm"].median()
    if city_median and nh_median and city_median > 0:
        return ((nh_median - city_median) / city_median) * 100
    return None
