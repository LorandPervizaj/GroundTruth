"""Tests for listing validation rules."""

from decimal import Decimal

import pytest

from groundtruth.models.enums import ListingType, PropertyType
from groundtruth.processing.extractors.property_type import HOUSE_MIN_AREA_SQM
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


def test_house_under_min_area_invalid(validator: ListingValidator) -> None:
    listing = NormalizedListingSchema(
        source_website="merrjep",
        source_listing_id="shtepi-1",
        original_url="https://example.com/1",
        listing_type=ListingType.RENT,
        property_type=PropertyType.HOUSE,
        rent_price=Decimal("400"),
        area_sqm=120.0,
    )
    result = validator.validate(listing)
    assert not result.is_valid
    assert any(issue.code == "house_area_too_small" for issue in result.issues)


def test_house_at_min_area_valid(validator: ListingValidator) -> None:
    listing = NormalizedListingSchema(
        source_website="merrjep",
        source_listing_id="shtepi-2",
        original_url="https://example.com/2",
        listing_type=ListingType.RENT,
        property_type=PropertyType.HOUSE,
        rent_price=Decimal("600"),
        area_sqm=HOUSE_MIN_AREA_SQM,
    )
    result = validator.validate(listing)
    assert result.is_valid


def test_villa_small_area_not_house_rule(validator: ListingValidator) -> None:
    listing = NormalizedListingSchema(
        source_website="merrjep",
        source_listing_id="vila-1",
        original_url="https://example.com/3",
        listing_type=ListingType.RENT,
        property_type=PropertyType.VILLA,
        rent_price=Decimal("800"),
        area_sqm=90.0,
    )
    result = validator.validate(listing)
    assert result.is_valid


def test_sale_price_under_3000_invalid(validator: ListingValidator) -> None:
    listing = NormalizedListingSchema(
        source_website="merrjep",
        source_listing_id="sale-low",
        original_url="https://example.com/low",
        listing_type=ListingType.SALE,
        sale_price=Decimal("2900"),
        area_sqm=80.0,
        price_per_sqm=Decimal("36.25"),
    )
    result = validator.validate(listing)
    assert not result.is_valid
    assert any(issue.code == "price_too_low" for issue in result.issues)


def test_rent_price_per_sqm_too_high_invalid(validator: ListingValidator) -> None:
    """€111/m² rent on a small unit — far above ~€5/m² city median."""
    listing = NormalizedListingSchema(
        source_website="pro-rks",
        source_listing_id="rent-psm-high",
        original_url="https://example.com/rent-high",
        listing_type=ListingType.RENT,
        rent_price=Decimal("550"),
        area_sqm=5.0,
        price_per_sqm=Decimal("110.0"),
    )
    result = validator.validate(listing)
    assert not result.is_valid
    assert any(issue.code == "price_per_sqm_too_high" for issue in result.issues)


def test_rent_price_per_sqm_in_range_valid(validator: ListingValidator) -> None:
    listing = NormalizedListingSchema(
        source_website="merrjep",
        source_listing_id="rent-ok",
        original_url="https://example.com/rent-ok",
        listing_type=ListingType.RENT,
        rent_price=Decimal("350"),
        area_sqm=70.0,
        price_per_sqm=Decimal("5.0"),
    )
    result = validator.validate(listing)
    assert result.is_valid


def test_rent_total_over_8000_invalid(validator: ListingValidator) -> None:
    listing = NormalizedListingSchema(
        source_website="merrjep",
        source_listing_id="rent-high-total",
        original_url="https://example.com/rent-total",
        listing_type=ListingType.RENT,
        rent_price=Decimal("12000"),
        area_sqm=90.0,
        price_per_sqm=Decimal("133.33"),
    )
    result = validator.validate(listing)
    assert not result.is_valid
    assert any(issue.code == "price_too_high" for issue in result.issues)


def test_sale_price_per_sqm_under_500_invalid(validator: ListingValidator) -> None:
    """Rent-sized totals mislabeled as sale (e.g. €4,900 for 147 m² apartment)."""
    listing = NormalizedListingSchema(
        source_website="merrjep",
        source_listing_id="sale-psm",
        original_url="https://example.com/psm",
        listing_type=ListingType.SALE,
        sale_price=Decimal("4900"),
        area_sqm=147.0,
        price_per_sqm=Decimal("33.33"),
    )
    result = validator.validate(listing)
    assert not result.is_valid
    assert any(issue.code == "price_per_sqm_too_low" for issue in result.issues)


def test_sale_price_per_sqm_over_15000_invalid(validator: ListingValidator) -> None:
    listing = NormalizedListingSchema(
        source_website="merrjep",
        source_listing_id="sale-psm-high",
        original_url="https://example.com/high",
        listing_type=ListingType.SALE,
        sale_price=Decimal("2000000"),
        area_sqm=100.0,
        price_per_sqm=Decimal("20000"),
    )
    result = validator.validate(listing)
    assert not result.is_valid
    assert any(issue.code == "price_per_sqm_too_high" for issue in result.issues)


def test_conflicting_prices_invalid(validator: ListingValidator) -> None:
    listing = NormalizedListingSchema(
        source_website="gjirafa",
        source_listing_id="both-prices",
        original_url="https://example.com/both",
        listing_type=ListingType.SALE,
        sale_price=Decimal("100000"),
        rent_price=Decimal("500"),
        area_sqm=80.0,
        price_per_sqm=Decimal("1250"),
    )
    result = validator.validate(listing)
    assert not result.is_valid
    assert any(issue.code == "conflicting_prices" for issue in result.issues)


def test_price_per_sqm_inconsistent_invalid(validator: ListingValidator) -> None:
    listing = NormalizedListingSchema(
        source_website="merrjep",
        source_listing_id="inconsistent",
        original_url="https://example.com/inc",
        listing_type=ListingType.SALE,
        sale_price=Decimal("100000"),
        area_sqm=100.0,
        price_per_sqm=Decimal("500"),
    )
    result = validator.validate(listing)
    assert not result.is_valid
    assert any(issue.code == "price_per_sqm_inconsistent" for issue in result.issues)


def test_likely_rent_as_sale_invalid(validator: ListingValidator) -> None:
    listing = NormalizedListingSchema(
        source_website="merrjep",
        source_listing_id="rent-as-sale",
        original_url="https://example.com/ras",
        listing_type=ListingType.SALE,
        sale_price=Decimal("4500"),
        area_sqm=90.0,
        price_per_sqm=Decimal("50"),
    )
    result = validator.validate(listing)
    assert not result.is_valid
    assert any(issue.code == "likely_rent_as_sale" for issue in result.issues)


def test_house_missing_area_invalid(validator: ListingValidator) -> None:
    listing = NormalizedListingSchema(
        source_website="merrjep",
        source_listing_id="shtepi-3",
        original_url="https://example.com/4",
        listing_type=ListingType.RENT,
        property_type=PropertyType.HOUSE,
        rent_price=Decimal("400"),
        area_sqm=None,
    )
    result = validator.validate(listing)
    assert not result.is_valid
    assert any(issue.code == "house_area_missing" for issue in result.issues)
