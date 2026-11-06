"""Analytics event logging must not fail user requests on dedupe."""

from __future__ import annotations

from unittest.mock import patch

from groundtruth.schemas.product_analytics import ProductEvent
from groundtruth.services.product_analytics import log_product_event
from groundtruth.services.product_submissions import DuplicateSubmission


def test_log_product_event_swallows_duplicate_submission() -> None:
    event = ProductEvent(event="valuation_requested", neighborhood="Ulpiana", area_sqm=70)
    with patch(
        "groundtruth.services.product_analytics.append_product_submission",
        side_effect=DuplicateSubmission("fp"),
    ):
        log_product_event(event)  # must not raise


def test_only_authenticated_search_probe_suppresses_test_telemetry(monkeypatch):
    from starlette.requests import Request

    from groundtruth.config import get_settings

    monkeypatch.setattr(get_settings(), "health_check_token", "controlled-test-token")
    for token, suppressed in [("wrong", False), ("controlled-test-token", True)]:
        request = Request(
            {
                "type": "http",
                "method": "GET",
                "scheme": "https",
                "path": "/api/search",
                "query_string": b"",
                "headers": [
                    (b"x-health-token", token.encode()),
                    (b"x-metrik-deployment-probe", b"1"),
                ],
            }
        )
        with patch("groundtruth.services.product_analytics.append_product_submission") as append:
            log_product_event(ProductEvent(event="search_performed"), request)
            assert append.called is (not suppressed)
