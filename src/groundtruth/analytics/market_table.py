"""The single LinkedIn-ready neighborhood market table."""

import pandas as pd

from groundtruth.analytics.metrics import (
    gross_rental_yield,
    inventory_count,
    luxury_concentration,
    price_stats,
    rent_stats,
)


def build_neighborhood_market_table(df: pd.DataFrame) -> pd.DataFrame:
    """
    One table with everything that matters:

    Neighborhood | Median €/m² | Inventory | Median Size | Median Rent | Yield | Luxury %
    """
    prices = price_stats(df)
    if prices.empty:
        return pd.DataFrame()

    inventory = inventory_count(df)
    rents = rent_stats(df)
    luxury = luxury_concentration(df)

    sale_df = df[df["listing_type"] == "sale"]
    rent_df = df[df["listing_type"] == "rent"]
    yields = gross_rental_yield(sale_df, rent_df) if not sale_df.empty and not rent_df.empty else pd.DataFrame()

    size_stats = (
        sale_df.groupby("neighborhood_id")["area_sqm"]
        .agg(median_size_sqm="median", mean_size_sqm="mean")
        .reset_index()
    )

    table = prices.merge(inventory, on="neighborhood_id", how="left")
    table = table.merge(size_stats, on="neighborhood_id", how="left")
    table = table.merge(rents, on="neighborhood_id", how="left")
    table = table.merge(luxury, on="neighborhood_id", how="left")
    if not yields.empty:
        table = table.merge(
            yields[["neighborhood_id", "gross_yield_pct"]], on="neighborhood_id", how="left"
        )

    return table.sort_values("median_price_per_sqm", ascending=False)
