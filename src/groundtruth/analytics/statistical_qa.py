"""Automated statistical QA release gate."""

from __future__ import annotations

import csv
import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from io import StringIO
from pathlib import Path
from typing import Any, Literal

from groundtruth.analytics.metric_registry import metric_definition
from groundtruth.claims.hashes import sha256_file

QAStatus = Literal["PASS", "PASS_WITH_WARNINGS", "FAIL"]


@dataclass(frozen=True)
class QAIssue:
    level: Literal["WARN", "FAIL"]
    code: str
    entity: str
    metric: str | None
    message: str
    evidence: dict[str, Any]


def evaluate_lookup_payload(
    payload: dict[str, Any],
    *,
    manifest_revision: str | None,
    previous: dict[str, Any] | None = None,
) -> list[QAIssue]:
    entity = f"{payload.get('entity_type')}/{payload.get('slug')}"
    issues: list[QAIssue] = []
    total = int(payload.get("total_listings") or 0)
    if total < 0:
        issues.append(
            QAIssue(
                "FAIL",
                "NEGATIVE_INVENTORY",
                entity,
                None,
                "Inventory is negative",
                {"total": total},
            )
        )
    revision = payload.get("corpus_revision") or (
        payload.get("corpus_updated_at") if payload.get("corpus_revision") is not None else None
    )
    if manifest_revision and revision and revision != manifest_revision:
        issues.append(
            QAIssue(
                "FAIL",
                "CORPUS_REVISION_MISMATCH",
                entity,
                None,
                "Lookup and manifest revisions differ",
                {"lookup": revision, "manifest": manifest_revision},
            )
        )

    pulse = payload.get("pulse") or {}
    alias_pairs = (
        ("median_sale_psm_eur", "average_sale_psm_eur"),
        ("median_rent_psm_eur", "average_rent_psm_eur"),
        ("recent_valid_listings", "active_listings"),
    )
    for replacement, deprecated in alias_pairs:
        if replacement in pulse and deprecated in pulse and pulse[replacement] != pulse[deprecated]:
            issues.append(
                QAIssue(
                    "FAIL",
                    "DEPRECATED_ALIAS_DIVERGENCE",
                    entity,
                    replacement,
                    "Deprecated alias differs from replacement",
                    {"replacement": pulse[replacement], "deprecated": pulse[deprecated]},
                )
            )

    for metric_id, metric in (pulse.get("metrics") or {}).items():
        try:
            definition = metric_definition(metric_id)
        except ValueError:
            issues.append(
                QAIssue("FAIL", "UNKNOWN_METRIC", entity, metric_id, "Metric is not registered", {})
            )
            continue
        sample_n = int(metric.get("sample_n") or 0)
        if sample_n < 0 or sample_n > total:
            issues.append(
                QAIssue(
                    "FAIL",
                    "IMPOSSIBLE_SAMPLE_N",
                    entity,
                    metric_id,
                    "Metric sample exceeds its parent population",
                    {"sample_n": sample_n, "population_n": total},
                )
            )
        if metric.get("statistic") != definition.statistic:
            issues.append(
                QAIssue(
                    "FAIL",
                    "WRONG_REGISTERED_STATISTIC",
                    entity,
                    metric_id,
                    "Metric statistic differs from registry",
                    {"actual": metric.get("statistic"), "registered": definition.statistic},
                )
            )
        if metric.get("population") != definition.population_id:
            issues.append(
                QAIssue(
                    "FAIL",
                    "WRONG_REGISTERED_POPULATION",
                    entity,
                    metric_id,
                    "Metric population differs from registry",
                    {"actual": metric.get("population"), "registered": definition.population_id},
                )
            )

    for section in ("bedroom_breakdown", "size_breakdown"):
        seen: set[str] = set()
        for row in payload.get(section) or []:
            key = str(
                row.get("bedrooms") if section == "bedroom_breakdown" else row.get("size_band")
            )
            if key in seen:
                issues.append(
                    QAIssue(
                        "FAIL",
                        "DUPLICATE_EXCLUSIVE_BUCKET",
                        entity,
                        section,
                        "Exclusive bucket appears more than once",
                        {"bucket": key},
                    )
                )
            seen.add(key)
            union_n = int(row.get("union_sample_n", row.get("listings", 0)) or 0)
            for field in ("sale_sample_n", "rent_sample_n"):
                n = int(row.get(field, 0) or 0)
                if n > union_n:
                    issues.append(
                        QAIssue(
                            "FAIL",
                            "BUCKET_SAMPLE_EXCEEDS_UNION",
                            entity,
                            field,
                            "Bucket metric N exceeds union N",
                            {"sample_n": n, "union_n": union_n, "bucket": key},
                        )
                    )

    if previous:
        previous_pulse = previous.get("pulse") or {}
        for metric in ("median_sale_psm_eur", "median_rent_eur", "recent_valid_listings"):
            current_value = pulse.get(metric)
            previous_value = previous_pulse.get(metric)
            if current_value is None or not previous_value:
                continue
            delta_pct = (
                100.0 * (float(current_value) - float(previous_value)) / float(previous_value)
            )
            if abs(delta_pct) >= 30:
                issues.append(
                    QAIssue(
                        "WARN",
                        "LARGE_RELEASE_DELTA",
                        entity,
                        metric,
                        "Large release-to-release movement",
                        {
                            "current": current_value,
                            "previous": previous_value,
                            "delta_pct": round(delta_pct, 1),
                        },
                    )
                )
    return issues


def run_statistical_qa(
    cache_dir: Path,
    output_dir: Path,
    *,
    previous_cache_dir: Path | None = None,
) -> tuple[QAStatus, dict[str, Path]]:
    manifest_path = cache_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    revision = manifest.get("corpus_revision")
    issues: list[QAIssue] = []
    checked = 0
    previous_by_key: dict[tuple[str, str], dict[str, Any]] = {}
    if previous_cache_dir and (previous_cache_dir / "manifest.json").is_file():
        old_manifest = json.loads(
            (previous_cache_dir / "manifest.json").read_text(encoding="utf-8")
        )
        for entry in old_manifest.get("entries") or []:
            path = previous_cache_dir / entry["path"]
            if path.is_file():
                previous_by_key[(entry["entity_type"], entry["slug"])] = json.loads(
                    path.read_text(encoding="utf-8")
                )

    for entry in manifest.get("entries") or []:
        path = cache_dir / entry["path"]
        payload = json.loads(path.read_text(encoding="utf-8"))
        issues.extend(
            evaluate_lookup_payload(
                payload,
                manifest_revision=revision,
                previous=previous_by_key.get((entry["entity_type"], entry["slug"])),
            )
        )
        checked += 1
    failures = [issue for issue in issues if issue.level == "FAIL"]
    warnings = [issue for issue in issues if issue.level == "WARN"]
    status: QAStatus = "FAIL" if failures else "PASS_WITH_WARNINGS" if warnings else "PASS"
    generated_at = datetime.now(UTC).isoformat()
    details = {
        "generated_at": generated_at,
        "status": status,
        "checked_entities": checked,
        "issues": [asdict(issue) for issue in issues],
    }
    summary = {
        "generated_at": generated_at,
        "status": status,
        "checked_entities": checked,
        "failures": len(failures),
        "warnings": len(warnings),
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    details_path = output_dir / "market_qa_details.json"
    summary_path = output_dir / "market_qa_summary.json"
    csv_path = output_dir / "market_qa_summary.csv"
    details_path.write_text(json.dumps(details, indent=2), encoding="utf-8")
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    buffer = StringIO()
    writer = csv.DictWriter(
        buffer, fieldnames=["level", "code", "entity", "metric", "message", "evidence"]
    )
    writer.writeheader()
    for issue in issues:
        row = asdict(issue)
        row["evidence"] = json.dumps(row["evidence"], sort_keys=True)
        writer.writerow(row)
    csv_path.write_text(buffer.getvalue(), encoding="utf-8")
    qa_hash = sha256_file(details_path)
    manifest["statistical_qa"] = {
        "status": status,
        "details_sha256": qa_hash,
        "summary": str(summary_path),
        "details": str(details_path),
    }
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    if status == "FAIL":
        raise ValueError(f"statistical QA failed with {len(failures)} hard failure(s)")
    return status, {"summary": summary_path, "details": details_path, "csv": csv_path}
