"""Unit tests for duplicate scoring."""

from decimal import Decimal

from groundtruth.models.enums import Currency, ListingType
from groundtruth.processing.deduplicator.scoring import DuplicateScorer
from groundtruth.schemas.pipeline import NormalizedListingSchema


def _listing(**kwargs) -> NormalizedListingSchema:
    defaults = {
        "source_website": "test",
        "source_listing_id": "1",
        "original_url": "https://example.com/1",
        "listing_type": ListingType.SALE,
        "currency": Currency.EUR,
    }
    defaults.update(kwargs)
    return NormalizedListingSchema(**defaults)


class TestDuplicateScorer:
    def setup_method(self) -> None:
        self.scorer = DuplicateScorer(threshold=85.0)

    def test_identical_listings_high_confidence(self) -> None:
        a = _listing(
            sale_price=Decimal("92000"),
            area_sqm=65.0,
            bedrooms=2,
            neighborhood_id=1,
            description_cleaned="Banesa ne shitje te Dardania",
        )
        b = _listing(
            source_listing_id="2",
            original_url="https://example.com/2",
            sale_price=Decimal("92000"),
            area_sqm=65.0,
            bedrooms=2,
            neighborhood_id=1,
            description_cleaned="Banesa ne shitje te Dardania",
        )
        result = self.scorer.score(a, b, candidate_id=1, reference_id=2)
        assert result.confidence >= 85.0
        assert result.is_likely_duplicate

    def test_different_listings_low_confidence(self) -> None:
        a = _listing(sale_price=Decimal("50000"), area_sqm=40.0, bedrooms=1)
        b = _listing(
            source_listing_id="2",
            sale_price=Decimal("200000"),
            area_sqm=120.0,
            bedrooms=4,
        )
        result = self.scorer.score(a, b, candidate_id=1, reference_id=2)
        assert not result.is_likely_duplicate
