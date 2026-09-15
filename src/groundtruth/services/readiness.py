"""Shared readiness evaluation for /api/ready and ops checks."""

from __future__ import annotations

from typing import Any

from groundtruth.analytics.valuation import comparables_cache_ready
from groundtruth.config import Settings
from groundtruth.services.artifact_integrity import get_artifact_integrity_state
from groundtruth.services.lookup_cache import cache_is_loaded


def evaluate_readiness(settings: Settings) -> dict[str, Any]:
    """Return a machine-readable readiness payload.

    ``ok`` is True only when every required production dependency is healthy.
    Development stays permissive so local work does not require release bundles.
    """
    lookup_cache = cache_is_loaded()
    comparables_ready = comparables_cache_ready()
    integrity = get_artifact_integrity_state()
    reasons: list[str] = []

    require_artifacts = (not settings.is_development) and settings.api_require_lookup_cache
    if require_artifacts:
        if not lookup_cache:
            reasons.append("lookup_cache_not_loaded")
        if not comparables_ready:
            reasons.append("comparables_not_ready")
        if not integrity.verified:
            reasons.append("artifacts_unverified")
            if integrity.error:
                reasons.append(f"artifact_error:{integrity.error}")

    db_ok: bool | None = None
    if require_artifacts:
        db_ok = _database_reachable()
        if not db_ok:
            reasons.append("database_unavailable")

    ok = not reasons
    payload: dict[str, Any] = {"ok": ok}
    if reasons:
        payload["reasons"] = reasons
    return payload


def _database_reachable() -> bool:
    try:
        from sqlalchemy import text

        from groundtruth.database.session import get_session_factory

        session = get_session_factory()()
        try:
            session.execute(text("SELECT 1"))
            return True
        finally:
            session.close()
    except Exception:
        return False
