"""Observability probes: liveness vs readiness vs gated metrics."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def api_client():
    from groundtruth.api.app import app

    with TestClient(app) as client:
        yield client


def test_liveness_health_always_200(api_client: TestClient) -> None:
    res = api_client.get("/api/health")
    assert res.status_code == 200
    assert res.json() == {"status": "ok"}


def test_metrics_hidden_without_token_in_production(api_client: TestClient) -> None:
    from groundtruth.config import Settings

    with patch(
        "groundtruth.api.deps.get_settings",
        return_value=Settings(app_env="production", health_check_token="secret-ops"),
    ):
        res = api_client.get("/api/metrics")
    assert res.status_code == 404


def test_metrics_ok_with_token_in_production(api_client: TestClient) -> None:
    from groundtruth.config import Settings

    settings = Settings(app_env="production", health_check_token="secret-ops")
    with patch("groundtruth.api.deps.get_settings", return_value=settings):
        res = api_client.get("/api/metrics", headers={"X-Health-Token": "secret-ops"})
    assert res.status_code == 200
    body = res.json()
    for key in ("total_requests", "total_errors", "by_status", "by_path_prefix"):
        assert key in body


def test_health_perf_requires_token_in_production(api_client: TestClient) -> None:
    from groundtruth.config import Settings

    with patch(
        "groundtruth.api.deps.get_settings",
        return_value=Settings(app_env="production", health_check_token="secret-ops"),
    ):
        assert api_client.get("/api/health/perf").status_code == 404
        ok = api_client.get("/api/health/perf", headers={"X-Health-Token": "secret-ops"})
    assert ok.status_code == 200
    assert "corpus_warm" in ok.json()
    assert "warm_requests" in ok.json()
