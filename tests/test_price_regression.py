"""Regression tests for price extraction bugs found at scale."""

from decimal import Decimal
from types import SimpleNamespace

from groundtruth.models.enums import ListingType
from groundtruth.services.parsing import ParsingService


def _raw(payload: dict) -> SimpleNamespace:
    return SimpleNamespace(
        id=1,
        scrape_run_id=1,
        source_website="gjirafa",
        source_listing_id=payload.get("source_listing_id", "banesa-test"),
        original_url="https://listime.gjirafa.com/Shpallje/Patundshmeri/banesa-test",
        spider_version="1.0.0",
        raw_payload=payload,
    )


class TestPriceRegression:
    def setup_method(self) -> None:
        self.parser = ParsingService()

    def test_comma_thousands_sale_price(self) -> None:
        """Gjirafa uses 125,000 EUR — must not parse as 125.00."""
        payload = {
            "source_listing_id": "banesa-91141",
            "title": "Shitet Banesa ne Ulpian",
            "listing_type": "sale",
            "listing_type_raw": "Shitet",
            "price_raw": "125,000 EUR",
            "area_raw": "52",
            "description": "Cmimi: 125000 euro",
        }
        parsed = self.parser.parse_raw(_raw(payload))
        assert parsed.listing_type == ListingType.SALE
        assert parsed.sale_price == Decimal("125000.00")
        assert parsed.rent_price is None

    def test_european_dot_thousands(self) -> None:
        payload = {
            "listing_type": "sale",
            "price_raw": "90.000 EUR",
            "area_raw": "65",
        }
        parsed = self.parser.parse_raw(_raw(payload))
        assert parsed.sale_price == Decimal("90000.00")

    def test_sale_shorthand_thousands_fixup(self) -> None:
        """Gjirafa sale prices like 1,300 EUR often mean 130,000 EUR."""
        payload = {
            "listing_type": "sale",
            "listing_type_raw": "Shitet",
            "price_raw": "1,300 EUR",
            "area_raw": "65",
            "description": "Shitet banesa ne Lagje te Spitalit, siperfaqe: 65m2.",
        }
        parsed = self.parser.parse_raw(_raw(payload))
        assert parsed.sale_price == Decimal("130000.00")

    def test_placeholder_one_eur_falls_back_to_description(self) -> None:
        """Gjirafa sometimes shows 1 EUR — real price lives in description."""
        payload = {
            "listing_type": "rent",
            "listing_type_raw": "Qira",
            "price_raw": "1 EUR",
            "area_raw": "55",
            "description": "Leshohet banesa me qira. Cmimi 350 euro.",
        }
        parsed = self.parser.parse_raw(_raw(payload))
        assert parsed.rent_price == Decimal("350.00")
