"""Export and load cached annual market report JSON."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from groundtruth.analytics.annual_report import build_annual_report_payload
from groundtruth.config import PROJECT_ROOT
from groundtruth.gazetteers.version import compute_gazetteer_version
from groundtruth.portals.registry import public_parser_placeholders

DEFAULT_ANNUAL_REPORT_PATH = PROJECT_ROOT / "data" / "api" / "annual_report.json"


def corpus_last_updated(session: Session) -> datetime | None:
    """When the active corpus was last processed (latest ETL run)."""
    row = session.execute(
        text(
            """
            SELECT created_at
            FROM etl_metrics
            ORDER BY id DESC
            LIMIT 1
            """
        )
    ).first()
    if row is None or row.created_at is None:
        return None
    return row.created_at


def corpus_data_revision(session: Session) -> str:
    """Fingerprint of latest ETL — statistics cache refreshes when this changes."""
    row = session.execute(
        text(
            """
            SELECT id, created_at, normalization_version
            FROM etl_metrics
            ORDER BY id DESC
            LIMIT 1
            """
        )
    ).first()
    if row is None:
        return "none"
    created = row.created_at.isoformat() if row.created_at else ""
    return f"{row.id}:{created}:{row.normalization_version}"


def finalize_annual_report_payload(
    payload: dict[str, Any],
    *,
    data_revision: str | None = None,
) -> dict[str, Any]:
    """Attach generation metadata for cache consumers and the public API."""
    gazetteer_version = compute_gazetteer_version()
    methodology = dict(payload.get("methodology") or {})
    methodology["gazetteer_version"] = gazetteer_version
    methodology["parser_versions"] = public_parser_placeholders()
    methodology["sources"] = public_parser_placeholders()
    return {
        **payload,
        "generated_at": datetime.now(UTC).replace(microsecond=0).isoformat(),
        "data_revision": data_revision,
        "methodology": methodology,
    }


def export_annual_report(
    session: Session,
    *,
    output: Path | None = None,
    max_age_months: int | None = None,
) -> Path:
    """Build the annual report and write it to ``data/api/annual_report.json``."""
    kwargs: dict[str, Any] = {}
    if max_age_months is not None:
        kwargs["max_age_months"] = max_age_months
    revision = corpus_data_revision(session)
    payload = finalize_annual_report_payload(
        build_annual_report_payload(session, **kwargs),
        data_revision=revision,
    )
    path = output or DEFAULT_ANNUAL_REPORT_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def load_annual_report_cache(path: Path | None = None) -> dict[str, Any] | None:
    """Load cached annual report JSON if present."""
    target = path or DEFAULT_ANNUAL_REPORT_PATH
    if not target.is_file():
        return None
    try:
        return json.loads(target.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
