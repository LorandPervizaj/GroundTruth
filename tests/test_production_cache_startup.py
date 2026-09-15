"""Production startup invariants for required lookup cache."""

from __future__ import annotations

from unittest.mock import patch

import pytest


def _production_env(monkeypatch: pytest.MonkeyPatch, *, require_cache: bool = True) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv(
        "DATABASE_URL",
        "postgresql+psycopg://app:secure-secret-here@localhost:5432/groundtruth",
    )
    monkeypatch.setenv("PRODUCT_WRITE_BACKEND", "database")
    monkeypatch.setenv("HEALTH_CHECK_TOKEN", "a-secure-random-token-value-ok")
    monkeypatch.setenv("FORWARDED_ALLOW_IPS", "172.16.0.0/12")
    monkeypatch.setenv("API_DOCS_ENABLED", "false")
    monkeypatch.setenv("API_REQUIRE_LOOKUP_CACHE", "true" if require_cache else "false")


def test_production_rejects_disabled_lookup_cache_requirement(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _production_env(monkeypatch, require_cache=False)
    from groundtruth.config import get_settings
    from groundtruth.startup import validate_production_settings

    get_settings.cache_clear()
    with pytest.raises(SystemExit, match="API_REQUIRE_LOOKUP_CACHE"):
        validate_production_settings(get_settings())


def test_production_startup_fails_when_lookup_cache_empty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """production + API_REQUIRE_LOOKUP_CACHE + empty cache → lifespan RuntimeError."""
    _production_env(monkeypatch, require_cache=True)
    from groundtruth.config import get_settings

    get_settings.cache_clear()

    with (
        patch("groundtruth.api.app.validate_production_settings", return_value=None),
        patch(
            "groundtruth.services.artifact_integrity.verify_and_record_release_artifacts",
            return_value=__import__(
                "groundtruth.services.artifact_integrity", fromlist=["ArtifactIntegrityState"]
            ).ArtifactIntegrityState(verified=True),
        ),
        patch("groundtruth.api.app.load_lookup_cache_from_disk", return_value=0),
        patch(
            "groundtruth.analytics.valuation.comparables_cache_ready",
            return_value=False,
        ),
    ):
        from fastapi.testclient import TestClient

        from groundtruth.api.app import app

        with (
            pytest.raises(RuntimeError, match="Production requires verified lookup"),
            TestClient(app),
        ):
            pass


def test_production_startup_fails_when_artifacts_unverified(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _production_env(monkeypatch, require_cache=True)
    from groundtruth.config import get_settings
    from groundtruth.services.artifact_integrity import ArtifactIntegrityState

    get_settings.cache_clear()

    with (
        patch("groundtruth.api.app.validate_production_settings", return_value=None),
        patch(
            "groundtruth.services.artifact_integrity.verify_and_record_release_artifacts",
            return_value=ArtifactIntegrityState(verified=False, error="sha256 mismatch"),
        ),
    ):
        from fastapi.testclient import TestClient

        from groundtruth.api.app import app

        with (
            pytest.raises(RuntimeError, match="verification failed"),
            TestClient(app),
        ):
            pass
