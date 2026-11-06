"""Area concepts and evidence purposes must not weaken valuation quarantine."""

from copy import deepcopy

import pytest

from groundtruth.analytics.harta_evidence import classify_harta_evidence
from groundtruth.scrapers.harta_area import extract_area_facts
from groundtruth.scrapers.harta_contract import minimized_property
from groundtruth.services.normalization import NormalizationService
from tests.test_harta import parse, prop


@pytest.mark.parametrize(
    "text,expected",
    [
        ("50m² neto | 65m² bruto", [("net", "50"), ("gross", "65")]),
        (
            "Sipërfaqe neto prej 96 m² dhe sipërfaqe faktike prej 130 m²",
            [("net", "96"), ("reported_actual", "130")],
        ),
        ("Sipërfaqe: 66m² (neto)", [("net", "66")]),
        ("125m² hapësirë banimi + 94m² terasë", [("interior", "125"), ("terrace", "94")]),
        ("Sipërfaqja: 80m²", [("unspecified", "80")]),
        ("Prishtinë.118m²", [("unspecified", "118")]),
        ("Gross area 90 sqm; Interior 75 sqm", [("gross", "90"), ("interior", "75")]),
        ("Neto 55,5 m2 | bruto 65 m2", [("net", "55,5"), ("gross", "65")]),
        ("Telefon +38344123456; çmimi 120000 EUR", []),
    ],
)
def test_explicit_area_labels_and_clause_boundaries(text, expected):
    assert [(f["concept"], f["value_raw"]) for f in extract_area_facts(text)] == expected


@pytest.mark.parametrize(
    "text",
    [
        "Sipërfaqja: 80m²",
        "80m² bruto",
        "Terasë 80m²",
        "Garazh 80m² neto",
        "Neto -80m²",
        "Neto 70–80m²",
        "Neto ~80m²",
        "Neto 80m² garazh",
        "Jo neto 80m²",
        "Nuk është neto 80m²",
        "Rreth 80m² neto",
    ],
)
def test_noninterior_measurements_never_fill_valuation_area(text):
    p = parse(prop(living_area=None, surface_area=80, description=text))
    normalized, _ = NormalizationService().normalize(p)
    assert p.area_sqm is None and normalized.area_sqm is None
    assert normalized.price_per_sqm is None
    assert "harta_missing_interior_area" in p.extra_fields["source_validation_issues"]
    assert not classify_harta_evidence(p, validation_error_codes=[])["valuation_eligible"]


def test_explicit_net_and_gross_remain_separate_with_provenance():
    p = parse(prop(living_area=None, surface_area=50, description="50m² neto | 65m² bruto"))
    assert p.area_sqm == 50
    assert p.extra_fields["gross_area_raw"] == "65"
    assert p.extra_fields["surface_area_basis"] == "net"
    assert p.extra_fields["area_basis"] == "description_explicit_net_or_interior"
    evidence = classify_harta_evidence(p, validation_error_codes=[])
    assert evidence["valuation_eligible"]
    assert evidence["gross_area_research"]["candidate"]
    assert not evidence["gross_area_research"]["validated_for_pooled_statistics"]


def test_structured_interior_conflicts_and_multiple_net_claims_stay_quarantined():
    for p in [
        parse(prop(description="75m² neto", living_area=80)),
        parse(prop(description="75m² neto | 80m² neto", living_area=None)),
    ]:
        assert "harta_conflicting_interior_area" in p.extra_fields["source_validation_issues"]
        assert not classify_harta_evidence(p, validation_error_codes=[])["valuation_eligible"]


def test_location_fields_survive_missing_area_without_changing_validation():
    source = prop(
        living_area=None,
        address=None,
        features={
            "street": "Rruga A",
            "neighborhood": "Bregu i Diellit",
            "locality": "Prishtinë",
            "owner_phone": "+38344123456",
            "promotion": "private",
        },
    )
    minimal = minimized_property(source)
    assert "owner_phone" not in str(minimal) and "promotion" not in str(minimal)
    parsed = parse(minimal)
    assert parsed.street_raw == "Rruga A" and parsed.neighborhood_raw == "Bregu i Diellit"
    evidence = classify_harta_evidence(
        parsed, validation_error_codes=["harta_missing_interior_area"]
    )
    assert evidence["use_class"] == "location_evidence_only"
    assert evidence["location_matching_candidate"] and not evidence["valuation_eligible"]
    assert evidence["location_verification_status"] == "unverified_source_assertion"
    assert evidence["location_provenance"]["street_origin"] == "property.features.street"


def test_validation_is_required_and_gross_projection_cannot_mutate_parsed_data():
    p = parse(prop(description="90m² bruto"))
    before = deepcopy(p)
    assert not classify_harta_evidence(p)["valuation_eligible"]
    evidence = classify_harta_evidence(p, validation_error_codes=["price_too_low"])
    assert not evidence["valuation_eligible"]
    assert not evidence["gross_area_research"]["candidate"]
    assert p == before


def test_unqualified_conflicting_measurement_is_not_silently_ignored():
    parsed = parse(prop(description="Sipërfaqja: 99 m²"))
    assert "harta_description_area_conflict" in parsed.extra_fields["source_validation_issues"]
