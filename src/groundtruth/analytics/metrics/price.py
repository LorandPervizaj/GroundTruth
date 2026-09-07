"""Price and inventory metrics."""

import numpy as np
import pandas as pd

from groundtruth.logging import get_logger

logger = get_logger(__name__)


def price_stats(df: pd.DataFrame, group_col: str = "neighborhood_id") -> pd.DataFrame:
    """Median, mean, std, quartiles for price per sqm by group."""
    sale_df = df[df["listing_type"] == "sale"].copy()
    if sale_df.empty:
        logger.warning("no_sale_listings_for_price_stats")
        return pd.DataFrame()

    grouped = sale_df.groupby(group_col)
    return (
        grouped["price_per_sqm"]
        .agg(
            inventory="count",
            mean_price_per_sqm="mean",
            median_price_per_sqm="median",
            std_price_per_sqm="std",
            q1_price_per_sqm=lambda s: s.quantile(0.25),
            q3_price_per_sqm=lambda s: s.quantile(0.75),
        )
        .reset_index()
    )


def inventory_count(df: pd.DataFrame, group_col: str = "neighborhood_id") -> pd.DataFrame:
    """Active listing count by group."""
    active = df[df["is_active"].eq(True)] if "is_active" in df.columns else df
    return active.groupby(group_col).size().reset_index(name="inventory")


def price_distribution(df: pd.DataFrame, bins: int = 20) -> dict:
    """Histogram data for price per sqm distribution."""
    prices = df["price_per_sqm"].dropna()
    if prices.empty:
        return {"bins": [], "counts": []}
    counts, bin_edges = np.histogram(prices, bins=bins)
    return {"bins": bin_edges.tolist(), "counts": counts.tolist()}


def price_percentiles(
    series: pd.Series,
    percentiles: list[float] | None = None,
) -> dict[str, float | None]:
    """Compute percentile breakpoints from a price-per-sqm series.

    Returns a dict keyed by percentile label (e.g. ``"p10"``, ``"p50"``, ``"p90"``).
    """
    if percentiles is None:
        percentiles = [0.10, 0.50, 0.90]
    if series.empty:
        return {f"p{int(p * 100)}": None for p in percentiles}
    result: dict[str, float | None] = {}
    for p in percentiles:
        val = series.quantile(p)
        result[f"p{int(p * 100)}"] = round(float(val)) if pd.notna(val) else None
    return result
