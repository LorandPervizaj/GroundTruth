"""Authentication contract for the owner-only Telegram webhook."""

from unittest.mock import patch

from fastapi.testclient import TestClient

from groundtruth.api.app import app

client = TestClient(app)


def test_webhook_requires_secret(monkeypatch) -> None:
    monkeypatch.setenv("TELEGRAM_WEBHOOK_SECRET", "webhook-secret")
    response = client.post("/api/telegram/webhook", json={"update_id": 1})
    assert response.status_code == 403


def test_webhook_routes_authenticated_update(monkeypatch) -> None:
    monkeypatch.setenv("TELEGRAM_WEBHOOK_SECRET", "webhook-secret")
    update = {"message": {"chat": {"id": 123}, "text": "/status"}}
    with patch("groundtruth.api.routes_product_writes.handle_telegram_update") as handler:
        response = client.post(
            "/api/telegram/webhook",
            json=update,
            headers={"X-Telegram-Bot-Api-Secret-Token": "webhook-secret"},
        )
    assert response.status_code == 200
    handler.assert_called_once_with(update)
