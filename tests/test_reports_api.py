"""Tests for published reports API."""

import pytest
from fastapi.testclient import TestClient

from groundtruth.api.app import app


@pytest.fixture
def client():
    return TestClient(app)


def test_list_reports_returns_json(client, tmp_path, monkeypatch):
    reports_dir = tmp_path / "generated"
    reports_dir.mkdir()
    (reports_dir / "quarterly_report_2026-Q1.md").write_text("# Q1\n\nMedian up.", encoding="utf-8")

    from groundtruth.config import get_settings

    monkeypatch.setattr(get_settings(), "reports_generated_dir", reports_dir)

    res = client.get("/api/reports")
    assert res.status_code == 200
    data = res.json()
    assert data["reports"]
    assert data["reports"][0]["type"] == "Quarterly"
    assert "quarterly_report" in data["reports"][0]["filename"]


def test_get_report_file_whitelist(client, tmp_path, monkeypatch):
    reports_dir = tmp_path / "generated"
    reports_dir.mkdir()
    path = reports_dir / "corpus_report_test.md"
    path.write_text("# Corpus\n\nBody.", encoding="utf-8")

    from groundtruth.config import get_settings

    monkeypatch.setattr(get_settings(), "reports_generated_dir", reports_dir)

    res = client.get("/api/reports/files/corpus_report_test.md")
    assert res.status_code == 200
    assert "Corpus" in res.text

    bad = client.get("/api/reports/files/not%20allowed.md")
    assert bad.status_code == 400

    traversal = client.get("/api/reports/files/..%2Fetc%2Fpasswd.md")
    # 400 if the handler runs; 404 if the ASGI stack rejects the path segment.
    assert traversal.status_code in (400, 404)


def test_statistics_and_legacy_redirects(client):
    assert client.get("/statistics").status_code == 200
    assert client.get("/reports").status_code == 200
    assert client.get("/annual").status_code == 200
    about = client.get("/about", follow_redirects=False)
    assert about.status_code == 200
    assert 'data-page-title="about_title"' in about.text
    assert client.get("/changelog", follow_redirects=False).status_code == 404
    assert client.get("/alerts", follow_redirects=False).status_code == 200
    assert client.get("/find").status_code == 200


def test_annual_pdf_download(client, monkeypatch):
    from groundtruth.analytics import annual_export

    sample = {
        "generated_at": "2026-06-12T00:00:00+00:00",
        "total_listings": 100,
        "kpis": {
            "total_listings": 100,
            "rent_pct": 70.0,
            "median_sale_price_per_sqm": 1200.0,
            "median_rent": 350.0,
        },
        "volume": {"labels": ["2026-01"], "rent": [50], "sale": [20]},
        "prices": {"labels": ["2026-01"], "values": [1200.0], "metric": "median"},
        "rent_prices": {"labels": ["2026-01"], "values": [350.0], "metric": "median"},
        "neighborhood_table": [],
        "neighborhood_rankings": {
            "expensive": [],
            "affordable": [],
            "min_sale_listings": 15,
        },
        "sources": [],
        "coverage": {"price_pct": 95.0, "area_pct": 80.0, "neighborhood_pct": 85.0},
        "methodology": {
            "window_months": 12,
            "cutoff_date": "2025-06-12",
            "date_field": "listing_date",
            "note": "Asking prices.",
            "sources": ["1.3.1"],
        },
        "conclusions": {
            "sq": ["Test përmbledhje."],
            "en": ["Test summary."],
        },
    }
    monkeypatch.setattr(annual_export, "load_annual_report_cache", lambda path=None: sample)
    res = client.get("/api/reports/annual_pdf?lang=en")
    assert res.status_code == 200
    assert res.headers["content-type"] == "application/pdf"
    assert res.content[:4] == b"%PDF"
    assert len(res.content) > 5000


def test_annual_data_serves_cache_when_present(client, tmp_path, monkeypatch):
    cache = tmp_path / "annual_report.json"
    cache.write_text(
        '{"total_listings": 42, "generated_at": "2026-06-01T00:00:00+00:00", '
        '"kpis": {"total_listings": 42}, "volume": {"labels": [], "rent": [], "sale": []}, '
        '"prices": {"labels": [], "values": [], "metric": "median"}, '
        '"rent_prices": {"labels": [], "values": [], "metric": "median"}, '
        '"conclusions": {"sq": [], "en": []}, "methodology": {"date_field": "listing_date", "deduped": true}}',
        encoding="utf-8",
    )
    from groundtruth.analytics import annual_export

    monkeypatch.setattr(annual_export, "DEFAULT_ANNUAL_REPORT_PATH", cache)
    res = client.get("/api/reports/annual_data")
    assert res.status_code == 200
    assert res.json()["total_listings"] == 42
    assert res.json()["generated_at"] == "2026-06-01T00:00:00+00:00"


def test_annual_data_active_corpus_shape(client, monkeypatch):
    from groundtruth.analytics import annual_export

    monkeypatch.setattr(
        annual_export,
        "load_annual_report_cache",
        lambda path=None: None,
    )
    res = client.get("/api/reports/annual_data")
    assert res.status_code == 200
    data = res.json()
    assert "volume" in data
    assert "prices" in data
    assert data["prices"].get("metric") == "median"
    assert "kpis" in data
    assert "methodology" in data
    assert data["methodology"]["date_field"] == "listing_date"
    assert data["methodology"]["deduped"] is True
    assert "rent_prices" in data
    assert "sources" in data
    assert "coverage" in data
    assert "narratives" in data
    assert "conclusions" in data
    assert "sq" in data["conclusions"]
    assert "en" in data["conclusions"]
    assert len(data["conclusions"]["sq"]) == len(data["conclusions"]["en"])
    assert "narratives_i18n" in data
    assert "neighborhood_rankings" in data
    assert data["total_listings"] == data["kpis"]["total_listings"]
