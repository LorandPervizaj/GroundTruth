"""Generate nightly market_snapshots from normalized listings."""

from datetime import date

import pandas as pd
from sqlalchemy.orm import Session

from groundtruth.analytics.market_health import compute_market_health_score
from groundtruth.analytics.market_table import build_neighborhood_market_table
from groundtruth.logging import get_logger
from groundtruth.models.market import MarketSnapshot

logger = get_logger(__name__)


def generate_market_snapshots(
    session: Session,
    df: pd.DataFrame,
    snapshot_date: date | None = None,
) -> list[MarketSnapshot]:
    """Compute and persist market snapshots for all neighborhoods."""
    snapshot_date = snapshot_date or date.today()
    table = build_neighborhood_market_table(df)
    if table.empty:
        logger.warning("no_data_for_snapshots", date=str(snapshot_date))
        return []

    sale_df = df[df["listing_type"] == "sale"]
    new_build_pct = (
        sale_df.groupby("neighborhood_id")["is_new_construction"]
        .mean()
        .mul(100)
        .reset_index(name="new_build_percentage")
    )
    table = table.merge(new_build_pct, on="neighborhood_id", how="left")

    snapshots: list[MarketSnapshot] = []
    for _, row in table.iterrows():
        entity = MarketSnapshot(
            snapshot_date=snapshot_date,
            neighborhood_id=int(row["neighborhood_id"]),
            median_price=row.get("median_price_per_sqm"),
            mean_price=row.get("mean_price_per_sqm"),
            median_price_per_sqm=row.get("median_price_per_sqm"),
            mean_price_per_sqm=row.get("mean_price_per_sqm"),
            inventory=int(row.get("inventory", 0)),
            median_size_sqm=row.get("median_size_sqm"),
            mean_size_sqm=row.get("mean_size_sqm"),
            median_rent=row.get("median_rent"),
            gross_yield_pct=row.get("gross_yield_pct"),
            luxury_percentage=row.get("luxury_percentage"),
            new_build_percentage=row.get("new_build_percentage"),
            market_health_score=compute_market_health_score(row),
        )
        session.add(entity)
        snapshots.append(entity)

    session.flush()
    logger.info("snapshots_generated", count=len(snapshots), date=str(snapshot_date))
    return snapshots
