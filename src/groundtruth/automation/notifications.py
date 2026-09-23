"""Concise operational notifications. Secrets are read only from the environment."""

from __future__ import annotations

import os
import smtplib
from email.message import EmailMessage
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


def send_email_report(
    result: PipelineRunResult,
    *,
    host: str | None = None,
    port: int | None = None,
    username: str | None = None,
    password: str | None = None,
    sender: str | None = None,
    recipient: str | None = None,
) -> bool:
    smtp_host = host or os.getenv("SMTP_HOST")
    smtp_port = port or int(os.getenv("SMTP_PORT", "587"))
    smtp_username = username or os.getenv("SMTP_USERNAME")
    smtp_password = password or os.getenv("SMTP_PASSWORD")
    from_address = sender or os.getenv("SMTP_FROM") or smtp_username
    to_address = recipient or os.getenv("PIPELINE_EMAIL_TO")
    if not all((smtp_host, smtp_username, smtp_password, from_address, to_address)):
        return False
    message = EmailMessage()
    message["Subject"] = f"GroundTruth {result.outcome.upper()}: {result.release_id}"
    message["From"] = from_address
    message["To"] = to_address
    body = [format_pipeline_notification(result), "", "Stage details:"]
    for stage in result.stages:
        body.append(
            f"- {stage.name}: {stage.status}; duration={stage.duration_seconds}; "
            f"counts={stage.counts}; error={stage.error or '-'}"
        )
    message.set_content("\n".join(body))
    with smtplib.SMTP(smtp_host, smtp_port, timeout=20) as client:
        client.starttls()
        client.login(smtp_username, smtp_password)
        client.send_message(message)
    return True


def safe_notify_pipeline_result(result: PipelineRunResult) -> dict[str, Any]:
    """Notify without hiding the pipeline's real outcome or exposing credentials."""
    channels: list[str] = []
    errors: list[str] = []
    for name, sender in (("telegram", notify_pipeline_result), ("email", send_email_report)):
        try:
            if sender(result):
                channels.append(name)
        except Exception as exc:
            errors.append(f"{name}:{type(exc).__name__}")
    return {
        "sent": bool(channels),
        "channels": channels,
        "configured": bool(channels or errors),
        **({"errors": errors} if errors else {}),
    }
