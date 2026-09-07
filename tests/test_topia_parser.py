"""Tests for Topia Real Estate parser."""

from groundtruth.models.enums import ListingType, PropertyType
from groundtruth.processing.parsers.topia import is_prishtina, parse_topia_property
from groundtruth.services.topia_parsing import TopiaParsingService

SAMPLE_RENT = {
    "id": 10465,
    "name": "Banesë me 2 dhoma gjumi me qira në lagjen Lakrishtë",
    "slug": "banese-me-2-dhoma-gjumi-me-qira-ne-lagjen-lakrishte-t2768",
    "description": "Banesa ka sipërfaqe 90m2.",
    "reference": "T2768",
    "business_type": "rent",
    "type": "Apartment",
    "gross_area": "90",
    "bed_room": "2",
    "bath_room": "1",
    "floor": "8",
    "city": "Prishtina",
    "zone": ["Lakrishtë", "Pejton"],
    "price": "1250.00",
    "created_at": "2026-06-12T11:29:27.000000Z",
    "images": [{"url": "https://example.com/1.jpg", "type": "image"}],
}

SAMPLE_SALE = {
    **SAMPLE_RENT,
    "id": 10466,
    "reference": "T5324",
    "business_type": "sale",
    "price": "147500.00",
    "type": "Apartment",
}


def test_is_prishtina() -> None:
    assert is_prishtina(SAMPLE_RENT)
    assert not is_prishtina({**SAMPLE_RENT, "city": "Prizren"})


def test_parse_topia_rent() -> None:
    parsed = parse_topia_property(SAMPLE_RENT, prishtina_only=True)
    assert parsed is not None
    assert parsed["listing_type"] == "rent"
    assert parsed["rent_price"] == 1250.0
    assert parsed["area_sqm"] == 90.0
    assert parsed["bedrooms"] == 2


def test_parse_topia_sale() -> None:
    parsed = parse_topia_property(SAMPLE_SALE, prishtina_only=True)
    assert parsed is not None
    assert parsed["listing_type"] == "sale"
    assert parsed["sale_price"] == 147500.0


def test_topia_parsing_service_schema() -> None:
    schema = TopiaParsingService().parse_payload(
        {"property": SAMPLE_RENT},
        url="https://topia-ks.com/en/property/10465/test.html",
    )
    assert schema is not None
    assert schema.source_website == "topia"
    assert schema.source_listing_id == "T2768"
    assert schema.listing_type == ListingType.RENT
    assert schema.property_type == PropertyType.APARTMENT
    assert schema.neighborhood_raw == "Lakrishtë, Pejton"
