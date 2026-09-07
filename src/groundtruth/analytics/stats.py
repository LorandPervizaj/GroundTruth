"""Robust statistics for market comparisons — bootstrap CI, IQR, MAD."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class SummaryStats:
    """Descriptive statistics for a numeric sample."""

    n: int
    median: float
    mean: float
    std: float
    iqr: float
    mad: float
    q25: float
    q75: float
    min: float
    max: float

    def as_dict(self) -> dict[str, float | int]:
        return {
            "n": self.n,
            "median": round(self.median, 2),
            "mean": round(self.mean, 2),
            "std": round(self.std, 2),
            "iqr": round(self.iqr, 2),
            "mad": round(self.mad, 2),
            "q25": round(self.q25, 2),
            "q75": round(self.q75, 2),
            "min": round(self.min, 2),
            "max": round(self.max, 2),
        }


def summarize(values: pd.Series | np.ndarray) -> SummaryStats | None:
    """Compute robust summary statistics; returns None if n=0."""
    series = pd.Series(values).dropna()
    if series.empty:
        return None
    q25, q75 = series.quantile(0.25), series.quantile(0.75)
    median = float(series.median())
    mad = float((series - median).abs().median())
    return SummaryStats(
        n=len(series),
        median=median,
        mean=float(series.mean()),
        std=float(series.std(ddof=1)) if len(series) > 1 else 0.0,
        iqr=float(q75 - q25),
        mad=mad,
        q25=float(q25),
        q75=float(q75),
        min=float(series.min()),
        max=float(series.max()),
    )


def comparable_area_weights(
    areas: pd.Series | np.ndarray,
    target_area: float,
    *,
    bandwidth_m2: float = 10.0,
) -> np.ndarray:
    """Gaussian weights by area distance — closer listings count more."""
    arr = np.asarray(areas, dtype=float)
    if bandwidth_m2 <= 0:
        return np.ones_like(arr)
    return np.exp(-0.5 * ((arr - target_area) / bandwidth_m2) ** 2)


def weighted_average(
    values: pd.Series | np.ndarray,
    weights: pd.Series | np.ndarray,
) -> float | None:
    """Weighted arithmetic mean; returns None if no positive weight."""
    v = np.asarray(values, dtype=float)
    w = np.asarray(weights, dtype=float)
    mask = np.isfinite(v) & np.isfinite(w) & (w > 0)
    if not mask.any():
        return None
    v, w = v[mask], w[mask]
    total = w.sum()
    if total <= 0:
        return None
    return float(np.dot(v, w) / total)


def bootstrap_weighted_mean_ci(
    values: pd.Series | np.ndarray,
    weights: pd.Series | np.ndarray,
    *,
    n_resamples: int = 5000,
    ci: float = 0.95,
    seed: int = 42,
) -> tuple[float, float, float] | None:
    """Bootstrap percentile CI for a weighted mean. Returns (mean, lo, hi)."""
    v = pd.Series(values).dropna().to_numpy(dtype=float)
    w = pd.Series(weights).dropna().to_numpy(dtype=float)
    if len(v) == 0 or len(v) != len(w):
        return None
    w = np.clip(w, 0, None)
    if w.sum() <= 0:
        w = np.ones_like(w)
    mean = weighted_average(v, w)
    if mean is None:
        return None
    p = w / w.sum()
    rng = np.random.default_rng(seed)
    idx = rng.choice(len(v), size=(n_resamples, len(v)), replace=True, p=p)
    sampled_values = v[idx]
    sampled_weights = w[idx]
    totals = sampled_weights.sum(axis=1)
    valid = totals > 0
    if not valid.any():
        return None
    boot_means = (sampled_values[valid] * sampled_weights[valid]).sum(axis=1) / totals[valid]
    alpha = (1 - ci) / 2
    return (
        mean,
        float(np.quantile(boot_means, alpha)),
        float(np.quantile(boot_means, 1 - alpha)),
    )


def bootstrap_median_ci(
    values: pd.Series | np.ndarray,
    *,
    n_resamples: int = 5000,
    ci: float = 0.95,
    seed: int = 42,
) -> tuple[float, float, float] | None:
    """Bootstrap percentile CI for the median. Returns (median, lo, hi)."""
    series = pd.Series(values).dropna()
    if series.empty:
        return None
    rng = np.random.default_rng(seed)
    arr = series.to_numpy()
    medians = np.array(
        [np.median(rng.choice(arr, size=len(arr), replace=True)) for _ in range(n_resamples)]
    )
    alpha = (1 - ci) / 2
    return (
        float(np.median(arr)),
        float(np.quantile(medians, alpha)),
        float(np.quantile(medians, 1 - alpha)),
    )


def compare_medians(
    group_a: pd.Series | np.ndarray,
    group_b: pd.Series | np.ndarray,
    *,
    label_a: str = "A",
    label_b: str = "B",
    n_resamples: int = 5000,
    seed: int = 42,
) -> dict:
    """Compare two groups with medians, bootstrap CIs, and median difference."""
    stats_a = summarize(group_a)
    stats_b = summarize(group_b)
    if stats_a is None or stats_b is None:
        return {"error": "empty group"}

    ci_a = bootstrap_median_ci(group_a, n_resamples=n_resamples, seed=seed)
    ci_b = bootstrap_median_ci(group_b, n_resamples=n_resamples, seed=seed)

    a = pd.Series(group_a).dropna().to_numpy()
    b = pd.Series(group_b).dropna().to_numpy()
    rng = np.random.default_rng(seed)
    diffs = []
    for _ in range(n_resamples):
        sample_a = rng.choice(a, size=len(a), replace=True)
        sample_b = rng.choice(b, size=len(b), replace=True)
        diffs.append(np.median(sample_a) - np.median(sample_b))
    diff_median = float(np.median(a) - np.median(b))
    diff_lo = float(np.quantile(diffs, 0.025))
    diff_hi = float(np.quantile(diffs, 0.975))

    return {
        label_a: {**stats_a.as_dict(), "median_ci_lo": ci_a[1], "median_ci_hi": ci_a[2]},
        label_b: {**stats_b.as_dict(), "median_ci_lo": ci_b[1], "median_ci_hi": ci_b[2]},
        "median_difference": round(diff_median, 2),
        "difference_ci_95": (round(diff_lo, 2), round(diff_hi, 2)),
        "significant_at_95": diff_lo > 0 or diff_hi < 0,
    }
