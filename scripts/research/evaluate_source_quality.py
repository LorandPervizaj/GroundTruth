"""Reproduce Part 2 on the existing local research DB; never activates weights.

Run from the repository root. All DB work shares one repeatable-read, read-only
transaction. The host, port and database are verified before connecting. No
service management, migrations, network page requests, or publication occur here.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path

from dotenv import dotenv_values
from pydantic import TypeAdapter
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from groundtruth.analytics.corpus_filters import ACTIVE_CORPUS_WHERE
from groundtruth.analytics.source_quality import build_report, utc, write_report
from groundtruth.analytics.source_quality_audit import audit_summary, compare_snapshot, number
from groundtruth.analytics.source_quality_evaluation import (
    audit_sample,
    field_diagnostics,
    latest_records,
    selection_simulation,
    sensitivity,
)
from groundtruth.analytics.source_quality_models import QualityPolicy, QualityRecord
from groundtruth.analytics.source_quality_population import pipeline_records
from groundtruth.portals.registry import all_portal_names, parser_versions

TABLE_TIMES = {
    "raw_listings": "scraped_at",
    "parsed_listings": "parsed_at",
    "normalized_listings": "normalized_at",
    "invalid_listings": "created_at",
    "scrape_runs": "started_at",
    "etl_metrics": "created_at",
}


def save(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, sort_keys=True, indent=2, default=str, allow_nan=False) + "\n",
        encoding="utf-8",
    )


def research_url(env_path: Path) -> str:
    value = dotenv_values(env_path).get("DATABASE_URL")
    if not value:
        raise ValueError("Research configuration has no database URL")
    url = make_url(value)
    if (
        url.host not in {"localhost", "127.0.0.1"}
        or url.port != 15432
        or url.database != "rema"
        or not url.drivername.startswith("postgresql")
    ):
        raise ValueError("Refusing any database except the documented local research target")
    return value


def inventory(session: Session, as_of: datetime, days: int = 30) -> dict:
    result = {
        "evaluation_as_of": as_of.isoformat(),
        "read_only": session.scalar(text("SHOW transaction_read_only")),
        "server_version": session.scalar(text("SHOW server_version")),
        "snapshot_token": session.scalar(text("SELECT txid_current_snapshot()::text")),
        "tables": {},
    }
    for table, timestamp in TABLE_TIMES.items():
        result["tables"][table] = dict(
            session.execute(
                text(
                    f"SELECT count(*) records,max(id) high_water,min({timestamp}) earliest_timestamp,max({timestamp}) latest_timestamp FROM {table}"
                )
            )
            .mappings()
            .one()
        )
    result["live_schema"] = [
        dict(r)
        for r in session.execute(
            text(
                "SELECT table_name,column_name,data_type FROM information_schema.columns WHERE table_schema='public' AND table_name=ANY(:tables) ORDER BY table_name,ordinal_position"
            ),
            {"tables": list(TABLE_TIMES)},
        ).mappings()
    ]
    result["recent_scrape_runs"] = [
        dict(r)
        for r in session.execute(
            text(
                "SELECT spider_name,count(*) total_runs,count(*) FILTER(WHERE lower(status::text)='completed') completed_runs,sum(errors_count) reported_errors,max(started_at) latest_run FROM scrape_runs WHERE started_at BETWEEN :start AND :end GROUP BY 1 ORDER BY 1"
            ),
            {"start": as_of - timedelta(days=days), "end": as_of},
        ).mappings()
    ]
    result["lifecycle_date_availability"] = [
        dict(r)
        for r in session.execute(
            text(
                "SELECT source_website,count(*) lifecycle_listing_count,count(first_seen_at) first_seen_count,count(last_seen_at) last_seen_count,min(first_seen_at) earliest_first_seen,max(last_seen_at) latest_last_seen FROM listing_lifecycle_states WHERE updated_at<=:as_of GROUP BY 1 ORDER BY 1"
            ),
            {"as_of": as_of},
        ).mappings()
    ]
    result["raw_sources"] = [
        dict(r)
        for r in session.execute(
            text(
                "SELECT source_website,count(*) records,count(distinct source_listing_id) unique_listings,min(scraped_at) first_capture,max(scraped_at) latest_capture FROM raw_listings GROUP BY 1 ORDER BY 1"
            )
        ).mappings()
    ]
    for table in ("parsed_listings", "normalized_listings"):
        result[table] = [
            dict(r)
            for r in session.execute(
                text(
                    f"SELECT source_website,parser_version,count(*) records,count(distinct source_listing_id) unique_listings FROM {table} GROUP BY 1,2 ORDER BY 1,2"
                )
            ).mappings()
        ]
    result["invalid_by_source_stage"] = [
        dict(r)
        for r in session.execute(
            text(
                "SELECT coalesce(r.source_website,p.source_website,n.source_website,'UNKNOWN') source_website,i.stage,count(*) records FROM invalid_listings i LEFT JOIN raw_listings r ON r.id=i.raw_listing_id LEFT JOIN parsed_listings p ON p.id=i.parsed_listing_id LEFT JOIN normalized_listings n ON n.id=i.normalized_listing_id GROUP BY 1,2 ORDER BY 1,2"
            )
        ).mappings()
    ]
    result["integrity"] = dict(
        session.execute(
            text(
                "SELECT count(*) FILTER(WHERE raw_listing_id IS NULL AND parsed_listing_id IS NULL AND normalized_listing_id IS NULL) unlinked_quarantine_records FROM invalid_listings"
            )
        )
        .mappings()
        .one()
    )
    result["integrity"].update(
        dict(
            session.execute(
                text(
                    "SELECT count(*) FILTER(WHERE r.id IS NULL) parsed_without_raw FROM parsed_listings p LEFT JOIN raw_listings r ON r.id=p.raw_listing_id"
                )
            )
            .mappings()
            .one()
        )
    )
    result["integrity"].update(
        dict(
            session.execute(
                text(
                    "SELECT count(*) FILTER(WHERE p.id IS NULL) normalized_without_parsed FROM normalized_listings n LEFT JOIN parsed_listings p ON p.id=n.parsed_listing_id"
                )
            )
            .mappings()
            .one()
        )
    )
    result["scrape_runs"] = [
        dict(r)
        for r in session.execute(
            text(
                "SELECT spider_name,status,count(*) runs,min(started_at) first_run,max(started_at) latest_run,sum(errors_count) reported_errors FROM scrape_runs GROUP BY 1,2 ORDER BY 1,2"
            )
        ).mappings()
    ]
    result["etl_metrics"] = [
        dict(r)
        for r in session.execute(
            text(
                "SELECT source,sum(total_scraped) run_record_sum,sum(parsed_success) parsed_success_sum,sum(parsed_failed) parsed_failed_sum,sum(normalized_failed) normalized_failed_sum,sum(validation_failed) validation_failed_sum,max(created_at) latest_metrics FROM etl_metrics GROUP BY 1 ORDER BY 1"
            )
        ).mappings()
    ]
    result["historical_evidence_note"] = (
        "ETL totals overlap reprocessing; never use their sum as independent listing denominators. Golden labels are not publisher-origin verification by default."
    )
    golden = Path("data/golden/golden_v1.csv")
    if golden.exists():
        with golden.open(encoding="utf-8") as stream:
            rows = list(csv.DictReader(stream))
        result["golden_evidence"] = {
            "rows": len(rows),
            "rows_with_nonempty_correct_fields": sum(
                any(str(v or "").strip() for k, v in r.items() if k.startswith("correct_"))
                for r in rows
            ),
            "publisher_error_attribution": "UNKNOWN; not automatically applied to history or location scoring",
        }
    return result


def safe_snapshot(records: list[QualityRecord]) -> list[dict]:
    snapshot = []
    for record in records:
        value = record.model_dump(mode="json")
        if value["listing"]:
            value["listing"].update(
                original_url="",
                description_original=None,
                description_cleaned=None,
                image_urls=[],
                confidence_details=None,
            )
        snapshot.append(value)
    return snapshot


def eligible_population(session: Session, as_of: datetime) -> list[dict]:
    return [
        dict(r)
        for r in session.execute(
            text(f"""
        SELECT DISTINCT ON (nl.source_website,nl.source_listing_id)
          nl.source_website,nl.source_listing_id,nl.id normalized_id,nl.parsed_listing_id,
          p.raw_listing_id
        FROM normalized_listings nl JOIN parsed_listings p ON p.id=nl.parsed_listing_id
        WHERE nl.normalized_at<=:as_of
          AND nl.source_website=ANY(:sources)
          {ACTIVE_CORPUS_WHERE}
        ORDER BY nl.source_website,nl.source_listing_id,nl.id DESC
    """),
            {
                "as_of": as_of,
                "sources": sorted(all_portal_names()),
                "parser_versions": list(parser_versions().values()),
                "cutoff_date": (as_of - timedelta(days=365)).date(),
            },
        ).mappings()
    ]


def audit_rows(session: Session, records: list[QualityRecord], as_of: datetime) -> list[dict]:
    selected = audit_sample(records)
    ids = [r.observation_id for _, r in selected]
    # Only the selected sample loads source snapshots, kept in memory and never exported.
    rows = {
        r["id"]: dict(r)
        for r in session.execute(
            text("""
      SELECT r.id,r.raw_payload,r.raw_html,
        (SELECT row_to_json(p) FROM parsed_listings p WHERE p.raw_listing_id=r.id AND p.parsed_at<=:as_of ORDER BY p.parsed_at DESC,p.id DESC LIMIT 1) parsed,
        (SELECT row_to_json(n) FROM normalized_listings n JOIN parsed_listings p ON p.id=n.parsed_listing_id WHERE p.raw_listing_id=r.id AND p.parsed_at<=:as_of AND n.normalized_at<=:as_of ORDER BY p.parsed_at DESC,p.id DESC LIMIT 1) normalized
      FROM raw_listings r WHERE r.id=ANY(:ids)
    """),
            {"ids": ids, "as_of": as_of},
        ).mappings()
    }
    return [
        compare_snapshot(
            record=r,
            stratum=stratum,
            payload=rows[r.observation_id]["raw_payload"],
            html=rows[r.observation_id]["raw_html"],
            parsed=rows[r.observation_id]["parsed"],
            normalized=rows[r.observation_id]["normalized"],
        )
        for stratum, r in selected
    ]


def collection_review(
    session: Session, as_of: datetime, records: list[QualityRecord], days: int = 30
) -> dict:
    data = {
        "recent_run_throughput": [
            dict(r)
            for r in session.execute(
                text(
                    "SELECT spider_name,count(*) runs,sum(listings_found) listings_found_sum,sum(listings_stored) listings_stored_sum FROM scrape_runs WHERE started_at BETWEEN :start AND :end GROUP BY 1 ORDER BY 1"
                ),
                {"start": as_of - timedelta(days=days), "end": as_of},
            ).mappings()
        ],
        "etl_skip_evidence": [
            dict(r)
            for r in session.execute(
                text(
                    "SELECT source, sum(CASE WHEN field_rates->>'skipped_age' ~ '^[0-9]+$' THEN (field_rates->>'skipped_age')::int ELSE 0 END) skipped_age_run_sum FROM etl_metrics WHERE created_at<=:as_of GROUP BY 1 ORDER BY 1"
                ),
                {"as_of": as_of},
            ).mappings()
        ],
    }
    ids = [
        r.observation_id
        for r in latest_records([r for r in records if r.outcome != "pending"])
        if r.source_name == "pro-rks" and "conflicting_prices" in r.error_codes
    ]
    props = list(
        session.scalars(
            text("SELECT raw_payload->'property' FROM raw_listings WHERE id=ANY(:ids)"),
            {"ids": ids},
        )
    )

    def enabled(value):
        return value is True or value == 1 or str(value).lower() in {"true", "1"}

    single_zero = sum(
        (
            enabled(p.get("forSale"))
            and not enabled(p.get("forRent"))
            and number(p.get("rentPrice")) == 0
        )
        or (
            enabled(p.get("forRent"))
            and not enabled(p.get("forSale"))
            and number(p.get("sellPrice")) == 0
        )
        for p in props
    )
    data["dual_market_review"] = {
        "conflicting_price_records": len(ids),
        "source_explicitly_marks_both_sale_and_rent": sum(
            enabled(p.get("forSale")) and enabled(p.get("forRent")) for p in props
        ),
        "source_single_market_with_inactive_price_zero": single_zero,
        "source_both_price_fields_present": sum(
            p.get("sellPrice") is not None and p.get("rentPrice") is not None for p in props
        ),
        "interpretation": "Inactive-market zero prices retained by the parser explain many persisted conflicts. This is a pipeline representation problem, not verified publisher inaccuracy; other cases still require review.",
    }
    return data


def run(args) -> None:
    sources = sorted(all_portal_names())
    as_of = utc(datetime.fromisoformat(args.as_of.replace("Z", "+00:00")))
    output = Path(args.output)
    if output.exists() and any(output.iterdir()):
        raise ValueError("Use an empty output directory to preserve earlier evaluations")
    engine = create_engine(research_url(Path(args.env_file)), connect_args={"connect_timeout": 5})
    try:
        with Session(engine, autoflush=False) as session, session.begin():
            session.execute(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY"))
            session.execute(text("SET LOCAL statement_timeout='180s'"))
            baseline = inventory(session, as_of, args.days)
            print(
                "Verified private PostgreSQL snapshot; transaction_read_only="
                + baseline["read_only"],
                flush=True,
            )
            records = pipeline_records(
                session, sources=sources, as_of=as_of, window_days=args.history_days
            )
            print(f"Read {len(records)} stored raw versions without HTML/descriptions", flush=True)
            # Remove unneeded URLs before both fingerprinting and saving the input snapshot.
            records = TypeAdapter(list[QualityRecord]).validate_python(safe_snapshot(records))
            recent = [r for r in records if r.observed_at >= as_of - timedelta(days=args.days)]
            historical_processed = [r for r in records if r.outcome != "pending"]
            baseline.update(
                observation_window_days=args.days,
                historical_window_days=args.history_days,
                scoring_policy_version=QualityPolicy().version,
                registered_sources=sources,
            )
            baseline["snapshot_identity"] = hashlib.sha256(
                json.dumps(baseline, sort_keys=True, default=str).encode()
            ).hexdigest()
            report = build_report(
                recent, sources=sources, as_of=as_of, window_days=args.days, segment=True
            )
            historical = build_report(
                records, sources=sources, as_of=as_of, window_days=args.history_days, segment=True
            )
            processed = build_report(
                historical_processed,
                sources=sources,
                as_of=as_of,
                window_days=args.history_days,
                segment=True,
            )
            print(
                "Computed common recent, historical intake, and historical processed cohorts",
                flush=True,
            )
            audits = audit_rows(session, historical_processed, as_of)
            collection = collection_review(session, as_of, records, args.days)
            eligible = eligible_population(session, as_of)
            eligible_ids = {r["raw_listing_id"]: r["normalized_id"] for r in eligible}
            compatible = [
                r for r in latest_records(historical_processed) if r.observation_id in eligible_ids
            ]
            impact = selection_simulation(
                compatible,
                processed,
                eligible_keys={(r["source_website"], r["source_listing_id"]) for r in eligible},
                normalized_ids=eligible_ids,
            )
            baseline["active_corpus_before_cross_dedup"] = dict(
                Counter(r["source_website"] for r in eligible)
            )
            baseline["read_only_verified_at_end"] = session.scalar(
                text("SHOW transaction_read_only")
            )
            # Reconcile immutable high waters inside this exact evaluation snapshot.
            baseline["high_waters_unchanged_in_snapshot"] = all(
                session.scalar(text(f"SELECT max(id) FROM {table}")) == meta["high_water"]
                for table, meta in baseline["tables"].items()
            )
    finally:
        engine.dispose()
    write_report(report, output)
    write_report(historical, output / "historical_intake")
    write_report(processed, output / "historical_processed")
    save(output / "source_quality_baseline.json", baseline)
    save(output / "source_quality_collection_review.json", collection)
    save(output / "pipeline_snapshot.json", [r.model_dump(mode="json") for r in records])
    save(
        output / "source_quality_diagnostics.json",
        {
            "recent": field_diagnostics(recent, report),
            "historical_intake": field_diagnostics(records, historical),
            "historical_processed": field_diagnostics(historical_processed, processed),
        },
    )
    save(
        output / "source_quality_sensitivity.json",
        {"recent": sensitivity(report), "historical_processed": sensitivity(processed)},
    )
    save(
        output / "source_quality_audit_checks.json",
        {
            "seed": "gate2-2026-10-21",
            "sample_population": "latest historical processed identity per source listing; random segment strata kept separate from enriched cases; intake pending counts are evaluated separately",
            "summary": audit_summary(audits),
            "checks": audits,
        },
    )
    save(output / "source_quality_impact.json", impact)
    save(
        output / "source_weights_proposed.json",
        {
            "status": "PROPOSED — NOT ACTIVE",
            "scoring_policy_version": report.scoring_policy_version,
            "evaluation_snapshot_identity": baseline["snapshot_identity"],
            "evaluation_as_of": as_of,
            "sources": [
                {
                    "source_id": s.source_name,
                    "segment": s.segment,
                    "quality_score": s.source_quality_score,
                    "proposed_weight": s.proposed_weight,
                    "status": s.weight_status,
                    "eligibility_reason": s.eligibility_reason,
                }
                for s in report.sources
            ],
        },
    )
    verification = "# Stored-source verification\n\nAutomated evidence checks with agent review; no independent human/physical-location verification claimed. Random segment strata and failure-enriched strata must not be pooled into source-wide error-rate estimates.\n\n"
    verification += "| Source | Sampled | Strata | Segments |\n|---|---:|---|---|\n"
    for source, data in audit_summary(audits).items():
        verification += f"| {source} | {data['sample_count']} | {json.dumps(data['strata'], sort_keys=True)} | {json.dumps(data['segments'], sort_keys=True)} |\n"
    verification += "\nEach check is traceable through a local raw-record ID and safe field path in `source_quality_audit_checks.json`. No source descriptions, contact fields, or raw values are exported. `unverified` does not prove a source omitted information. Disagreement flags require review before attribution. No audit flag is automatically injected into location/history scores.\n"
    (output / "source_quality_verification.md").write_text(verification, encoding="utf-8")
    (output / "source_quality_impact.md").write_text(
        "# Offline representative selection impact\n\nPROPOSED — NOT ACTIVE. Same historical processed, currently corpus-eligible apartment/studio records in both arms. Existing grouping and priority winners versus listing-quality-first deterministic selection.\n\n```json\n"
        + json.dumps(impact, sort_keys=True, indent=2, allow_nan=False)
        + "\n```\n",
        encoding="utf-8",
    )
    for s in report.sources:
        if s.segment == "all":
            print(
                json.dumps(
                    {
                        "source": s.source_name,
                        "versions": s.records_examined,
                        "unique": s.unique_source_listing_count,
                        "score": s.source_quality_score,
                        "coverage": s.observed_criterion_coverage,
                        "weight": s.proposed_weight,
                    }
                ),
                flush=True,
            )
    print(f"Wrote private evaluation artifacts to {output}", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", default="C:/MetrikResearch/config/research.env")
    parser.add_argument("--as-of", required=True)
    parser.add_argument("--days", type=int, default=30)
    parser.add_argument("--history-days", type=int, default=140)
    parser.add_argument("--output", default="reports/generated/source_quality/part2/evaluation")
    args = parser.parse_args()
    if args.days < 1 or args.history_days < args.days:
        parser.error("history-days must be >= days >= 1")
    try:
        run(args)
    except Exception as exc:
        # Database exceptions may include secrets. Preserve only the exception class.
        print(
            f"Evaluation failed ({type(exc).__name__}); no source rows or connection details printed.",
            flush=True,
        )
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
