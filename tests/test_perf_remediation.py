"""Tests for non-blocking API startup and lookup disk cache."""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient


def test_corpus_warm_non_blocking_startup(monkeypatch: pytest.MonkeyPatch) -> None:
    """API should accept traffic before corpus warm completes."""
    monkeypatch.setenv("APP_ENV", "development")
    from groundtruth.config import get_settings

    get_settings.cache_clear()
    with (
        patch("groundtruth.api.app.start_background_corpus_warm") as mock_warm,
        patch("groundtruth.api.app.load_lookup_cache_from_disk", return_value=0),
    ):
        from groundtruth.api.app import app

        with TestClient(app) as client:
            r = client.get("/api/health/perf")
            assert r.status_code == 200
            mock_warm.assert_called_once()


def test_lookup_cache_roundtrip(tmp_path, monkeypatch) -> None:
    from groundtruth.services.lookup_cache import (
        get_cached_listing_counts,
        get_cached_lookup,
        load_lookup_cache_from_disk,
    )

    cache_base = tmp_path / "lookup_cache"
    monkeypatch.setattr(
        "groundtruth.services.lookup_cache.get_settings",
        lambda: type("S", (), {"reports_generated_dir": tmp_path})(),
    )

    manifest = {
        "built_at": "2026-06-18T00:00:00+00:00",
        "corpus_revision": "2026-06-01",
        "entry_count": 1,
        "entries": [
            {"entity_type": "neighborhood", "slug": "ulpiana", "path": "neighborhood/ulpiana.json"}
        ],
        "corpus_meta": {
            "corpus_updated_at": "2026-06-01T00:00:00",
            "active_listings": 100,
            "active_listings_confidence": "medium",
            "raw_listings": 120,
            "cross_portal_duplicates_removed": 20,
            "cross_portal_duplicate_groups": 5,
            "median_days_on_market": None,
            "data_sources": ["gjirafa"],
            "source_count": 1,
            "geocode_coverage_pct": None,
            "geocode_mismatch_pct": None,
            "dataset_version": "v2.0",
            "dataset_frozen_at": None,
            "dataset_fingerprint": "abc",
            "invalid_pct": 0.2,
            "golden_accuracy_pct": 99.9,
            "public_product_scope": "rent_and_sale",
        },
    }
    cache_base.mkdir(parents=True)
    (cache_base / "neighborhood").mkdir()
    payload = {
        "entity_type": "neighborhood",
        "slug": "ulpiana",
        "display_name": "Ulpiana",
        "city": "Prishtina",
        "pulse": {
            "median_sale_psm": 1200,
            "median_rent_psm": 8,
            "median_sale_price": 90000,
            "median_rent_price": 450,
            "active_listings": 50,
            "confidence": "medium",
        },
        "bedroom_breakdown": [],
        "size_breakdown": [],
        "recent_listings": [],
        "breadcrumb": [],
        "also_known_as": [],
        "corpus_updated_at": "2026-06-01T00:00:00",
        "total_listings": 50,
    }
    (cache_base / "neighborhood" / "ulpiana.json").write_text(json.dumps(payload), encoding="utf-8")
    (cache_base / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

    n = load_lookup_cache_from_disk()
    assert n == 1
    cached = get_cached_lookup("neighborhood", "ulpiana")
    assert cached is not None
    assert cached.slug == "ulpiana"
    assert get_cached_listing_counts()["neighborhood/ulpiana"] == 50


def test_search_listing_count_fallback_from_pulse_and_sale_types() -> None:
    from groundtruth.services.lookup_cache import _search_listing_count

    payload = {
        "pulse": {"active_listings": 2},
        "sale_by_property_type": [
            {"property_type": "house", "listings": 14},
            {"property_type": "land", "listings": 3},
        ],
    }
    assert _search_listing_count(payload) == 19
    assert _search_listing_count({**payload, "total_listings": 23}) == 23


def test_parse_health_threshold() -> None:
    from groundtruth.services.parse_health import ParseHealthAlert

    alert = ParseHealthAlert(
        source="gjirafa",
        scrape_run_id=1,
        parse_failure_rate=0.15,
        parsed_failed=15,
        total_scraped=100,
        threshold=0.10,
        created_at=__import__("datetime").datetime.now(__import__("datetime").UTC),
    )
    assert "15.0%" in alert.message
    assert "gjirafa" in alert.message
