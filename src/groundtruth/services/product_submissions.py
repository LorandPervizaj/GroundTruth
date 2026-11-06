"""Product submission persistence backends."""

from __future__ import annotations

import hashlib
import json
import threading
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from sqlalchemy import text

from groundtruth.config import get_settings
from groundtruth.database.session import get_session_factory
from groundtruth.models.product import ProductSubmission


class DuplicateSubmission(Exception):
    """Raised when an identical submission arrives within the dedupe window."""


_dedupe_lock = threading.Lock()
_recent_hashes: dict[str, float] = {}


def _jsonl_path(kind: str) -> Path:
    return get_settings().product_log_dir / f"{kind}.jsonl"


def _submission_fingerprint(kind: str, payload: dict[str, Any]) -> str:
    canonical = json.dumps({"kind": kind, **payload}, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _remember_or_reject(fingerprint: str, *, window_seconds: int) -> float:
    now = time.monotonic()
    with _dedupe_lock:
        expired = [key for key, ts in _recent_hashes.items() if now - ts > window_seconds]
        for key in expired:
            _recent_hashes.pop(key, None)
        previous = _recent_hashes.get(fingerprint)
        if previous is not None and now - previous <= window_seconds:
            raise DuplicateSubmission(fingerprint)
        _recent_hashes[fingerprint] = now
    return now


def clear_submission_dedupe_cache() -> None:
    with _dedupe_lock:
        _recent_hashes.clear()


def append_product_submission(kind: str, payload: dict[str, Any]) -> None:
    """Persist a public product submission using the configured backend.

    Raises DuplicateSubmission for identical payloads within the configured window.
    Raises on database/IO failure so callers do not report false durable success.
    """
    settings = get_settings()
    if settings.product_write_backend == "azure_table":
        from groundtruth.services.table_submissions import active_store

        active_store().append(
            kind, payload, window_seconds=max(0, int(settings.product_submission_dedupe_seconds))
        )
        return
    window = max(0, int(settings.product_submission_dedupe_seconds))
    fingerprint = _submission_fingerprint(kind, payload)
    reservation = None
    if window > 0:
        reservation = _remember_or_reject(fingerprint, window_seconds=window)

    try:
        _persist_product_submission(kind, payload)
    except Exception:
        # A failed durable write must remain retryable, never a successful duplicate.
        with _dedupe_lock:
            if reservation is not None and _recent_hashes.get(fingerprint) == reservation:
                _recent_hashes.pop(fingerprint, None)
        raise


def _persist_product_submission(kind: str, payload: dict[str, Any]) -> None:
    settings = get_settings()

    row = {
        "ts": datetime.now(UTC).isoformat(),
        **payload,
    }
    if settings.product_write_backend == "database":
        session = get_session_factory()()
        try:
            window = max(0, int(settings.product_submission_dedupe_seconds))
            if window:
                fingerprint = _submission_fingerprint(kind, payload)
                # One transaction-wide lock serializes identical submissions across
                # processes/revisions; durable state remains authoritative after restart.
                lock_key = int.from_bytes(bytes.fromhex(fingerprint)[:8], signed=True)
                session.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": lock_key})
                stored_payload = "payload" if "ts" in payload else "(payload - 'ts')"
                duplicate = session.execute(
                    text(
                        "SELECT id FROM product_submissions WHERE kind=:kind "
                        "AND created_at >= :cutoff AND "
                        + stored_payload
                        + " = CAST(:payload AS jsonb) LIMIT 1"
                    ),
                    {
                        "kind": kind,
                        "cutoff": datetime.now(UTC) - timedelta(seconds=window),
                        "payload": json.dumps(payload, sort_keys=True, ensure_ascii=False),
                    },
                ).scalar()
                if duplicate is not None:
                    raise DuplicateSubmission(fingerprint)
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
