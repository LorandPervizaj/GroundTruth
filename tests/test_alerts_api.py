"""API tests for price alert signups."""

import json
from pathlib import Path

from fastapi.testclient import TestClient

from groundtruth.api.app import app

client = TestClient(app)


class TestAlertsAPI:
    def test_submit_alert(self, tmp_path: Path, monkeypatch) -> None:
        captured: list[dict] = []

        def _capture(kind: str, payload: dict) -> None:
            captured.append({"kind": kind, **payload})
            path = tmp_path / "alerts.jsonl"
            path.write_text(json.dumps(payload) + "\n", encoding="utf-8")

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
                "max_price_eur": 650,
            },
        )
        assert res.status_code == 200
        assert res.json()["status"] == "ok"
        assert len(captured) == 1
        row = captured[0]
        assert row["kind"] == "alerts"
        assert row["email"] == "user@example.com"
        assert row["neighborhood_slug"] == "ulpiana"

    def test_invalid_email_rejected(self) -> None:
        res = client.post(
            "/api/alerts",
            json={"email": "not-an-email", "neighborhood_slug": "ulpiana"},
        )
        assert res.status_code == 422
