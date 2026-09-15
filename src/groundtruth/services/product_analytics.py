"""Anonymous product event persistence for v1.0 user research."""

from __future__ import annotations

from starlette.requests import Request

from groundtruth.schemas.product_analytics import ProductEvent
from groundtruth.services.product_submissions import (
    DuplicateSubmission,
    append_product_submission,
)

_DEFAULT_MUNICIPALITY = "Prishtina"


def enrich_product_event(event: ProductEvent, request: Request | None = None) -> ProductEvent:
    """Fill anonymous context defaults before persistence."""
    updates: dict = {}
    if not event.municipality:
        updates["municipality"] = _DEFAULT_MUNICIPALITY
    if request is not None and not event.visitor_id:
        visitor = request.headers.get("X-Visitor-Id")
        if visitor:
            updates["visitor_id"] = visitor[:64]
    if event.listing_type is None and event.valuation_type:
        updates["listing_type"] = event.valuation_type
    if updates:
        return event.model_copy(update=updates)
    return event


def log_product_event(event: ProductEvent, request: Request | None = None) -> None:
    """Persist an anonymous product event.

    DuplicateSubmission is swallowed: analytics dedupe must not fail the user request
    (contact/alerts routes handle DuplicateSubmission explicitly instead).
    """
    try:
        append_product_submission(
            "events", enrich_product_event(event, request).model_dump(exclude_none=True)
        )
    except DuplicateSubmission:
        return
