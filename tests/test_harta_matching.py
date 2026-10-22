"""Research matching cannot turn neighborhood collisions into apartment identity."""

import runpy
from copy import deepcopy
from datetime import UTC, datetime
from unittest.mock import MagicMock

import pytest

from groundtruth.analytics.harta_matching import (
    candidate_assessment,
    identity_verdict,
    matching_gate,
    street_key,
)


def listing(source="harta", **updates):
    return {
        "source_website": source,
        "listing_type": "sale",
        "sale_price": 100000,
        "rent_price": None,
        "street_raw": "Rruga A",
        "bedrooms": 2,
        "bathrooms": 1,
        "floor": 3,
        "area_sqm": None,
        "reported_surface_area": 80,
        "neighborhood_id": 1,
        "building_id": 10,
        "title": "Banese ne shitje",
        **updates,
    }


def reviews(n, verdict="verified_true"):
    return [
        {
            "harta_source_id": str(i),
            "other_source": "gjirafa",
            "other_source_id": str(i),
            "verdict": verdict,
        }
        for i in range(n)
    ]


def test_same_location_price_and_layout_never_verifies_apartment_identity():
    a, b = listing(), listing("gjirafa")
    before = deepcopy((a, b))
    result = candidate_assessment(a, b)
    assert result["signals"]["building_equal"] and result["signals"]["street_equal"]
    assert not result["signals"]["interior_area_near"]
    assert not result["verified_identity"]
    assert identity_verdict(corroborating_unit_fields=8) == "unresolved"
    assert (a, b) == before


@pytest.mark.parametrize("left,right", [("harta", "harta")])
def test_same_portal_and_cross_transaction_pairs_rejected(left, right):
    assert not candidate_assessment(listing(left), listing(right))["eligible"]
    assert not candidate_assessment(listing(), listing("gjirafa", listing_type="rent"))["eligible"]


def test_unit_specific_evidence_and_corroboration_required():
    assert identity_verdict(shared_unit_key=True, corroborating_unit_fields=1) == "unresolved"
    assert identity_verdict(shared_unit_key=True, corroborating_unit_fields=2) == "verified_true"
    assert (
        identity_verdict(shared_property_cross_reference=True, corroborating_unit_fields=2)
        == "verified_true"
    )
    assert identity_verdict(conflicting_unit_keys=True) == "verified_false"
    assert (
        identity_verdict(
            shared_unit_key=True, conflicting_unit_keys=True, corroborating_unit_fields=2
        )
        == "unresolved"
    )


def test_unresolved_is_not_zero_false_rate_or_hundred_percent_precision():
    gate = matching_gate(reviews(40, "unresolved"))
    assert gate["precision_among_resolved"] is None
    assert gate["unresolved"] == 40 and not gate["research_matching_support_enabled"]


def test_gate_is_bounded_and_requires_reliable_resolved_identity_evidence():
    for n in [0, 29, 51]:
        assert not matching_gate(reviews(n))["research_matching_support_enabled"]
    assert matching_gate(reviews(40))["research_matching_support_enabled"]
    rows = reviews(40)
    rows[0]["verdict"] = "verified_false"
    gate = matching_gate(rows)
    assert not gate["research_matching_support_enabled"]
    assert not gate["automatic_merge_enabled"] and not gate["field_transfer_enabled"]
    rows = reviews(40)
    rows[:3] = [{**r, "verdict": "unresolved"} for r in rows[:3]]
    assert not matching_gate(rows)["research_matching_support_enabled"]


def test_duplicate_pairs_and_unknown_verdicts_cannot_satisfy_gate():
    with pytest.raises(ValueError):
        matching_gate(reviews(1) * 40)
    with pytest.raises(ValueError):
        matching_gate(reviews(40, "unchecked"))
    rows = reviews(40)
    for row in rows:
        row["harta_source_id"] = "one-apartment"
    assert not matching_gate(rows)["research_matching_support_enabled"]


def test_six_source_calibration_query_explicitly_excludes_harta():
    mod = runpy.run_path("scripts/research/evaluate_source_quality.py")
    session = MagicMock()
    session.execute.return_value.mappings.return_value = []
    six = ["gjirafa", "merrjep", "pro-rks", "vision", "topia", "myrealestate"]
    assert mod["eligible_population"](session, datetime.now(UTC), six) == []
    assert session.execute.call_args.args[1]["sources"] == six
    assert "harta" not in session.execute.call_args.args[1]["sources"]


def test_city_labels_alone_cannot_supply_street_identity():
    assert street_key("Rruga, Prishtinë, Kosovë") == ""
