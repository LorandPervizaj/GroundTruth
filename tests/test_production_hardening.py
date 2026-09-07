"""Production hardening — startup guards and security headers."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


def test_security_headers_on_api() -> None:
    from groundtruth.api.app import app

    with TestClient(app) as client:
        res = client.get("/api/ready")
        assert res.status_code == 200
        assert res.headers.get("X-Content-Type-Options") == "nosniff"
        assert res.headers.get("X-Frame-Options") == "DENY"


def test_production_rejects_dev_database_password(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv(
        "DATABASE_URL",
        "postgresql+psycopg://groundtruth:groundtruth_dev_password@localhost:5432/groundtruth",
    )
    from groundtruth.config import get_settings
    from groundtruth.startup import validate_production_settings

    get_settings.cache_clear()
    with pytest.raises(SystemExit):
        validate_production_settings(get_settings())


def test_production_rejects_jsonl_writes(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv(
        "DATABASE_URL",
        "postgresql+psycopg://app:secure-secret-here@localhost:5432/groundtruth",
    )
    monkeypatch.setenv("PRODUCT_WRITE_BACKEND", "jsonl")
    from groundtruth.config import get_settings
    from groundtruth.startup import validate_production_settings

    get_settings.cache_clear()
    with pytest.raises(SystemExit):
        validate_production_settings(get_settings())


def test_production_rejects_placeholder_ops_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv(
        "DATABASE_URL",
        "postgresql+psycopg://app:secure-secret-here@localhost:5432/groundtruth",
    )
    monkeypatch.setenv("PRODUCT_WRITE_BACKEND", "database")
    monkeypatch.setenv("HEALTH_CHECK_TOKEN", "replace-me")
    from groundtruth.config import get_settings
    from groundtruth.startup import validate_production_settings

    get_settings.cache_clear()
    with pytest.raises(SystemExit):
        validate_production_settings(get_settings())


def test_production_rejects_wildcard_proxy_trust(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv(
        "DATABASE_URL",
        "postgresql+psycopg://app:secure-secret-here@localhost:5432/groundtruth",
    )
    monkeypatch.setenv("PRODUCT_WRITE_BACKEND", "database")
    monkeypatch.setenv("HEALTH_CHECK_TOKEN", "a-secure-random-token-value")
    monkeypatch.setenv("FORWARDED_ALLOW_IPS", "*")
    from groundtruth.config import get_settings
    from groundtruth.startup import validate_production_settings

    get_settings.cache_clear()
    with pytest.raises(SystemExit):
        validate_production_settings(get_settings())


def test_production_rejects_api_docs_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv(
        "DATABASE_URL",
        "postgresql+psycopg://app:secure-secret-here@localhost:5432/groundtruth",
    )
    monkeypatch.setenv("PRODUCT_WRITE_BACKEND", "database")
    monkeypatch.setenv("HEALTH_CHECK_TOKEN", "a-secure-random-token-value")
    monkeypatch.setenv("API_DOCS_ENABLED", "true")
    from groundtruth.config import get_settings
    from groundtruth.startup import validate_production_settings

    get_settings.cache_clear()
    with pytest.raises(SystemExit):
        validate_production_settings(get_settings())


def test_perf_health_locked_in_production_without_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv(
        "DATABASE_URL",
        "postgresql+psycopg://app:secure-secret-here@localhost:5432/groundtruth",
    )
    monkeypatch.setenv("PRODUCT_WRITE_BACKEND", "database")
    monkeypatch.setenv("HEALTH_CHECK_TOKEN", "test-token")
    from groundtruth.config import get_settings

    get_settings.cache_clear()

    with patch_lifespan_validation():
        from groundtruth.api.app import app

        with TestClient(app) as client:
            res = client.get("/api/health/perf")
            assert res.status_code == 404
            res_ok = client.get("/api/health/perf", headers={"X-Health-Token": "test-token"})
            assert res_ok.status_code == 200


def test_sitemap_includes_market_urls() -> None:
    from groundtruth.api.app import app

    with TestClient(app) as client:
        res = client.get("/sitemap.xml")
        assert res.status_code == 200
        body = res.text
        assert "/market/neighborhood/" in body
        assert "/rent-yield" in body


class patch_lifespan_validation:
    """Skip production validation when importing app in tests."""

    def __enter__(self):
        from unittest.mock import patch

        self._patch = patch(
            "groundtruth.api.app.validate_production_settings",
            return_value=None,
        )
        self._patch.start()
        return self

    def __exit__(self, *args):
        self._patch.stop()
