"""Unit tests for the percentile + city-comparison builders wired into market lookup."""

from __future__ import annotations

import pandas as pd

from groundtruth.analytics.metrics.price import price_percentiles
from groundtruth.services.lookup import (
    _build_city_comparison,
    _build_price_percentiles,
)


def _sale_row(psm: float, ptype: str = "APARTMENT") -> dict:
    return {
        "listing_type": "sale",
        "property_type": ptype,
        "price_per_sqm": psm,
        "rent_price": None,
        "area_sqm": 70.0,
    }


def _rent_row(rent: float, area: float = 70.0, ptype: str = "APARTMENT") -> dict:
    return {
        "listing_type": "rent",
        "property_type": ptype,
        "price_per_sqm": None,
        "rent_price": rent,
        "area_sqm": area,
    }


def test_price_percentiles_helper_orders_and_counts():
    series = pd.Series([1000, 1500, 2000, 2500, 3000], dtype=float)
    out = price_percentiles(series)
    assert set(out) == {"p10", "p50", "p90"}
    assert out["p10"] < out["p50"] < out["p90"]
    assert out["p50"] == 2000


def test_price_percentiles_helper_empty_returns_none_values():
    out = price_percentiles(pd.Series(dtype=float))
    assert out == {"p10": None, "p50": None, "p90": None}


def test_build_price_percentiles_returns_ordered_with_n():
    seg = pd.DataFrame([_sale_row(p) for p in (900, 1200, 1500, 1800, 2400, 3000)])
    result = _build_price_percentiles(seg)
    assert result is not None
    assert result.n == 6
    assert result.p10_sale_psm <= result.p50_sale_psm <= result.p90_sale_psm


def test_build_price_percentiles_no_sale_returns_none():
    seg = pd.DataFrame([_rent_row(600)])
    assert _build_price_percentiles(seg) is None


def test_build_city_comparison_premium_neighborhood_is_top_tier():
    # Neighborhood is expensive (5000 €/m²); city is mostly cheap.
    nh = pd.DataFrame([_sale_row(5000), _sale_row(5100), _sale_row(4900)] + [_rent_row(700)])
    city = pd.DataFrame(
        [_sale_row(p) for p in (1000, 1200, 1500, 2000, 2500, 3000, 5000, 5100, 4900)]
        + [_rent_row(450), _rent_row(700)]
    )
    cmp = _build_city_comparison(nh, city)
    assert cmp is not None
    assert cmp.price_tier in {"$", "$$", "$$$", "$$$$"}
    assert cmp.price_tier == "$$$$"  # nh median well above city Q3
    assert cmp.premium_pct is not None and cmp.premium_pct > 0
    assert cmp.neighborhood_sale_psm is not None
    assert cmp.city_median_sale_psm is not None


def test_build_city_comparison_cheap_neighborhood_is_bottom_tier():
    nh = pd.DataFrame([_sale_row(800), _sale_row(850), _sale_row(900)])
    city = pd.DataFrame([_sale_row(p) for p in (800, 850, 900, 2000, 3000, 4000, 5000, 6000)])
    cmp = _build_city_comparison(nh, city)
    assert cmp is not None
    assert cmp.price_tier == "$"
    assert cmp.premium_pct is not None and cmp.premium_pct < 0


def test_build_city_comparison_empty_returns_none():
    assert _build_city_comparison(pd.DataFrame(), pd.DataFrame()) is None
