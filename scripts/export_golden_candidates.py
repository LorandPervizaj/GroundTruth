"""Export stratified golden dataset candidates — never overwrites verified golden files."""

from __future__ import annotations

import csv
import re
from pathlib import Path

import typer
from rich.console import Console

from groundtruth.config import PROJECT_ROOT
from groundtruth.database.session import get_session_factory
from groundtruth.models.etl import InvalidListing
from groundtruth.models.pipeline import NormalizedListing, ParsedListing, RawListing
from groundtruth.models.reference import Neighborhood

app = typer.Typer()
console = Console()

GOLDEN_DIR = PROJECT_ROOT / "data" / "golden"
FIELDNAMES = [
    "stratum",
    "source_listing_id",
    "title",
    "description",
    "price_raw",
    "area_raw",
    "parsed_price",
    "parsed_area",
    "parsed_neighborhood",
    "parsed_type",
    "correct_price",
    "correct_area",
    "correct_neighborhood",
    "correct_type",
    "correct_building",
    "verified_by",
    "notes",
]


def _next_version() -> int:
    versions: list[int] = []
    for path in GOLDEN_DIR.glob("golden_v*"):
        match = re.search(r"golden_v(\d+)", path.name)
        if match:
            versions.append(int(match.group(1)))
    return max(versions, default=0) + 1


def _listing_row(
    listing: NormalizedListing,
    *,
    stratum: str,
    nh_map: dict[int, str],
    parsed: ParsedListing | None,
    extra_price_raw: str = "",
    extra_area_raw: str = "",
) -> dict[str, str]:
    extra = (parsed.extra_fields or {}) if parsed else {}
    price = (
        listing.rent_price
        if listing.listing_type and listing.listing_type.value == "rent"
        else listing.sale_price
    )
    payload = (parsed and parsed.extra_fields) or {}
    return {
        "stratum": stratum,
        "source_listing_id": listing.source_listing_id,
        "title": extra.get("title", ""),
        "description": (listing.description_original or "")[:500],
        "price_raw": extra_price_raw,
        "area_raw": extra_area_raw,
        "parsed_price": str(price) if price else "",
        "parsed_area": str(listing.area_sqm or ""),
        "parsed_neighborhood": nh_map.get(listing.neighborhood_id, ""),
        "parsed_type": listing.listing_type.value if listing.listing_type else "",
        "correct_price": "",
        "correct_area": "",
        "correct_neighborhood": "",
        "correct_type": "",
        "correct_building": "",
        "verified_by": "",
        "notes": "",
    }


@app.command()
def export(
    version: int | None = typer.Option(None, help="Golden version number (auto if omitted)"),
    random_count: int = 700,
    low_confidence_count: int = 100,
    high_confidence_count: int = 100,
    invalid_count: int = 100,
) -> None:
    """
    Export 1,000 stratified candidates for manual labeling.

    Split: random / low confidence / high confidence / invalid.
    Writes golden_v{N}_candidates.csv — never overwrites golden_v{N}.csv.
    """
    version = version or _next_version()
    output = GOLDEN_DIR / f"golden_v{version}_candidates.csv"
    if output.exists():
        console.print(f"[red]Refusing to overwrite {output}[/red]")
        raise typer.Exit(1)

    session = get_session_factory()()
    try:
        nh_map = {n.id: n.name for n in session.query(Neighborhood).all()}
        all_listings = session.query(NormalizedListing).all()
        if not all_listings:
            console.print("[yellow]No listings in database.[/yellow]")
            raise typer.Exit(0)

        by_id = {listing.source_listing_id: listing for listing in all_listings}
        selected: dict[str, tuple[NormalizedListing, str]] = {}

        import random

        random.seed(42)
        pool = list(all_listings)
        random.shuffle(pool)
        for listing in pool:
            if len([s for s in selected.values() if s[1] == "random"]) >= random_count:
                break
            selected.setdefault(listing.source_listing_id, (listing, "random"))

        low = (
            session.query(NormalizedListing)
            .order_by(NormalizedListing.confidence_score.asc().nullsfirst())
            .limit(low_confidence_count * 2)
            .all()
        )
        for listing in low:
            if len([s for s in selected.values() if s[1] == "low_confidence"]) >= low_confidence_count:
                break
            selected.setdefault(listing.source_listing_id, (listing, "low_confidence"))

        high = (
            session.query(NormalizedListing)
            .order_by(NormalizedListing.confidence_score.desc().nullslast())
            .limit(high_confidence_count * 2)
            .all()
        )
        for listing in high:
            if len([s for s in selected.values() if s[1] == "high_confidence"]) >= high_confidence_count:
                break
            selected.setdefault(listing.source_listing_id, (listing, "high_confidence"))

        invalid_rows = session.query(InvalidListing).limit(invalid_count * 3).all()
        for inv in invalid_rows:
            if len([s for s in selected.values() if s[1] == "invalid"]) >= invalid_count:
                break
            snap = inv.snapshot or {}
            sid = snap.get("source_listing_id")
            if not sid or sid in selected:
                continue
            listing = by_id.get(sid)
            if listing:
                selected[sid] = (listing, "invalid")

        target = random_count + low_confidence_count + high_confidence_count + invalid_count
        if len(selected) < target:
            for listing in pool:
                if len(selected) >= target:
                    break
                selected.setdefault(listing.source_listing_id, (listing, "random"))

        GOLDEN_DIR.mkdir(parents=True, exist_ok=True)
        with output.open("w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=FIELDNAMES)
            writer.writeheader()
            for listing, stratum in selected.values():
                parsed = session.query(ParsedListing).filter_by(id=listing.parsed_listing_id).first()
                price_raw = ""
                area_raw = ""
                if parsed and parsed.raw_listing_id:
                    raw = session.get(RawListing, parsed.raw_listing_id)
                    if raw and raw.raw_payload:
                        price_raw = raw.raw_payload.get("price_raw") or ""
                        area_raw = raw.raw_payload.get("area_raw") or ""
                writer.writerow(
                    _listing_row(
                        listing,
                        stratum=stratum,
                        nh_map=nh_map,
                        parsed=parsed,
                        extra_price_raw=price_raw,
                        extra_area_raw=area_raw,
                    )
                )

        counts = {}
        for _, stratum in selected.values():
            counts[stratum] = counts.get(stratum, 0) + 1
        console.print(f"[green]Exported {len(selected)} candidates to {output}[/green]")
        for stratum, count in sorted(counts.items()):
            console.print(f"  {stratum}: {count}")
        console.print(
            f"\nLabel correct_* columns, then save verified rows as "
            f"[bold]data/golden/golden_v{version}.csv[/bold] (never edit candidates file)."
        )
    finally:
        session.close()


if __name__ == "__main__":
    app()
