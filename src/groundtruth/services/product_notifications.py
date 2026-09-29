"""Best-effort private notifications for public Metrik submissions."""

from __future__ import annotations

import json
import os
from typing import Any

import httpx

from groundtruth.config import PROJECT_ROOT
from groundtruth.logging import get_logger

logger = get_logger(__name__)

_LABELS = {
    "contact": "Contact message",
    "public_reports": "Public problem report",
    "listing_submissions": "Listing submission",
    "feedback": "Data feedback",
    "alerts": "Price-alert request",
    "bot_reply": "Bot reply",
    "scrape": "Scrape update",
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


def telegram_command_reply(command: str) -> str:
    """Return safe, read-only Metrik status text for an owner bot command."""
    manifest_path = PROJECT_ROOT / "reports" / "generated" / "lookup_cache" / "manifest.json"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        manifest = {}
    release = manifest.get("release") or {}
    qa = manifest.get("statistical_qa") or {}
    release_id = release.get("release_id") or "not available"
    data_through = release.get("data_through") or "not available"
    qa_status = qa.get("status") or release.get("qa_decision") or "not available"
    source_sha = release.get("source_git_sha") or os.getenv("GROUNDTRUTH_SOURCE_GIT_SHA", "unknown")

    normalized = command.lower().split("@", 1)[0]
    if normalized in {"/start", "/help"}:
        return (
            "Metrik owner bot\n"
            "/status - Current service and release status\n"
            "/latest - Latest verified release\n"
            "/sources - Source-monitoring information\n"
            "/quality - Latest data-quality result\n"
            "/deployment - Current release and source revision\n"
            "/scrape - Current or latest GroundTruth research run\n"
            "/scrape_start - Start the weekly research workflow\n"
            "/scrape_stop - Cancel a running research workflow\n"
            "Research and deployment report start, release, deployment, failure, and rollback here.\n"
            "Contact, feedback, reports, and listing submissions arrive here automatically.\n"
            "/help - Show these commands"
        )
    if normalized == "/status":
        return f"✅ Metrik is online\nRelease: {release_id}\nData through: {data_through}\nQA: {qa_status}"
    if normalized == "/latest":
        return f"Latest verified release: {release_id}\nData through: {data_through}"
    if normalized == "/quality":
        return f"Latest data-quality result: {qa_status}\nRelease: {release_id}"
    if normalized == "/deployment":
        return f"Production release: {release_id}\nSource revision: {source_sha}"
    if normalized == "/sources":
        return (
            "Detailed source health is private to the research pipeline. "
            "The bot sends its source summary after each weekly run."
        )
    return "Unknown command. Send /help to see available commands."


def handle_telegram_update(update: dict[str, Any]) -> bool:
    """Reply only when an incoming command belongs to the configured owner chat."""
    message = update.get("message")
    if not isinstance(message, dict):
        return False
    chat = message.get("chat")
    if not isinstance(chat, dict):
        return False
    owner_chat_id = os.getenv("TELEGRAM_CHAT_ID")
    if not owner_chat_id or str(chat.get("id")) != owner_chat_id:
        logger.warning("telegram_command_rejected_non_owner")
        return False
    text = str(message.get("text") or "").strip()
    if not text.startswith("/"):
        return False
    return notify_product_submission("bot_reply", {"message": owner_command_reply(text)})


def owner_command_reply(text: str) -> str:
    """Run an owner command. Scrape commands can start or cancel the research workflow."""
    from groundtruth.services.scrape_control import scrape_snapshot, start_scrape, stop_scrape

    parts = text.strip().split()
    command = parts[0].lower().split("@", 1)[0]
    if command in {"/scrape", "/scrape_status"}:
        return scrape_snapshot()[1]
    if command == "/scrape_start":
        return start_scrape()
    if command == "/scrape_stop":
        return stop_scrape()
    if command in {"/auto_update", "/automatic_update"}:
        return (
            "Automatic scrape updates were retired. The research and deployment workflows "
            "now message this chat when they start, publish, deploy, fail, or roll back."
        )
    return telegram_command_reply(command)
