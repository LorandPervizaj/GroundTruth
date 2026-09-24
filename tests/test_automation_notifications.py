from groundtruth.automation.models import PipelineRunResult, StageResult
from groundtruth.automation.notifications import (
    format_pipeline_notification,
    send_email_report,
    send_telegram_message,
)


def test_failure_notification_is_concise_and_actionable() -> None:
    result = PipelineRunResult(
        run_id="run-1",
        release_id="2026-W39-abc",
        started_at="2026-09-23T00:00:00+00:00",
        requested_days=7,
        data_through="2026-09-22",
        outcome="failed",
        stages=[
            StageResult(
                name="source_health",
                status="failed",
                counts={"green": 7, "yellow": 0, "red": 1},
                error="topia returned zero observations",
            )
        ],
    )
    message = format_pipeline_notification(result)
    assert "Failed stage: source_health" in message
    assert "previous production remains active" in message
    assert "token" not in message.lower()


def test_telegram_is_optional_without_secrets(monkeypatch) -> None:
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)
    assert send_telegram_message("hello") is False


def test_email_is_optional_without_credentials(monkeypatch) -> None:
    for key in ("SMTP_USERNAME", "SMTP_PASSWORD", "SMTP_FROM", "PIPELINE_EMAIL_TO"):
        monkeypatch.delenv(key, raising=False)
    result = PipelineRunResult(
        run_id="run-1",
        release_id="release-1",
        started_at="2026-09-23T00:00:00+00:00",
        requested_days=7,
    )
    assert send_email_report(result) is False
