"""Tests for robust market €/m² metrics."""

import pandas as pd

from groundtruth.analytics.market_metrics import median_rent_psm, rent_psm_series
from groundtruth.services.lookup import _bedroom_breakdown, _build_pulse, _size_breakdown


def test_rent_psm_filters_outliers() -> None:
    rent = pd.DataFrame(
        {
            "listing_type": ["rent"] * 3,
            "rent_price": [300.0, 400.0, 450_000.0],
            "area_sqm": [60.0, 80.0, 46.0],
        }
    )
    psm = rent_psm_series(rent)
    assert len(psm) == 2
    assert float(psm.median()) == 5
    assert median_rent_psm(psm) == 5


def test_size_breakdown_uses_median_not_mean() -> None:
    rows = pd.DataFrame(
        {
            "listing_type": ["rent", "rent", "rent", "sale"],
            "property_type": ["APARTMENT"] * 4,
            "rent_price": [300.0, 350.0, 450_000.0, None],
            "sale_price": [None, None, None, 120_000.0],
            "area_sqm": [60.0, 65.0, 46.0, 60.0],
            "price_per_sqm": [None, None, None, 2000.0],
            "bedrooms": [2, 2, 1, 2],
            "source_website": ["merrjep"] * 4,
            "source_listing_id": ["1", "2", "3", "4"],
        }
    )
    band = next(r for r in _size_breakdown(rows) if r.size_band == "50-70")
    assert band.average_rent_psm_eur == 5
    assert band.median_rent_eur == 330


def test_bedroom_breakdown_buckets_four_plus() -> None:
    rows = pd.DataFrame(
        {
            "listing_type": ["rent", "rent", "rent"],
            "property_type": ["APARTMENT"] * 3,
            "rent_price": [400.0, 500.0, 600.0],
            "sale_price": [None, None, None],
            "area_sqm": [80.0, 90.0, 100.0],
            "price_per_sqm": [None, None, None],
            "bedrooms": [4, 5, 6],
            "source_website": ["gjirafa"] * 3,
            "source_listing_id": ["1", "2", "3"],
        }
    )
    breakdown = _bedroom_breakdown(rows)
    four_plus = [r for r in breakdown if r.label == "4BR+"]
    assert len(four_plus) == 1
    assert four_plus[0].listings == 3


def test_build_pulse_robust_to_mislabeled_rent() -> None:
    segment = pd.DataFrame(
        {
            "listing_type": ["rent", "rent"],
            "property_type": ["APARTMENT", "APARTMENT"],
            "rent_price": [300.0, 450_000.0],
            "sale_price": [None, None],
            "area_sqm": [60.0, 46.0],
            "price_per_sqm": [None, None],
            "bedrooms": [2, 1],
            "source_website": ["merrjep", "merrjep"],
            "source_listing_id": ["1", "2"],
        }
    )
    pulse = _build_pulse(segment, observations=2)
    assert pulse.average_rent_psm_eur == 5
    assert pulse.median_rent_eur == 300
