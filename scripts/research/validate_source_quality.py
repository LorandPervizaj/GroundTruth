"""Verify private Part 2 outputs and reproduce the primary report offline."""

import argparse
import csv
import hashlib
import json
from pathlib import Path

from pydantic import TypeAdapter

from groundtruth.analytics.source_quality import build_report, write_report
from groundtruth.analytics.source_quality_models import QualityRecord, QualityReport
from groundtruth.portals.registry import all_portal_names


def validate(output: Path, repeat: Path) -> dict:
    report = QualityReport.model_validate_json((output / "source_quality_report.json").read_bytes())
    sources = set(all_portal_names())
    assert {s.source_name for s in report.sources} == sources
    assert abs(sum(report.scoring_policy.weights.values()) - 1) < 1e-9
    for source in report.sources:
        assert (
            source.accepted_count + source.rejected_count + source.pending_count
            == source.unique_source_listing_count
        )
        assert (
            source.records_examined - source.unique_source_listing_count
            == source.repeated_observation_count
        )
        assert source.source_quality_score is None or 0 <= source.source_quality_score <= 100
        if source.weight_status == "insufficient_evidence":
            assert source.proposed_weight == 1
    for source in sources:
        summaries = [s for s in report.sources if s.source_name == source]
        overall = next(s for s in summaries if s.segment == "all")
        assert (
            sum(s.unique_source_listing_count for s in summaries if s.segment != "all")
            == overall.unique_source_listing_count
        )
    with (output / "source_quality_summary.csv").open(newline="", encoding="utf-8") as stream:
        csv_rows = list(csv.DictReader(stream))
    assert len(csv_rows) == len(report.sources)
    assert {(r["source_name"], r["segment"]) for r in csv_rows} == {
        (r.source_name, r.segment) for r in report.sources
    }
    for path in output.rglob("*.json"):
        json.loads(
            path.read_text(encoding="utf-8"),
            parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)),
        )
    records = TypeAdapter(list[QualityRecord]).validate_json(
        (output / "pipeline_snapshot.json").read_bytes()
    )
    days = (report.evaluation_window["end"] - report.evaluation_window["start"]).days
    reproduced = build_report(
        records,
        sources=sorted(sources),
        as_of=report.evaluation_as_of,
        window_days=days,
        segment=True,
        policy=report.scoring_policy,
    )
    assert reproduced.model_dump(mode="json") == report.model_dump(mode="json")
    if repeat.exists() and any(repeat.iterdir()):
        raise ValueError("Reproduction output must be empty")
    write_report(reproduced, repeat)
    hashes = {}
    for name in (
        "source_quality_report.json",
        "source_quality_summary.csv",
        "source_quality_report.schema.json",
    ):
        original = (output / name).read_bytes()
        assert original == (repeat / name).read_bytes(), name
        hashes[name] = hashlib.sha256(original).hexdigest()
    audit = json.loads((output / "source_quality_audit_checks.json").read_text())
    assert set(audit["summary"]) == sources
    assert all(row["sample_count"] == 30 for row in audit["summary"].values())
    assert len({(r["source_name"], r["raw_record_id"]) for r in audit["checks"]}) == 180
    weights = json.loads((output / "source_weights_proposed.json").read_text())
    assert weights["status"] == "PROPOSED — NOT ACTIVE"
    result = {
        "status": "PASS",
        "unique_recent_listings": len(report.listings),
        "source_segment_summaries": len(report.sources),
        "reviewed_snapshot_checks": len(audit["checks"]),
        "artifact_sha256": hashes,
        "reproduced_offline": True,
    }
    (output / "source_quality_qa.json").write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--repeat", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(validate(args.output, args.repeat), sort_keys=True))
