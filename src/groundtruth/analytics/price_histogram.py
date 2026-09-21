"""Price distribution histograms for market segments.

Sale distributions use asking €/m² in fixed €50/m² intervals, analytically
restricted to values strictly below SALE_DISTRIBUTION_MAX_PSM.
Rent distributions use monthly asking rent in fixed €20 intervals via sane_rent_rows.
"""

from __future__ import annotations

import math
from typing import Any, Literal

import numpy as np
import pandas as pd

from groundtruth.analytics.display_rounding import round_rent_eur, round_sale_psm
from groundtruth.analytics.market_metrics import sale_psm_series, sane_rent_rows
from groundtruth.analytics.sample_confidence import confidence_level

ListingTypeLit = Literal["sale", "rent"]
MIN_BIN_LISTINGS = 5
# Safety ceiling for fixed-width grids (city-wide rent at €20 can approach ~150).
MAX_HISTOGRAM_BINS = 250

SALE_BIN_WIDTH_PSM = 50
RENT_BIN_WIDTH_EUR = 20

# Analytical filter for public *sale* distribution charts and their paired
# summary percentiles only. Exclusive upper bound: €4,000/m² itself is out.
# Does not alter raw listings, rent metrics, or unrelated market aggregates.
SALE_DISTRIBUTION_MAX_PSM = 4000.0


def sale_psm_for_distribution(values: pd.Series) -> tuple[pd.Series, int]:
    """Apply the public sale-distribution ceiling; return (kept, excluded_count)."""
    clean = values.dropna().astype(float)
    if clean.empty:
        return clean, 0
    kept = clean[clean < SALE_DISTRIBUTION_MAX_PSM]
    return kept, int(len(clean) - len(kept))


def _aligned_edges(
    vmin: float,
    vmax: float,
    width: int,
    *,
    max_exclusive: float | None = None,
) -> np.ndarray:
    """Build inclusive left / exclusive-style right edges on a fixed step."""
    start = int(math.floor(vmin / width) * width)
    if max_exclusive is not None:
        stop = int(max_exclusive)
        if stop <= start:
            stop = start + width
    else:
        stop = int(math.ceil(vmax / width) * width)
        # np.histogram's last bin is closed on the right — pad when vmax lands on an edge.
        if stop <= vmax:
            stop += width
        if stop <= start:
            stop = start + width
    edges = np.arange(start, stop + width, width, dtype=float)
    if len(edges) < 2:
        edges = np.array([float(start), float(start + width)], dtype=float)
    # Cap runaway grids (pathological spreads) without silently widening the step.
    if len(edges) - 1 > MAX_HISTOGRAM_BINS:
        edges = edges[: MAX_HISTOGRAM_BINS + 1]
    return edges


def _histogram_bins(
    values: pd.Series,
    *,
    width: int,
    round_edge,
    max_exclusive: float | None = None,
) -> list[dict[str, int]]:
    clean = values.dropna().astype(float)
    if clean.empty:
        return []
    edges = _aligned_edges(
        float(clean.min()),
        float(clean.max()),
        width,
        max_exclusive=max_exclusive,
    )
    counts, _ = np.histogram(clean, bins=edges)
    out: list[dict[str, int]] = []
    for i, count in enumerate(counts):
        if int(count) <= 0:
            continue
        start = round_edge(edges[i])
        end = round_edge(edges[i + 1])
        if start is None or end is None:
            continue
        if max_exclusive is not None:
            limit = int(max_exclusive)
            if start >= limit:
                continue
            # Keep the exclusive ceiling as the printed right edge (e.g. 3950–4000).
            if end > limit:
                end = limit
            if end <= start:
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
) -> dict[str, Any]:
    work = segment[segment["listing_type"] == listing_type].copy()
    if work.empty:
        return {"listing_type": listing_type, "bins": [], "n": 0, "confidence": "insufficient"}

    excluded_n = 0
    max_exclusive: float | None = None
    if listing_type == "sale":
        # Same validation band as public percentiles / pulse medians, then the
        # distribution-only ceiling (strictly below €4,000/m²).
        values, excluded_n = sale_psm_for_distribution(sale_psm_series(work))
        round_edge = round_sale_psm
        max_exclusive = SALE_DISTRIBUTION_MAX_PSM
        width = SALE_BIN_WIDTH_PSM
    else:
        # Public product: rent distributions are monthly asking rent, not €/m².
        # Restrict to the same rows the rent medians use, otherwise out-of-band
        # listings (offices, yearly quotes, bad areas) show up as a fake tail.
        # The sale €4,000/m² ceiling is never applied here.
        values = sane_rent_rows(work)["rent_price"].dropna()
        round_edge = round_rent_eur
        width = RENT_BIN_WIDTH_EUR

    n = int(len(values))
    if n < MIN_BIN_LISTINGS:
        payload: dict[str, Any] = {
            "listing_type": listing_type,
            "bins": [],
            "n": n,
            "confidence": confidence_level(n),
        }
        if listing_type == "sale":
            payload["max_psm_exclusive"] = int(SALE_DISTRIBUTION_MAX_PSM)
            payload["excluded_n"] = excluded_n
        return payload

    payload = {
        "listing_type": listing_type,
        "bins": _histogram_bins(
            values,
            width=width,
            round_edge=round_edge,
            max_exclusive=max_exclusive,
        ),
        "n": n,
        "confidence": confidence_level(n),
    }
    if listing_type == "sale":
        payload["max_psm_exclusive"] = int(SALE_DISTRIBUTION_MAX_PSM)
        payload["excluded_n"] = excluded_n
    return payload
