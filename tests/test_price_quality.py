"""Tests for monthly price outlier filtering."""

import pandas as pd

from groundtruth.analytics.price_quality import monthly_medians_from_frame, robust_monthly_medians


def test_robust_monthly_medians_excludes_dec_trough() -> None:
    raw = {f"2025-{m:02d}": 1200.0 for m in range(1, 13)}
    raw["2025-12"] = 461.0
    counts = {m: 50 for m in raw}
    counts["2025-12"] = 59

    cleaned, exclusions = robust_monthly_medians(raw, counts, min_count=20)
    assert "2025-12" not in cleaned
    assert any(x["month"] == "2025-12" and x["reason"] == "thin_sample_trough" for x in exclusions)


def test_robust_monthly_medians_keeps_low_sample_with_warning() -> None:
    raw = {"2025-08": 1000.0, "2025-09": 800.0}
    counts = {"2025-08": 1, "2025-09": 1}

    cleaned, exclusions = robust_monthly_medians(raw, counts, min_count=20)
    assert cleaned == raw
    assert all(x["reason"] == "low_sample" for x in exclusions)


def test_monthly_medians_from_frame() -> None:
    df = pd.DataFrame(
        [
            {"listing_month": "2025-08", "price_per_sqm": 1000.0},
            {"listing_month": "2025-09", "price_per_sqm": 800.0},
        ]
    )
    cleaned, counts, exclusions, raw = monthly_medians_from_frame(
        df, month_col="listing_month", value_col="price_per_sqm"
    )
    assert cleaned == {"2025-08": 1000.0, "2025-09": 800.0}
    assert len(exclusions) == 2
