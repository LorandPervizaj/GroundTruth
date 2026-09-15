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
