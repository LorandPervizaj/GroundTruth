"""Capture failed neighborhood extractions for future ML training."""

from __future__ import annotations

import csv
from pathlib import Path

from groundtruth.config import get_settings

COLUMNS = [
    "source_listing_id",
    "raw_text",
    "regex_result",
    "gazetteer_result",
    "correct_label",
]


def failures_path() -> Path:
    return get_settings().gazetteer_dir.parent / "training" / "neighborhood_failures.csv"


def log_neighborhood_failure(
    *,
    source_listing_id: str,
    raw_text: str,
    regex_result: str | None,
    gazetteer_result: str | None,
) -> None:
    """Append one failure row. correct_label is left empty for manual labeling."""
    path = failures_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    write_header = not path.exists()
    with path.open("a", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=COLUMNS)
        if write_header:
            writer.writeheader()
        writer.writerow(
            {
                "source_listing_id": source_listing_id,
                "raw_text": raw_text[:2000],
                "regex_result": regex_result or "",
                "gazetteer_result": gazetteer_result or "",
                "correct_label": "",
            }
        )
