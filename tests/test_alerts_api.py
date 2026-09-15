"""Alert product honesty — signup closed until notifications exist."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from groundtruth.api.app import app
from groundtruth.services.product_submissions import clear_submission_dedupe_cache

client = TestClient(app)


@pytest.fixture(autouse=True)
def _clear_dedupe():
    clear_submission_dedupe_cache()
    yield
    clear_submission_dedupe_cache()


class TestAlertsUnavailable:
    def test_alerts_signup_disabled_by_default(self) -> None:
        res = client.post(
            "/api/alerts",
            json={
                "email": "user@example.com",
                "neighborhood_slug": "ulpiana",
                "listing_type": "rent",
            },
            headers={"Content-Type": "application/json"},
        )
        assert res.status_code == 503
        body = res.json()
        assert body["status"] == "unavailable"
        assert "not available" in body["detail"].lower()

    def test_alerts_disabled_does_not_persist(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        captured: list[dict] = []

        def _capture(kind: str, payload: dict) -> None:
            captured.append({"kind": kind, **payload})

        monkeypatch.setattr(
            "groundtruth.services.alerts.append_product_submission",
            _capture,
        )
        res = client.post(
            "/api/alerts",
            json={"email": "user@example.com", "neighborhood_slug": "ulpiana"},
            headers={"Content-Type": "application/json"},
        )
        assert res.status_code == 503
        assert captured == []

    def test_alerts_page_does_not_claim_success(self) -> None:
        res = client.get("/alerts")
        assert res.status_code == 200
        assert "alert-unavailable" in res.text
        assert 'id="alert-form" hidden' in res.text or 'id="alert-form"' in res.text

    def test_enabled_signup_still_validates_email(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("ALERTS_SIGNUP_ENABLED", "true")
        from groundtruth.config import get_settings

        get_settings.cache_clear()
        res = client.post(
            "/api/alerts",
            json={"email": "not-an-email", "neighborhood_slug": "ulpiana"},
            headers={"Content-Type": "application/json"},
        )
        assert res.status_code == 422
        get_settings.cache_clear()

    def test_enabled_signup_persists(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("ALERTS_SIGNUP_ENABLED", "true")
        from groundtruth.config import get_settings

        get_settings.cache_clear()
        captured: list[dict] = []

        def _capture(kind: str, payload: dict) -> None:
            captured.append({"kind": kind, **payload})

        monkeypatch.setattr(
            "groundtruth.services.alerts.append_product_submission",
            _capture,
        )
        res = client.post(
            "/api/alerts",
            json={
                "email": "user@example.com",
                "neighborhood_slug": "ulpiana",
                "listing_type": "rent",
            },
            headers={"Content-Type": "application/json"},
        )
        assert res.status_code == 200
        assert res.json()["status"] == "ok"
        assert len(captured) == 1
        get_settings.cache_clear()
