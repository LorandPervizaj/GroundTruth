"""Part 2 reporting and attribution safeguards on isolated synthetic records."""

import json
from copy import deepcopy
from datetime import timedelta

import pytest

from groundtruth.analytics.source_quality_audit import compare_snapshot, number, source_facts
from groundtruth.analytics.source_quality_evaluation import (
    audit_sample,
    field_diagnostics,
    selection_simulation,
    sensitivity,
)
from tests.test_source_quality import AS_OF, record, report


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("120.000 EUR", 120000),
        ("80,5 m²", 80.5),
        ("80", 80),
        (None, None),
        ("unknown", None),
        (float("inf"), None),
        ("1,200.50", None),
    ],
)
def test_conservative_source_number_review(raw, expected):
    assert number(raw) == expected


def test_source_comparison_distinguishes_parser_normalizer_and_unknown():
    r = record()
    raw = {
        "source_listing_id": "1",
        "listing_type": "sale",
        "price_raw": "120000 EUR",
        "area_raw": "80",
        "description": "Private source text must never enter an audit output",
    }
    parsed = r.listing.model_dump(mode="json")
    normalized = deepcopy(parsed)
    parsed["sale_price"] = None
    normalized["area_sqm"] = 81
    result = compare_snapshot(
        record=r, stratum="random", payload=raw, html=None, parsed=parsed, normalized=normalized
    )
    assert result["checks"]["price"]["status"] == "parser_missing"
    assert result["checks"]["area_sqm"]["status"] == "normalizer_disagreement_requires_review"
    assert result["checks"]["property_type"]["status"] == "unverified"
    assert "Private source text" not in json.dumps(result)
    assert "120000" not in json.dumps(result)
    assert "UNVERIFIED" in result["property_location_accuracy"]


def test_pending_record_not_counted_as_parser_bug():
    r = record(outcome="pending", listing=None)
    result = compare_snapshot(
        record=r,
        stratum="failure_enriched",
        payload={"price_raw": "120000"},
        html=None,
        parsed=None,
        normalized=None,
    )
    assert result["checks"]["price"]["status"] == "pipeline_unprocessed"


@pytest.mark.parametrize(
    "value,expected", [("145k EUR", 145000), ("80 m2", 80), ("120 EUR/m2", None), ("80 90", None)]
)
def test_review_does_not_confuse_suffixes_or_units(value, expected):
    assert number(value) == expected


def test_independent_html_price_and_ambiguous_areas():
    facts = source_facts(
        "merrjep",
        {"description": "80 m² apartment, 90 m² gross"},
        '<script type="application/ld+json">{"offers":{"price":120000}}</script>',
    )
    assert facts["price"]["value"] == 120000
    assert facts["area_sqm"]["value"] is None
    assert (
        source_facts("myrealestate", {}, '<div class="price_area">100,000 EUR</div>')["price"][
            "value"
        ]
        == 100000
    )


def test_stratified_sample_deterministic_unique_and_bounded():
    records = [
        record(
            source=s, identity=str(i), listing_changes={"listing_type": "sale" if i % 2 else "rent"}
        )
        for s in ("gjirafa", "merrjep")
        for i in range(1, 41)
    ]
    one = audit_sample(records)
    two = audit_sample(list(reversed(records)))

    def keys(rows):
        return [(s, r.source_name, r.source_listing_id) for s, r in rows]

    assert keys(one) == keys(two)
    assert len(one) == 60
    assert len({(r.source_name, r.source_listing_id) for _, r in one}) == 60
    assert len([s for s, _ in one if s == "random_segment_stratum"]) == 30


def test_postgresql_enum_names_select_correct_rental_price():
    r = record(listing_changes={"listing_type": "rent", "sale_price": None, "rent_price": "800"})
    raw = {"listing_type": "rent", "price_raw": "800 EUR"}
    data = r.listing.model_dump(mode="json")
    data["listing_type"] = "RENT"
    result = compare_snapshot(
        record=r, stratum="random", payload=raw, html=None, parsed=data, normalized=data
    )
    assert result["checks"]["price"]["status"] == "agrees_with_stored_source"


def test_missing_fields_have_structured_denominators():
    rows = [
        record(listing_changes={"area_sqm": None}),
        record(identity="2", outcome="rejected", failure_stage="parse", listing=None),
    ]
    data = field_diagnostics(rows, report(rows))["gjirafa"]
    assert data["unique_listings"] == 2
    assert data["missing_fields"]["area_sqm"] == dict(
        missing_count=1, observed_denominator=1, missing_rate=1, unavailable_extraction_count=1
    )
    assert "UNKNOWN" in data["duplication"]["unique_property_contribution"]


def test_proxy_dates_do_not_claim_publication_freshness_or_completeness():
    from groundtruth.analytics.source_quality import assess_listing
    from groundtruth.analytics.source_quality_models import QualityPolicy

    r = record(publication_date_basis="proxy")
    assessed = assess_listing(r, as_of=AS_OF, policy=QualityPolicy())
    assert assessed.scores["freshness"] is None
    assert assessed.freshness_basis == "unverified_proxy_date"
    assert assessed.scores["completeness"] < 100
    diagnostic = field_diagnostics([r], report([r]))["gjirafa"]
    assert diagnostic["freshness"]["proxy_date_count"] == 1
    assert diagnostic["freshness"]["publication_date_count"] == 0


def test_sensitivity_is_bounded_and_does_not_change_policy():
    r = report(
        [record(), record(source="merrjep", listing_changes={"area_sqm": None})], segment=True
    )
    before = r.model_dump_json()
    data = sensitivity(r)
    assert len(data["scenarios"]) == 15
    assert data["minimum_measured_validity_subset"] == []
    assert all(
        0 <= score <= 100 for scenario in data["scenarios"] for score in scenario["scores"].values()
    )
    assert before == r.model_dump_json()


def test_offline_winner_change_same_eligible_records_no_input_mutation():
    rows = [
        record(listing_changes={"street_id": None, "building_id": None}),
        record(source="merrjep"),
    ]
    r = report(rows, segment=True)
    before = [x.model_dump_json() for x in rows]
    result = selection_simulation(
        rows, r, eligible_keys={(x.source_name, x.source_listing_id) for x in rows}
    )
    assert result["groups_evaluated"] == 1
    assert result["groups_with_changed_winner"] == 1
    assert result["current"]["source_counts"] == {"gjirafa": 1}
    assert result["proposed"]["source_counts"] == {"merrjep": 1}
    assert result["proposed"]["mean_completeness"] > result["current"]["mean_completeness"]
    assert result["current"]["invalid_winners"] == result["proposed"]["invalid_winners"] == 0
    assert before == [x.model_dump_json() for x in rows]


def test_latest_version_preserves_failure_and_excludes_unselected_ids():
    rows = [
        record(observed_at=AS_OF - timedelta(days=1)),
        record(observation_id=100, outcome="rejected", failure_stage="parse", listing=None),
        record(source="merrjep"),
    ]
    r = report(rows)
    result = selection_simulation(rows, r, eligible_keys={("gjirafa", "1")})
    assert result["status"] == "no_eligible_records"


def test_research_runner_refuses_nonlocal_or_production_database(tmp_path):
    from scripts.research.evaluate_source_quality import research_url

    path = tmp_path / "research.env"
    path.write_text(
        "DATABASE_URL=postgresql+psycopg://user:password@production.example:5432/product\n"
    )
    with pytest.raises(ValueError, match="Refusing"):
        research_url(path)
    path.write_text("DATABASE_URL=postgresql+psycopg://user:password@localhost:15432/rema\n")
    assert "localhost:15432" in research_url(path)
