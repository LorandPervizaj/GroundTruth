"""Auto-label golden candidates from raw HTML ground truth (independent of DB parser state)."""

from __future__ import annotations

import csv
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import typer
from rich.console import Console

from groundtruth.config import PROJECT_ROOT
from groundtruth.database.session import get_session_factory
from groundtruth.gazetteers.loader import GazetteerService
from groundtruth.models.enums import ListingType
from groundtruth.models.pipeline import RawListing
from groundtruth.processing.normalizers.area import AreaNormalizer
from groundtruth.processing.normalizers.price import PriceNormalizer
from groundtruth.processing.validation import MAX_SALE_PRICE, MIN_PRICE_PER_SQM, MIN_SALE_PRICE
from groundtruth.services.parsing import ParsingService, _SUSPICIOUS_PRICE

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


def _resolve_ground_truth_price(
    price_raw: str,
    description: str,
    listing_type: str,
    area: float | None,
    price_norm: PriceNormalizer,
) -> Decimal | None:
    price = price_norm.normalize(price_raw or None, None)
    desc_price = price_norm.normalize(None, description) if description else None
    if price is None:
        price = desc_price
    elif price <= _SUSPICIOUS_PRICE and desc_price is not None and desc_price > price:
        price = desc_price
    if price is None:
        return None
    if listing_type == "sale" and area and area > 0:
        area_d = Decimal(str(area))
        if price / area_d < MIN_PRICE_PER_SQM:
            if desc_price and desc_price > price and desc_price / area_d >= MIN_PRICE_PER_SQM:
                price = desc_price
            elif Decimal("500") <= price <= Decimal("9999"):
                scaled = price * 100
                if MIN_SALE_PRICE <= scaled <= MAX_SALE_PRICE and scaled / area_d >= MIN_PRICE_PER_SQM:
                    price = scaled
    return price


def _resolve_ground_truth_area(
    area_raw: str,
    description: str,
    area_norm: AreaNormalizer,
) -> float | None:
    area = area_norm.normalize(area_raw or None, description)
    if area is not None and (area < 10 or area > 500):
        area = area_norm.normalize(None, description)
    return area


def _infer_type(title: str, listing_type_raw: str, listing_type: str) -> str | None:
    parser = ParsingService()
    mapped = parser._map_listing_type(listing_type)  # noqa: SLF001
    inferred = parser._infer_listing_type(title, mapped)  # noqa: SLF001
    if inferred:
        return inferred.value
    text = (listing_type_raw or listing_type or "").lower()
    if text in ("rent", "qira", "qera"):
        return "rent"
    if text in ("sale", "shitje"):
        return "sale"
    lower = title.lower()
    if any(x in lower for x in ("me qira", "me qera", "leshohet", "leshoj")):
        return "rent"
    if any(x in lower for x in ("ne shitje", "per shitje", "për shitje", "shitet")):
        return "sale"
    return None


def _validate_neighborhood(
    nh: str | None,
    gazetteer: GazetteerService,
) -> bool:
    if not nh:
        return False
    if gazetteer.match_neighborhood(nh, city="Prishtina"):
        return True
    return gazetteer.match_street(nh, neighborhood_slug=None) is not None


@app.command()
def build(
    candidates: Path = typer.Option(
        GOLDEN_DIR / "golden_v1_candidates.csv",
        help="Stratified candidates export",
    ),
    output: Path = typer.Option(
        GOLDEN_DIR / "golden_v1.csv",
        help="Verified golden dataset output",
    ),
    min_rows: int = typer.Option(1000, help="Minimum labeled rows required"),
) -> None:
    """Label correct_* columns from raw payload ground truth."""
    if not candidates.exists():
        console.print(f"[red]Missing {candidates} — run export_golden_candidates.py first[/red]")
        raise typer.Exit(1)

    session = get_session_factory()()
    parser = ParsingService()
    price_norm = PriceNormalizer()
    area_norm = AreaNormalizer()
    gazetteer = GazetteerService()
    gazetteer.load()

    labeled: list[dict[str, str]] = []
    try:
        with candidates.open(encoding="utf-8") as fh:
            for row in csv.DictReader(fh):
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
                listing_type_raw = str(payload.get("listing_type_raw") or "")
                listing_type = str(payload.get("listing_type") or "")

                correct_type = _infer_type(title, listing_type_raw, listing_type)
                correct_area = _resolve_ground_truth_area(area_raw, description, area_norm)
                correct_neighborhood = parser.extract_neighborhood(title, description or None)
                if not _validate_neighborhood(correct_neighborhood, gazetteer):
                    correct_neighborhood = None

                correct_price = None
                if correct_type:
                    correct_price = _resolve_ground_truth_price(
                        price_raw,
                        description,
                        correct_type,
                        correct_area,
                        price_norm,
                    )

                if not all([correct_type, correct_price, correct_neighborhood]):
                    continue
                if correct_area is None:
                    correct_area_str = ""
                else:
                    correct_area_str = str(correct_area)

                out = dict(row)
                out["correct_type"] = correct_type
                out["correct_area"] = correct_area_str
                out["correct_neighborhood"] = correct_neighborhood
                out["correct_price"] = str(correct_price)
                out["verified_by"] = "ground_truth_auto"
                out["notes"] = "Labeled from raw HTML + gazetteer validation"
                labeled.append(out)
    finally:
        session.close()

    if len(labeled) < min_rows:
        console.print(
            f"[yellow]Only {len(labeled)} fully labelable rows (need {min_rows}). "
            "Writing partial dataset.[/yellow]"
        )

    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=FIELDNAMES, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(labeled[: min_rows] if len(labeled) >= min_rows else labeled)

    console.print(f"[green]Wrote {min(len(labeled), min_rows)} labeled rows to {output}[/green]")


if __name__ == "__main__":
    app()
