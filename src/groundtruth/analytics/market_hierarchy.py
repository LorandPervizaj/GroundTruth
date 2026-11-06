"""Explicit, read-only canonical market projection for reports and shadow runs.

This does not rewrite historical FKs, filter municipalities or expand parent
memberships. Public cache consumers retain their existing aggregation until a
reviewed release opts into this projection.
"""

from __future__ import annotations

import pandas as pd

from groundtruth.gazetteers.market_graph import canonical_market_slug


def canonical_market_frame(
    frame: pd.DataFrame, neighborhood_references: list[dict]
) -> pd.DataFrame:
    """Consolidate confirmed equivalent labels; preserve units and source labels."""
    result = frame.copy()
    by_id = {row["id"]: row for row in neighborhood_references}
    by_slug = {row["slug"]: row for row in neighborhood_references}
    result["source_neighborhood_id"] = frame["neighborhood_id"]
    result["source_neighborhood"] = frame["neighborhood"]
    for index, row in frame.iterrows():
        if pd.isna(row.neighborhood_id):
            continue
        old = by_id.get(int(row.neighborhood_id))
        if old is None:
            continue
        slug = canonical_market_slug(old["slug"])
        target = by_slug.get(slug)
        if target and slug != old["slug"]:
            result.at[index, "neighborhood_id"] = target["id"]
            result.at[index, "neighborhood"] = target["name"]
    return result


def count_market_label_changes(before: pd.DataFrame, after: pd.DataFrame) -> int:
    """Count real label/ID changes; unknown-to-unknown is not a movement."""
    if not before.index.equals(after.index):
        raise ValueError("Market comparison requires identical observation indexes")
    ids_changed = before.neighborhood_id.fillna(-1) != after.neighborhood_id.fillna(-1)
    labels_changed = before.neighborhood.fillna("") != after.neighborhood.fillna("")
    return int((ids_changed | labels_changed).sum())
