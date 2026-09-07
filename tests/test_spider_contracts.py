"""Per-source spider HTML/JSON contract tests — catch structural breakage early."""

from __future__ import annotations

import json
from pathlib import Path

from groundtruth.processing.parsers.gjirafa import parse_listing_html
from groundtruth.processing.parsers.merrjep import parse_listing_html as parse_merrjep_html
from groundtruth.processing.parsers.myrealestate import parse_myrealestate_property
from groundtruth.processing.parsers.pro_rks import parse_detail_payload
from groundtruth.processing.parsers.topia import parse_topia_property
from groundtruth.processing.parsers.vision import parse_wp_property

_FIXTURES = Path(__file__).resolve().parent / "fixtures"


def _text(*parts: str) -> str:
    return _FIXTURES.joinpath(*parts).read_text(encoding="utf-8")


def _json(*parts: str):
    return json.loads(_text(*parts))


GJIRAFA_FIXTURE = _text("gjirafa", "listing.html")
MERRJEP_FIXTURE = _text("merrjep", "listing.html")
PRO_RKS_FIXTURE = _json("pro_rks", "detail.json")
TOPIA_FIXTURE = _json("topia", "property.json")
VISION_FIXTURE = _json("vision", "property.json")
MYREALESTATE_FIXTURE = _json("myrealestate", "property.json")


class TestSpiderContracts:
    """Structural assumptions per source — independent of golden dataset."""

    def test_gjirafa_selectors_present(self) -> None:
        parsed = parse_listing_html(
            GJIRAFA_FIXTURE, "https://listime.gjirafa.com/Shpallje/Patundshmeri/test-1"
        )
        assert parsed.get("area_raw") is not None
        assert parsed.get("listing_type") == "rent"
        assert parsed.get("price_raw") is not None or parsed.get("bedrooms_raw") is not None

    def test_merrjep_ldjson_or_html_price(self) -> None:
        parsed = parse_merrjep_html(MERRJEP_FIXTURE, "https://www.merrjep.com/ad/test/1")
        assert parsed.get("has_ld_json") is True or parsed.get("price_html") is not None

    def test_pro_rks_payload_fields(self) -> None:
        parsed = parse_detail_payload(PRO_RKS_FIXTURE)
        assert parsed.get("surface_m2") == 78
        assert parsed.get("for_rent") is True

    def test_topia_payload_fields(self) -> None:
        parsed = parse_topia_property(TOPIA_FIXTURE, prishtina_only=True)
        assert parsed is not None
        assert parsed.get("listing_type") == "rent"
        assert parsed.get("area_sqm") == 70

    def test_vision_payload_fields(self) -> None:
        from groundtruth.scrapers.vision_api import DEFAULT_RESIDENTIAL_TYPE_SLUGS

        parsed = parse_wp_property(
            VISION_FIXTURE,
            allowed_types=DEFAULT_RESIDENTIAL_TYPE_SLUGS,
            prishtina_only=True,
        )
        assert parsed is not None
        assert parsed.get("area_sqm") is not None

    def test_myrealestate_payload_fields(self) -> None:
        parsed = parse_myrealestate_property(MYREALESTATE_FIXTURE, prishtina_only=True)
        assert parsed is not None
        assert parsed.get("listing_type") == "rent"
