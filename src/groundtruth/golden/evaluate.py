"""Evaluate parser accuracy against versioned golden datasets."""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

from groundtruth.config import PROJECT_ROOT
from groundtruth.models.enums import ListingType
from groundtruth.services.parsing import ParsingService

GOLDEN_DIR = PROJECT_ROOT / "data" / "golden"
BASELINE_PATH = GOLDEN_DIR / "parser_baseline.json"


@dataclass
class GoldenEvaluation:
    """Field-level accuracy from a golden dataset run."""

    total: int
    neighborhood: float
    price: float
    area: float
    type_accuracy: float
    overall: float

    def as_dict(self) -> dict[str, float]:
        return {
            "neighborhood": self.neighborhood,
            "price": self.price,
            "area": self.area,
            "type": self.type_accuracy,
            "overall": self.overall,
        }


def load_golden_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8") as fh:
        return [r for r in csv.DictReader(fh) if (r.get("source_listing_id") or "").strip()]


def verified_rows(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    """Rows with at least one correct_* field filled in."""
    verified = []
    for row in rows:
        if any((row.get(k) or "").strip() for k in row if k.startswith("correct_")):
            verified.append(row)
    return verified


def evaluate_golden_rows(rows: list[dict[str, str]]) -> GoldenEvaluation | None:
    labeled = verified_rows(rows)
    if not labeled:
        return None

    parser = ParsingService()
    counts = {"neighborhood": 0, "price": 0, "area": 0, "type": 0}
    denominators = {"neighborhood": 0, "price": 0, "area": 0, "type": 0}

    for row in labeled:
        title = row.get("title") or ""
        description = row.get("description") or ""

        if row.get("correct_neighborhood"):
            denominators["neighborhood"] += 1
            nh = parser.extract_neighborhood(title, description or None)
            if nh == row["correct_neighborhood"].strip():
                counts["neighborhood"] += 1

        if row.get("correct_type"):
            denominators["type"] += 1
            payload_type = row.get("correct_type", "").strip().lower()
            listing_type = payload_type if payload_type in ("sale", "rent") else "sale"
            payload = {
                "source_listing_id": row["source_listing_id"],
                "title": title,
                "description": description,
                "listing_type": listing_type,
                "listing_type_raw": "Qira" if listing_type == "rent" else "Shitet",
                "price_raw": row.get("price_raw") or row.get("parsed_price") or "",
                "area_raw": row.get("area_raw") or row.get("parsed_area") or "",
            }
            raw = SimpleNamespace(
                id=1,
                scrape_run_id=1,
                source_website="gjirafa",
                source_listing_id=row["source_listing_id"],
                original_url="https://example.com",
                spider_version="1.0.0",
                raw_payload=payload,
            )
            parsed = parser.parse_raw(raw)
            if parsed.listing_type and parsed.listing_type.value == payload_type:
                counts["type"] += 1

            if row.get("correct_price"):
                denominators["price"] += 1
                expected = Decimal(str(row["correct_price"]).replace(",", ""))
                actual = (
                    parsed.rent_price
                    if parsed.listing_type == ListingType.RENT
                    else parsed.sale_price
                )
                if actual == expected:
                    counts["price"] += 1

            if row.get("correct_area"):
                denominators["area"] += 1
                if parsed.area_sqm == float(row["correct_area"]):
                    counts["area"] += 1

    def rate(field: str) -> float:
        if denominators[field] == 0:
            return 1.0
        return counts[field] / denominators[field]

    nh = rate("neighborhood")
    pr = rate("price")
    ar = rate("area")
    ty = rate("type")
    scored_fields = [f for f in ("neighborhood", "price", "area", "type") if denominators[f] > 0]
    overall = sum(rate(f) for f in scored_fields) / len(scored_fields) if scored_fields else 0.0

    return GoldenEvaluation(
        total=len(labeled),
        neighborhood=nh,
        price=pr,
        area=ar,
        type_accuracy=ty,
        overall=overall,
    )


def evaluate_golden_file(path: Path) -> GoldenEvaluation | None:
    if not path.exists():
        return None
    return evaluate_golden_rows(load_golden_rows(path))


def load_baseline() -> dict:
    if not BASELINE_PATH.exists():
        return {}
    return json.loads(BASELINE_PATH.read_text(encoding="utf-8"))


def latest_golden_file() -> Path | None:
    files = sorted(GOLDEN_DIR.glob("golden_v*.csv"))
    files = [f for f in files if "_candidates" not in f.name]
    return files[-1] if files else None
