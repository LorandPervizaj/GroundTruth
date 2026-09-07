"""API tests for public methodology metadata."""

import pytest
from fastapi.testclient import TestClient

from groundtruth.api.app import app

client = TestClient(app)

pytestmark = pytest.mark.usefixtures("require_postgres")


class TestMethodologyAPI:
    def test_methodology_meta_shape(self) -> None:
        res = client.get("/api/methodology")
        assert res.status_code == 200
        data = res.json()
        assert data["version"] == "1.0.0"
        assert data["released"] == "2026-06-09"
        assert data["canonical_path"] == "/methodology"
        assert "summary" in data
        assert isinstance(data["parser_versions"], list)
        assert len(data["parser_versions"]) >= 1
        assert data.get("dataset_version") == "v2.0"
        assert data.get("dataset_frozen_at") is not None
        assert data.get("golden_accuracy_pct") == 99.9

    def test_methodology_page_serves(self) -> None:
        res = client.get("/methodology")
        assert res.status_code == 200
        assert "method-cite-panel" in res.text
        assert "methodology_hero" in res.text or "Metodologjia" in res.text
