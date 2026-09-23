"""Telegram delivery for owner-only Metrik product submissions."""

from unittest.mock import Mock

from groundtruth.services.product_notifications import (
    format_product_submission,
    notify_product_submission,
)


def test_format_product_submission() -> None:
    message = format_product_submission(
        "contact",
        {"name": "Ada", "email": "ada@example.com", "message": "Please contact me."},
    )
    assert "Metrik — Contact message" in message
    assert "Ada" in message
    assert "ada@example.com" in message
    assert "Please contact me." in message


def test_notification_is_disabled_without_owner_secrets(monkeypatch) -> None:
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)
    assert notify_product_submission("contact", {"message": "hello"}) is False


def test_notification_only_targets_configured_owner(monkeypatch) -> None:
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test-token")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "123456")
    response = Mock()
    response.raise_for_status.return_value = None
    post = Mock(return_value=response)
    monkeypatch.setattr("groundtruth.services.product_notifications.httpx.post", post)

    assert notify_product_submission("public_reports", {"message": "broken page"}) is True
    assert post.call_args.kwargs["data"]["chat_id"] == "123456"
    assert "test-token" not in post.call_args.kwargs["data"]["text"]
