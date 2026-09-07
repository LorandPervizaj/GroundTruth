"""Tests for product analytics aggregation."""

from datetime import UTC, datetime, timedelta

from groundtruth.services.product_metrics import build_product_analytics_snapshot


def _event(name: str, **extra) -> dict:
    return {
        "ts": datetime.now(UTC).isoformat(),
        "event": name,
        "visitor_id": extra.pop("visitor_id", "visitor-1"),
        **extra,
    }


def test_build_snapshot_counts_core_funnels() -> None:
    now = datetime.now(UTC)
    events = [
        {**_event("valuation_requested", listing_type="rent"), "ts": now.isoformat()},
        {
            **_event(
                "valuation_completed",
                listing_type="rent",
                confidence_tier="Medium",
                response_time_ms=420,
            ),
            "ts": now.isoformat(),
        },
        {**_event("market_page_viewed", neighborhood="Ulpiana"), "ts": now.isoformat()},
        {
            **_event("search_performed", results_count=2, query_length=5),
            "ts": now.isoformat(),
        },
        {**_event("zero_results", query_length=4), "ts": now.isoformat()},
        {**_event("rent_yield_viewed"), "ts": now.isoformat()},
        {**_event("report_downloaded", report_type="annual_pdf"), "ts": now.isoformat()},
        {
            **_event("market_view", neighborhood="Arberia", visitor_id="visitor-2"),
            "ts": (now - timedelta(days=1)).isoformat(),
        },
    ]
    snap = build_product_analytics_snapshot(events, window_days=7)
    assert snap.event_count == 8
    assert snap.valuations_requested == 1
    assert snap.valuations_completed == 1
    assert snap.market_page_views == 2
    assert snap.searches_performed == 1
    assert snap.zero_result_searches == 1
    assert snap.rent_yield_views == 1
    assert snap.report_downloads == 1
    assert snap.wau == 2
    assert snap.avg_valuation_response_ms == 420.0
    assert snap.confidence_tier_counts.get("medium") == 1


def test_legacy_event_aliases_normalized() -> None:
    events = [
        _event("valuation_search"),
        _event("valuation_success", confidence_tier="High"),
    ]
    snap = build_product_analytics_snapshot(events, window_days=7)
    assert snap.valuations_requested == 1
    assert snap.valuations_completed == 1
