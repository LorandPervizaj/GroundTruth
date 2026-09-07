"""Tests for bedroom extraction and sanitization."""

from groundtruth.models.pipeline import RawListing
from groundtruth.processing.extractors.bedrooms import extract_bedrooms_from_text, sanitize_bedrooms
from groundtruth.services.merrjep_parsing import MerrJepParsingService
from groundtruth.services.parsing import ParsingService


def test_plus_one_format() -> None:
    assert extract_bedrooms_from_text("Banes 2+1 me qera ne Pejton") == 2
    assert extract_bedrooms_from_text("3 + 1 ne shitje") == 3


def test_dhoma_format() -> None:
    assert extract_bedrooms_from_text("Sallon + kuzhine, 2 dhoma gjumi") == 2


def test_albanian_word_bedroom_counts() -> None:
    assert extract_bedrooms_from_text("posedon dy dhoma gjumi sallon me kuzhin") == 2
    assert extract_bedrooms_from_text("Tri dhoma gjumi | dy ballkona") == 3
    assert extract_bedrooms_from_text("dy dhoma te gjumit, sallon") == 2


def test_singular_dhoma_gjumi_is_one() -> None:
    assert extract_bedrooms_from_text("Sallon* Kuzhinë* Koridor* Dhoma gjumi* Banjo") == 1
    assert extract_bedrooms_from_text("Nje dhome gjumi me banjo") == 1


def test_attached_plus_one_format() -> None:
    assert extract_bedrooms_from_text("Banese me qira Pejton_2+1") == 2
    assert extract_bedrooms_from_text("banes (3+1) me qera") == 3


def test_title_priority_over_description() -> None:
    assert extract_bedrooms_from_text("Banes 2+1 me qera", "Tri dhoma gjumi") == 2


def test_garsoniere_is_zero() -> None:
    assert extract_bedrooms_from_text("Garsoniere me qera") == 0
    assert extract_bedrooms_from_text("Studio me qira ne qender") == 0


def test_living_room_not_counted() -> None:
    assert extract_bedrooms_from_text("Dhome e ndejese me kuzhin | Tri dhoma gjumi") == 3
    assert extract_bedrooms_from_text("dhoma e dites dhe kuzhina") == 0


def test_dhoma_e_gjumit_and_typos() -> None:
    assert extract_bedrooms_from_text("Qendrimi ditore me kuzhin,-Dhoma e gjumit") == 1
    assert extract_bedrooms_from_text("Dy Dhoma t Gjumit (Dyshek C") == 2
    assert extract_bedrooms_from_text("92 m2 | Dy dhoma glumi") == 2
    assert extract_bedrooms_from_text("63 m2 | Nje dhoma glum") == 1


def test_structure_list_one_dhome() -> None:
    assert extract_bedrooms_from_text("Sallon | Kuzhine | Dhome | Banjo | Koridor") == 1


def test_english_bedroom_count() -> None:
    assert extract_bedrooms_from_text("Modern 2 bedroom apartment") == 2
    assert extract_bedrooms_from_text("one bed flat for rent") == 1


def test_gasoniere_typos_are_studio() -> None:
    assert extract_bedrooms_from_text("Banes Gasoniere me qera") == 0
    assert extract_bedrooms_from_text("Gasonjerk me qera ne Ulpiana") == 0
    assert extract_bedrooms_from_text("Gasonjere me qera ne Kolovic") == 0


def test_living_room_only_is_studio() -> None:
    assert extract_bedrooms_from_text("Dhome e ndejes lidhet me kuzhin | Banjo") == 0


def test_sallon_kuzhin_implies_one_bedroom() -> None:
    assert extract_bedrooms_from_text("Sallon + kuzhinë, koridor, banjo") == 1


def test_dhoma_field_metadata() -> None:
    assert extract_bedrooms_from_text("Lloji i Pronës: Banesë- Dhoma: 2- Banjo: 1") == 2
    assert extract_bedrooms_from_text("Dhoma: 1? Banjo: 1? Kati: 7") == 1
    assert extract_bedrooms_from_text("Dhoma: 2.5? Banjo: 1") == 2


def test_dhomen_endenjes_is_studio() -> None:
    assert extract_bedrooms_from_text("Dhomen e ndenjes me kuzhine|Banjo|Korridor") == 0


def test_merrjep_dhomshe_and_fjetje_variants() -> None:
    assert extract_bedrooms_from_text("banesa eshte dydhomshe e mobiluar") == 2
    assert extract_bedrooms_from_text("banesa eshte tridhomshe e mobiluar") == 3
    assert extract_bedrooms_from_text("dy dhoma te fjetjes, dhome dite me kuzhine") == 2
    assert extract_bedrooms_from_text("|Dy dhoma |Kuzhinen|Banjo") == 2
    assert extract_bedrooms_from_text("DyDhoma gjumi||Banjo") == 2
    assert extract_bedrooms_from_text("Dhom gjumiKoridor1 Banjo") == 1
    assert extract_bedrooms_from_text("Dhoma gjumi - 3Dhom") == 3


def test_sanitize_rejects_area_price_confusion() -> None:
    assert sanitize_bedrooms(55, area_sqm=55.0) is None
    assert sanitize_bedrooms(320, price=320.0) is None
    assert sanitize_bedrooms(11) is None
    assert sanitize_bedrooms(2, area_sqm=78.0) == 2


def test_merrjep_extracts_bedrooms_from_title() -> None:
    parser = MerrJepParsingService()
    schema, prov = parser.parse_payload(
        {
            "title": "Banes 2+1 me qera ne PEJTON",
            "description": "Sallon + kuzhine, 2 dhoma gjumi, kati 11 me lift",
            "listing_type": "rent",
        },
        url="https://www.merrjep.com/shpallja/x/1",
    )
    assert schema.bedrooms == 2
    assert prov["bedrooms"]["rule_id"] == "MJ-BED-001"


def test_gjirafa_sanitizes_bad_bedrooms_raw() -> None:
    service = ParsingService()
    raw = RawListing(
        id=1,
        scrape_run_id=1,
        spider_version="1.0.0",
        source_website="gjirafa",
        source_listing_id="banesa-55494",
        original_url="https://listime.gjirafa.com/Shpallje/Patundshmeri/banesa-55494",
        raw_payload={
            "source_listing_id": "banesa-55494",
            "title": "Banes me qira",
            "category": "Banesa",
            "listing_type": "rent",
            "listing_type_raw": "Qira",
            "price_raw": "300 EUR",
            "area_raw": "55",
            "bedrooms_raw": "55",
            "description": "Banes me qira",
        },
        raw_html=None,
    )
    parsed = service.parse_raw(raw)
    assert parsed.bedrooms is None
