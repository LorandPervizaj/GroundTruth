"""Rental market metrics."""

import pandas as pd

from groundtruth.logging import get_logger

logger = get_logger(__name__)


def rent_stats(df: pd.DataFrame, group_col: str = "neighborhood_id") -> pd.DataFrame:
    """Median and mean rent by group."""
    rent_df = df[df["listing_type"] == "rent"].copy()
    if rent_df.empty:
        logger.warning("no_rent_listings_for_rent_stats")
        return pd.DataFrame()

    grouped = rent_df.groupby(group_col)
    return grouped["rent_price"].agg(
        rent_inventory="count",
        median_rent="median",
        mean_rent="mean",
    ).reset_index()
