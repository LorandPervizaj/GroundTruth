"""Tests for display rounding helpers."""

from groundtruth.analytics.display_rounding import (
    round_area,
    round_percent,
    round_psm,
    round_rent_eur,
    round_rent_psm,
    round_sale_eur,
)


def test_round_rent_eur_nearest_ten() -> None:
    assert round_rent_eur(412) == 410
    assert round_rent_eur(458) == 460
    assert round_rent_eur(454) == 450
    assert round_rent_eur(455) == 460
    assert round_rent_eur(None) is None


def test_round_sale_eur_nearest_thousand() -> None:
    assert round_sale_eur(143_450) == 143_000
    assert round_sale_eur(132_643) == 133_000
    assert round_sale_eur(148_499) == 148_000
    assert round_sale_eur(148_500) == 149_000
    assert round_sale_eur(None) is None


def test_round_psm() -> None:
    assert round_psm(1251.9) == 1250
    assert round_psm(1244) == 1240


def test_round_rent_psm_nearest_euro() -> None:
    assert round_rent_psm(5.26) == 5
    assert round_rent_psm(5.6) == 6
    assert round_rent_psm(4.44) == 4
    assert round_rent_psm(12.44) == 12
    assert round_rent_psm(0.4) is None
    assert round_rent_psm(None) is None


def test_median_rent_psm() -> None:
    import pandas as pd

    from groundtruth.analytics.market_metrics import median_rent_psm, median_sale_psm

    assert median_sale_psm(pd.Series([1500.4, 1600.8])) == 1550
    assert median_rent_psm(pd.Series([4.6, 5.8])) == 5


def test_round_area() -> None:
    assert round_area(2340) == 2350
    assert round_area(63.7) == 50


def test_round_percent() -> None:
    assert round_percent(62.7) == 63.0
