"""Best-effort private notifications for public Metrik submissions."""

from __future__ import annotations

import os
from typing import Any

import httpx

from groundtruth.logging import get_logger

logger = get_logger(__name__)

_LABELS = {
    "contact": "Contact message",
    "public_reports": "Public problem report",
    "listing_submissions": "Listing submission",
    "feedback": "Data feedback",
    "alerts": "Price-alert request",
}


def _format_value(value: Any) -> str:
    text = str(value).replace("\r", " ").strip()
    return text[:800] + ("…" if len(text) > 800 else "")


def format_product_submission(kind: str, payload: dict[str, Any]) -> str:
    """Create a compact plain-text owner notification."""
    lines = [f"📨 Metrik — {_LABELS.get(kind, kind.replace('_', ' ').title())}"]
    for key, value in payload.items():
        if value is None or value == "":
            continue
        lines.append(f"{key.replace('_', ' ').title()}: {_format_value(value)}")
    return "\n".join(lines)[:3900]


def notify_product_submission(kind: str, payload: dict[str, Any]) -> bool:
    """Send a submission to the one configured owner chat without affecting persistence."""
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    owner_chat_id = os.getenv("TELEGRAM_CHAT_ID")
    if not token or not owner_chat_id:
        return False
    try:
        response = httpx.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            data={
                "chat_id": owner_chat_id,
                "text": format_product_submission(kind, payload),
                "disable_web_page_preview": "true",
            },
            timeout=5.0,
        )
        response.raise_for_status()
        return True
    except (httpx.HTTPError, OSError):
        logger.exception("product_submission_telegram_failed", submission_kind=kind)
        return False
