"""Buyer Score — best neighborhoods for a given budget."""

import pandas as pd


def recommend_neighborhoods(
    market_table: pd.DataFrame,
    budget_eur: float,
    *,
    top_n: int = 5,
    neighborhood_names: dict[int, str] | None = None,
) -> pd.DataFrame:
    """
    Rank neighborhoods for a buyer with a given budget.

    Considers: €/m², average size achievable, inventory, rental yield.
    """
    if market_table.empty:
        return pd.DataFrame()

    scored = market_table.copy()
    scored["affordable_area"] = budget_eur / scored["median_price_per_sqm"].replace(0, pd.NA)
    scored["value_score"] = (
        scored["affordable_area"].fillna(0) * 0.35
        + scored.get("inventory", 0).fillna(0) * 0.25
        + scored.get("gross_yield_pct", 0).fillna(0) * 0.25
        + (100 - scored["median_price_per_sqm"].rank(pct=True) * 100) * 0.15
    )

    top = scored.nlargest(top_n, "value_score")
    if neighborhood_names:
        top = top.copy()
        top["neighborhood_name"] = top["neighborhood_id"].map(neighborhood_names)

    return top[
        [
            c
            for c in [
                "neighborhood_name",
                "neighborhood_id",
                "median_price_per_sqm",
                "affordable_area",
                "inventory",
                "gross_yield_pct",
                "value_score",
            ]
            if c in top.columns
        ]
    ]
