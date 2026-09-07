"""Aggregate product events into PM-facing dashboard metrics."""

from __future__ import annotations

import contextlib
import json
from collections import Counter, defaultdict
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from groundtruth.config import get_settings
from groundtruth.schemas.product_analytics import ProductAnalyticsSnapshot, TopNeighborhoodRow

# Canonical event names (legacy aliases mapped in _normalize_event)
VALUATION_REQUESTED = "valuation_requested"
VALUATION_COMPLETED = "valuation_completed"
MARKET_PAGE_VIEWED = "market_page_viewed"
SEARCH_PERFORMED = "search_performed"
ZERO_RESULTS = "zero_results"
RENT_YIELD_VIEWED = "rent_yield_viewed"
REPORT_DOWNLOADED = "report_downloaded"

_EVENT_ALIASES: dict[str, str] = {
    "valuation_search": VALUATION_REQUESTED,
    "valuation_view": VALUATION_COMPLETED,
    "valuation_success": VALUATION_COMPLETED,
    "valuation_insufficient": "valuation_failed",
    "market_view": MARKET_PAGE_VIEWED,
    "market_search": SEARCH_PERFORMED,
    "market_search_select": "search_result_click",
    "compare_view": "compare_viewed",
}


def _normalize_event(name: str) -> str:
    return _EVENT_ALIASES.get(name, name)


def _parse_ts(raw: Any) -> datetime | None:
    if raw is None:
        return None
    if isinstance(raw, datetime):
        return raw if raw.tzinfo else raw.replace(tzinfo=UTC)
    try:
        return datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except ValueError:
        return None


def _load_events_jsonl(path: Path, *, since: datetime) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        ts = _parse_ts(row.get("ts"))
        if ts is None or ts < since:
            continue
        rows.append(row)
    return rows


def _load_events_db(session: Session, *, since: datetime) -> list[dict[str, Any]]:
    from groundtruth.models.product import ProductSubmission

    stmt = (
        select(ProductSubmission)
        .where(ProductSubmission.kind == "events")
        .where(ProductSubmission.created_at >= since)
        .order_by(ProductSubmission.created_at)
    )
    return [dict(row.payload) for row in session.execute(stmt).scalars().all()]


def load_product_events(
    *,
    days: int = 30,
    session: Session | None = None,
) -> list[dict[str, Any]]:
    """Load product events from DB or JSONL within the rolling window."""
    since = datetime.now(UTC) - timedelta(days=days)
    settings = get_settings()
    if settings.product_write_backend == "database":
        if session is None:
            from groundtruth.database.session import get_session_factory

            factory = get_session_factory()
            db = factory()
            try:
                return _load_events_db(db, since=since)
            finally:
                db.close()
        return _load_events_db(session, since=since)

    return _load_events_jsonl(settings.product_log_dir / "events.jsonl", since=since)


def build_product_analytics_snapshot(
    events: list[dict[str, Any]],
    *,
    window_days: int,
) -> ProductAnalyticsSnapshot:
    """Compute dashboard metrics from raw event rows."""
    if not events:
        return ProductAnalyticsSnapshot(
            window_days=window_days,
            event_count=0,
            dau=0,
            wau=0,
            repeat_visitor_rate_pct=None,
            valuations_per_day={},
            valuations_requested=0,
            valuations_completed=0,
            valuation_success_rate_pct=None,
            market_page_views=0,
            searches_performed=0,
            zero_result_searches=0,
            zero_result_rate_pct=None,
            rent_yield_views=0,
            report_downloads=0,
            top_neighborhoods=[],
            confidence_tier_counts={},
            avg_valuation_response_ms=None,
            listing_type_counts={},
        )

    visitor_days: dict[str, set[str]] = defaultdict(set)
    daily_visitors: dict[str, set[str]] = defaultdict(set)
    weekly_visitors: set[str] = set()
    nh_counter: Counter[str] = Counter()
    confidence_counter: Counter[str] = Counter()
    listing_counter: Counter[str] = Counter()
    valuations_by_day: Counter[str] = Counter()
    response_times: list[float] = []

    valuations_requested = 0
    valuations_completed = 0
    valuation_failures = 0
    market_page_views = 0
    searches_performed = 0
    zero_result_searches = 0
    rent_yield_views = 0
    report_downloads = 0

    for row in events:
        event = _normalize_event(str(row.get("event", "")))
        ts = _parse_ts(row.get("ts"))
        day_key = ts.date().isoformat() if ts else "unknown"
        visitor = str(row.get("visitor_id") or f"anon:{day_key}")

        daily_visitors[day_key].add(visitor)
        weekly_visitors.add(visitor)
        visitor_days[visitor].add(day_key)

        nh = row.get("neighborhood") or row.get("slug")
        if nh:
            nh_counter[str(nh)] += 1

        lt = row.get("listing_type") or row.get("valuation_type")
        if lt:
            listing_counter[str(lt).lower()] += 1

        conf = row.get("confidence_tier") or row.get("confidence")
        if conf:
            confidence_counter[str(conf).lower()] += 1

        if event == VALUATION_REQUESTED:
            valuations_requested += 1
            valuations_by_day[day_key] += 1
        elif event == VALUATION_COMPLETED:
            valuations_completed += 1
        elif event == "valuation_failed":
            valuation_failures += 1
        elif event == MARKET_PAGE_VIEWED:
            market_page_views += 1
        elif event == SEARCH_PERFORMED:
            searches_performed += 1
        elif event == ZERO_RESULTS:
            zero_result_searches += 1
        elif event == RENT_YIELD_VIEWED:
            rent_yield_views += 1
        elif event == REPORT_DOWNLOADED:
            report_downloads += 1

        rt = row.get("response_time_ms")
        if rt is not None and event in (VALUATION_COMPLETED, VALUATION_REQUESTED):
            with contextlib.suppress(TypeError, ValueError):
                response_times.append(float(rt))

    dau = max((len(v) for v in daily_visitors.values()), default=0)
    wau = len(weekly_visitors)
    repeat_visitors = sum(1 for days in visitor_days.values() if len(days) >= 2)
    repeat_rate = round(100.0 * repeat_visitors / wau, 1) if wau else None

    attempts = valuations_requested or (valuations_completed + valuation_failures)
    success_rate = round(100.0 * valuations_completed / attempts, 1) if attempts else None
    zero_rate = (
        round(100.0 * zero_result_searches / searches_performed, 1) if searches_performed else None
    )
    avg_rt = round(sum(response_times) / len(response_times), 1) if response_times else None

    top = [
        TopNeighborhoodRow(neighborhood=name, events=count)
        for name, count in nh_counter.most_common(15)
    ]

    return ProductAnalyticsSnapshot(
        window_days=window_days,
        event_count=len(events),
        dau=dau,
        wau=wau,
        repeat_visitor_rate_pct=repeat_rate,
        valuations_per_day=dict(sorted(valuations_by_day.items())),
        valuations_requested=valuations_requested,
        valuations_completed=valuations_completed,
        valuation_success_rate_pct=success_rate,
        market_page_views=market_page_views,
        searches_performed=searches_performed,
        zero_result_searches=zero_result_searches,
        zero_result_rate_pct=zero_rate,
        rent_yield_views=rent_yield_views,
        report_downloads=report_downloads,
        top_neighborhoods=top,
        confidence_tier_counts=dict(confidence_counter),
        avg_valuation_response_ms=avg_rt,
        listing_type_counts=dict(listing_counter),
    )


def product_analytics_snapshot(
    *, days: int = 30, session: Session | None = None
) -> ProductAnalyticsSnapshot:
    events = load_product_events(days=days, session=session)
    return build_product_analytics_snapshot(events, window_days=days)
