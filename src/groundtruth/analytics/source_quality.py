"""Read-only quality scoring; deliberately independent of corpus and dedup winners."""

from __future__ import annotations

import csv
import hashlib
import json
from collections import Counter, defaultdict
from datetime import UTC, datetime, timedelta
from pathlib import Path
from statistics import mean

import pandas as pd

from groundtruth.analytics.listing_fingerprint import coarse_block_key
from groundtruth.analytics.source_quality_models import (
    CRITERIA,
    ListingAssessment,
    QualityPolicy,
    QualityRecord,
    QualityReport,
    SourceAssessment,
)
from groundtruth.models.enums import PropertyType
from groundtruth.processing.deduplicator.scoring import DuplicateScorer
from groundtruth.processing.validation import ListingValidator

CONSISTENCY_CODES = frozenset(
    {"conflicting_prices", "price_per_sqm_inconsistent", "likely_rent_as_sale", "invalid_location"}
)


def utc(value: datetime) -> datetime:
    """SQLite/legacy naive database timestamps are interpreted as UTC."""
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def proposed_weight(score: float, policy: QualityPolicy) -> float:
    return round(min(policy.maximum_weight, max(policy.minimum_weight, 1 + (score - 70) / 100)), 4)


def assess_listing(
    record: QualityRecord, *, as_of: datetime, policy: QualityPolicy
) -> ListingAssessment:
    listing = record.listing
    scores: dict[str, float | None] = dict.fromkeys(CRITERIA)
    codes = set(record.error_codes)
    precision = None
    freshness_basis = "unknown_publication_date"
    evidence = [v for v in record.verification if utc(v.checked_at) <= utc(as_of)]
    location = [v for v in evidence if v.kind == "location" and v.origin == "source"]
    history = [v for v in evidence if v.kind == "historical" and v.origin == "source"]
    consistency = [v for v in evidence if v.kind == "consistency"]
    if record.outcome == "rejected":
        scores["validity"] = 0
    if listing is not None:
        validation = ListingValidator().validate(listing)
        codes.update(issue.code for issue in validation.issues)
        if listing.listing_type is None:
            codes.add("missing_listing_type")
        if listing.property_type is None:
            codes.add("missing_property_type")
        if record.outcome != "pending":
            scores["validity"] = 0 if codes or not validation.is_valid else 100
        # Presence is independent of correctness. Validity owns invalid values.
        fields = {
            "price": listing.sale_price if listing.listing_type == "sale" else listing.rent_price,
            "area": listing.area_sqm,
            "transaction": listing.listing_type,
            "property": listing.property_type,
            "municipality": listing.city,
            "neighborhood": listing.neighborhood_id,
            "street": listing.street_id,
            "publication": listing.listing_date
            if record.publication_date_basis == "source_declared"
            else None,
        }
        if listing.property_type in {
            PropertyType.APARTMENT,
            PropertyType.HOUSE,
            PropertyType.VILLA,
        }:
            fields["bedrooms"] = listing.bedrooms
        importance = {"price": 3, "area": 3, "transaction": 2, "property": 2, "municipality": 2}
        scores["completeness"] = (
            100
            * sum(importance.get(k, 1) for k, v in fields.items() if v is not None and v != "")
            / sum(importance.get(k, 1) for k in fields)
        )
        precision = 100 * sum(
            (
                0.2 if listing.city else 0,
                0.3 if listing.neighborhood_id else 0,
                0.3 if listing.street_id else 0,
                0.2 if listing.building_id else 0,
            )
        )
        checks = []
        if listing.sale_price is not None and listing.rent_price is not None:
            checks.append(False)
        if (
            listing.price_per_sqm is not None
            and listing.area_sqm is not None
            and listing.area_sqm > 0
            and (listing.sale_price is not None or listing.rent_price is not None)
        ):
            # The existing validator ignores nonpositive stored €/m² for this check.
            checks.append(listing.price_per_sqm > 0 and "price_per_sqm_inconsistent" not in codes)
        if listing.floor is not None and listing.total_floors is not None:
            checks.append(listing.floor <= listing.total_floors)
        # Price contradictions already counted above; each check contributes once.
        if codes & (CONSISTENCY_CODES - {"conflicting_prices", "price_per_sqm_inconsistent"}):
            checks.append(False)
        checks.extend(v.correct for v in consistency)
        if checks:
            scores["consistency"] = 100 * mean(checks)
        if listing.listing_date and record.publication_date_basis == "source_declared":
            age = (utc(as_of).date() - listing.listing_date).days
            scores["freshness"] = 0 if age < 0 else 100 * max(0, 1 - age / policy.freshness_days)
            freshness_basis = "future_publication_date" if age < 0 else "publication_date"
        elif listing.listing_date:
            freshness_basis = (
                "unverified_proxy_date"
                if record.publication_date_basis == "proxy"
                else "unknown_date_origin"
            )
    if scores["freshness"] is None and record.source_updated_at is not None:
        age = (utc(as_of) - utc(record.source_updated_at)).total_seconds() / 86400
        scores["freshness"] = 0 if age < 0 else 100 * max(0, 1 - age / policy.freshness_days)
        freshness_basis = "future_source_update" if age < 0 else "source_update"
    if location:
        scores["location"] = 100 * mean(v.correct for v in location)
    if history:
        scores["historical_reliability"] = 100 * mean(v.correct for v in history)
    coverage = sum(policy.weights[k] for k, v in scores.items() if v is not None)
    composite = sum(
        policy.weights[k] * (v if v is not None else policy.unknown_imputation)
        for k, v in scores.items()
    )
    origins = {v.origin for v in evidence if not v.correct}
    origin = "mixed" if len(origins) > 1 else next(iter(origins), "unattributed")
    if record.failure_stage in {"parse", "normalize"} and not origins:
        origin = "pipeline_failure_unattributed"
    return ListingAssessment(
        source_name=record.source_name,
        source_listing_id=record.source_listing_id,
        observation_id=record.observation_id,
        segment=str(listing.listing_type) if listing and listing.listing_type else "unknown",
        outcome=record.outcome,
        scores={k: round(v, 6) if v is not None else None for k, v in scores.items()},
        quality_score=round(composite, 6),
        observed_criterion_coverage=round(coverage, 6),
        location_precision_score=round(precision, 6) if precision is not None else None,
        location_verification_status="verified" if location else "unknown",
        freshness_basis=freshness_basis,
        freshness_evidence={
            "publication_date_basis": record.publication_date_basis,
            "publication_date": listing.listing_date.isoformat()
            if listing and listing.listing_date
            else None,
            "crawl_timestamp": utc(record.observed_at).isoformat(),
            **{
                name: utc(getattr(record, name)).isoformat() if getattr(record, name) else None
                for name in (
                    "source_updated_at",
                    "first_seen_at",
                    "last_seen_at",
                    "active_verified_at",
                )
            },
        },
        error_codes=sorted(codes),
        error_origin=origin,
    )


def duplicate_diagnostics(latest: dict, policy: QualityPolicy) -> tuple[set, set]:
    """Reuse candidate blocking/scoring only; never select a priority winner.

    These are probable structured matches, not independently verified duplicates.
    Descriptions are excluded, and duplicate diagnostics never alter quality scores.
    """
    blocks = defaultdict(list)
    comparable, matched = set(), set()
    scorer = DuplicateScorer(threshold=policy.duplicate_threshold)
    for key, record in latest.items():
        listing = record.listing
        if not listing or not listing.listing_type or not listing.area_sqm or listing.area_sqm <= 0:
            continue
        price = listing.rent_price if listing.listing_type == "rent" else listing.sale_price
        if price is None or price <= 0:
            continue
        block = coarse_block_key(pd.Series(listing.model_dump()))
        if block is not None:
            comparable.add(key)
            blocks[block].append(
                (
                    key,
                    listing.model_copy(
                        update={"description_cleaned": None, "description_original": None}
                    ),
                )
            )
    for candidates in blocks.values():
        for index, (key, listing) in enumerate(candidates):
            for other_key, other in candidates[index + 1 :]:
                if key[0] != other_key[0] and scorer.score(listing, other).is_likely_duplicate:
                    matched.update((key, other_key))
    return comparable, matched


def build_report(
    records: list[QualityRecord],
    *,
    sources: list[str],
    as_of: datetime,
    window_days: int = 30,
    segment: bool = False,
    policy: QualityPolicy | None = None,
) -> QualityReport:
    if window_days < 1:
        raise ValueError("window_days must be positive")
    policy = policy or QualityPolicy()
    as_of = utc(as_of)
    start = as_of - timedelta(days=window_days)
    selected = [
        r for r in records if r.source_name in sources and start <= utc(r.observed_at) <= as_of
    ]
    selected.sort(
        key=lambda r: (r.source_name, r.source_listing_id, utc(r.observed_at), r.observation_id)
    )
    keys = [(r.source_name, r.source_listing_id, r.observation_id) for r in selected]
    if len(keys) != len(set(keys)):
        raise ValueError("Duplicate observation identity in input")
    latest = {(r.source_name, r.source_listing_id): r for r in selected}
    comparable, cross_matches = duplicate_diagnostics(latest, policy)
    assessments = [assess_listing(r, as_of=as_of, policy=policy) for r in latest.values()]
    raw_counts = Counter((r.source_name, r.source_listing_id) for r in selected)
    summaries = []
    for source in sorted(set(sources)):
        source_items = [a for a in assessments if a.source_name == source]
        for label in ["all", "sale", "rent", "unknown"] if segment else ["all"]:
            items = [a for a in source_items if label == "all" or a.segment == label]
            n = len(items)
            samples = {k: sum(a.scores[k] is not None for a in items) for k in CRITERIA}
            values = {
                k: round(mean(a.scores[k] for a in items if a.scores[k] is not None), 6)
                if samples[k]
                else None
                for k in CRITERIA
            }
            coverage = mean(a.observed_criterion_coverage for a in items) if n else 0
            score = round(mean(a.quality_score for a in items), 6) if n else None
            reasons = []
            if n < policy.minimum_sample:
                reasons.append("insufficient_sample")
            if coverage + 1e-9 < policy.minimum_coverage:
                reasons.append("insufficient_measurement_coverage")
            if not n or samples["location"] / n < policy.minimum_location_verification:
                reasons.append("insufficient_independent_location_verification")
            pending = sum(a.outcome == "pending" for a in items)
            if not n or (n - pending) / n < policy.minimum_processed_fraction:
                reasons.append("insufficient_processing_coverage")
            hashes = Counter(
                latest[(source, a.source_listing_id)].content_hash
                for a in items
                if latest[(source, a.source_listing_id)].content_hash
            )
            summaries.append(
                SourceAssessment(
                    source_name=source,
                    segment=label,
                    records_examined=sum(raw_counts[(source, a.source_listing_id)] for a in items),
                    unique_source_listing_count=n,
                    accepted_count=sum(a.outcome == "accepted" for a in items),
                    rejected_count=sum(a.outcome == "rejected" for a in items),
                    pending_count=pending,
                    repeated_observation_count=sum(
                        raw_counts[(source, a.source_listing_id)] - 1 for a in items
                    ),
                    within_source_content_duplicate_count=sum(c - 1 for c in hashes.values()),
                    cross_portal_duplicate_listing_count=sum(
                        (source, a.source_listing_id) in cross_matches for a in items
                    ),
                    cross_portal_comparable_count=sum(
                        (source, a.source_listing_id) in comparable for a in items
                    ),
                    **{f"{k}_score": v for k, v in values.items()},
                    location_precision_score=round(
                        mean(
                            a.location_precision_score
                            for a in items
                            if a.location_precision_score is not None
                        ),
                        6,
                    )
                    if any(a.location_precision_score is not None for a in items)
                    else None,
                    location_verification_status="unknown"
                    if not samples["location"]
                    else "verified"
                    if samples["location"] == n
                    else "partial",
                    unknown_criteria=[k for k in CRITERIA if samples[k] < n or not n],
                    criterion_sample_counts=samples,
                    observed_criterion_coverage=round(coverage, 6),
                    source_quality_score=score,
                    score_status="no_data"
                    if not n
                    else "provisional"
                    if coverage < 1
                    else "measured",
                    proposed_weight=1 if reasons else proposed_weight(score, policy),
                    weight_status="insufficient_evidence" if reasons else "eligible_recommendation",
                    eligibility_reason=reasons,
                    error_code_counts=dict(
                        sorted(Counter(c for a in items for c in a.error_codes).items())
                    ),
                    error_origin_counts=dict(
                        sorted(
                            Counter(
                                a.error_origin
                                for a in items
                                if a.error_codes or a.outcome == "rejected"
                            ).items()
                        )
                    ),
                )
            )
    # Canonical input hashing identifies the exact scoring snapshot without exporting payloads.
    canonical = json.dumps(
        [r.model_dump(mode="json") for r in selected], sort_keys=True, allow_nan=False
    )
    return QualityReport(
        scoring_policy_version=policy.version,
        generated_at=as_of,
        evaluation_as_of=as_of,
        evaluation_window={"start": start, "end": as_of},
        input_fingerprint=hashlib.sha256(canonical.encode()).hexdigest(),
        scoring_policy=policy,
        sources=summaries,
        listings=assessments,
    )


def write_report(report: QualityReport, output: Path) -> None:
    output.mkdir(parents=True, exist_ok=True)
    (output / "source_quality_report.json").write_text(
        json.dumps(report.model_dump(mode="json"), sort_keys=True, indent=2, allow_nan=False)
        + "\n",
        encoding="utf-8",
    )
    with (output / "source_quality_summary.csv").open("w", encoding="utf-8", newline="") as stream:
        fields = list(SourceAssessment.model_fields)
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for source in report.sources:
            row = source.model_dump(mode="json")
            writer.writerow(
                {
                    k: json.dumps(v, sort_keys=True) if isinstance(v, (list, dict)) else v
                    for k, v in row.items()
                }
            )
    (output / "source_quality_report.schema.json").write_text(
        json.dumps(QualityReport.model_json_schema(), sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
