"""Tests for MerrJep measurement-first parser."""

import json
from types import SimpleNamespace

from groundtruth.processing.parsers.merrjep import parse_listing_html
from groundtruth.services.merrjep_parsing import MerrJepParsingService
from groundtruth.services.parsing import ParsingService

SAMPLE_PRODUCT = {
    "@type": "Product",
    "name": "Banese ne shitje",
    "description": ("Banesë në shitje në Ulpianë. Çmimi: €105,000. 44m² 📍 Ulpiana, Kosovë"),
    "offers": {"price": 0.0, "priceCurrency": "EUR"},
}

PUBLISHED_SNIPPET = """
<div class="ad-publish-info-area">
    <span class="ci-text-muted">Publikuar:</span>
    <bdi class="published-date">maj 16 2026</bdi>
    <bdi class="published-time">14:30</bdi>
</div>
"""

SAMPLE_HTML = (
    '<html><script type="application/ld+json">'
    + json.dumps(SAMPLE_PRODUCT)
    + f"</script>{PUBLISHED_SNIPPET}</html>"
)


class TestMerrJepParser:
    def test_parse_listing_html_ldjson(self) -> None:
        payload = parse_listing_html(
            SAMPLE_HTML,
            "https://www.merrjep.com/shpallja/banese-ne-shitje/15838177",
        )
        assert payload["has_ld_json"] is True
        assert payload["price_ldjson"] == 0.0
        assert payload["listing_type"] == "sale"
        assert payload["published_date"] == "2026-05-16"
        assert payload["published_date_raw"] == "maj 16 2026"
        assert payload["published_time_raw"] == "14:30"

    def test_price_fallback_from_description(self) -> None:
        parser = MerrJepParsingService()
        schema, prov = parser.parse_html(
            SAMPLE_HTML,
            "https://www.merrjep.com/shpallja/banese-ne-shitje/15838177",
        )
        assert schema.sale_price is not None
        assert abs(float(schema.sale_price) - 105000.0) < 1.0
        assert prov["sale_price"]["rule_id"] in ("MJ-PRICE-004", "MJ-PRICE-002")

    def test_price_per_sqm_times_area(self) -> None:
        product = {
            "@type": "Product",
            "name": "Banes ne shitje",
            "description": (
                "Banesa posedon 89.7m² kati 6. Qmimi per m2: 1,250 EUR. Garazh: 15,000 EUR."
            ),
            "offers": {"price": 0.0, "priceCurrency": "EUR"},
        }
        html = (
            '<html><script type="application/ld+json">' + json.dumps(product) + "</script></html>"
        )
        parser = MerrJepParsingService()
        schema, prov = parser.parse_html(
            html,
            "https://www.merrjep.com/shpallja/x/15882961",
        )
        assert schema.sale_price is not None
        assert abs(float(schema.sale_price) - 112125.0) < 1.0
        assert prov["sale_price"]["rule_id"] == "MJ-PRICE-005"

    def test_neighborhood_gazetteer_first(self) -> None:
        parser = MerrJepParsingService()
        schema, prov = parser.parse_html(
            SAMPLE_HTML,
            "https://www.merrjep.com/shpallja/banese-ne-shitje/15838177",
        )
        assert schema.neighborhood_raw is not None
        assert prov["neighborhood_raw"]["rule_id"] == "MJ-NH-001"

    def test_parsing_service_routes_merrjep(self) -> None:
        payload = parse_listing_html(
            SAMPLE_HTML,
            "https://www.merrjep.com/shpallja/banese-ne-shitje/15838177",
        )
        raw = SimpleNamespace(
            id=42,
            scrape_run_id=7,
            source_website="merrjep",
            source_listing_id="15838177",
            original_url="https://www.merrjep.com/shpallja/banese-ne-shitje/15838177",
            spider_version="0.2.0",
            raw_payload=payload,
        )
        parsed = ParsingService().parse_raw(raw)
        assert parsed.source_website == "merrjep"
        assert parsed.parser_version == "0.1.1-merrjep"
        assert parsed.spider_version == "0.2.0"
        assert parsed.sale_price is not None
        assert parsed.listing_date is not None
        assert str(parsed.listing_date) == "2026-05-16"
        assert parsed.extra_fields.get("provenance")

    def test_price_from_html_format_money_int(self) -> None:
        product = {
            "@type": "Product",
            "name": "Banes me qera",
            "description": "Banes me qira ne Pejton. Kontaktoni per cmim.",
            "offers": {"price": 0.0, "priceCurrency": "EUR"},
        }
        html = (
            '<html><script type="application/ld+json">'
            + json.dumps(product)
            + '</script><span class="new-price">'
            '<bdi class="format-money-int" value="450"></bdi><span>EUR</span>'
            "</span></html>"
        )
        parser = MerrJepParsingService()
        schema, prov = parser.parse_html(
            html,
            "https://www.merrjep.com/shpallja/banes-me-qera/15745411",
        )
        assert schema.rent_price is not None
        assert float(schema.rent_price) == 450.0
        assert prov["rent_price"]["rule_id"] == "MJ-PRICE-006"

    def test_bedroom_dhoma_is_apartment_not_room(self) -> None:
        parser = MerrJepParsingService()
        schema, _ = parser.parse_payload(
            {
                "title": "Banes 2+1 me qera ne PEJTON",
                "description": "Sallon + kuzhine, 2 dhoma gjumi, kati 11 me lift",
                "listing_type": "rent",
            },
            url="https://www.merrjep.com/shpallja/x/1",
        )
        assert schema.property_type.value == "apartment"

    def test_garsoniere_is_studio(self) -> None:
        parser = MerrJepParsingService()
        schema, _ = parser.parse_payload(
            {
                "title": "Garsoniere me qera",
                "description": "Garsoniere e mobiluar ne qender",
                "listing_type": "rent",
            },
            url="https://www.merrjep.com/shpallja/x/2",
        )
        assert schema.property_type.value == "studio"
