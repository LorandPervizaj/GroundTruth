"""Small public API latency smoke test for a deployed Metrik instance."""

from __future__ import annotations

import argparse
import statistics
import time
from collections.abc import Iterable

import httpx


def _time_request(client: httpx.Client, method: str, path: str, **kwargs) -> float:
    t0 = time.perf_counter()
    response = client.request(method, path, **kwargs)
    elapsed_ms = (time.perf_counter() - t0) * 1000
    response.raise_for_status()
    return elapsed_ms


def _summary(values: Iterable[float]) -> str:
    vals = sorted(values)
    if not vals:
        return "no samples"
    p95 = vals[min(len(vals) - 1, int(len(vals) * 0.95))]
    return f"p50={statistics.median(vals):.1f}ms p95={p95:.1f}ms max={max(vals):.1f}ms"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--iterations", type=int, default=10)
    parser.add_argument("--market", default="/api/lookup/neighborhood/ulpiana")
    args = parser.parse_args()

    checks = {
        "ready": ("GET", "/api/ready", {}),
        "meta": ("GET", "/api/meta", {}),
        "search": ("GET", "/api/search?q=ulp", {}),
        "lookup": ("GET", args.market, {}),
        "compare": ("GET", "/api/compare?neighborhoods=ulpiana,arberia", {}),
    }
    with httpx.Client(base_url=args.base_url, timeout=10.0) as client:
        for label, (method, path, kwargs) in checks.items():
            samples = [
                _time_request(client, method, path, **kwargs) for _ in range(args.iterations)
            ]
            print(f"{label}: {_summary(samples)}")


if __name__ == "__main__":
    main()
