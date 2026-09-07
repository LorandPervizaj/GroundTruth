"""Request timing middleware and cold-start metrics."""

from __future__ import annotations

import logging
import time
from collections import deque
from dataclasses import dataclass

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

logger = logging.getLogger(__name__)

_WARM_LOOKUP_LATENCIES_MS: deque[float] = deque(maxlen=500)
_WARM_VALUATE_LATENCIES_MS: deque[float] = deque(maxlen=500)
_LOOKUP_PATH = "/api/lookup/"
_VALUATE_PATH = "/api/valuate"


@dataclass
class LatencySnapshot:
    corpus_warm_ms: float | None = None
    warm_lookup_p50_ms: float | None = None
    warm_lookup_p95_ms: float | None = None
    warm_valuate_p50_ms: float | None = None
    warm_valuate_p95_ms: float | None = None
    sample_count: int = 0


def _percentile(values: list[float], pct: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    idx = min(len(ordered) - 1, int(len(ordered) * pct))
    return ordered[idx]


def record_warm_latency(path: str, elapsed_ms: float) -> None:
    if path.startswith(_LOOKUP_PATH):
        _WARM_LOOKUP_LATENCIES_MS.append(elapsed_ms)
    elif path == _VALUATE_PATH or path.startswith(_VALUATE_PATH):
        _WARM_VALUATE_LATENCIES_MS.append(elapsed_ms)


def latency_snapshot() -> LatencySnapshot:
    from groundtruth.api.corpus_warm import corpus_warm_state

    warm = corpus_warm_state()
    lookup_vals = list(_WARM_LOOKUP_LATENCIES_MS)
    valuate_vals = list(_WARM_VALUATE_LATENCIES_MS)
    snap = LatencySnapshot(
        corpus_warm_ms=warm.duration_ms,
        sample_count=len(lookup_vals) + len(valuate_vals),
    )
    if lookup_vals:
        snap.warm_lookup_p50_ms = _percentile(lookup_vals, 0.50)
        snap.warm_lookup_p95_ms = _percentile(lookup_vals, 0.95)
    if valuate_vals:
        snap.warm_valuate_p50_ms = _percentile(valuate_vals, 0.50)
        snap.warm_valuate_p95_ms = _percentile(valuate_vals, 0.95)
    return snap


class RequestTimingMiddleware(BaseHTTPMiddleware):
    """Log and expose per-request server time via X-Response-Time-ms."""

    async def dispatch(self, request: Request, call_next) -> Response:
        from groundtruth.api.metrics import record_request

        t0 = time.perf_counter()
        response = await call_next(request)
        elapsed_ms = (time.perf_counter() - t0) * 1000
        path = request.url.path
        response.headers["X-Response-Time-ms"] = f"{elapsed_ms:.1f}"
        record_request(path=path, status_code=response.status_code)
        if path.startswith(_LOOKUP_PATH) or path.startswith(_VALUATE_PATH):
            record_warm_latency(path, elapsed_ms)
            logger.info(
                "api_request_timing",
                extra={
                    "path": path,
                    "method": request.method,
                    "elapsed_ms": round(elapsed_ms, 1),
                    "status": response.status_code,
                },
            )
        return response
