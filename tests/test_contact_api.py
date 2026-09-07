"""Contact/report/listing public submission endpoints."""

from fastapi.testclient import TestClient

from groundtruth.api.app import app

client = TestClient(app)


def test_contact_submission() -> None:
    res = client.post(
        "/api/contact",
        json={
            "name": "Test User",
            "email": "test@example.com",
            "topic": "general",
            "message": "I have a question about Metrik data.",
        },
    )
    assert res.status_code == 200
    assert res.json()["status"] == "ok"


def test_public_report_submission() -> None:
    res = client.post(
        "/api/public-report",
        json={
            "issue": "bug",
            "page_url": "http://example.com/valuate",
            "message": "The valuation page did not respond.",
        },
    )
    assert res.status_code == 200
    assert res.json()["status"] == "ok"


def test_listing_submission_requires_url_or_notes() -> None:
    res = client.post(
        "/api/listing-submissions",
        json={
            "listing_type": "rent",
            "property_type": "apartment",
            "neighborhood": "Ulpiana",
        },
    )
    assert res.status_code == 422


def test_listing_submission() -> None:
    res = client.post(
        "/api/listing-submissions",
        json={
            "listing_type": "rent",
            "property_type": "apartment",
            "listing_url": "https://example.com/listing/1",
            "neighborhood": "Ulpiana",
            "price_eur": 500,
            "area_sqm": 70,
        },
    )
    assert res.status_code == 200
    assert res.json()["status"] == "ok"
