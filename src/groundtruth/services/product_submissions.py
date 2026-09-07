"""Product submission persistence backends."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from groundtruth.config import get_settings
from groundtruth.database.session import get_session_factory
from groundtruth.models.product import ProductSubmission


def _jsonl_path(kind: str) -> Path:
    return get_settings().product_log_dir / f"{kind}.jsonl"


def append_product_submission(kind: str, payload: dict[str, Any]) -> None:
    """Persist a public product submission using the configured backend."""
    row = {
        "ts": datetime.now(UTC).isoformat(),
        **payload,
    }
    settings = get_settings()
    if settings.product_write_backend == "database":
        session = get_session_factory()()
        try:
            session.add(ProductSubmission(kind=kind, payload=row))
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()
        return

    path = _jsonl_path(kind)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=False) + "\n")
