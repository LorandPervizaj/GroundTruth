"""Public product write endpoints (feedback, alerts, contact, events, lang)."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from groundtruth.api.deps import rate_limit
from groundtruth.api.security import limiter, log_api_abuse
from groundtruth.config import get_settings
from groundtruth.schemas.alerts import SavedAlertRequest
from groundtruth.schemas.contact import (
    ContactRequest,
    ListingSubmissionRequest,
    PublicReportRequest,
)
from groundtruth.schemas.feedback import DataFeedbackRequest
from groundtruth.schemas.product_analytics import ProductEvent
from groundtruth.services.alerts import log_price_alert
from groundtruth.services.feedback import log_data_feedback
from groundtruth.services.product_analytics import log_product_event
from groundtruth.services.product_notifications import notify_product_submission
from groundtruth.services.product_submissions import (
    DuplicateSubmission,
    append_product_submission,
)

router = APIRouter(tags=["product-writes"])

_ALERTS_UNAVAILABLE = {
    "status": "unavailable",
    "detail": (
        "Email price alerts are not available yet. "
        "Use the local watchlist on this page; we are not collecting emails for alerts."
    ),
}


class LangPreference(BaseModel):
    lang: Literal["sq", "en"]


def _require_json_content_type(request: Request) -> None:
    content_type = (request.headers.get("content-type") or "").split(";")[0].strip().lower()
    if content_type != "application/json":
        log_api_abuse(
            reason="invalid_content_type",
            path=request.url.path,
            client_ip=request.client.host if request.client else None,
            content_type=content_type or None,
        )
        raise HTTPException(status_code=415, detail="Content-Type must be application/json")


def _persist(kind: str, payload: dict) -> dict[str, str]:
    try:
        append_product_submission(kind, payload)
    except DuplicateSubmission:
        return {"status": "duplicate"}
    except Exception:
        raise HTTPException(
            status_code=503,
            detail="Unable to persist submission. Try again later.",
        ) from None
    notify_product_submission(kind, payload)
    return {"status": "ok"}


@router.post("/api/events")
@limiter.limit(rate_limit("api_rate_limit_events"))
def track_event(request: Request, event: ProductEvent) -> dict[str, str]:
    _require_json_content_type(request)
    log_product_event(event, request)
    return {"status": "ok"}


@router.post("/api/feedback")
@limiter.limit(rate_limit("api_rate_limit_feedback"))
def submit_feedback(request: Request, feedback: DataFeedbackRequest) -> dict[str, str]:
    _require_json_content_type(request)
    try:
        log_data_feedback(feedback)
    except DuplicateSubmission:
        return {"status": "duplicate"}
    except Exception:
        raise HTTPException(
            status_code=503,
            detail="Unable to persist submission. Try again later.",
        ) from None
    notify_product_submission("feedback", feedback.model_dump(exclude_none=True))
    return {"status": "ok"}


@router.post("/api/alerts")
@limiter.limit(rate_limit("api_rate_limit_alerts"))
def submit_alert(request: Request, alert: SavedAlertRequest) -> JSONResponse:
    """Alert signup — closed until automated notifications exist."""
    _require_json_content_type(request)
    settings = get_settings()
    if not settings.alerts_signup_enabled:
        return JSONResponse(status_code=503, content=_ALERTS_UNAVAILABLE)
    try:
        log_price_alert(alert)
    except DuplicateSubmission:
        return JSONResponse(content={"status": "duplicate"})
    except Exception:
        raise HTTPException(
            status_code=503,
            detail="Unable to persist submission. Try again later.",
        ) from None
    notify_product_submission("alerts", alert.model_dump(exclude_none=True))
    return JSONResponse(content={"status": "ok"})


@router.post("/api/contact")
@limiter.limit(rate_limit("api_rate_limit_contact"))
def submit_contact(request: Request, contact: ContactRequest) -> dict[str, str]:
    _require_json_content_type(request)
    return _persist("contact", contact.model_dump(exclude_none=True))


@router.post("/api/public-report")
@limiter.limit(rate_limit("api_rate_limit_contact"))
def submit_public_report(request: Request, report: PublicReportRequest) -> dict[str, str]:
    _require_json_content_type(request)
    return _persist("public_reports", report.model_dump(exclude_none=True))


@router.post("/api/listing-submissions")
@limiter.limit(rate_limit("api_rate_limit_contact"))
def submit_listing_submission(
    request: Request,
    listing: ListingSubmissionRequest,
) -> dict[str, str]:
    _require_json_content_type(request)
    return _persist("listing_submissions", listing.model_dump(exclude_none=True))


@router.post("/api/lang")
@limiter.limit(rate_limit("api_rate_limit_lang"))
def set_language(request: Request, pref: LangPreference) -> JSONResponse:
    """Persist UI language in a session cookie (expires when browser closes)."""
    if pref.lang not in ("sq", "en"):
        raise HTTPException(status_code=400, detail="lang must be sq or en")
    response = JSONResponse({"lang": pref.lang})
    settings = get_settings()
    response.set_cookie(
        "metrik_lang",
        pref.lang,
        path="/",
        httponly=True,
        samesite="lax",
        secure=not settings.is_development,
    )
    return response
