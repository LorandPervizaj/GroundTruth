"""Robust price series helpers — thin-sample months and obvious median artifacts."""

from __future__ import annotations

from typing import Any

import pandas as pd

DEFAULT_MIN_MONTHLY_N = 20
DEFAULT_TROUGH_RATIO = 0.75
DEFAULT_SPIKE_RATIO = 1.15


def _monthly_median_outlier(
    month: str,
    value: float,
    others: pd.Series,
    *,
    trough_ratio: float,
    spike_ratio: float,
) -> str | None:
    if others.empty:
        return None
    baseline = float(others.median())
    if baseline <= 0:
        return None
    if value <= baseline * trough_ratio:
        return "thin_sample_trough"
    if value >= baseline * spike_ratio:
        return "thin_sample_spike"
    return None


def robust_monthly_medians(
    monthly_values: dict[str, float],
    monthly_counts: dict[str, int],
    *,
    min_count: int = DEFAULT_MIN_MONTHLY_N,
    trough_ratio: float = DEFAULT_TROUGH_RATIO,
    spike_ratio: float = DEFAULT_SPIKE_RATIO,
) -> tuple[dict[str, float], list[dict[str, Any]]]:
    """
    Drop monthly medians that are unreliable (low n) or extreme vs other months.

    Returns cleaned {month: median} and exclusion records for transparency.
    """
    if not monthly_values:
        return {}, []

    exclusions: list[dict[str, Any]] = []
    cleaned: dict[str, float] = {}
    months = sorted(monthly_values)

    for month in months:
        value = float(monthly_values[month])
        n = int(monthly_counts.get(month, 0))
        if n < min_count:
            exclusions.append(
                {
                    "month": month,
                    "reason": "low_sample",
                    "n": n,
                    "raw_median": int(round(value)),
                }
            )
            cleaned[month] = value
            continue

        others = pd.Series({m: monthly_values[m] for m in months if m != month})
        outlier = _monthly_median_outlier(
            month,
            value,
            others,
            trough_ratio=trough_ratio,
            spike_ratio=spike_ratio,
        )
        if outlier:
            exclusions.append(
                {
                    "month": month,
                    "reason": outlier,
                    "n": n,
                    "raw_median": int(round(value)),
                }
            )
            continue

        cleaned[month] = value

    return cleaned, exclusions


def monthly_medians_from_frame(
    df: pd.DataFrame,
    *,
    month_col: str,
    value_col: str,
    min_count: int = DEFAULT_MIN_MONTHLY_N,
) -> tuple[dict[str, float], dict[str, int], list[dict[str, Any]], dict[str, float]]:
    """Compute monthly medians from a dataframe and apply robust filtering."""
    empty: tuple[dict[str, float], dict[str, int], list[dict[str, Any]], dict[str, float]] = (
        {},
        {},
        [],
        {},
    )
    if df.empty or value_col not in df.columns:
        return empty

    work = df.dropna(subset=[month_col, value_col])
    if work.empty:
        return empty

    grouped = work.groupby(month_col)[value_col]
    raw_medians = {str(m): float(v) for m, v in grouped.median().items()}
    counts = {str(m): int(n) for m, n in grouped.count().items()}
    cleaned, exclusions = robust_monthly_medians(
        raw_medians,
        counts,
        min_count=min_count,
    )
    return cleaned, counts, exclusions, raw_medians
