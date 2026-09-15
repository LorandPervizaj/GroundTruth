"""Price distribution histograms for market segments.

Sale distributions use asking €/m².
Rent distributions use monthly asking rent (not €/m²).
"""

from __future__ import annotations

from typing import Any, Literal

import numpy as np
import pandas as pd

from groundtruth.analytics.display_rounding import round_rent_eur, round_sale_psm
from groundtruth.analytics.sample_confidence import confidence_level

ListingTypeLit = Literal["sale", "rent"]
MIN_BIN_LISTINGS = 5


def _histogram_bins(
    values: pd.Series,
    *,
    bins: int = 10,
    round_edge,
) -> list[dict[str, int]]:
    clean = values.dropna()
    if clean.empty:
        return []
    counts, edges = np.histogram(clean, bins=min(bins, max(3, len(clean) // 5)))
    out: list[dict[str, int]] = []
    for i, count in enumerate(counts):
        if int(count) <= 0:
            continue
        start = round_edge(edges[i])
        end = round_edge(edges[i + 1])
        if start is None or end is None:
            continue
        out.append(
            {
                "bin_start": start,
                "bin_end": end,
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
        round_edge = round_sale_psm
    else:
        # Public product: rent distributions are monthly asking rent, not €/m².
        values = work["rent_price"].dropna()
        round_edge = round_rent_eur

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
        "bins": _histogram_bins(values, bins=bins, round_edge=round_edge),
        "n": n,
        "confidence": confidence_level(n),
    }
