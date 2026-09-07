"""Background corpus cache warm-up — non-blocking API startup."""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass

from groundtruth.logging import get_logger

logger = get_logger(__name__)


@dataclass
class CorpusWarmState:
    started_at: float | None = None
    finished_at: float | None = None
    error: str | None = None
    active_listings: int = 0
    raw_listings: int = 0
    duration_ms: float | None = None


_state = CorpusWarmState()
_lock = threading.Lock()
_warm_thread: threading.Thread | None = None


def is_corpus_warm() -> bool:
    with _lock:
        return _state.finished_at is not None and _state.error is None


def corpus_warm_state() -> CorpusWarmState:
    with _lock:
        return CorpusWarmState(
            started_at=_state.started_at,
            finished_at=_state.finished_at,
            error=_state.error,
            active_listings=_state.active_listings,
            raw_listings=_state.raw_listings,
            duration_ms=_state.duration_ms,
        )


def corpus_warm_in_progress() -> bool:
    with _lock:
        return _state.started_at is not None and _state.finished_at is None


def _run_warm() -> None:
    global _state
    t0 = time.perf_counter()
    try:
        from groundtruth.analytics.corpus import active_corpus_bundle
        from groundtruth.database.session import get_session_factory

        session = get_session_factory()()
        try:
            bundle = active_corpus_bundle(session)
            active_n = len(bundle.active)
            raw_n = len(bundle.deduped)
        finally:
            session.close()
        elapsed_ms = (time.perf_counter() - t0) * 1000
        with _lock:
            _state.active_listings = active_n
            _state.raw_listings = raw_n
            _state.duration_ms = elapsed_ms
            _state.finished_at = time.perf_counter()
        logger.info(
            "corpus_cache_warmed",
            active_listings=active_n,
            raw_listings=raw_n,
            duration_ms=round(elapsed_ms, 1),
        )
    except Exception as exc:
        elapsed_ms = (time.perf_counter() - t0) * 1000
        with _lock:
            _state.error = str(exc) or type(exc).__name__
            _state.duration_ms = elapsed_ms
            _state.finished_at = time.perf_counter()
        logger.exception("corpus_cache_warm_failed")


def start_background_corpus_warm() -> None:
    """Kick off corpus warm in a daemon thread (idempotent)."""
    global _warm_thread, _state
    with _lock:
        if _warm_thread is not None and _warm_thread.is_alive():
            return
        if _state.finished_at is not None and _state.error is None:
            return
        _state = CorpusWarmState(started_at=time.perf_counter())
        _warm_thread = threading.Thread(target=_run_warm, name="corpus-warm", daemon=True)
        _warm_thread.start()


def blocking_warm_corpus_cache() -> CorpusWarmState:
    """Synchronous warm (profiling / tests)."""
    _run_warm()
    return corpus_warm_state()
