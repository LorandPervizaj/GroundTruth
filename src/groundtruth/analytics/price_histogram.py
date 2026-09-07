"""€/m² distribution histograms for market segments."""

from __future__ import annotations

from typing import Any, Literal

import numpy as np
import pandas as pd

from groundtruth.analytics.display_rounding import round_psm
from groundtruth.analytics.sample_confidence import confidence_level

ListingTypeLit = Literal["sale", "rent"]
MIN_BIN_LISTINGS = 5


def _histogram_bins(values: pd.Series, *, bins: int = 10) -> list[dict[str, int]]:
    clean = values.dropna()
    if clean.empty:
        return []
    counts, edges = np.histogram(clean, bins=min(bins, max(3, len(clean) // 5)))
    out: list[dict[str, int]] = []
    for i, count in enumerate(counts):
        if int(count) <= 0:
            continue
        out.append(
            {
                "bin_start": round_psm(edges[i]),
                "bin_end": round_psm(edges[i + 1]),
                "count": int(count),
            }
        )
    return out


def segment_price_distribution(
    segment: pd.DataFrame,
    listing_type: ListingTypeLit,
    *,
    bins: int = 10,
) -> dict[str, Any]:
    work = segment[segment["listing_type"] == listing_type].copy()
    if work.empty:
        return {"listing_type": listing_type, "bins": [], "n": 0, "confidence": "insufficient"}

    if listing_type == "sale":
        values = work["price_per_sqm"].dropna()
    else:
        values = (work["rent_price"] / work["area_sqm"]).dropna()

    n = int(len(values))
    if n < MIN_BIN_LISTINGS:
        return {
            "listing_type": listing_type,
            "bins": [],
            "n": n,
            "confidence": confidence_level(n),
        }

    return {
        "listing_type": listing_type,
        "bins": _histogram_bins(values, bins=bins),
        "n": n,
        "confidence": confidence_level(n),
    }
