"""Background comparables cache warm-up — non-blocking API startup."""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass

from groundtruth.logging import get_logger

logger = get_logger(__name__)


@dataclass
class ComparablesWarmState:
    started_at: float | None = None
    finished_at: float | None = None
    error: str | None = None
    rent_rows: int = 0
    sale_rows: int = 0
    duration_ms: float | None = None


_state = ComparablesWarmState()
_lock = threading.Lock()
_warm_thread: threading.Thread | None = None


def comparables_warm_state() -> ComparablesWarmState:
    with _lock:
        return ComparablesWarmState(
            started_at=_state.started_at,
            finished_at=_state.finished_at,
            error=_state.error,
            rent_rows=_state.rent_rows,
            sale_rows=_state.sale_rows,
            duration_ms=_state.duration_ms,
        )


def _run_warm() -> None:
    global _state
    t0 = time.perf_counter()
    try:
        from groundtruth.analytics.valuation import _load_comparables_pair
        from groundtruth.database.session import get_session_factory

        session = get_session_factory()()
        try:
            rent_df, sale_df = _load_comparables_pair(session)
            rent_n = len(rent_df)
            sale_n = len(sale_df)
        finally:
            session.close()
        elapsed_ms = (time.perf_counter() - t0) * 1000
        with _lock:
            _state.rent_rows = rent_n
            _state.sale_rows = sale_n
            _state.duration_ms = elapsed_ms
            _state.finished_at = time.perf_counter()
        logger.info(
            "comparables_cache_warmed",
            rent_rows=rent_n,
            sale_rows=sale_n,
            duration_ms=round(elapsed_ms, 1),
        )
    except Exception as exc:
        elapsed_ms = (time.perf_counter() - t0) * 1000
        with _lock:
            _state.error = str(exc) or type(exc).__name__
            _state.duration_ms = elapsed_ms
            _state.finished_at = time.perf_counter()
        logger.exception("comparables_cache_warm_failed")


def start_background_comparables_warm() -> None:
    """Kick off comparables warm in a daemon thread (idempotent)."""
    global _warm_thread, _state
    from groundtruth.analytics.valuation import comparables_cache_ready

    if comparables_cache_ready():
        return
    with _lock:
        if _warm_thread is not None and _warm_thread.is_alive():
            return
        if _state.finished_at is not None and _state.error is None:
            return
        _state = ComparablesWarmState(started_at=time.perf_counter())
        _warm_thread = threading.Thread(target=_run_warm, name="comparables-warm", daemon=True)
        _warm_thread.start()
