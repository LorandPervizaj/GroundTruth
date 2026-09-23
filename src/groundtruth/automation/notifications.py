"""Concise operational notifications. Secrets are read only from the environment."""

from __future__ import annotations

import os
from typing import Any

import httpx

from groundtruth.automation.models import PipelineRunResult


def format_pipeline_notification(result: PipelineRunResult) -> str:
    stages = {stage.name: stage for stage in result.stages}
    source = stages.get("source_health")
    quality = stages.get("data_quality")
    failed = next((stage for stage in result.stages if stage.status == "failed"), None)
    icon = "✅" if result.outcome == "verified" else "⚠️" if result.outcome == "warning" else "❌"
    lines = [
        f"{icon} GroundTruth weekly: {result.outcome.upper()}",
        f"Release: {result.release_id}",
        f"Run: {result.run_id}",
        f"Data through: {result.data_through or 'unknown'}",
    ]
    if source:
        lines.append(
            "Sources: "
            f"{source.counts.get('green', 0)} green / "
            f"{source.counts.get('yellow', 0)} yellow / "
            f"{source.counts.get('red', 0)} red"
        )
    if quality:
        lines.append(
            f"Normalized: {quality.counts.get('normalized', 0)}; "
            f"quarantined: {quality.counts.get('quarantined', 0)}"
        )
    if failed:
        lines.extend(
            [
                f"Failed stage: {failed.name}",
                f"Error: {(failed.error or 'unknown error')[:500]}",
                "Publication: blocked; previous production remains active.",
            ]
        )
    elif result.release_bundle:
        lines.append("Release verification: passed; bundle ready for deployment.")
    return "\n".join(lines)[:3800]


def send_telegram_message(
    message: str,
    *,
    token: str | None = None,
    chat_id: str | None = None,
    timeout: float = 15.0,
) -> bool:
    bot_token = token or os.getenv("TELEGRAM_BOT_TOKEN")
    destination = chat_id or os.getenv("TELEGRAM_CHAT_ID")
    if not bot_token or not destination:
        return False
    response = httpx.post(
        f"https://api.telegram.org/bot{bot_token}/sendMessage",
        data={"chat_id": destination, "text": message, "disable_web_page_preview": "true"},
        timeout=timeout,
    )
    response.raise_for_status()
    return True


def notify_pipeline_result(result: PipelineRunResult) -> bool:
    return send_telegram_message(format_pipeline_notification(result))


def safe_notify_pipeline_result(result: PipelineRunResult) -> dict[str, Any]:
    """Notify without hiding the pipeline's real outcome or exposing credentials."""
    try:
        sent = notify_pipeline_result(result)
        return {"sent": sent, "channel": "telegram" if sent else "not_configured"}
    except Exception as exc:
        return {"sent": False, "channel": "telegram", "error": type(exc).__name__}
