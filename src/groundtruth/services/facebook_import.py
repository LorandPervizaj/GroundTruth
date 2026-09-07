"""Import manual Facebook Marketplace captures into informal quarantine store."""

from __future__ import annotations

import json
from pathlib import Path

from groundtruth.config import PROJECT_ROOT
from groundtruth.processing.parsers.facebook_marketplace import parse_marketplace_capture
from groundtruth.schemas.facebook import FacebookMarketplaceCapture, InformalListingRecord

INFORMAL_LISTINGS_PATH = PROJECT_ROOT / "data" / "sources" / "facebook" / "informal_listings.jsonl"


def _load_existing_urls(path: Path) -> set[str]:
    if not path.exists():
        return set()
    urls: set[str] = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
            url = row.get("original_url")
            if url:
                urls.add(str(url))
        except json.JSONDecodeError:
            continue
    return urls


def import_marketplace_jsonl(
    input_path: Path,
    *,
    output_path: Path | None = None,
) -> dict[str, int]:
    """Parse JSONL batch and append new informal listings (dedupe by URL)."""
    out = output_path or INFORMAL_LISTINGS_PATH
    out.parent.mkdir(parents=True, exist_ok=True)
    seen = _load_existing_urls(out)

    imported = 0
    skipped = 0
    failed = 0
    new_rows: list[InformalListingRecord] = []

    for _line_no, line in enumerate(input_path.read_text(encoding="utf-8").splitlines(), start=1):
        line = line.strip()
        if not line:
            continue
        try:
            raw = json.loads(line)
            capture = FacebookMarketplaceCapture.model_validate(raw)
            record = parse_marketplace_capture(capture)
        except Exception:
            failed += 1
            continue
        if record.original_url in seen:
            skipped += 1
            continue
        seen.add(record.original_url)
        new_rows.append(record)
        imported += 1

    if new_rows:
        with out.open("a", encoding="utf-8") as fh:
            for row in new_rows:
                fh.write(json.dumps(row.model_dump(), ensure_ascii=False) + "\n")

    return {"imported": imported, "skipped": skipped, "failed": failed, "total": len(seen)}


def load_informal_listings(path: Path | None = None) -> list[dict]:
    target = path or INFORMAL_LISTINGS_PATH
    if not target.exists():
        return []
    rows: list[dict] = []
    for line in target.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return rows


def informal_listing_count(path: Path | None = None) -> int:
    return len(load_informal_listings(path))
