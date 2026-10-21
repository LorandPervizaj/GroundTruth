"""Synthetic scoring cases; no live data or publisher rankings."""

from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from groundtruth.analytics.source_quality import assess_listing, build_report, proposed_weight
from groundtruth.analytics.source_quality_models import QualityPolicy, QualityRecord, Verification

AS_OF = datetime(2026, 10, 21, tzinfo=UTC)


def record(source="gjirafa", identity="1", **changes):
    listing = {
        "source_website": source,
        "source_listing_id": identity,
        "original_url": "https://example.invalid/property/1",
        "listing_type": "sale",
        "property_type": "apartment",
        "sale_price": "120000",
        "area_sqm": 80,
        "price_per_sqm": "1500",
        "city": "Prishtina",
        "neighborhood_id": 1,
        "street_id": 1,
        "building_id": 1,
        "bedrooms": 2,
        "listing_date": "2026-10-21",
    }
    listing.update(changes.pop("listing_changes", {}))
    data = dict(
        source_name=source,
        source_listing_id=identity,
        observation_id=int(identity),
        observed_at=AS_OF,
        outcome="accepted",
        listing=listing,
        publication_date_basis="source_declared",
    )
    data.update(changes)
    return QualityRecord.model_validate(data)


def assess(item):
    return assess_listing(item, as_of=AS_OF, policy=QualityPolicy())


def verification(kind="location", correct=True, origin="source", **kwargs):
    return Verification(
        evidence_id="synthetic-check",
        checked_at=AS_OF,
        kind=kind,
        correct=correct,
        origin=origin,
        **kwargs,
    )


def report(records, **kwargs):
    return build_report(records, sources=["gjirafa", "merrjep"], as_of=AS_OF, **kwargs)


def test_complete_listing_and_unknown_accuracy():
    item = assess(record())
    assert item.scores == dict(
        validity=100,
        completeness=100,
        location=None,
        consistency=100,
        freshness=100,
        historical_reliability=None,
    )
    assert item.location_precision_score == 100
    assert item.location_verification_status == "unknown"
    assert item.observed_criterion_coverage == 0.7
    assert item.quality_score == 85


def test_category_completeness_and_missing_fields():
    incomplete = assess(
        record(listing_changes=dict(sale_price=None, area_sqm=None, street_id=None))
    )
    assert incomplete.scores["completeness"] < 100
    assert incomplete.scores["validity"] == 0
    assert incomplete.scores["consistency"] is None
    assert (
        assess(record(listing_changes=dict(property_type="land", bedrooms=None))).scores[
            "completeness"
        ]
        == 100
    )
    assert (
        assess(record(listing_changes=dict(property_type="apartment", bedrooms=None))).scores[
            "completeness"
        ]
        < 100
    )


@pytest.mark.parametrize(
    "changes,code",
    [
        ({"sale_price": "-1"}, "price_too_low"),
        ({"area_sqm": -1}, "area_too_small"),
        ({"area_sqm": 1001}, "area_too_large"),
        ({"price_per_sqm": "5000"}, "price_per_sqm_inconsistent"),
        ({"rent_price": "500"}, "conflicting_prices"),
        ({"listing_type": None}, "missing_listing_type"),
        ({"property_type": None}, "missing_property_type"),
    ],
)
def test_invalid_values_use_validation_authority(changes, code):
    item = assess(record(listing_changes=changes))
    assert item.scores["validity"] == 0
    assert code in item.error_codes


def test_missing_information_is_not_a_contradiction():
    item = assess(record(listing_changes=dict(price_per_sqm=None)))
    assert item.scores["consistency"] is None


def test_freshness_separates_publication_and_crawl():
    assert assess(record(listing_changes=dict(listing_date="2025-01-01"))).scores["freshness"] == 0
    missing = assess(record(listing_changes=dict(listing_date=None, scraped_at=AS_OF)))
    assert missing.scores["freshness"] is None
    future = assess(record(listing_changes=dict(listing_date="2026-10-22")))
    assert future.scores["freshness"] == 0
    assert future.freshness_basis == "future_publication_date"


def test_verified_location_and_independent_history():
    item = assess(record(verification=[verification(), verification("historical")]))
    assert item.scores["location"] == 100
    assert item.scores["historical_reliability"] == 100
    assert item.quality_score == 100
    parser = assess(record(verification=[verification("historical", False, "parser")]))
    assert parser.scores["historical_reliability"] is None
    assert parser.error_origin == "parser"
    source = assess(record(verification=[verification("historical", False)]))
    assert source.scores["historical_reliability"] == 0
    assert source.error_origin == "source"


def test_future_verification_not_used():
    evidence = verification().model_copy(update={"checked_at": AS_OF + timedelta(days=1)})
    assert assess(record(verification=[evidence])).scores["location"] is None


def test_rejected_parser_and_validation_records_remain_in_denominator():
    records = [
        record(),
        record(
            identity="2",
            outcome="rejected",
            listing=None,
            failure_stage="parse",
            error_codes=["parse_error"],
        ),
        record(
            identity="3",
            outcome="rejected",
            failure_stage="validate",
            error_codes=["invalid_location"],
        ),
    ]
    summary = report(records).sources[0]
    assert summary.unique_source_listing_count == 3
    assert (summary.accepted_count, summary.rejected_count, summary.pending_count) == (1, 2, 0)
    assert summary.validity_score == pytest.approx(100 / 3, abs=1e-6)
    assert summary.criterion_sample_counts["completeness"] == 2
    assert summary.error_origin_counts["pipeline_failure_unattributed"] == 1


def test_latest_snapshot_and_windows_and_segmentation():
    old = record(observation_id=10, observed_at=AS_OF - timedelta(days=1))
    new = record(observation_id=11, outcome="rejected", error_codes=["invalid_location"])
    excluded = record(identity="2", observed_at=AS_OF - timedelta(days=31))
    future = record(identity="3", observed_at=AS_OF + timedelta(seconds=1))
    rent = record(
        identity="4",
        listing_changes=dict(
            listing_type="rent", sale_price=None, rent_price="800", price_per_sqm="10"
        ),
    )
    result = report([new, old, excluded, future, rent], segment=True)
    all_source = result.sources[0]
    assert all_source.records_examined == 3
    assert all_source.unique_source_listing_count == 2
    assert all_source.repeated_observation_count == 1
    assert all_source.rejected_count == 1
    assert result.sources[1].unique_source_listing_count == 1  # sale
    assert result.sources[2].unique_source_listing_count == 1  # rent


def test_zero_records_and_small_samples_are_neutral():
    summary, empty = report([record()]).sources
    assert summary.proposed_weight == empty.proposed_weight == 1
    assert empty.source_quality_score is None
    assert empty.score_status == "no_data"
    assert empty.validity_score is None
    assert "insufficient_sample" in summary.eligibility_reason


def test_conservative_eligibility_and_no_unknown_selection_bias():
    items = [record(identity=str(i)) for i in range(1, 31)]
    assert report(items).sources[0].proposed_weight == 1
    verified = [r.model_copy(update={"verification": [verification()]}) for r in items]
    summary = report(verified).sources[0]
    assert summary.observed_criterion_coverage == 0.95
    assert summary.weight_status == "eligible_recommendation"
    assert summary.proposed_weight == 1.25
    # Coverage uses all unique records, including failed/unmeasured rows.
    failed = record(identity="31", outcome="rejected", listing=None, failure_stage="parse")
    assert report([*verified, failed]).sources[0].observed_criterion_coverage < 0.95


@pytest.mark.parametrize(
    "score,expected", [(70, 1), (95, 1.25), (45, 0.75), (0, 0.75), (100, 1.25)]
)
def test_weight_formula(score, expected):
    assert proposed_weight(score, QualityPolicy()) == expected


def test_policy_weights_and_nonfinite_inputs():
    assert sum(QualityPolicy().weights.values()) == 1
    with pytest.raises(ValidationError):
        QualityPolicy(weights={"validity": 1})
    with pytest.raises(ValidationError):
        record(listing_changes=dict(area_sqm=float("nan")))


def test_new_source_has_no_reputation_dependency():
    result = build_report([record(source="future-portal")], sources=["future-portal"], as_of=AS_OF)
    assert (
        result.sources[0].source_quality_score == report([record()]).sources[0].source_quality_score
    )


def test_content_duplicates_are_separate_from_repeated_observations():
    items = [
        record(content_hash="same"),
        record(identity="2", content_hash="same"),
        record(source="merrjep", content_hash="same"),
    ]
    summaries = report(items).sources
    assert summaries[0].within_source_content_duplicate_count == 1
    assert summaries[0].repeated_observation_count == 0
    assert summaries[1].within_source_content_duplicate_count == 0
    assert summaries[0].cross_portal_duplicate_listing_count == 2
    assert summaries[0].cross_portal_comparable_count == 2
    assert summaries[1].cross_portal_duplicate_listing_count == 1


def test_freshness_update_and_observation_dates_are_distinct():
    item = assess(
        record(
            listing_changes=dict(listing_date=None),
            source_updated_at=AS_OF - timedelta(days=90),
            first_seen_at=AS_OF - timedelta(days=120),
            last_seen_at=AS_OF,
        )
    )
    assert item.scores["freshness"] == 50
    assert item.freshness_basis == "source_update"
    assert item.freshness_evidence["publication_date"] is None
    assert item.freshness_evidence["active_verified_at"] is None
    observation_only = assess(
        record(listing_changes=dict(listing_date=None), first_seen_at=AS_OF, last_seen_at=AS_OF)
    )
    assert observation_only.scores["freshness"] is None


def test_newly_registered_source_discovered_by_cli(monkeypatch, tmp_path):
    import json
    from dataclasses import replace

    from typer.testing import CliRunner

    from groundtruth.cli import app
    from groundtruth.portals import registry

    monkeypatch.setattr(
        registry, "PORTALS", (*registry.PORTALS, replace(registry.PORTALS[0], name="future-portal"))
    )
    fixture = tmp_path / "fixture.json"
    fixture.write_text(json.dumps([record(source="future-portal").model_dump(mode="json")]))
    result = CliRunner().invoke(
        app,
        [
            "analytics",
            "source-quality",
            "report",
            "--as-of",
            "2026-10-21",
            "--source",
            "future-portal",
            "--fixture",
            str(fixture),
            "--output",
            str(tmp_path / "out"),
        ],
    )
    assert result.exit_code == 0, result.output


def test_duplicate_observation_identity_rejected():
    with pytest.raises(ValueError, match="Duplicate observation"):
        report([record(), record()])
