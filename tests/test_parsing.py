"""Tests for raw → parsed transformation."""

from types import SimpleNamespace

from groundtruth.models.enums import ListingType, PropertyType
from groundtruth.services.parsing import ParsingService


def _raw_listing(payload: dict) -> SimpleNamespace:
    return SimpleNamespace(
        id=1,
        scrape_run_id=1,
        source_website="gjirafa",
        source_listing_id=payload.get("source_listing_id", "banesa-123"),
        original_url=payload.get("original_url", "https://listime.gjirafa.com/Shpallje/Patundshmeri/banesa-123"),
        spider_version="1.0.0",
        raw_payload=payload,
    )


class TestGjirafaParsing:
    def setup_method(self) -> None:
        self.parser = ParsingService()

    def test_parses_rent_listing_from_payload(self) -> None:
        payload = {
            "source_listing_id": "banesa-49374",
            "title": "Banese me qira ne Emshir",
            "category": "Banesa",
            "listing_type": "rent",
            "listing_type_raw": "Qira",
            "price_raw": "300 EUR",
            "area_raw": "60",
            "bedrooms_raw": "2",
            "listing_date_raw": "08/06/2026 10:23",
            "city_raw": "Prishtine",
            "description": "Leshohet banese me qira ne Emshir, 2 dhoma gjumi",
            "image_urls": ["https://noah.gjirafa.com/mrj1/abc.png"],
        }
        parsed = self.parser.parse_raw(_raw_listing(payload))

        assert parsed.listing_type == ListingType.RENT
        assert parsed.property_type == PropertyType.APARTMENT
        assert parsed.rent_price is not None
        assert float(parsed.rent_price) == 300.0
        assert parsed.area_sqm == 60.0
        assert parsed.bedrooms == 2
        assert parsed.city == "Prishtina"
        assert parsed.neighborhood_raw == "Emshir"
        assert parsed.description_original is not None
