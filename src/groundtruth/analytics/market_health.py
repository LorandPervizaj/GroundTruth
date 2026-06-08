"""Market Health Score — composite neighborhood ranking."""

import pandas as pd


def compute_market_health_score(row: pd.Series) -> float:
    """
    Composite score (0–100) from:

    Price growth + Inventory + Rental yield + Luxury % + Price stability + Construction activity
    """
    components: list[float] = []

    if pd.notna(row.get("gross_yield_pct")):
        components.append(min(row["gross_yield_pct"] * 10, 100))

    if pd.notna(row.get("inventory")):
        inv_score = min(row["inventory"] / 50 * 100, 100)
        components.append(inv_score)

    if pd.notna(row.get("luxury_percentage")):
        components.append(min(row["luxury_percentage"] * 2, 100))

    if pd.notna(row.get("new_build_percentage")):
        components.append(min(row["new_build_percentage"], 100))

    if pd.notna(row.get("price_stability_score")):
        components.append(row["price_stability_score"])

    if not components:
        return 0.0
    return round(sum(components) / len(components), 2)


def rank_neighborhoods(market_table: pd.DataFrame) -> pd.DataFrame:
    """Add market_health_score and rank neighborhoods."""
    ranked = market_table.copy()
    ranked["market_health_score"] = ranked.apply(compute_market_health_score, axis=1)
    ranked["rank"] = ranked["market_health_score"].rank(ascending=False, method="dense").astype(int)
    return ranked.sort_values("rank")
