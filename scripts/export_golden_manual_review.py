"""Export a random sample from golden_v1 for independent human verification.

The auto-labels are shown alongside raw HTML fields so reviewers can judge whether
the benchmark was labeled correctly — not whether the parser matches itself.
"""

from __future__ import annotations

import csv
import random
from pathlib import Path

import typer
from rich.console import Console

from groundtruth.config import PROJECT_ROOT
from groundtruth.database.session import get_session_factory
from groundtruth.golden.evaluate import load_golden_rows
from groundtruth.models.pipeline import RawListing
from groundtruth.services.parsing import ParsingService

app = typer.Typer()
console = Console()
GOLDEN_DIR = PROJECT_ROOT / "data" / "golden"

FIELDNAMES = [
    "review_id",
    "source_listing_id",
    "original_url",
    "stratum",
    "title",
    "description_excerpt",
    "price_raw",
    "area_raw",
    "listing_type_raw",
    "auto_label_price",
    "auto_label_area",
    "auto_label_neighborhood",
    "auto_label_type",
    "parser_price",
    "parser_area",
    "parser_neighborhood",
    "parser_type",
    "human_price_ok",
    "human_area_ok",
    "human_neighborhood_ok",
    "human_type_ok",
    "human_notes",
]


@app.command()
def export(
    input_file: Path = typer.Option(GOLDEN_DIR / "golden_v1.csv"),
    output: Path = typer.Option(GOLDEN_DIR / "golden_v1_manual_review_100.csv"),
    sample_size: int = typer.Option(100),
    seed: int = typer.Option(42),
) -> None:
    """Export N random golden rows with raw HTML + auto-labels for manual audit."""
    rows = load_golden_rows(input_file)
    labeled = [r for r in rows if (r.get("correct_price") or "").strip()]
    if not labeled:
        console.print(f"[red]No labeled rows in {input_file}[/red]")
        raise typer.Exit(1)

    random.seed(seed)
    sample = random.sample(labeled, min(sample_size, len(labeled)))

    session = get_session_factory()()
    parser = ParsingService()
    out_rows: list[dict[str, str]] = []

    try:
        for i, row in enumerate(sample, start=1):
            sid = row["source_listing_id"]
            raw = (
                session.query(RawListing)
                .filter_by(source_website="gjirafa", source_listing_id=sid)
                .order_by(RawListing.id.desc())
                .first()
            )
            payload = (raw.raw_payload if raw else {}) or {}
            title = row.get("title") or payload.get("title") or ""
            description = row.get("description") or payload.get("description") or ""
            price_raw = row.get("price_raw") or payload.get("price_raw") or ""
            area_raw = row.get("area_raw") or payload.get("area_raw") or ""
            listing_type_raw = str(payload.get("listing_type_raw") or payload.get("listing_type") or "")

            from types import SimpleNamespace

            parsed = parser.parse_raw(
                SimpleNamespace(
                    id=1,
                    scrape_run_id=1,
                    source_website="gjirafa",
                    source_listing_id=sid,
                    original_url=raw.original_url if raw else "",
                    spider_version="1.0.0",
                    raw_payload={
                        "title": title,
                        "description": description,
                        "price_raw": price_raw,
                        "area_raw": area_raw,
                        "listing_type": row.get("correct_type") or payload.get("listing_type"),
                        "listing_type_raw": listing_type_raw,
                    },
                )
            )
            parser_price = parsed.rent_price or parsed.sale_price
            parser_nh = parser.extract_neighborhood(title, description or None)

            out_rows.append(
                {
                    "review_id": str(i),
                    "source_listing_id": sid,
                    "original_url": raw.original_url if raw else "",
                    "stratum": row.get("stratum", ""),
                    "title": title,
                    "description_excerpt": (description or "")[:400],
                    "price_raw": price_raw,
                    "area_raw": area_raw,
                    "listing_type_raw": listing_type_raw,
                    "auto_label_price": row.get("correct_price", ""),
                    "auto_label_area": row.get("correct_area", ""),
                    "auto_label_neighborhood": row.get("correct_neighborhood", ""),
                    "auto_label_type": row.get("correct_type", ""),
                    "parser_price": str(parser_price) if parser_price else "",
                    "parser_area": str(parsed.area_sqm or ""),
                    "parser_neighborhood": parser_nh or "",
                    "parser_type": parsed.listing_type.value if parsed.listing_type else "",
                    "human_price_ok": "",
                    "human_area_ok": "",
                    "human_neighborhood_ok": "",
                    "human_type_ok": "",
                    "human_notes": "",
                }
            )
    finally:
        session.close()

    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(out_rows)

    console.print(f"[green]Exported {len(out_rows)} rows to {output}[/green]")
    console.print(
        "Fill human_*_ok with yes/no after reading title, description, price_raw, area_raw. "
        "Do not trust auto_label_* without verification."
    )


if __name__ == "__main__":
    app()
