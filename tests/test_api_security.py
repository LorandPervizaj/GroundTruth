"""API security — rate limits, input caps, abuse resistance."""

import pytest
from fastapi.testclient import TestClient

from groundtruth.api.app import app
from groundtruth.api.security import limiter

client = TestClient(app)

_FEEDBACK_PAYLOAD = {
    "kind": "listing",
    "issue": "wrong_price",
    "source": "merrjep",
    "source_listing_id": "sec-test",
}

_ALERT_PAYLOAD = {
    "email": "test@example.com",
    "neighborhood_slug": "ulpiana",
}


class TestInputCaps:
    def test_search_rejects_long_query(self) -> None:
        res = client.get("/api/search", params={"q": "a" * 81})
        assert res.status_code == 400

    def test_compare_rejects_more_than_three(self) -> None:
        res = client.get(
            "/api/compare",
            params={"neighborhoods": "ulpiana,arberia,dardania,matiqan"},
        )
        assert res.status_code == 400
        assert "3" in res.json()["detail"]

    def test_valuate_rejects_absurd_area(self) -> None:
        res = client.post(
            "/api/valuate",
            json={
                "neighborhood": "Ulpiana",
                "area_sqm": 9999,
                "valuation_type": "rent",
            },
        )
        assert res.status_code == 422

    def test_valuate_rejects_absurd_sale_price(self) -> None:
        res = client.post(
            "/api/valuate",
            json={
                "neighborhood": "Ulpiana",
                "area_sqm": 80,
                "valuation_type": "sale",
                "listing_sale_eur": 99_000_000,
            },
        )
        assert res.status_code == 422

    def test_oversized_body_rejected(self) -> None:
        huge = "x" * 40_000
        res = client.post(
            "/api/feedback",
            json={**_FEEDBACK_PAYLOAD, "message": huge},
            headers={"Content-Length": str(len(huge) + 200)},
        )
        assert res.status_code in (413, 422)


@pytest.mark.rate_limit
class TestRateLimits:
    @pytest.fixture(autouse=True)
    def tight_feedback_limit(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("API_RATE_LIMIT_FEEDBACK", "3/minute")
        monkeypatch.setenv("API_RATE_LIMIT_ALERTS", "2/minute")
        from groundtruth.config import get_settings

        get_settings.cache_clear()
        limiter.reset()
        yield
        limiter.reset()

    def test_feedback_rate_limit(self) -> None:
        for _ in range(3):
            res = client.post("/api/feedback", json=_FEEDBACK_PAYLOAD)
            assert res.status_code == 200
        res = client.post("/api/feedback", json=_FEEDBACK_PAYLOAD)
        assert res.status_code == 429

    def test_alerts_rate_limit(self) -> None:
        for _ in range(2):
            res = client.post("/api/alerts", json=_ALERT_PAYLOAD)
            assert res.status_code == 200
        res = client.post("/api/alerts", json=_ALERT_PAYLOAD)
        assert res.status_code == 429
