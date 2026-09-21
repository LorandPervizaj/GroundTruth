"""Consistent rounding for user-facing API numbers."""

from __future__ import annotations

import math
from typing import Any

import pandas as pd


def _round_to_step(value: float, step: int) -> int:
    return int(math.floor(value / step + 0.5)) * step


def round_rent_eur(value: Any) -> int | None:
    """Rent totals and medians — nearest €10."""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    return _round_to_step(float(value), 10)


def round_sale_eur(value: Any) -> int | None:
    """Sale totals and medians — nearest €1,000."""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    return _round_to_step(float(value), 1000)


def round_sale_psm(value: Any) -> int | None:
    """Sale €/m² — nearest €10."""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    return _round_to_step(float(value), 10)


def round_rent_psm(value: Any) -> int | None:
    """Rent €/m²/mo — nearest whole € (typical band is €3–15/mo)."""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    rounded = _round_to_step(float(value), 1)
    return rounded if rounded >= 1 else None


def round_psm(value: Any) -> int | None:
    """Sale €/m² display (alias)."""
    return round_sale_psm(value)


def round_area(value: Any) -> int | None:
    """Area — nearest whole m² (global public-display policy)."""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    return _round_to_step(float(value), 1)


def round_percent(value: Any, *, digits: int = 0) -> float | None:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    return round(float(value), digits)
