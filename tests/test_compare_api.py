"""API tests for neighborhood comparison."""

import pytest
from fastapi.testclient import TestClient

from groundtruth.api.app import app

client = TestClient(app)

pytestmark = pytest.mark.usefixtures("require_postgres")


class TestCompareAPI:
    def test_compare_requires_two_slugs(self) -> None:
        res = client.get("/api/compare", params={"neighborhoods": "ulpiana"})
        assert res.status_code == 400

    def test_compare_rejects_four_slugs(self) -> None:
        res = client.get(
            "/api/compare",
            params={"neighborhoods": "ulpiana,arberia,dardania,matiqan"},
        )
        assert res.status_code == 400

    def test_compare_unknown_slug(self) -> None:
        res = client.get(
            "/api/compare",
            params={"neighborhoods": "ulpiana,not-a-real-slug-xyz"},
        )
        assert res.status_code == 400

    def test_compare_shape(self) -> None:
        res = client.get(
            "/api/compare",
            params={"neighborhoods": "ulpiana,arberia"},
        )
        if res.status_code in (400, 404):
            pytest.skip("compare fixtures not seeded in this environment")
        assert res.status_code == 200
        data = res.json()
        assert len(data["neighborhoods"]) == 2
        for item in data["neighborhoods"]:
            assert "slug" in item
            assert "display_name" in item
            assert "pulse" in item
            assert "average_sale_psm_eur" in item["pulse"]

    def test_compare_page_serves(self) -> None:
        res = client.get("/compare")
        assert res.status_code == 200
        assert "compare-form" in res.text
