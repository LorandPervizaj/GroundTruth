"""Tests for confidence scoring."""

from decimal import Decimal

from groundtruth.models.enums import ListingType
from groundtruth.processing.confidence import ConfidenceFactors, ConfidenceScorer
from groundtruth.schemas.pipeline import NormalizedListingSchema, ParsedListingSchema


def test_high_confidence_valid_listing() -> None:
    scorer = ConfidenceScorer()
    parsed = ParsedListingSchema(
        source_website="gjirafa",
        source_listing_id="banesa-1",
        original_url="https://example.com/1",
        neighborhood_raw="Emshir",
        listing_type=ListingType.RENT,
    )
    normalized = NormalizedListingSchema(
        source_website="gjirafa",
        source_listing_id="banesa-1",
        original_url="https://example.com/1",
        listing_type=ListingType.RENT,
        rent_price=Decimal("300"),
        area_sqm=60.0,
        neighborhood_id=11,
        description_original="Banese me qira",
        geocode_precision="neighborhood",
        latitude=42.65,
        longitude=21.14,
    )
    result = scorer.score(
        normalized,
        parsed,
        factors=ConfidenceFactors(neighborhood_match_type="exact"),
        is_valid=True,
    )
    assert result.score >= 0.85


def test_low_confidence_invalid_listing() -> None:
    scorer = ConfidenceScorer()
    parsed = ParsedListingSchema(
        source_website="gjirafa",
        source_listing_id="banesa-2",
        original_url="https://example.com/2",
    )
    normalized = NormalizedListingSchema(
        source_website="gjirafa",
        source_listing_id="banesa-2",
        original_url="https://example.com/2",
        listing_type=ListingType.SALE,
        sale_price=Decimal("125"),
        area_sqm=52.0,
    )
    result = scorer.score(
        normalized,
        parsed,
        factors=ConfidenceFactors(),
        is_valid=False,
    )
    assert result.score < 0.70
