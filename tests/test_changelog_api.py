"""Public changelog contract and page."""

from fastapi.testclient import TestClient

from groundtruth.api.app import app

client = TestClient(app)


def test_public_changelog_api() -> None:
    response = client.get("/api/changelog?category=product&limit=2")
    assert response.status_code == 200
    entries = response.json()["entries"]
    assert 0 < len(entries) <= 2
    assert all(entry["category"] == "product" for entry in entries)


def test_changelog_page_is_not_a_redirect() -> None:
    response = client.get("/changelog", follow_redirects=False)
    assert response.status_code == 200
    assert 'id="changelog-list"' in response.text


def test_alerts_page_is_not_a_redirect() -> None:
    response = client.get("/alerts", follow_redirects=False)
    assert response.status_code == 200
    assert 'id="alert-form"' in response.text
