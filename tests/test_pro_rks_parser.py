"""Tests for Pro Real Estate API parser."""

from groundtruth.models.enums import ListingType, PropertyType
from groundtruth.processing.parsers.pro_rks import parse_detail_payload, strip_html
from groundtruth.services.pro_rks_parsing import ProRksParsingService

SAMPLE_PROPERTY = {
    "id": "uuid-1",
    "slug": "15982",
    "title_en": "82m2 Apartment for #SALE in Prishtina e Re",
    "description": "<p>Modern apartment with parking.</p>",
    "forSale": True,
    "forRent": False,
    "category": ["apartment"],
    "sellPrice": 114800,
    "surfaceM2": 82,
    "numberOfBedRooms": 2,
    "numberOfBathRooms": 1,
    "floor": 7,
    "numberOfFloors": 12,
    "furnishing": ["livingRoom", "kitchen", "bathroom"],
    "heatingSystem": ["keds"],
    "garage": False,
    "latitude": "42.63655695",
    "longitude": "21.16360476",
    "city": {"name": "Prishtinë"},
    "street": {"title": "Prishtina e Re"},
    "complex": {"name": "Prishtina Green Hill"},
    "builder": {"name": "NIC & Albioni"},
    "images": [
        {
            "lg": {"url": "media/2026-06/sample-lg.png"},
            "original": {"url": "media/2026-06/sample-original.png"},
            "createdAt": "2026-06-10T09:15:00.000Z",
        }
    ],
}

SAMPLE_AGENT = {
    "fullName": "Agent Name",
    "email": "agent@pro-rks.com",
    "phone": "+38344123456",
}


def test_strip_html() -> None:
    assert strip_html("<p>Hello <b>world</b></p>") == "Hello world"


def test_parse_apartment_sale_detail() -> None:
    payload = {
        "property": SAMPLE_PROPERTY,
        "agent": SAMPLE_AGENT,
        "listing_type_hint": "sale",
    }
    service = ProRksParsingService()
    schema = service.parse_payload(
        payload,
        url="https://www.pro-rks.com/en/shpalljet/15982",
    )

    assert schema.source_website == "pro-rks"
    assert schema.listing_type == ListingType.SALE
    assert schema.property_type == PropertyType.APARTMENT
    assert float(schema.sale_price) == 114800.0
    assert schema.area_sqm == 82.0
    assert schema.bedrooms == 2
    assert schema.bathrooms == 1
    assert schema.floor == 7
    assert schema.total_floors == 12
    assert schema.is_furnished is True
    assert schema.image_urls
    assert schema.extra_fields.get("latitude") == "42.63655695"
    assert schema.extra_fields.get("agent") == {"fullName": "Agent Name"}
    assert schema.listing_date is not None
    assert schema.listing_date.isoformat() == "2026-06-10"


def test_emshir_listing_location_hints_from_title_and_address() -> None:
    payload = {
        "property": {
            "slug": "10861",
            "title_en": "63.8m² Apartment for #SALE in Emshir.",
            "description_en": (
                "Apartments for sale in Emshir on Ali Vitija street. flooring installed by Ontex."
            ),
            "forSale": True,
            "category": ["apartment"],
            "sellPrice": 102080,
            "surfaceM2": 63.8,
            "numberOfBedRooms": 1,
            "address": "Kalabri - Emshir, Prishtinë",
            "street": {"title": "Ali Vitija"},
            "city": {"name": "Prishtinë"},
        },
        "listing_type_hint": "sale",
    }
    schema = ProRksParsingService().parse_payload(
        payload,
        url="https://www.pro-rks.com/en/property/10861",
    )
    assert "Emshir" in (schema.neighborhood_raw or "")
    assert "Ontex" not in (schema.neighborhood_raw or "")


def test_land_category_in_payload() -> None:
    normalized = parse_detail_payload(
        {
            "property": {
                "slug": "16006",
                "category": ["land"],
                "forSale": True,
                "surfaceM2": 1300,
            }
        },
        listing_type_hint="sale",
    )
    assert normalized["categories"] == ["land"]
