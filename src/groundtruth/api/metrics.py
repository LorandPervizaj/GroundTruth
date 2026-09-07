"""Lightweight in-process request metrics (no external deps required)."""

from __future__ import annotations

import threading
from dataclasses import dataclass, field

_lock = threading.Lock()


@dataclass
class RequestMetrics:
    total_requests: int = 0
    total_errors: int = 0
    by_status: dict[int, int] = field(default_factory=dict)
    by_path_prefix: dict[str, int] = field(default_factory=dict)


_metrics = RequestMetrics()


def record_request(*, path: str, status_code: int) -> None:
    prefix = _path_prefix(path)
    with _lock:
        _metrics.total_requests += 1
        if status_code >= 500:
            _metrics.total_errors += 1
        _metrics.by_status[status_code] = _metrics.by_status.get(status_code, 0) + 1
        _metrics.by_path_prefix[prefix] = _metrics.by_path_prefix.get(prefix, 0) + 1


def metrics_snapshot() -> dict:
    with _lock:
        return {
            "total_requests": _metrics.total_requests,
            "total_errors": _metrics.total_errors,
            "by_status": dict(sorted(_metrics.by_status.items())),
            "by_path_prefix": dict(sorted(_metrics.by_path_prefix.items())),
        }


def _path_prefix(path: str) -> str:
    if path.startswith("/api/lookup/"):
        return "/api/lookup/*"
    if path.startswith("/api/"):
        parts = path.strip("/").split("/")
        if len(parts) >= 2:
            return f"/api/{parts[1]}"
    if path.startswith("/static/"):
        return "/static/*"
    return path if path in ("/", "/market") else path.rsplit("/", 1)[0] or path
