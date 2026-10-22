"""Replay a minimized, bounded Harta diagnostic capture without DB/source writes.

The input contains the original and additional cohorts, typed description facts,
and pseudonymous publisher groups. Full descriptions/contacts are unnecessary.
Optional research DB access resolves reference IDs and loads the historical
quality baseline in a PostgreSQL read-only transaction. New cohorts stay in memory.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

from dotenv import dotenv_values
from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from groundtruth.analytics.harta_evidence import classify_harta_evidence
from groundtruth.analytics.source_quality import build_report, write_report
from groundtruth.analytics.source_quality_models import QualityRecord
from groundtruth.analytics.source_quality_population import pipeline_records
from groundtruth.processing.validation import ListingValidator
from groundtruth.services.harta_parsing import HartaParsingService
from groundtruth.services.normalization import NormalizationService


def analyze(capture: dict, output: Path, session: Session | None = None) -> dict:
    rows = capture["records"]
    if not 1 <= len(rows) <= 100 or len({r["source_id"] for r in rows}) != len(rows):
        raise ValueError("Diagnosis requires at most 100 distinct scoped identities")
    as_of = datetime.fromisoformat(capture["captured_at"])
    parser, normalizer, validator = (
        HartaParsingService(),
        NormalizationService(session),
        ListingValidator(),
    )
    quality = defaultdict(list)
    segments = defaultdict(list)
    evidence = []
    parsing_errors = []
    original_ids = {r["source_id"] for r in rows if r["cohort"] == "original"}
    baseline = []
    if session is not None:
        baseline = [
            r
            for r in pipeline_records(session, sources=["harta"], as_of=as_of, window_days=30)
            if r.source_listing_id in original_ids
        ]
        # The capture precedes the repair crawl, so it cannot see later results.
        report = build_report(baseline, sources=["harta"], as_of=as_of, segment=True)
        write_report(report, output / "quality_baseline")
    for index, row in enumerate(rows, 1):
        prop = row["property"]
        try:
            parsed = parser.parse_payload(
                {"property": prop}, url="https://harta.info/property/" + row["source_id"]
            )
            normalized, factors = normalizer.normalize(parsed)
            result = validator.validate(normalized)
            errors = sorted(
                {i.code for i in result.issues}
                | set(parsed.extra_fields["source_validation_issues"])
                | ({"invalid_location"} if factors.location_invalid else set())
            )
        except Exception as exc:
            parsing_errors.append({"source_id": row["source_id"], "error_type": type(exc).__name__})
            continue
        record = QualityRecord(
            source_name="harta",
            source_listing_id=row["source_id"],
            observation_id=index,
            observed_at=as_of,
            outcome="rejected" if errors else "accepted",
            failure_stage="validate" if errors else None,
            error_codes=errors,
            listing=normalized,
            publication_date_basis="source_declared",
            content_hash=hashlib.sha256(
                json.dumps(prop, sort_keys=True, ensure_ascii=False).encode()
            ).hexdigest(),
        )
        quality[row["cohort"]].append(record)
        projected = classify_harta_evidence(parsed, validation_error_codes=errors)
        projected.update(
            {
                "cohort": row["cohort"],
                "population_kind": "diagnostic_projection_not_persisted_pipeline",
                "publisher_proxy": row["publisher_proxy"],
            }
        )
        evidence.append(projected)
        typed = prop.get("description_facts", {}).get("area_measurements", [])
        fmt = (
            "explicit_area_concept"
            if any(f["concept"] not in {"unspecified", "ambiguous"} for f in typed)
            else "unqualified_area"
            if typed
            else "description_without_area"
            if row["description_present"]
            else "no_description"
        )
        projected["listing_format"] = fmt
        profile = {
            "accepted": not errors,
            "structured_interior": prop.get("living_area") is not None,
            "resolved_interior": parsed.area_sqm is not None,
            "description_interior": parsed.extra_fields["area_basis"]
            == "description_explicit_net_or_interior",
            "surface": prop.get("surface_area") is not None,
            "surface_basis": parsed.extra_fields["surface_area_basis"],
            "location_candidate": projected["location_matching_candidate"],
            "street_present": bool(parsed.street_raw),
            "neighborhood_present": bool(parsed.neighborhood_raw),
            "gross_candidate": projected["gross_area_research"]["candidate"],
            "errors": errors,
        }
        for dimension, value in [
            ("cohort", row["cohort"]),
            ("transaction", prop["listing_type"]),
            ("property", prop["property_type"]),
            ("format", fmt),
            ("cohort_format", row["cohort"] + "/" + fmt),
            ("publisher_proxy", row["publisher_proxy"]),
        ]:
            segments[(dimension, value)].append(profile)
    segment_output = []
    for (dimension, value), profiles in segments.items():
        segment_output.append(
            {
                "dimension": dimension,
                "value": value,
                "sample": len(profiles),
                **{
                    key: sum(bool(p[key]) for p in profiles)
                    for key in [
                        "accepted",
                        "structured_interior",
                        "resolved_interior",
                        "description_interior",
                        "surface",
                        "location_candidate",
                        "street_present",
                        "neighborhood_present",
                        "gross_candidate",
                    ]
                },
                "surface_bases": dict(Counter(p["surface_basis"] for p in profiles)),
                "errors": dict(Counter(e for p in profiles for e in p["errors"])),
            }
        )
    quality_summary = {}
    for cohort, records in quality.items():
        report = build_report(records, sources=["harta"], as_of=as_of, segment=True)
        write_report(report, output / ("quality_" + cohort + "_diagnostic"))
        quality_summary[cohort] = report.sources[0].model_dump(mode="json")
    summary = {
        "captured_at": capture["captured_at"],
        "scope": capture["scope"],
        "cohort_counts": dict(Counter(r["cohort"] for r in rows)),
        "observation_grain": "One current property per source UUID; additional cohort diagnostic only; not a random site-wide sample.",
        "read_only": True,
        "parser_error_count": len(parsing_errors),
        "parse_errors": parsing_errors,
        "alternate_api_area_features": capture["feature_area_keys"],
        "plot_area_present": sum(r.get("plot_area") is not None for r in rows),
        "publisher_definition": "Pseudonymized public property owner_id, falling back to assigned_agent_id/agent_id; not a verified agency or publisher reliability measurement.",
        "segments": segment_output,
        "quality": quality_summary,
        "weight_active": False,
        "weight": 1.0,
        "quality_policy": "1.1.0",
        "source_truth_limits": [
            "Source-claimed net/interior is not an independent measurement.",
            "surface_area has mixed/unspecified semantics, not consistently gross.",
            "Gross-area research is separate and not validated for pooled statistics.",
            "No physical location verification or publisher reliability history.",
            "Two adjacent age-ordered apartment cohorts cannot establish whole-portal or condo/studio rates.",
        ],
    }
    output.mkdir(parents=True, exist_ok=True)
    (output / "analysis_summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf8"
    )
    (output / "evidence_candidates_private.json").write_text(
        json.dumps(evidence, indent=2, ensure_ascii=False), encoding="utf8"
    )
    print(
        "AREA_DIAGNOSIS",
        json.dumps([s for s in segment_output if s["dimension"] == "cohort"]),
        flush=True,
    )
    return summary


def main():
    args = argparse.ArgumentParser(description=__doc__)
    args.add_argument("--input", type=Path, required=True)
    args.add_argument("--output", type=Path, required=True)
    args.add_argument("--research-env", type=Path)
    options = args.parse_args()
    capture = json.loads(options.input.read_text(encoding="utf8"))
    if options.research_env:
        url = dotenv_values(options.research_env)["DATABASE_URL"]
        target = make_url(url)
        if (
            target.host not in {"localhost", "127.0.0.1"}
            or target.port != 15432
            or target.database != "rema"
        ):
            raise ValueError("Expected the private local research database")
        engine = create_engine(url, connect_args={"connect_timeout": 5})
        with (
            engine.connect().execution_options(postgresql_readonly=True) as connection,
            Session(bind=connection) as session,
        ):
            analyze(capture, options.output, session)
    else:
        analyze(capture, options.output)


if __name__ == "__main__":
    main()
