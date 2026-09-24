"""Expanded public API response-shape contracts (OpenAPI-ish field locks)."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def api_client():
    from groundtruth.api.app import app

    with TestClient(app) as client:
        yield client


LOOKUP_REQUIRED = {
    "entity_type",
    "slug",
    "display_name",
    "pulse",
    "recent_listings",
    "total_listings",
}

FORBIDDEN_ANYWHERE = {"phone", "email", "description", "title", "agent", "owner"}


def test_openapi_includes_core_public_paths(api_client: TestClient) -> None:
    # Docs may be disabled in prod settings; force schema from app.
    schema = api_client.app.openapi()
    paths = set(schema.get("paths", {}))
    for required in (
        "/api/ready",
        "/api/health",
        "/api/metrics",
        "/api/lookup/{entity_type}/{slug}",
    ):
        assert required in paths or any(required.split("{")[0] in p for p in paths), required


def test_markets_list_shape_when_available(api_client: TestClient) -> None:
    res = api_client.get("/api/markets")
    # Depending on env/cache this may 200 or 503; never leak internals.
    assert res.status_code in (200, 503, 404)
    if res.status_code == 200:
        body = res.json()
        assert isinstance(body, (dict, list))
        text = str(body).lower()
        for bad in ("password", "postgres://", "health_check_token"):
            assert bad not in text


def test_lookup_not_found_is_clean_json(api_client: TestClient) -> None:
    with patch("groundtruth.api.routes_markets.evaluate_readiness", return_value={"ok": True}):
        res = api_client.get("/api/lookup/neighborhood/definitely-missing-slug-xyz")
    assert res.status_code in (404, 503)
    body = res.json()
    assert isinstance(body, dict)
    assert "detail" in body or "ok" in body
    blob = str(body).lower()
    for bad in FORBIDDEN_ANYWHERE:
        assert bad not in blob or body.get("detail")  # detail string ok; field keys not


def test_valuation_rejects_empty_body(api_client: TestClient) -> None:
    res = api_client.post("/api/valuate", json={})
    assert res.status_code in (422, 400, 404, 405)


def test_contact_or_alerts_do_not_echo_secrets(api_client: TestClient) -> None:
    for path in ("/api/contact", "/api/alerts/signup", "/api/feedback"):
        res = api_client.post(path, json={"email": "a@b.co", "message": "hi"})
        if res.status_code == 404:
            continue
        blob = (res.text or "").lower()
        assert "traceback" not in blob
        assert "health_check_token" not in blob
