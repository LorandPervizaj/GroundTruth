"""Readiness probe HTTP semantics and failure modes."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def ready_client():
    from groundtruth.api.app import app

    with TestClient(app) as client:
        yield client


def test_ready_healthy_returns_200(ready_client: TestClient) -> None:
    with patch(
        "groundtruth.api.routes_markets.evaluate_readiness",
        return_value={"ok": True},
    ):
        res = ready_client.get("/api/ready")
    assert res.status_code == 200
    assert res.json()["ok"] is True


def test_ready_not_ready_returns_503(ready_client: TestClient) -> None:
    with patch(
        "groundtruth.api.routes_markets.evaluate_readiness",
        return_value={"ok": False, "reasons": ["lookup_cache_not_loaded"]},
    ):
        res = ready_client.get("/api/ready")
    assert res.status_code == 503
    body = res.json()
    assert body["ok"] is False
    assert "lookup_cache_not_loaded" in body["reasons"]


def test_ready_missing_artifact_reason(ready_client: TestClient) -> None:
    with patch(
        "groundtruth.api.routes_markets.evaluate_readiness",
        return_value={"ok": False, "reasons": ["artifacts_unverified", "artifact_error:missing"]},
    ):
        res = ready_client.get("/api/ready")
    assert res.status_code == 503
    assert res.json()["ok"] is False


def test_ready_corrupt_artifact_maps_to_503() -> None:
    from groundtruth.config import Settings
    from groundtruth.services.artifact_integrity import ArtifactIntegrityState
    from groundtruth.services.readiness import evaluate_readiness

    settings = Settings(app_env="production", api_require_lookup_cache=True)
    with (
        patch("groundtruth.services.readiness.cache_is_loaded", return_value=True),
        patch("groundtruth.services.readiness.comparables_cache_ready", return_value=True),
        patch(
            "groundtruth.services.readiness.get_artifact_integrity_state",
            return_value=ArtifactIntegrityState(verified=False, error="sha256 mismatch"),
        ),
        patch("groundtruth.services.readiness._database_reachable", return_value=True),
    ):
        payload = evaluate_readiness(settings)
    assert payload["ok"] is False
    assert "artifacts_unverified" in payload["reasons"]


def test_ready_invalid_artifact_metadata_maps_to_503() -> None:
    from groundtruth.config import Settings
    from groundtruth.services.artifact_integrity import ArtifactIntegrityState
    from groundtruth.services.readiness import evaluate_readiness

    settings = Settings(app_env="production", api_require_lookup_cache=True)
    with (
        patch("groundtruth.services.readiness.cache_is_loaded", return_value=True),
        patch("groundtruth.services.readiness.comparables_cache_ready", return_value=True),
        patch(
            "groundtruth.services.readiness.get_artifact_integrity_state",
            return_value=ArtifactIntegrityState(
                verified=False, error="ValueError: lookup cache manifest has no entries"
            ),
        ),
        patch("groundtruth.services.readiness._database_reachable", return_value=True),
    ):
        payload = evaluate_readiness(settings)
    assert payload["ok"] is False
    assert any("artifact_error" in r for r in payload["reasons"])


def test_ready_database_unavailable_maps_to_503() -> None:
    from groundtruth.config import Settings
    from groundtruth.services.artifact_integrity import ArtifactIntegrityState
    from groundtruth.services.readiness import evaluate_readiness

    settings = Settings(app_env="production", api_require_lookup_cache=True)
    with (
        patch("groundtruth.services.readiness.cache_is_loaded", return_value=True),
        patch("groundtruth.services.readiness.comparables_cache_ready", return_value=True),
        patch(
            "groundtruth.services.readiness.get_artifact_integrity_state",
            return_value=ArtifactIntegrityState(verified=True),
        ),
        patch("groundtruth.services.readiness._database_reachable", return_value=False),
    ):
        payload = evaluate_readiness(settings)
    assert payload["ok"] is False
    assert "database_unavailable" in payload["reasons"]


def test_ok_false_never_returns_http_200(ready_client: TestClient) -> None:
    """Contract: any ok:false readiness payload must use a non-success status."""
    with patch(
        "groundtruth.api.routes_markets.evaluate_readiness",
        return_value={"ok": False, "reasons": ["comparables_not_ready"]},
    ):
        res = ready_client.get("/api/ready")
    assert res.status_code != 200
    assert res.status_code == 503
    assert res.json()["ok"] is False
