"""Chaos / fail-closed checks around release integrity and readiness."""

from __future__ import annotations

from unittest.mock import patch

from fastapi.testclient import TestClient

from groundtruth.config import Settings
from groundtruth.services.artifact_integrity import ArtifactIntegrityState
from groundtruth.services.readiness import evaluate_readiness


def test_ready_fails_when_release_artifacts_corrupt() -> None:
    settings = Settings(app_env="production", api_require_lookup_cache=True)
    bad = ArtifactIntegrityState(verified=False, error="checksum_mismatch")
    with (
        patch("groundtruth.services.readiness.cache_is_loaded", return_value=True),
        patch("groundtruth.services.readiness.comparables_cache_ready", return_value=True),
        patch("groundtruth.services.readiness.get_artifact_integrity_state", return_value=bad),
        patch("groundtruth.services.readiness._database_reachable", return_value=True),
    ):
        result = evaluate_readiness(settings)
    assert result["ok"] is False
    assert "artifacts_unverified" in result["reasons"]
    assert any(r.startswith("artifact_error:") for r in result["reasons"])


def test_http_ready_503_on_artifact_chaos() -> None:
    from groundtruth.api.app import app

    with (
        TestClient(app) as client,
        patch(
            "groundtruth.api.routes_markets.evaluate_readiness",
            return_value={"ok": False, "reasons": ["artifacts_unverified", "artifact_error:chaos"]},
        ),
    ):
        res = client.get("/api/ready")
    assert res.status_code == 503
    assert res.json()["ok"] is False


def test_valuate_blocked_when_comparables_not_ready() -> None:
    from groundtruth.api.app import app

    prod = Settings(app_env="production", valuation_public_enabled=True, health_check_token="x")
    with (
        TestClient(app) as client,
        patch("groundtruth.api.routes_markets.get_settings", return_value=prod),
        patch("groundtruth.analytics.valuation.comparables_cache_ready", return_value=False),
    ):
        res = client.post(
            "/api/valuate",
            json={
                "valuation_type": "rent",
                "neighborhood": "Ulpiana",
                "area_sqm": 60,
                "bedrooms": 2,
            },
        )
    assert res.status_code == 503
    detail = str(res.json().get("detail", "")).lower()
    assert "loading" in detail or "unavailable" in detail
