"""Tests for property type classification and text-based refinement."""

from groundtruth.models.enums import PropertyType
from groundtruth.processing.extractors.property_type import (
    classify_property_type,
    refine_property_type,
)
from groundtruth.services.merrjep_parsing import MerrJepParsingService


def test_title_banes_beats_description_shtepi() -> None:
    assert (
        classify_property_type(
            "Ofrojm Banesen me Qera ne Aktash",
            "Shtepi e mobiluar me qira",
        )
        == PropertyType.APARTMENT
    )


def test_kat_shtepie_is_apartment() -> None:
    assert classify_property_type("Kat Shtepie 80m2 me qira", None) == PropertyType.APARTMENT


def test_shtepi_without_banes_is_house() -> None:
    assert classify_property_type("Shtepi me qera ne Fush Kosove", None) == PropertyType.HOUSE


def test_small_house_stays_house_after_refine() -> None:
    assert (
        refine_property_type(
            PropertyType.HOUSE,
            "Shtepi me qera ne Fush Kosove",
            "70m2 me oborr",
            70.0,
        )
        == PropertyType.HOUSE
    )


def test_villa_not_downgraded_by_area() -> None:
    assert (
        refine_property_type(
            PropertyType.VILLA,
            "Vila me qera",
            "100m2",
            100.0,
        )
        == PropertyType.VILLA
    )


def test_merrjep_banesa_listing_not_house() -> None:
    parser = MerrJepParsingService()
    schema, _ = parser.parse_payload(
        {
            "title": "Leshohet banesa me qera ne lagjen Aktash",
            "description": "Banesa 80m2, 2 dhoma gjumi",
            "listing_type": "rent",
        },
        url="https://www.merrjep.com/shpallja/x/1",
    )
    assert schema.property_type == PropertyType.APARTMENT
    assert schema.area_sqm == 80.0
