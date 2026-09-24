"""Prove ingestion vs valuation bound layers are intentional and distinct."""

from __future__ import annotations

from decimal import Decimal

from groundtruth.analytics import valuation as valuation_mod
from groundtruth.processing import validation as validation_mod


def test_ingestion_rent_bounds_wider_than_valuation_comparables() -> None:
    """Ingestion keeps broad sanity; valuation uses a tighter comparable band."""
    assert Decimal("50") == validation_mod.MIN_RENT_PRICE
    assert Decimal("8000") == validation_mod.MAX_RENT_PRICE
    assert valuation_mod.RENT_COMPARABLE_MIN_EUR == 80
    assert valuation_mod.RENT_COMPARABLE_MAX_EUR == 2500
    assert float(validation_mod.MIN_RENT_PRICE) < valuation_mod.RENT_COMPARABLE_MIN_EUR
    assert float(validation_mod.MAX_RENT_PRICE) > valuation_mod.RENT_COMPARABLE_MAX_EUR


def test_ingestion_sale_bounds_wider_than_valuation_comparables() -> None:
    assert Decimal("3000") == validation_mod.MIN_SALE_PRICE
    assert Decimal("10000000") == validation_mod.MAX_SALE_PRICE
    assert valuation_mod.SALE_COMPARABLE_MIN_EUR == 10_000
    assert valuation_mod.SALE_COMPARABLE_MAX_EUR == 500_000
    assert float(validation_mod.MIN_SALE_PRICE) < valuation_mod.SALE_COMPARABLE_MIN_EUR
    assert float(validation_mod.MAX_SALE_PRICE) > valuation_mod.SALE_COMPARABLE_MAX_EUR


def test_comparable_area_band_documented() -> None:
    assert valuation_mod.RENT_COMPARABLE_MIN_AREA_SQM == 20
    assert valuation_mod.RENT_COMPARABLE_MAX_AREA_SQM == 200
    assert valuation_mod.SALE_COMPARABLE_MIN_AREA_SQM == 20
    assert valuation_mod.SALE_COMPARABLE_MAX_AREA_SQM == 200
    assert validation_mod.MIN_AREA_SQM < valuation_mod.RENT_COMPARABLE_MIN_AREA_SQM
    assert validation_mod.MAX_AREA_SQM > valuation_mod.RENT_COMPARABLE_MAX_AREA_SQM
