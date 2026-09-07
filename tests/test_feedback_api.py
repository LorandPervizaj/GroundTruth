"""API tests for data-quality feedback."""

from fastapi.testclient import TestClient

from groundtruth.api.app import app

client = TestClient(app)


class TestFeedbackAPI:
    def test_listing_feedback_accepts(self) -> None:
        res = client.post(
            "/api/feedback",
            json={
                "kind": "listing",
                "issue": "wrong_price",
                "source": "merrjep",
                "source_listing_id": "abc123",
                "listing_url": "https://example.com/listing",
                "message": "Price shown is weekly not monthly",
            },
        )
        assert res.status_code == 200
        assert res.json()["status"] == "ok"

    def test_neighborhood_feedback_accepts(self) -> None:
        res = client.post(
            "/api/feedback",
            json={
                "kind": "neighborhood",
                "issue": "wrong_location",
                "entity_type": "neighborhood",
                "slug": "ulpiana",
                "display_name": "Ulpiana",
            },
        )
        assert res.status_code == 200

    def test_listing_missing_ids_rejected(self) -> None:
        res = client.post(
            "/api/feedback",
            json={"kind": "listing", "issue": "wrong_price"},
        )
        assert res.status_code == 422

    def test_other_requires_message(self) -> None:
        res = client.post(
            "/api/feedback",
            json={
                "kind": "neighborhood",
                "issue": "other",
                "entity_type": "neighborhood",
                "slug": "ulpiana",
            },
        )
        assert res.status_code == 422
