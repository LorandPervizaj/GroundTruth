"""Labelled-pair benchmark for cross-portal candidate blocking and scoring."""

from __future__ import annotations

import csv
from dataclasses import asdict, dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any

import pandas as pd

from groundtruth.analytics.listing_fingerprint import coarse_block_key
from groundtruth.models.enums import Currency, ListingType, PropertyType
from groundtruth.processing.deduplicator.scoring import DuplicateScorer
from groundtruth.schemas.pipeline import NormalizedListingSchema


@dataclass(frozen=True)
class BenchmarkResult:
    threshold: float
    labelled_pairs: int
    positive_pairs: int
    candidate_pairs: int
    true_positive: int
    false_positive: int
    false_negative: int
    true_negative: int
    precision: float
    recall: float
    blocking_recall: float


def load_benchmark(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _optional(row: dict[str, str], side: str, name: str, cast: type) -> Any:
    value = row.get(f"{side}_{name}", "").strip()
    return cast(value) if value else None


def _listing(row: dict[str, str], side: str) -> NormalizedListingSchema:
    listing_type = row[f"{side}_listing_type"].strip().lower()
    price = Decimal(row[f"{side}_price"])
    return NormalizedListingSchema(
        source_website=row[f"{side}_source"],
        source_listing_id=row[f"{side}_id"],
        original_url=f"https://benchmark.invalid/{side}/{row[f'{side}_id']}",
        listing_type=ListingType(listing_type),
        property_type=PropertyType.APARTMENT,
        sale_price=price if listing_type == "sale" else None,
        rent_price=price if listing_type == "rent" else None,
        currency=Currency.EUR,
        neighborhood_id=_optional(row, side, "neighborhood_id", int),
        street_id=_optional(row, side, "street_id", int),
        building_id=_optional(row, side, "building_id", int),
        area_sqm=_optional(row, side, "area_sqm", float),
        bedrooms=_optional(row, side, "bedrooms", int),
        bathrooms=_optional(row, side, "bathrooms", int),
        description_cleaned=row.get(f"{side}_description") or None,
    )


def _block_row(item: NormalizedListingSchema) -> pd.Series:
    return pd.Series(
        {
            "listing_type": item.listing_type.value if item.listing_type else None,
            "neighborhood_id": item.neighborhood_id,
            "area_sqm": item.area_sqm,
            "bedrooms": item.bedrooms,
            "sale_price": float(item.sale_price) if item.sale_price is not None else None,
            "rent_price": float(item.rent_price) if item.rent_price is not None else None,
        }
    )


def evaluate_pairs(
    rows: list[dict[str, str]], *, threshold: float
) -> tuple[BenchmarkResult, list[dict[str, Any]]]:
    scorer = DuplicateScorer(threshold=threshold)
    details: list[dict[str, Any]] = []
    tp = fp = fn = tn = candidates = blocked_positive = positives = 0
    for row in rows:
        left, right = _listing(row, "left"), _listing(row, "right")
        labelled = row["is_duplicate"].strip().lower() in {"1", "true", "yes"}
        positives += int(labelled)
        left_key, right_key = (
            coarse_block_key(_block_row(left)),
            coarse_block_key(_block_row(right)),
        )
        candidate = left_key is not None and left_key == right_key
        candidates += int(candidate)
        blocked_positive += int(candidate and labelled)
        score = scorer.score(left, right).confidence if candidate else 0.0
        predicted = candidate and score >= threshold
        tp += int(predicted and labelled)
        fp += int(predicted and not labelled)
        fn += int(not predicted and labelled)
        tn += int(not predicted and not labelled)
        details.append(
            {
                "pair_id": row["pair_id"],
                "source_pair": " | ".join(sorted((left.source_website, right.source_website))),
                "label": labelled,
                "candidate": candidate,
                "score": score,
                "predicted": predicted,
                "error": "false_positive"
                if predicted and not labelled
                else "false_negative"
                if not predicted and labelled
                else "",
            }
        )
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / positives if positives else 0.0
    blocking_recall = blocked_positive / positives if positives else 0.0
    return BenchmarkResult(
        threshold,
        len(rows),
        positives,
        candidates,
        tp,
        fp,
        fn,
        tn,
        round(precision, 4),
        round(recall, 4),
        round(blocking_recall, 4),
    ), details


def threshold_sensitivity(
    rows: list[dict[str, str]], thresholds: tuple[float, ...] = (70, 75, 80, 85, 90)
) -> list[dict[str, Any]]:
    return [asdict(evaluate_pairs(rows, threshold=value)[0]) for value in thresholds]
