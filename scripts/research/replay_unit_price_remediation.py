"""Compare archived snapshots in memory against the pre-fix Gjirafa price method.

No database sessions, ETL writes, network calls or source-weight calculations.
Only the trusted local baseline commit's single method is loaded, without
switching Git state or executing its module. Output retains numeric evidence,
provenance and hashes rather than descriptions, media or contact details.
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import subprocess
from collections import Counter
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import groundtruth.services.parsing as parsing
from groundtruth.processing.validation import ListingValidator
from groundtruth.services.normalization import NormalizationService


def baseline_method(ref):
    source = subprocess.check_output(
        ["git", "show", f"{ref}:src/groundtruth/services/parsing.py"], encoding="utf-8"
    )
    cls = next(
        n
        for n in ast.parse(source).body
        if isinstance(n, ast.ClassDef) and n.name == "ParsingService"
    )
    method = next(
        n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == "_fixup_sale_price"
    )
    namespace = {}
    exec(
        compile(ast.Module(body=[method], type_ignores=[]), "baseline-price-method", "exec"),
        vars(parsing),
        namespace,
    )
    return namespace["_fixup_sale_price"]


def replay(rows):
    parser, normalizer, validator = (
        parsing.ParsingService(),
        NormalizationService(),
        ListingValidator(),
    )
    output = []
    for row in rows:
        raw = SimpleNamespace(
            id=row["id"],
            scrape_run_id=1,
            source_website=row["source_website"],
            source_listing_id=row["source_listing_id"],
            original_url=row["original_url"],
            spider_version="1.0.0",
            raw_payload=row["raw_payload"],
            raw_html=row.get("raw_html"),
        )
        parsed = parser.parse_raw(raw)
        normalized, _ = normalizer.normalize(parsed)
        result = validator.validate(normalized)
        values = normalized.model_dump(mode="json")
        for field in ["description_original", "description_cleaned", "image_urls"]:
            values[field + "_sha256"] = hashlib.sha256(
                json.dumps(values.pop(field), sort_keys=True).encode()
            ).hexdigest()
        output.append(
            {
                "raw_id": row["id"],
                "source": row["source_website"],
                "parsed_sale_price": str(parsed.sale_price)
                if parsed.sale_price is not None
                else None,
                "sale_price_rule": parsed.extra_fields.get("provenance", {})
                .get("sale_price", {})
                .get("rule_id"),
                "normalized": values,
                "validation_codes": [i.code for i in result.issues],
            }
        )
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshots", type=Path, required=True)
    parser.add_argument("--baseline-ref", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    rows = json.loads(args.snapshots.read_text(encoding="utf-8"))
    with patch.object(
        parsing.ParsingService, "_fixup_sale_price", baseline_method(args.baseline_ref)
    ):
        before = replay(rows)
    after = replay(rows)
    changes = [
        {
            "raw_id": a["raw_id"],
            "source": a["source"],
            "before": a,
            "after": b,
            "changed_normalized_fields": [
                k for k in a["normalized"] if a["normalized"][k] != b["normalized"][k]
            ],
        }
        for a, b in zip(before, after, strict=True)
        if a != b
    ]
    expected = {26890, 27285, 45140, 76665}
    assert {c["raw_id"] for c in changes} == expected
    assert all(
        set(c["changed_normalized_fields"]) == {"sale_price", "price_per_sqm"} for c in changes
    )
    assert all(
        c["before"]["validation_codes"] == c["after"]["validation_codes"] == [] for c in changes
    )
    report = {
        "snapshot_sha256": hashlib.sha256(args.snapshots.read_bytes()).hexdigest(),
        "baseline_ref": args.baseline_ref,
        "replayed": len(rows),
        "sources": dict(Counter(r["source_website"] for r in rows)),
        "changed": len(changes),
        "unchanged": len(rows) - len(changes),
        "changes": changes,
        "limitation": "Bounded archived diagnostic cohort, not an exhaustive corpus replay. No persisted records updated.",
    }
    args.output.mkdir(parents=True, exist_ok=False)
    (args.output / "comparison_private.json").write_text(
        json.dumps(report, indent=2), encoding="utf-8"
    )
    print(json.dumps({k: v for k, v in report.items() if k != "changes"}))


if __name__ == "__main__":
    main()
