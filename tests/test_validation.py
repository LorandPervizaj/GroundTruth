"""Tests for listing validation rules."""

from decimal import Decimal

import pytest

from groundtruth.models.enums import ListingType
from groundtruth.processing.validation import ListingValidator
from groundtruth.schemas.pipeline import NormalizedListingSchema


@pytest.fixture
def validator() -> ListingValidator:
    return ListingValidator()


def test_valid_rent_listing(validator: ListingValidator) -> None:
    listing = NormalizedListingSchema(
        source_website="gjirafa",
        source_listing_id="banesa-1",
        original_url="https://example.com/1",
        listing_type=ListingType.RENT,
        rent_price=Decimal("300"),
        area_sqm=60.0,
        price_per_sqm=Decimal("5.00"),
    )
    result = validator.validate(listing)
    assert result.is_valid


def test_rent_price_too_low_flagged(validator: ListingValidator) -> None:
    listing = NormalizedListingSchema(
        source_website="gjirafa",
        source_listing_id="banesa-2",
        original_url="https://example.com/2",
        listing_type=ListingType.RENT,
        rent_price=Decimal("10"),
        area_sqm=60.0,
    )
    result = validator.validate(listing)
    assert not result.is_valid
    assert any(issue.code == "price_too_low" for issue in result.issues)


def test_area_too_small_flagged(validator: ListingValidator) -> None:
    listing = NormalizedListingSchema(
        source_website="gjirafa",
        source_listing_id="banesa-3",
        original_url="https://example.com/3",
        listing_type=ListingType.SALE,
        sale_price=Decimal("50000"),
        area_sqm=10.0,
        price_per_sqm=Decimal("5000"),
    )
    result = validator.validate(listing)
    assert not result.is_valid
    assert any(issue.code == "area_too_small" for issue in result.issues)
