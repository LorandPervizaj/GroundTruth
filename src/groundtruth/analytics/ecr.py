"""Evidence Conversion Rate — human validation into structural knowledge."""

from __future__ import annotations

import csv
from pathlib import Path

REVIEW_FIELDS = ("price", "area", "neighborhood", "type")


def count_reviewed_observations(path: Path) -> int:
    """
    Rows with at least one human-validated field.

    Counts dual-reviewer consensus or human_*_ok when present.
    """
    if not path.exists():
        return 0
    with path.open(encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    if not rows:
        return 0

    dual = "price_consensus" in rows[0] or "price_r1" in rows[0]
    count = 0
    for row in rows:
        if dual:
            if any(row.get(f"{f}_consensus", "").strip() for f in REVIEW_FIELDS):
                count += 1
                continue
            if any(
                row.get(f"{f}_r1", "").strip() and row.get(f"{f}_r2", "").strip()
                for f in REVIEW_FIELDS
            ):
                count += 1
        else:
            if any(row.get(f"human_{f}_ok", "").strip() for f in REVIEW_FIELDS):
                count += 1
    return count


def evidence_conversion_rate(
    structural_claims: int,
    reviewed_observations: int,
) -> float | None:
    """ECR = published structural claims / manually reviewed observations."""
    if reviewed_observations <= 0:
        return None
    return round(structural_claims / reviewed_observations, 4)
