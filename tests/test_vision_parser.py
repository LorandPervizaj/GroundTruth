"""Tests for Vision Real Estate parser."""

from groundtruth.models.enums import ListingType, PropertyType
from groundtruth.processing.parsers.vision import is_prishtina_district, parse_wp_property
from groundtruth.services.vision_parsing import VisionParsingService

SAMPLE_SALE = {
    "id": 999,
    "slug": "banese-test-prishtine",
    "link": "https://visionrealestateks.com/property/banese-test-prishtine/",
    "date": "2026-04-01T10:00:00",
    "title": {"rendered": "Banesë 61.63m² për shitje në Fushë Kosovë."},
    "content": {"rendered": "<p>Test description.</p>"},
    "property-statuses": [28],
    "property-types": [118],
    "class_list": ["property-type-banesa", "property-status-for-sale"],
    "property_meta": {
        "REAL_HOMES_property_price": "43141",
        "REAL_HOMES_property_size": "61.63",
        "REAL_HOMES_property_bedrooms": "1",
        "REAL_HOMES_property_bathrooms": "1",
        "REAL_HOMES_property_address": (
            "Nene Tereza, Fushë Kosovë, Municipality of Fushë Kosovë / Kosovo Polje, "
            "District of Prishtina, 10012, Kosovo"
        ),
        "REAL_HOMES_property_location": {
            "latitude": "42.63",
            "longitude": "21.17",
        },
    },
}

SAMPLE_RENT = {
    **SAMPLE_SALE,
    "id": 1000,
    "slug": "banese-rent-tophane",
    "property-statuses": [27],
    "class_list": ["property-type-banesa", "property-status-for-rent"],
    "property_meta": {
        **SAMPLE_SALE["property_meta"],
        "REAL_HOMES_property_price": "300",
        "REAL_HOMES_property_size": "64",
    },
}


def test_is_prishtina_district() -> None:
    assert is_prishtina_district(SAMPLE_SALE)
    outside = {
        "property_meta": {
            "REAL_HOMES_property_address": "Tirana, Albania",
        }
    }
    assert not is_prishtina_district(outside)


def test_parse_wp_property_sale() -> None:
    parsed = parse_wp_property(SAMPLE_SALE, prishtina_only=True)
    assert parsed is not None
    assert parsed["listing_type"] == "sale"
    assert parsed["sale_price"] == 43141.0
    assert parsed["area_sqm"] == 61.63


def test_parse_wp_property_rent() -> None:
    parsed = parse_wp_property(SAMPLE_RENT, prishtina_only=True)
    assert parsed is not None
    assert parsed["listing_type"] == "rent"
    assert parsed["rent_price"] == 300.0


def test_vision_parsing_service_sale_schema() -> None:
    schema = VisionParsingService().parse_payload(
        {"property": SAMPLE_SALE},
        url=SAMPLE_SALE["link"],
    )
    assert schema is not None
    assert schema.source_website == "vision"
    assert schema.listing_type == ListingType.SALE
    assert schema.property_type == PropertyType.APARTMENT
    assert float(schema.sale_price) == 43141.0
    assert schema.listing_date is not None
    assert schema.extra_fields.get("latitude") == 42.63
