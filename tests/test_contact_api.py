"""Contact/report/listing public submission endpoints."""

import uuid

import pytest
from fastapi.testclient import TestClient

from groundtruth.api.app import app
from groundtruth.services.product_submissions import clear_submission_dedupe_cache

client = TestClient(app)


@pytest.fixture(autouse=True)
def _clear_dedupe():
    clear_submission_dedupe_cache()
    yield
    clear_submission_dedupe_cache()


def test_contact_submission() -> None:
    res = client.post(
        "/api/contact",
        json={
            "name": "Test User",
            "email": "test@example.com",
            "topic": "general",
            "message": f"I have a question about Metrik data. {uuid.uuid4()}",
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
            "message": f"The valuation page did not respond. {uuid.uuid4()}",
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
            "listing_url": f"https://example.com/listing/{uuid.uuid4()}",
            "neighborhood": "Ulpiana",
            "price_eur": 500,
            "area_sqm": 70,
        },
    )
    assert res.status_code == 200
    assert res.json()["status"] == "ok"
