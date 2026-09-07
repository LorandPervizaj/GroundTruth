"""Listing health signals from observation lifecycle."""

from __future__ import annotations

from typing import Any

STALE_DOM_DAYS = 60
LONG_DOM_DAYS = 45


def listing_health_signals(
    *,
    days_on_market: int | None,
    price_changed: bool | None,
    observation_count: int | None = None,
) -> list[str]:
    signals: list[str] = []
    if days_on_market is not None:
        if days_on_market >= STALE_DOM_DAYS:
            signals.append("stale")
        elif days_on_market >= LONG_DOM_DAYS:
            signals.append("long_dom")
    if price_changed:
        signals.append("price_reduced")
    if (
        observation_count is not None
        and observation_count >= 4
        and days_on_market
        and days_on_market >= 30
    ):
        signals.append("tracked")
    return signals


def segment_health_summary(lifecycle_entries: list[dict[str, Any]]) -> dict[str, Any]:
    if not lifecycle_entries:
        return {
            "median_days_on_market": None,
            "stale_count": 0,
            "price_reduced_count": 0,
            "tracked_listings": 0,
        }
    dom_values = [
        e["days_on_market"] for e in lifecycle_entries if e.get("days_on_market") is not None
    ]
    stale = sum(1 for e in lifecycle_entries if (e.get("days_on_market") or 0) >= STALE_DOM_DAYS)
    reduced = sum(1 for e in lifecycle_entries if e.get("price_changed"))
    return {
        "median_days_on_market": int(sorted(dom_values)[len(dom_values) // 2])
        if dom_values
        else None,
        "stale_count": stale,
        "price_reduced_count": reduced,
        "tracked_listings": len(lifecycle_entries),
    }
