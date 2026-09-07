"""Tests for MY Real Estate parser."""

from groundtruth.models.enums import ListingType, PropertyType
from groundtruth.processing.parsers.myrealestate import (
    is_prishtina,
    parse_myrealestate_property,
    parse_price_from_html,
)
from groundtruth.services.myrealestate_parsing import MyRealEstateParsingService

SAMPLE_RENT = {
    "id": 24569,
    "slug": "banese-me-2-dhoma-gjumi-me-qira-ne-lagjen-mati-1-3",
    "link": "https://myrealestate-ks.com/properties/banese-me-2-dhoma-gjumi-me-qira-ne-lagjen-mati-1-3/",
    "date": "2026-05-27T14:06:17",
    "title": {"rendered": "Banesë me 2 dhoma gjumi me qira në lagjen Mati 1"},
    "content": {
        "rendered": "<p>Ofrohet me qira banesë moderne me sipërfaqe prej 83.4m².</p>",
    },
    "class_list": [
        "property_category-qira",
        "property_action_category-banes",
        "property_city-prishitne",
        "property_area-mati-1",
    ],
}

DETAIL_HTML = (
    '<div class="price_area">€ 400 <span class="price_label"></span></div>'
    '<img src="https://myrealestate-ks.com/wp-content/uploads/2026/05/sample.jpg" />'
)


def test_parse_price_from_html() -> None:
    assert parse_price_from_html(DETAIL_HTML) == 400.0
    assert parse_price_from_html('<div class="price_area">€ 155.000 </div>') == 155000.0


def test_extracts_image_urls_from_html() -> None:
    parsed = parse_myrealestate_property(SAMPLE_RENT, detail_html=DETAIL_HTML)
    assert parsed is not None
    assert parsed["image_urls"] == [
        "https://myrealestate-ks.com/wp-content/uploads/2026/05/sample.jpg"
    ]


def test_is_prishtina() -> None:
    assert is_prishtina(SAMPLE_RENT)
    outside = {**SAMPLE_RENT, "class_list": ["property_city-prizren"]}
    assert not is_prishtina(outside)


def test_parse_myrealestate_rent() -> None:
    parsed = parse_myrealestate_property(SAMPLE_RENT, detail_html=DETAIL_HTML)
    assert parsed is not None
    assert parsed["listing_type"] == "rent"
    assert parsed["rent_price"] == 400.0
    assert parsed["area_sqm"] == 83.4
    assert parsed["bedrooms"] == 2
    assert parsed["neighborhood"] == "Mati 1"


def test_myrealestate_parsing_service_schema() -> None:
    schema = MyRealEstateParsingService().parse_payload(
        {"property": SAMPLE_RENT},
        url=SAMPLE_RENT["link"],
        raw_html=DETAIL_HTML,
    )
    assert schema is not None
    assert schema.source_website == "myrealestate"
    assert schema.listing_type == ListingType.RENT
    assert schema.property_type == PropertyType.APARTMENT
    assert schema.rent_price == 400
