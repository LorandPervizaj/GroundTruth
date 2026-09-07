"""Freeze a reproducible dataset snapshot manifest (Dataset v1.0 baseline)."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import typer
from rich.console import Console
from sqlalchemy import text

from groundtruth.claims.hashes import (
    reproducibility_tuple,
)
from groundtruth.config import PROJECT_ROOT
from groundtruth.database.session import get_session_factory
from groundtruth.methodology.version import METHODOLOGY_VERSION
from groundtruth.services.etl import ETL_PIPELINE_VERSION
from groundtruth.services.merrjep_parsing import PARSER_VERSION as MERRJEP_PARSER_VERSION
from groundtruth.services.myrealestate_parsing import PARSER_VERSION as MYREALESTATE_PARSER_VERSION
from groundtruth.services.parsing import PARSER_VERSION as GJIRAFA_PARSER_VERSION
from groundtruth.services.pro_rks_parsing import PARSER_VERSION as PRO_RKS_PARSER_VERSION
from groundtruth.services.topia_parsing import PARSER_VERSION as TOPIA_PARSER_VERSION
from groundtruth.services.vision_parsing import PARSER_VERSION as VISION_PARSER_VERSION

app = typer.Typer()
console = Console()
DEFAULT_OUT = PROJECT_ROOT / "data" / "datasets" / "dataset_v1.0.json"
DEFAULT_V2_OUT = PROJECT_ROOT / "data" / "datasets" / "dataset_v2.0.json"


@app.command()
def run(
    version: str = typer.Option("v1.0", help="Dataset version label"),
    output: Path | None = typer.Option(None, help="Output manifest path"),
    corpus_report: Path | None = typer.Option(
        None,
        help="Path to corpus_report_*.json from corpus diagnostics (required for v2.0)",
    ),
    golden_accuracy: float | None = typer.Option(
        None,
        help="Golden parser accuracy %% for manifest (e.g. 99.9 from evaluate_golden_dataset.py)",
    ),
) -> None:
    """Write frozen dataset manifest with fingerprints and coverage stats."""
    is_v2 = version.startswith("v2")
    if output is None:
        output = DEFAULT_V2_OUT if is_v2 else DEFAULT_OUT

    session = get_session_factory()()
    try:
        repro = reproducibility_tuple(
            session, parser_version=None if is_v2 else GJIRAFA_PARSER_VERSION
        )
        stats = (
            session.execute(
                text(
                    """
                SELECT
                    COUNT(*) AS normalized_rows,
                    COUNT(DISTINCT (source_website, source_listing_id)) AS unique_listings,
                    COUNT(*) FILTER (WHERE listing_type = 'RENT') AS rent_rows,
                    COUNT(*) FILTER (WHERE listing_type = 'SALE') AS sale_rows,
                    COUNT(*) FILTER (WHERE is_furnished = true) AS furnished_true,
                    COUNT(*) FILTER (WHERE is_furnished = false) AS furnished_false,
                    COUNT(*) FILTER (WHERE is_furnished IS NULL) AS furnished_null,
                    ROUND(100.0 * COUNT(area_sqm) / NULLIF(COUNT(*), 0), 1) AS area_coverage_pct,
                    ROUND(100.0 * COUNT(neighborhood_id) / NULLIF(COUNT(*), 0), 1) AS neighborhood_coverage_pct
                FROM (
                    SELECT DISTINCT ON (source_website, source_listing_id) *
                    FROM normalized_listings
                    ORDER BY source_website, source_listing_id, id DESC
                ) latest
                """
                ),
            )
            .mappings()
            .one()
        )

        sources = (
            session.execute(
                text(
                    """
                SELECT source_website, parser_version,
                       COUNT(*) AS unique_listings
                FROM (
                    SELECT DISTINCT ON (source_website, source_listing_id)
                        source_website, source_listing_id, parser_version
                    FROM normalized_listings
                    ORDER BY source_website, source_listing_id, id DESC
                ) latest
                GROUP BY source_website, parser_version
                ORDER BY unique_listings DESC
                """
                ),
            )
            .mappings()
            .all()
        )

        from groundtruth.analytics.corpus import active_corpus_bundle

        bundle = active_corpus_bundle(session)
    finally:
        session.close()

    if is_v2 and corpus_report is None:
        console.print(
            "[yellow]v2.0 freeze: run corpus diagnostics first, then pass --corpus-report[/yellow]"
        )
        console.print("  uv run groundtruth corpus report")
        raise typer.Exit(1)

    corpus_summary = None
    if corpus_report is not None:
        corpus_summary = json.loads(corpus_report.read_text(encoding="utf-8"))

    invalid_pct = None
    golden_accuracy_pct = golden_accuracy
    canonical_active = len(bundle.active)
    cross_portal_groups = bundle.cross_portal_groups
    cross_portal_removed = len(bundle.deduped) - len(bundle.active)
    if corpus_summary:
        validation = corpus_summary.get("validation") or {}
        invalid_pct = validation.get("invalid_pct_of_normalized")
        corpus_summary.get("fingerprints") or {}
    else:
        pass

    quality = {
        "invalid_pct": invalid_pct,
        "golden_accuracy_pct": golden_accuracy_pct,
        "golden_eval_source": "data/golden/golden_v1.csv",
        "canonical_active_listings": canonical_active,
        "cross_portal_duplicate_groups": cross_portal_groups,
        "cross_portal_duplicates_removed": cross_portal_removed,
        "dedup_register": "data/deduplication/cross_portal_groups.csv",
        "public_product_scope": "rent_and_sale",
        "sale_scope_note": (
            "Rent and sale statistics are computed separately; thin sale segments "
            "show fewer metrics (confidence tier) rather than guessed numbers."
        ),
    }

    manifest = {
        "dataset_version": version,
        "frozen_at": datetime.now(UTC).isoformat(),
        "description": (
            "GroundTruth Kosovo residential corpus — Gjirafa + MerrJep"
            if is_v2
            else "GroundTruth Prishtina residential baseline — single source (Gjirafa), parser v1.3.1"
        ),
        "sources": [dict(row) for row in sources],
        "coverage": {k: float(v) if v is not None else None for k, v in dict(stats).items()},
        "versions": {
            "parser_versions": {
                "gjirafa": GJIRAFA_PARSER_VERSION,
                "merrjep": MERRJEP_PARSER_VERSION,
                "pro-rks": PRO_RKS_PARSER_VERSION,
                "topia": TOPIA_PARSER_VERSION,
                "vision": VISION_PARSER_VERSION,
                "myrealestate": MYREALESTATE_PARSER_VERSION,
            }
            if is_v2
            else {"parser_version": GJIRAFA_PARSER_VERSION},
            "etl_version": ETL_PIPELINE_VERSION,
            "methodology_version": METHODOLOGY_VERSION,
        },
        "fingerprints": repro
        if not corpus_summary
        else {**repro, **(corpus_summary.get("fingerprints") or {})},
        "corpus_summary": corpus_summary,
        "quality": quality,
        "calibration": {
            "manual_review_rows": 100,
            "ece_pct": 4.6,
            "all_fields_accuracy_pct": 92.0,
            "source": "data/golden/parser_baseline.json",
        },
        "claims_baseline": [
            "GT-000",
            "GT-001",
            "GT-003",
            "GT-005",
            "GT-006",
            "GT-007",
        ],
        "reports": {
            "audit": "reports/generated/audit_2026-06-09/",
            "quarterly": f"reports/generated/quarterly_report_{version.replace('.', '_')}_2026-06-09.md",
        },
        "notes": (
            "Multi-source residential corpus. Run corpus diagnostics before freeze; "
            "do not freeze until systemic quality issues are resolved."
            if is_v2
            else (
                "Do not mix pre-v1.3.1 normalized rows in comparative analysis. "
                "Next data increment should be MerrJep (source diversity), not more Gjirafa volume."
            )
        ),
    }

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(manifest, indent=2, default=str), encoding="utf-8")
    console.print(f"[green]Frozen {version} -> {output}[/green]")
    console.print(f"  unique listings: {stats['unique_listings']}")
    console.print(f"  dataset_hash: {repro['dataset_hash'][:16]}...")


if __name__ == "__main__":
    app()
