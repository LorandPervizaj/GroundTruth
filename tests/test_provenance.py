"""Tests for field-level provenance and decomposable confidence."""

from decimal import Decimal

from groundtruth.models.enums import ListingType
from groundtruth.processing.confidence import COMPONENT_WEIGHTS, ConfidenceFactors, ConfidenceScorer
from groundtruth.schemas.pipeline import NormalizedListingSchema, ParsedListingSchema
from groundtruth.services.parsing import ParsingService


def test_neighborhood_provenance_from_title() -> None:
    parser = ParsingService()
    raw_payload = {
        "title": "Banes me qira ne lagjen e Ulpiana",
        "description": "",
        "price_raw": "350 EUR",
        "listing_type": "rent",
        "category": "Banesa",
        "city_raw": "Prishtina",
    }
    from groundtruth.models.pipeline import RawListing

    raw = RawListing(
        id=1,
        scrape_run_id=1,
        spider_version="1.0",
        source_website="gjirafa",
        source_listing_id="test-ulpiana",
        original_url="https://example.com/test",
        raw_payload=raw_payload,
        scraped_at=None,
    )
    parsed = parser.parse_raw(raw)
    prov = parsed.extra_fields.get("provenance", {})
    assert "neighborhood_raw" in prov
    nh = prov["neighborhood_raw"]
    assert nh["rule_id"].startswith("NH-")
    assert "Ulpiana" in nh["value"]
    assert nh["source"] == "title"
    assert nh["confidence_contribution"] == 0.25


def test_decomposable_confidence_components() -> None:
    scorer = ConfidenceScorer()
    parsed = ParsedListingSchema(
        source_website="gjirafa",
        source_listing_id="banesa-1",
        original_url="https://example.com/1",
        neighborhood_raw="Ulpiana",
        listing_type=ListingType.RENT,
        extra_fields={
            "provenance": {
                "rent_price": {"confidence_contribution": 0.20},
                "neighborhood_raw": {"confidence_contribution": 0.25},
            }
        },
    )
    normalized = NormalizedListingSchema(
        source_website="gjirafa",
        source_listing_id="banesa-1",
        original_url="https://example.com/1",
        listing_type=ListingType.RENT,
        rent_price=Decimal("350"),
        area_sqm=60.0,
        neighborhood_id=11,
    )
    result = scorer.score(
        normalized,
        parsed,
        factors=ConfidenceFactors(neighborhood_match_type="exact"),
        is_valid=True,
    )
    assert "components" in result.details
    comps = result.details["components"]
    assert comps["price"] == 1.0
    assert comps["neighborhood"] == 1.0
    expected = round(sum(comps[k] * COMPONENT_WEIGHTS[k] for k in COMPONENT_WEIGHTS), 4)
    assert result.score == expected
