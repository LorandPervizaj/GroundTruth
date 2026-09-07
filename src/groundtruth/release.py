"""Release artifact build and verification helpers."""

from __future__ import annotations

import json
from pathlib import Path

from groundtruth.analytics.annual_export import DEFAULT_ANNUAL_REPORT_PATH, export_annual_report
from groundtruth.analytics.valuation import (
    COMPARABLES_META_FILE,
    RENT_COMPARABLES_FILE,
    SALE_COMPARABLES_FILE,
)
from groundtruth.database.session import get_session_factory
from groundtruth.services.lookup_cache import build_lookup_cache, lookup_cache_dir


def build_release_artifacts() -> tuple[Path, Path]:
    """Build lookup/comparables and statistics artifacts from the current DB."""
    from sqlalchemy import text

    session = get_session_factory()()
    try:
        session.execute(text("SET statement_timeout = '0'"))
        session.execute(text("SET lock_timeout = '0'"))
        lookup_manifest = build_lookup_cache(session)
        annual_path = export_annual_report(session)
    finally:
        session.close()
    return lookup_manifest, annual_path


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def verify_release_artifacts() -> list[str]:
    """Validate required public release artifacts and return status lines."""
    out: list[str] = []
    base = lookup_cache_dir()
    manifest_path = base / "manifest.json"
    if not manifest_path.is_file():
        raise FileNotFoundError(f"missing lookup cache manifest: {manifest_path}")
    manifest = _read_json(manifest_path)
    entries = manifest.get("entries")
    if not isinstance(entries, list) or not entries:
        raise ValueError("lookup cache manifest has no entries")

    missing = []
    for entry in entries:
        rel = entry.get("path")
        if not rel or not (base / rel).is_file():
            missing.append(rel or "<missing path>")
    if missing:
        raise FileNotFoundError(
            f"lookup cache references missing files ({len(missing)}): {missing[:5]}"
        )

    for filename in (COMPARABLES_META_FILE, RENT_COMPARABLES_FILE, SALE_COMPARABLES_FILE):
        path = base / filename
        if not path.is_file():
            raise FileNotFoundError(f"missing comparables artifact: {path}")

    annual_path = DEFAULT_ANNUAL_REPORT_PATH
    if not annual_path.is_file():
        raise FileNotFoundError(f"missing annual report artifact: {annual_path}")
    annual_payload = _read_json(annual_path)
    if not annual_payload.get("generated_at"):
        raise ValueError("annual report missing generated_at")

    out.append(f"lookup_cache_ok entries={len(entries)} path={manifest_path}")
    out.append(f"annual_report_ok path={annual_path}")
    return out
