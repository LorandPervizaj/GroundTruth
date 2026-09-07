"""Robust €/m² helpers for market aggregates — median + validation bands."""

from __future__ import annotations

import pandas as pd

from groundtruth.analytics.display_rounding import round_rent_psm, round_sale_psm
from groundtruth.processing.validation import (
    MAX_RENT_PRICE_PER_SQM,
    MAX_SALE_PRICE_PER_SQM,
    MIN_RENT_PRICE_PER_SQM,
    MIN_SALE_PRICE_PER_SQM,
)

_MIN_SALE_PSM = float(MIN_SALE_PRICE_PER_SQM)
_MAX_SALE_PSM = float(MAX_SALE_PRICE_PER_SQM)
_MIN_RENT_PSM = float(MIN_RENT_PRICE_PER_SQM)
_MAX_RENT_PSM = float(MAX_RENT_PRICE_PER_SQM)


def sale_psm_series(sale: pd.DataFrame) -> pd.Series:
    """Sale €/m² from normalized price_per_sqm, filtered to the validation band."""
    if sale.empty:
        return pd.Series(dtype=float)
    psm = sale["price_per_sqm"].dropna().astype(float)
    return psm[(psm >= _MIN_SALE_PSM) & (psm <= _MAX_SALE_PSM)]


def rent_psm_series(rent: pd.DataFrame) -> pd.Series:
    """Rent €/m²/mo from rent_price / area, filtered to the validation band."""
    if rent.empty:
        return pd.Series(dtype=float)
    psm = (rent["rent_price"] / rent["area_sqm"]).dropna().astype(float)
    return psm[(psm >= _MIN_RENT_PSM) & (psm <= _MAX_RENT_PSM)]


def sane_rent_rows(rent: pd.DataFrame) -> pd.DataFrame:
    """Rent listings whose implied €/m²/mo is within the validation band."""
    if rent.empty:
        return rent
    psm = rent_psm_series(rent)
    if psm.empty:
        return rent.iloc[0:0]
    return rent.loc[psm.index]


def sane_sale_rows(sale: pd.DataFrame) -> pd.DataFrame:
    """Sale listings whose €/m² is within the validation band."""
    if sale.empty:
        return sale
    psm = sale_psm_series(sale)
    if psm.empty:
        return sale.iloc[0:0]
    return sale.loc[psm.index]


def median_sale_psm(series: pd.Series) -> int | None:
    """Median sale €/m² for display."""
    if series.empty:
        return None
    return round_sale_psm(float(series.median()))


def median_rent_psm(series: pd.Series) -> int | None:
    """Median rent €/m²/mo for display."""
    if series.empty:
        return None
    return round_rent_psm(float(series.median()))


def median_psm(series: pd.Series) -> int | None:
    """Backward-compatible alias for sale €/m²."""
    return median_sale_psm(series)
