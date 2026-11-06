"""Archived defect regressions through the actual isolated parse/normalize/validate path."""

import json
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest

from groundtruth.processing.validation import ListingValidator
from groundtruth.provenance.rules import PRICE_SALE_UNIT_TOTAL, PRICE_SALE_UNIT_UNRESOLVED
from groundtruth.services.normalization import NormalizationService
from groundtruth.services.parsing import ParsingService

CASES = json.loads(
    (Path(__file__).parent / "fixtures/unit_price_arithmetic.json").read_text(encoding="utf-8")
)["cases"]


@pytest.fixture(scope="module")
def pipeline():
    return ParsingService(), NormalizationService(), ListingValidator()


def run(pipeline, case, **overrides):
    payload = {
        "category": "Banesa",
        "city_raw": "Prishtina",
        "listing_type": "sale",
        "listing_type_raw": "Shitet",
        "title": "Shitet banesa",
        **{k: case[k] for k in ["price_raw", "area_raw", "description"]},
        **overrides,
    }
    raw = SimpleNamespace(
        id=case["raw_record_id"],
        scrape_run_id=1,
        source_website="gjirafa",
        source_listing_id=case["case"],
        original_url="https://example.test/property",
        spider_version="1.0.0",
        raw_payload=payload,
    )
    parser, normalizer, validator = pipeline
    parsed = parser.parse_raw(raw)
    normalized, _ = normalizer.normalize(parsed)
    return parsed, normalized, validator.validate(normalized)


@pytest.mark.parametrize("case", CASES, ids=lambda c: c["case"])
def test_archived_unit_price_total_through_pipeline(pipeline, case):
    parsed, normalized, validation = run(pipeline, case)
    assert parsed.sale_price == normalized.sale_price == Decimal(case["expected_total"])
    assert normalized.price_per_sqm == Decimal(case["expected_rate"])
    assert normalized.area_sqm == float(case["area_raw"])
    assert normalized.currency.value == "EUR"
    assert validation.is_valid
    assert parsed.extra_fields["provenance"]["sale_price"]["rule_id"] == PRICE_SALE_UNIT_TOTAL


@pytest.mark.parametrize("case", CASES, ids=lambda c: c["case"])
def test_each_case_without_defensible_area_is_quarantined(pipeline, case):
    # Counterfactual control: preserve the literal rate, remove all source area evidence.
    parsed, normalized, validation = run(
        pipeline,
        case,
        area_raw=None,
        description=f"Çmimi: {case['expected_rate']} €/m²",
    )
    assert parsed.sale_price is normalized.sale_price is None
    assert normalized.price_per_sqm is None
    assert not validation.is_valid
    assert "missing_price" in {i.code for i in validation.issues}
    assert parsed.extra_fields["provenance"]["sale_price"]["rule_id"] == PRICE_SALE_UNIT_UNRESOLVED


@pytest.mark.parametrize(
    "description",
    [
        "Banesa 80m² bruto, 70m² neto. Çmimi: 1300€/m²",
        "Banesa 80m². Çmimi: 1300€/m² ose 1400€/m²",
        "Banesa 90m². Çmimi: 1300€/m²",
        "Banesa rreth 80m². Çmimi: 1300€/m²",
        "Banesa 80-90m². Çmimi: 1300€/m²",
        "Banesa 80m². Çmimi: -1300€/m²",
    ],
)
def test_ambiguous_rate_or_area_cannot_fall_back_to_100x(pipeline, description):
    _, normalized, validation = run(pipeline, CASES[0], description=description)
    assert normalized.sale_price is None
    assert "missing_price" in {i.code for i in validation.issues}


def test_source_total_already_correct_not_multiplied_twice(pipeline):
    _, normalized, validation = run(pipeline, CASES[0], price_raw="104000 EUR")
    assert normalized.sale_price == Decimal("104000")
    assert validation.is_valid


def test_existing_total_not_overridden_by_a_different_unit_price_claim(pipeline):
    _, normalized, validation = run(pipeline, CASES[0], price_raw="120000 EUR")
    assert normalized.sale_price == Decimal("120000")
    assert validation.is_valid


def test_unrelated_material_unit_price_does_not_replace_sale_shorthand(pipeline):
    _, normalized, validation = run(
        pipeline, CASES[0], description="Banesa 80m²; keramika 40 euro m2. Çmimi: 1300 euro."
    )
    assert normalized.sale_price == Decimal("130000")
    assert validation.is_valid


def test_legacy_shorthand_without_unit_claim_is_unchanged(pipeline):
    _, normalized, validation = run(pipeline, CASES[0], description="Banesa me siperfaqe 80m2.")
    assert normalized.sale_price == Decimal("130000")
    assert validation.is_valid


def test_rental_path_is_unchanged(pipeline):
    parsed, normalized, _ = run(
        pipeline,
        CASES[0],
        listing_type="rent",
        listing_type_raw="Qira",
        title="Banesa me qira",
    )
    assert parsed.sale_price is normalized.sale_price is None
    assert normalized.rent_price == Decimal("1300")


def test_about_in_contact_boilerplate_does_not_make_area_approximate(pipeline):
    _, normalized, validation = run(
        pipeline,
        CASES[0],
        description=CASES[0]["description"] + " Per informata rreth kesaj banese.",
    )
    assert normalized.sale_price == Decimal("104000")
    assert validation.is_valid


def test_golden_missing_price_expectation_is_scored_not_dropped():
    from groundtruth.golden.evaluate import evaluate_golden_rows

    base = {
        "source_listing_id": "unit-test",
        "title": "Shitet banesa",
        "description": "Çmimi 1300 €/m²",
        "price_raw": "1300 EUR",
        "correct_type": "sale",
        "correct_price": "MISSING",
    }
    result = evaluate_golden_rows([base])
    assert result.total == 1 and result.price == 1
    result = evaluate_golden_rows([{**base, "description": "", "price_raw": "130000 EUR"}])
    assert result.total == 1 and result.price == 0
