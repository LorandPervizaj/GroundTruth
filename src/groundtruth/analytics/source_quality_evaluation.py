"""Part 2 diagnostics and offline selection experiments. No pipeline writes."""

from __future__ import annotations

import hashlib
from collections import Counter
from statistics import mean, median

import pandas as pd

from groundtruth.analytics.cross_dedup import apply_cross_dedupe
from groundtruth.analytics.source_quality_models import (
    CRITERIA,
    QualityRecord,
    QualityReport,
)


def latest_records(records: list[QualityRecord]) -> list[QualityRecord]:
    ordered = sorted(
        records, key=lambda r: (r.source_name, r.source_listing_id, r.observed_at, r.observation_id)
    )
    return list({(r.source_name, r.source_listing_id): r for r in ordered}.values())


def field_diagnostics(records: list[QualityRecord], report: QualityReport) -> dict:
    """Every missingness rate states its actual observable denominator."""
    records = latest_records(records)
    assessments = {(a.source_name, a.source_listing_id): a for a in report.listings}
    result = {}
    for summary in report.sources:
        if summary.segment != "all":
            continue
        source = summary.source_name
        rows = [r for r in records if r.source_name == source]
        structured = [r.listing for r in rows if r.listing]
        n = len(rows)
        fields = {}
        for field in (
            "price",
            "area_sqm",
            "bedrooms",
            "city",
            "neighborhood_id",
            "street_id",
            "listing_date",
            "listing_type",
            "property_type",
        ):
            applicable = [
                x
                for x in structured
                if field != "bedrooms" or x.property_type in {"apartment", "house", "villa"}
            ]
            missing = sum(
                (x.rent_price if x.listing_type == "rent" else x.sale_price) is None
                if field == "price"
                else getattr(x, field) in (None, "")
                for x in applicable
            )
            fields[field] = {
                "missing_count": missing,
                "observed_denominator": len(applicable),
                "missing_rate": round(missing / len(applicable), 6) if applicable else None,
                "unavailable_extraction_count": n - len(structured),
            }
            if field == "listing_date":
                missing = sum(
                    r.listing.listing_date is None or r.publication_date_basis != "source_declared"
                    for r in rows
                    if r.listing
                )
                fields[field].update(
                    missing_count=missing,
                    missing_rate=round(missing / len(applicable), 6) if applicable else None,
                )
        ages = [
            (report.evaluation_as_of.date() - r.listing.listing_date).days
            for r in rows
            if r.listing
            and r.listing.listing_date
            and r.publication_date_basis == "source_declared"
        ]
        attrs = [assessments[(r.source_name, r.source_listing_id)] for r in rows]
        failures = {}
        for category, codes in {
            "invalid_price": {
                "price_too_low",
                "price_too_high",
                "price_per_sqm_too_low",
                "price_per_sqm_too_high",
            },
            "invalid_area": {"area_too_small", "area_too_large", "house_area_too_small"},
            "invalid_or_missing_classification": {
                "likely_rent_as_sale",
                "missing_listing_type",
                "missing_property_type",
            },
            "price_area_contradiction": {"price_per_sqm_inconsistent"},
            "conflicting_prices": {"conflicting_prices"},
            "geographic_conflict": {"invalid_location"},
        }.items():
            count = sum(bool(set(a.error_codes) & codes) for a in attrs)
            failures[category] = {
                "count": count,
                "denominator_unique_listings": n,
                "rate": round(count / n, 6) if n else None,
                "unavailable_extraction_count": n - len(structured),
            }
        parser_failed = sum(r.failure_stage == "parse" for r in rows)
        parser_ok = sum(r.listing is not None and r.failure_stage != "parse" for r in rows)
        classified = Counter(str(x.property_type) for x in structured)
        result[source] = {
            "population": "latest_raw_identity_all_outcomes",
            "unique_listings": n,
            "structured_listings": len(structured),
            "outcomes": dict(Counter(r.outcome for r in rows)),
            "validity": {
                "valid_count": sum(a.scores["validity"] == 100 for a in attrs),
                "measured_denominator": summary.criterion_sample_counts["validity"],
                "unknown_count": n - summary.criterion_sample_counts["validity"],
                "rejected_rate": round(summary.rejected_count / n, 6) if n else None,
            },
            "missing_fields": fields,
            "failure_frequencies": failures,
            "parser_attempts": {
                "observed_success_count": parser_ok,
                "observed_failure_count": parser_failed,
                "observed_attempt_denominator": parser_ok + parser_failed,
                "success_rate": round(parser_ok / (parser_ok + parser_failed), 6)
                if parser_ok + parser_failed
                else None,
                "unobserved_attempt_or_filtered_count": n - parser_ok - parser_failed,
                "caveat": "Pending/age-filtered records do not prove a parser failure",
            },
            "error_code_counts": summary.error_code_counts,
            "failure_stage_counts": dict(Counter(r.failure_stage for r in rows if r.failure_stage)),
            "error_attribution": "Pipeline diagnostics; publisher origin unverified without independent review",
            "location": {
                "neighborhoods_covered": len(
                    {x.neighborhood_id for x in structured if x.neighborhood_id}
                ),
                "municipality_text_count": sum(bool(x.city) for x in structured),
                "coordinate_precision_counts": dict(
                    Counter(x.geocode_precision or "unknown" for x in structured)
                ),
                "coordinates_present_count": sum(
                    x.latitude is not None and x.longitude is not None for x in structured
                ),
                "independently_verified_count": summary.criterion_sample_counts["location"],
                "unverified_denominator": n,
            },
            "freshness": {
                "publication_date_count": len(ages),
                "unknown_age_count": n - len(ages),
                "proxy_date_count": sum(
                    r.listing is not None
                    and r.listing.listing_date is not None
                    and r.publication_date_basis == "proxy"
                    for r in rows
                ),
                "median_age_days": median(ages) if ages else None,
                "minimum_age_days": min(ages) if ages else None,
                "maximum_age_days": max(ages) if ages else None,
                "stale_over_180_days": sum(a > 180 for a in ages),
                "future_dates": sum(a < 0 for a in ages),
                "first_seen_count": sum(r.first_seen_at is not None for r in rows),
                "last_seen_count": sum(r.last_seen_at is not None for r in rows),
            },
            "property_type_counts": dict(sorted(classified.items())),
            "transaction_counts": dict(
                Counter(str(x.listing_type or "unknown") for x in structured)
            ),
            "duplication": {
                "within_source_exact_content_excess": summary.within_source_content_duplicate_count,
                "within_source_denominator": n,
                "cross_source_probable_matches": summary.cross_portal_duplicate_listing_count,
                "cross_source_comparable_denominator": summary.cross_portal_comparable_count,
                "nonmatched_comparable_count": summary.cross_portal_comparable_count
                - summary.cross_portal_duplicate_listing_count,
                "unique_property_contribution": "UNKNOWN: incomplete candidate matching cannot prove unique properties",
            },
        }
    return result


def audit_sample(
    records: list[QualityRecord], *, seed: str = "gate2-2026-10-21", per_source: int = 30
) -> list[tuple[str, QualityRecord]]:
    """Separate reproducible probability and failure-enriched strata."""
    latest = latest_records(records)
    selected = []
    for source in sorted({r.source_name for r in latest}):
        rows = [r for r in latest if r.source_name == source]
        rows.sort(
            key=lambda r: hashlib.sha256(
                f"{seed}:{source}:{r.source_listing_id}".encode()
            ).hexdigest()
        )
        random_target = per_source // 2
        random = []
        for segment in ("sale", "rent"):
            random.extend(
                [r for r in rows if r.listing and r.listing.listing_type == segment][
                    : random_target // 2
                ]
            )
        random_ids = {r.source_listing_id for r in random}
        random.extend(
            [r for r in rows if r.source_listing_id not in random_ids][
                : random_target - len(random)
            ]
        )
        ids = {r.source_listing_id for r in random}
        rest = [r for r in rows if r.source_listing_id not in ids]
        failures = [
            r
            for r in rest
            if r.outcome != "accepted"
            or not r.listing
            or r.listing.neighborhood_id is None
            or r.listing.area_sqm is None
            or (r.listing.sale_price is None and r.listing.rent_price is None)
        ]
        enriched = failures[: per_source - len(random)]
        ids.update(r.source_listing_id for r in enriched)
        extra = [r for r in rest if r.source_listing_id not in ids][
            : per_source - len(random) - len(enriched)
        ]
        selected.extend(("random_segment_stratum", r) for r in random)
        selected.extend(("failure_enriched", r) for r in enriched)
        selected.extend(("random_top_up", r) for r in extra)
    return selected


def sensitivity(report: QualityReport) -> dict:
    """Perturb assumptions, never fit them to a preferred source order."""
    base = report.scoring_policy
    scenarios = [("baseline", base.weights, base.unknown_imputation)]
    for criterion in CRITERIA:
        for factor in (0.9, 1.1):
            weights = {k: v * (factor if k == criterion else 1) for k, v in base.weights.items()}
            total = sum(weights.values())
            scenarios.append(
                (
                    f"{criterion}_x{factor}",
                    {k: v / total for k, v in weights.items()},
                    base.unknown_imputation,
                )
            )
    scenarios.extend((f"unknown_{value}", base.weights, value) for value in (40, 60))
    outputs = []
    for name, weights, unknown in scenarios:
        values = {}
        for source in sorted({a.source_name for a in report.listings}):
            items = [a for a in report.listings if a.source_name == source]
            values[source] = round(
                mean(
                    sum(
                        weights[k] * (a.scores[k] if a.scores[k] is not None else unknown)
                        for k in CRITERIA
                    )
                    for a in items
                ),
                6,
            )
        outputs.append(
            {
                "scenario": name,
                "scores": values,
                "order": sorted(values, key=lambda s: (-values[s], s)),
            }
        )
    ranks = {s: [row["order"].index(s) + 1 for row in outputs] for s in outputs[0]["order"]}
    return {
        "interpretation": "Provisional pipeline-usability score ordering, not verified publisher reputation",
        "scenarios": outputs,
        "rank_ranges": {
            s: {"minimum": min(v), "maximum": max(v), "unstable": max(v) - min(v) > 1}
            for s, v in ranks.items()
        },
        "minimum_sample_subset": [
            s.source_name
            for s in report.sources
            if s.segment == "all" and s.unique_source_listing_count >= base.minimum_sample
        ],
        "minimum_measured_validity_subset": [
            source
            for source in outputs[0]["order"]
            if any(
                s.source_name == source
                and s.segment == "all"
                and s.criterion_sample_counts["validity"] >= base.minimum_sample
                for s in report.sources
            )
        ],
        "segment_orders": {
            segment: [
                s.source_name
                for s in sorted(
                    (
                        s
                        for s in report.sources
                        if s.segment == segment and s.source_quality_score is not None
                    ),
                    key=lambda s: (-s.source_quality_score, s.source_name),
                )
            ]
            for segment in ("sale", "rent")
        },
    }


def selection_simulation(
    records: list[QualityRecord],
    report: QualityReport,
    *,
    eligible_keys: set[tuple[str, str]],
    normalized_ids: dict[int, int] | None = None,
) -> dict:
    """Compare representatives on exactly the same eligible records and groups."""
    assessments = {(a.source_name, a.source_listing_id): a for a in report.listings}
    weights = {(s.source_name, s.segment): s.proposed_weight for s in report.sources}
    candidates = []
    for r in latest_records(records):
        key = (r.source_name, r.source_listing_id)
        if (
            key not in eligible_keys
            or not r.listing
            or r.listing.property_type not in {"apartment", "studio"}
        ):
            continue
        a = assessments[key]
        if a.scores["validity"] != 100 or r.outcome != "accepted":
            continue
        x = r.listing
        if not x.listing_type or not x.area_sqm or x.area_sqm <= 0:
            continue
        row = x.model_dump()
        # Preserve the existing matcher representation without exporting any descriptions.
        row.update(
            normalized_id=(normalized_ids or {}).get(r.observation_id, r.observation_id),
            property_type=str(x.property_type).upper(),
            listing_type=str(x.listing_type),
            confidence_score=x.confidence_score or 0,
        )
        row.update(
            quality=a.quality_score,
            freshness=a.scores["freshness"],
            completeness=a.scores["completeness"],
            precision=a.location_precision_score or 0,
            candidate_weight=weights.get(
                (r.source_name, a.segment), weights[(r.source_name, "all")]
            ),
        )
        candidates.append(row)
    if not candidates:
        return {"status": "no_eligible_records", "groups_evaluated": 0}
    tagged = apply_cross_dedupe(
        pd.DataFrame(candidates), threshold=report.scoring_policy.duplicate_threshold
    )
    current, proposed, changed, conflicts, duplicate_groups = [], [], 0, 0, 0
    for _, group in tagged.groupby("canonical_group_id", sort=True):
        original = group[group.is_canonical_primary].iloc[0]
        ordered = group.sort_values(
            [
                "quality",
                "candidate_weight",
                "completeness",
                "precision",
                "source_website",
                "source_listing_id",
                "normalized_id",
            ],
            ascending=[False, False, False, False, True, True, False],
            kind="stable",
        )
        # Listing usability has priority; uncalibrated source weights are only a tie-break.
        best = ordered.iloc[0]
        current.append(original)
        proposed.append(best)
        if len(group) > 1:
            duplicate_groups += 1
            changed += int(original.name != best.name)
            conflicts += int(
                group.candidate_weight.idxmax() != group.quality.idxmax()
                and group.candidate_weight.nunique() > 1
            )

    def metrics(rows):
        frame = pd.DataFrame(rows)
        sales = frame[(frame.listing_type == "sale") & (frame.property_type == "APARTMENT")]
        rentals = frame[(frame.listing_type == "rent") & (frame.property_type == "APARTMENT")]

        def psm_median(items):
            values = [
                float(x.sale_price if x.listing_type == "sale" else x.rent_price)
                / float(x.area_sqm)
                for x in items.itertuples()
                if (x.sale_price if x.listing_type == "sale" else x.rent_price) is not None
            ]
            return round(median(values), 6) if values else None

        return {
            "winner_count": len(rows),
            "mean_completeness": round(float(frame.completeness.mean()), 6),
            "mean_quality": round(float(frame.quality.mean()), 6),
            "mean_measured_freshness": round(float(frame.freshness.dropna().mean()), 6)
            if frame.freshness.notna().any()
            else None,
            "mean_location_precision": round(float(frame.precision.mean()), 6),
            "source_counts": dict(sorted(Counter(frame.source_website).items())),
            "sale_apartment_count": len(sales),
            "rent_apartment_count": len(rentals),
            "sale_median_asking_eur_per_sqm": psm_median(sales),
            "rent_median_asking_eur_per_sqm": psm_median(rentals),
            "invalid_winners": 0,
            "suspicious_winners": "UNKNOWN beyond existing validity checks",
        }

    return {
        "status": "offline_only_not_active",
        "underlying_eligible_records": len(candidates),
        "groups_evaluated": duplicate_groups,
        "groups_with_changed_winner": changed,
        "weight_quality_conflict_groups": conflicts,
        "current": metrics(current),
        "proposed": metrics(proposed),
        "method": "Same existing candidate groups and eligible apartment/studio records; highest listing quality, then proposed source weight, completeness, precision, source/ID tie-breaks",
        "limitation": "Incomplete grouping cannot establish true unique-property coverage; unchanged statistics do not prove equivalent valuations",
    }
