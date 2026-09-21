from __future__ import annotations

import pandas as pd

from groundtruth.services.lookup import _bedroom_breakdown, _build_pulse


def _segment() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "listing_type": ["sale", "rent", "rent"],
            "property_type": ["APARTMENT"] * 3,
            "sale_price": [100_000.0, None, None],
            "rent_price": [None, 300.0, 500.0],
            "area_sqm": [50.0, 50.0, 100.0],
            "price_per_sqm": [2_000.0, None, None],
            "bedrooms": [1, 1, 1],
            "source_website": ["a", "b", "c"],
            "source_listing_id": ["1", "2", "3"],
        }
    )


def test_correct_median_fields_equal_compatibility_aliases() -> None:
    pulse = _build_pulse(_segment(), observations=3)
    assert pulse.median_sale_psm_eur == pulse.average_sale_psm_eur == 2000
    assert pulse.median_rent_psm_eur == pulse.average_rent_psm_eur == 6
    assert pulse.recent_valid_listings == pulse.active_listings == 3


def test_metric_payload_carries_full_contract() -> None:
    pulse = _build_pulse(_segment(), observations=3)
    metric = pulse.metrics["median_sale_psm"]
    assert metric.value == pulse.median_sale_psm_eur
    assert metric.statistic == "median"
    assert metric.unit == "EUR_PER_M2"
    assert metric.sample_n == 1
    assert metric.population == "recent.sale.apartment_studio"
    assert metric.window == {"days": 365}


def test_breakdown_has_separate_sale_rent_and_union_denominators() -> None:
    row = _bedroom_breakdown(_segment())[0]
    assert row.sale_sample_n == 1
    assert row.rent_sample_n == 2
    assert row.union_sample_n == row.listings == 3
