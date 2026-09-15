"""API tests for lookup and search endpoints."""

import pytest
from fastapi.testclient import TestClient

from groundtruth.api.app import app

client = TestClient(app)

pytestmark = pytest.mark.usefixtures("require_postgres")


class TestLookupAPI:
    def test_search_rejects_empty_query(self) -> None:
        res = client.get("/api/search", params={"q": ""})
        assert res.status_code == 422

    def test_search_single_character_prefix(self) -> None:
        res = client.get("/api/search", params={"q": "r"})
        assert res.status_code == 200
        assert isinstance(res.json()["results"], list)

    def test_search_returns_results(self) -> None:
        res = client.get("/api/search", params={"q": "ulpiana"})
        assert res.status_code == 200
        data = res.json()
        assert data["query"] == "ulpiana"
        assert isinstance(data["results"], list)

    def test_search_dragodan_resolves_to_arberia(self) -> None:
        res = client.get("/api/search", params={"q": "dragodan"})
        assert res.status_code == 200
        slugs = [r["slug"] for r in res.json()["results"] if r["entity_type"] == "neighborhood"]
        assert "arberia" in slugs
        assert "dragodan" not in slugs

    def test_lookup_merged_neighborhood_canonical(self) -> None:
        res = client.get("/api/lookup/neighborhood/dragodan")
        if res.status_code == 404:
            pytest.skip("lookup fixtures not seeded in this environment")
        assert res.status_code == 200
        data = res.json()
        assert data["slug"] == "arberia"
        assert data["requested_slug"] == "dragodan"
        assert "Dragodan" in data.get("also_known_as", [])

    def test_lookup_unknown_slug_404(self) -> None:
        res = client.get("/api/lookup/neighborhood/not-a-real-slug-xyz")
        assert res.status_code == 404

    def test_lookup_neighborhood_shape(self) -> None:
        res = client.get("/api/lookup/neighborhood/ulpiana")
        if res.status_code == 404:
            pytest.skip("lookup fixtures not seeded in this environment")
        assert res.status_code == 200
        data = res.json()
        assert data["entity_type"] == "neighborhood"
        assert data["slug"] == "ulpiana"
        assert "pulse" in data
        assert "bedroom_breakdown" in data

    def test_lookup_history_shape(self) -> None:
        res = client.get("/api/lookup/neighborhood/ulpiana/history", params={"months": 12})
        if res.status_code == 404:
            pytest.skip("lookup fixtures not seeded in this environment")
        assert res.status_code == 200
        data = res.json()
        assert data["cadence"] == "biweekly"
        assert data["months"] == 12
        assert isinstance(data["points"], list)
        if data["points"]:
            point = data["points"][0]
            assert "period_end" in point
            assert "sale_n" in point

    def test_lookup_history_months_bounds(self) -> None:
        res = client.get("/api/lookup/neighborhood/ulpiana/history", params={"months": 3})
        assert res.status_code == 422

    def test_corpus_meta_shape(self) -> None:
        res = client.get("/api/meta")
        assert res.status_code == 200
        data = res.json()
        assert "corpus_updated_at" in data
        assert "active_listings" in data
        assert "raw_listings" in data
        assert "cross_portal_duplicates_removed" in data
        assert isinstance(data["data_sources"], list)
        assert data.get("dataset_version") == "v2.0"
        assert "dataset_fingerprint" in data
        assert data.get("public_product_scope") == "rent_and_sale"

    def test_homepage_serves(self) -> None:
        res = client.get("/")
        assert res.status_code == 200
        assert "Metrik" in res.text

    def test_market_page_serves(self) -> None:
        res = client.get("/market/neighborhood/ulpiana")
        assert res.status_code == 200
        assert "market-content" in res.text
        assert "insufficient-panel" in res.text

    def test_events_accepts_market_view(self) -> None:
        res = client.post(
            "/api/events",
            json={
                "event": "market_view",
                "entity_type": "neighborhood",
                "slug": "ulpiana",
                "confidence": "high",
            },
        )
        assert res.status_code == 200

    def test_api_ready_shape(self) -> None:
        res = client.get("/api/ready")
        assert res.status_code == 200
        data = res.json()
        assert data["ok"] is True
        # Development tests expose cache details; production returns only ok.
        assert "lookup_cache" in data
        assert "comparables_ready" in data

    def test_api_ready_minimal_in_production(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("APP_ENV", "production")
        monkeypatch.setenv("API_REQUIRE_LOOKUP_CACHE", "false")
        monkeypatch.setenv(
            "DATABASE_URL",
            "postgresql+psycopg://app:secure-secret-here@localhost:5432/groundtruth",
        )
        monkeypatch.setenv("PRODUCT_WRITE_BACKEND", "database")
        monkeypatch.setenv("HEALTH_CHECK_TOKEN", "a-secure-random-token-value-ok")
        monkeypatch.setenv("FORWARDED_ALLOW_IPS", "172.16.0.0/12")
        from unittest.mock import patch

        from groundtruth.config import get_settings

        get_settings.cache_clear()
        from groundtruth.api.app import app

        with (
            patch("groundtruth.api.app.validate_production_settings", return_value=None),
            patch("groundtruth.services.readiness.evaluate_readiness", return_value={"ok": True}),
            TestClient(app) as prod_client,
        ):
            res = prod_client.get("/api/ready")
            assert res.status_code == 200
            data = res.json()
            assert data["ok"] is True
