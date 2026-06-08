"""Analyze neighborhood misses, invalid listings, and duplicate candidates."""

from __future__ import annotations

from collections import Counter, defaultdict

import typer
from rich.console import Console
from rich.table import Table

from groundtruth.database.session import get_session_factory
from groundtruth.models.etl import InvalidListing
from groundtruth.models.enums import ListingType
from groundtruth.models.pipeline import NormalizedListing, ParsedListing
from groundtruth.models.reference import Neighborhood
from groundtruth.processing.invalid_classification import classify_invalid_listing

app = typer.Typer()
console = Console()


@app.command()
def neighborhoods(top: int = 50) -> None:
    """List unmatched neighborhood_raw strings ranked by frequency."""
    session = get_session_factory()()
    try:
        rows = (
            session.query(
                ParsedListing.neighborhood_raw,
                ParsedListing.extra_fields,
                ParsedListing.city,
            )
            .join(NormalizedListing, NormalizedListing.parsed_listing_id == ParsedListing.id)
            .filter(NormalizedListing.neighborhood_id.is_(None))
            .all()
        )
        counts: Counter[str] = Counter()
        examples: dict[str, str] = {}
        for nh_raw, extra, city in rows:
            title = (extra or {}).get("title", "")
            key = nh_raw or f"(none) | {title[:80]}"
            counts[key] += 1
            if key not in examples:
                examples[key] = f"city={city} title={title[:60]}"

        table = Table(title=f"Unmatched neighborhood_raw (top {top})")
        table.add_column("Count", justify="right")
        table.add_column("neighborhood_raw")
        table.add_column("Example")
        for val, cnt in counts.most_common(top):
            table.add_row(str(cnt), val, examples.get(val, ""))
        console.print(table)
        console.print(f"\nTotal unmatched: {sum(counts.values())}")
    finally:
        session.close()


@app.command()
def invalid_listings() -> None:
    """Categorize all invalid listings."""
    session = get_session_factory()()
    try:
        rows = session.query(InvalidListing).order_by(InvalidListing.id).all()
        if not rows:
            console.print("[green]No invalid listings.[/green]")
            return

        by_code: Counter[str] = Counter()
        for row in rows:
            for code in row.error_codes or []:
                by_code[code] += 1

        console.print("[bold]Invalid listings by error code[/bold]")
        for code, cnt in by_code.most_common():
            console.print(f"  {code}: {cnt}")

        table = Table(title=f"All invalid listings ({len(rows)})")
        table.add_column("ID")
        table.add_column("Stage")
        table.add_column("Codes")
        table.add_column("Listing")
        table.add_column("Price")
        table.add_column("Area")
        table.add_column("Category")
        table.add_column("Message")

        for row in rows:
            snap = row.snapshot or {}
            listing_id = snap.get("source_listing_id", "?")
            price = snap.get("rent_price") or snap.get("sale_price")
            area = snap.get("area_sqm")
            category = classify_invalid_listing(row)
            table.add_row(
                str(row.id),
                row.stage.value,
                ", ".join(row.error_codes or []),
                str(listing_id),
                str(price),
                str(area),
                category,
                (row.message or "")[:60],
            )
        by_category = Counter(classify_invalid_listing(row) for row in rows)
        console.print("\n[bold]By classification[/bold]")
        for cat, cnt in by_category.most_common():
            console.print(f"  {cat}: {cnt}")
        console.print(table)
    finally:
        session.close()


@app.command("export-normalized")
def export_normalized(
    output: str = "data/normalized_review_sample.csv",
    limit: int = 100,
) -> None:
    """Export normalized listings for manual quality review."""
    import csv
    from pathlib import Path

    session = get_session_factory()()
    try:
        nh_map = {n.id: n.name for n in session.query(Neighborhood).all()}
        listings = (
            session.query(NormalizedListing)
            .order_by(NormalizedListing.confidence_score.asc().nullsfirst())
            .limit(limit)
            .all()
        )
        rows = []
        for listing in listings:
            price = listing.rent_price if listing.listing_type == ListingType.RENT else listing.sale_price
            rows.append(
                {
                    "source_listing_id": listing.source_listing_id,
                    "original_url": listing.original_url,
                    "listing_type": listing.listing_type.value if listing.listing_type else "",
                    "price": str(price) if price else "",
                    "area_sqm": str(listing.area_sqm) if listing.area_sqm else "",
                    "price_per_sqm": str(listing.price_per_sqm) if listing.price_per_sqm else "",
                    "neighborhood": nh_map.get(listing.neighborhood_id, ""),
                    "confidence_score": str(listing.confidence_score or ""),
                    "parser_version": listing.parser_version,
                    "looks_correct": "",
                    "notes": "",
                }
            )
        path = Path(output)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()) if rows else [])
            if rows:
                writer.writeheader()
                writer.writerows(rows)
        console.print(f"[green]Exported {len(rows)} listings to {path}[/green]")
        console.print("Fill in looks_correct (yes/no) and notes columns during review.")
    finally:
        session.close()


@app.command("duplicate-metrics")
def duplicate_metrics(
    input_file: str = "data/duplicate_candidates.csv",
) -> None:
    """Compute precision/recall after labeling duplicate_candidates.csv."""
    import csv
    from pathlib import Path

    path = Path(input_file)
    if not path.exists():
        console.print(f"[red]File not found: {path}[/red]")
        raise typer.Exit(1)

    labeled = []
    with path.open(encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            label = (row.get("actually_duplicate") or "").strip().lower()
            if label in ("yes", "y", "true", "1"):
                labeled.append((row["listing_a"], row["listing_b"], True))
            elif label in ("no", "n", "false", "0"):
                labeled.append((row["listing_a"], row["listing_b"], False))

    if not labeled:
        console.print("[yellow]No labeled pairs found. Fill actually_duplicate with yes/no.[/yellow]")
        raise typer.Exit(0)

    predicted_positive = len(labeled)
    true_positive = sum(1 for _, _, is_dup in labeled if is_dup)
    false_positive = predicted_positive - true_positive
    false_negative = 0  # needs negative pair labels — document limitation

    precision = true_positive / predicted_positive if predicted_positive else 0.0
    console.print(f"\n[bold]Duplicate detection metrics[/bold] ({len(labeled)} labeled pairs)")
    console.print(f"  Labeled as duplicate (yes):  {true_positive}")
    console.print(f"  Labeled as distinct (no):    {false_positive}")
    console.print(f"  Precision:                   {precision:.1%}")
    console.print(
        "\n  Note: Recall requires labeling known non-duplicate pairs the algorithm missed."
    )
    console.print("  Add a separate negatives file later for full precision/recall.")


@app.command("confidence-summary")
def confidence_summary() -> None:
    """Show confidence score distribution across normalized listings."""
    session = get_session_factory()()
    try:
        listings = session.query(NormalizedListing).all()
        if not listings:
            console.print("[yellow]No normalized listings.[/yellow]")
            return
        scores = [listing.confidence_score for listing in listings if listing.confidence_score is not None]
        if not scores:
            console.print("[yellow]No confidence scores — run ETL with --reprocess.[/yellow]")
            return
        buckets = {"high (>=0.85)": 0, "medium (0.70-0.85)": 0, "low (<0.70)": 0}
        for score in scores:
            if score >= 0.85:
                buckets["high (>=0.85)"] += 1
            elif score >= 0.70:
                buckets["medium (0.70-0.85)"] += 1
            else:
                buckets["low (<0.70)"] += 1
        console.print("[bold]Confidence distribution[/bold]")
        for label, cnt in buckets.items():
            console.print(f"  {label}: {cnt} ({100 * cnt / len(scores):.1f}%)")
        console.print(f"  Mean: {sum(scores) / len(scores):.3f}")
    finally:
        session.close()


@app.command("export-duplicates")
def export_duplicates(
    output: str = "data/duplicate_candidates.csv",
    limit: int = 100,
) -> None:
    """Write duplicate candidate pairs to CSV for manual labeling."""
    import csv
    from pathlib import Path

    session = get_session_factory()()
    rows: list[dict[str, str]] = []
    try:
        listings = session.query(NormalizedListing).order_by(NormalizedListing.id).all()
        signatures: dict[tuple, list[NormalizedListing]] = defaultdict(list)
        for listing in listings:
            price = (
                listing.rent_price
                if listing.listing_type == ListingType.RENT
                else listing.sale_price
            )
            if price is None or listing.area_sqm is None:
                continue
            sig = (
                listing.neighborhood_id,
                round(listing.area_sqm, 1),
                listing.bedrooms,
                int(price // 50) * 50,
            )
            signatures[sig].append(listing)

        for group in signatures.values():
            if len(group) < 2:
                continue
            for i in range(len(group)):
                for j in range(i + 1, len(group)):
                    if len(rows) >= limit:
                        break
                    a, b = group[i], group[j]
                    rows.append(
                        {
                            "listing_a": a.source_listing_id,
                            "url_a": a.original_url,
                            "listing_b": b.source_listing_id,
                            "url_b": b.original_url,
                            "neighborhood_id": str(a.neighborhood_id),
                            "area_sqm": str(a.area_sqm),
                            "bedrooms": str(a.bedrooms),
                            "price": str(a.rent_price or a.sale_price),
                            "actually_duplicate": "",
                        }
                    )
                if len(rows) >= limit:
                    break
            if len(rows) >= limit:
                break

        path = Path(output)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()) if rows else [])
            if rows:
                writer.writeheader()
                writer.writerows(rows)
        console.print(f"[green]Exported {len(rows)} pairs to {path}[/green]")
    finally:
        session.close()


@app.command()
def duplicate_candidates(limit: int = 50) -> None:
    """Export in-batch duplicate candidate pairs for manual labeling."""
    session = get_session_factory()()
    try:
        listings = session.query(NormalizedListing).order_by(NormalizedListing.id).all()
        signatures: dict[tuple, list[NormalizedListing]] = defaultdict(list)

        for listing in listings:
            price = (
                listing.rent_price
                if listing.listing_type == ListingType.RENT
                else listing.sale_price
            )
            if price is None or listing.area_sqm is None:
                continue
            sig = (
                listing.neighborhood_id,
                round(listing.area_sqm, 1),
                listing.bedrooms,
                int(price // 50) * 50,
            )
            signatures[sig].append(listing)

        table = Table(title="Duplicate candidates (for manual review)")
        table.add_column("Listing A")
        table.add_column("Listing B")
        table.add_column("Neighborhood")
        table.add_column("Area")
        table.add_column("Beds")
        table.add_column("Price")
        table.add_column("Actually duplicate?")

        pairs = 0
        for group in signatures.values():
            if len(group) < 2:
                continue
            for i in range(len(group)):
                for j in range(i + 1, len(group)):
                    if pairs >= limit:
                        break
                    a, b = group[i], group[j]
                    price_a = a.rent_price if a.listing_type == ListingType.RENT else a.sale_price
                    table.add_row(
                        a.source_listing_id,
                        b.source_listing_id,
                        str(a.neighborhood_id),
                        str(a.area_sqm),
                        str(a.bedrooms),
                        str(price_a),
                        "",
                    )
                    pairs += 1
                if pairs >= limit:
                    break
            if pairs >= limit:
                break

        console.print(table)
        console.print(f"\nShowing {pairs} pairs. Label in a spreadsheet for precision tuning.")
    finally:
        session.close()


if __name__ == "__main__":
    app()
