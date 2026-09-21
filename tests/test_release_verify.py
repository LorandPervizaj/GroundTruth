"""Tests for release artifact verification (hashes, schema, public safety)."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from groundtruth.analytics.valuation import (
    COMPARABLES_META_FILE,
    RENT_COMPARABLES_FILE,
    SALE_COMPARABLES_FILE,
)
from groundtruth.claims.hashes import sha256_file
from groundtruth.release import verify_release_artifacts
from groundtruth.schemas.lookup import MarketLookup, MarketPulse, RecentListing


def _recent() -> dict:
    return RecentListing(
        source="gjirafa",
        source_listing_id="1",
        url="https://example.com/a",
        listing_type="rent",
        price_eur=400.0,
        area_sqm=50.0,
        bedrooms=1,
    ).model_dump(mode="json")


def _lookup_payload() -> dict:
    return MarketLookup(
        entity_type="neighborhood",
        slug="dardania",
        display_name="Dardania",
        pulse=MarketPulse(active_listings=5, confidence="low"),
        recent_listings=[RecentListing.model_validate(_recent())],
        total_listings=5,
    ).model_dump(mode="json")


def _write_bytes(path: Path, data: bytes) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return sha256_file(path)


def _write_json(path: Path, payload: object) -> str:
    return _write_bytes(path, json.dumps(payload).encode("utf-8"))


def _valid_bundle(tmp_path: Path) -> tuple[Path, Path]:
    """Create a minimal valid lookup_cache + annual report. Returns (cache_dir, annual_path)."""
    cache = tmp_path / "lookup_cache"
    cache.mkdir()
    entry_rel = "neighborhood/dardania.json"
    entry_sha = _write_json(cache / entry_rel, _lookup_payload())

    artifact_hashes = {
        COMPARABLES_META_FILE: _write_json(
            cache / COMPARABLES_META_FILE,
            {"corpus_revision": "2026-01-01T00:00:00+00:00", "rent_rows": 0, "sale_rows": 0},
        ),
        RENT_COMPARABLES_FILE: _write_bytes(cache / RENT_COMPARABLES_FILE, b"\x1f\x8bfake-gzip"),
        SALE_COMPARABLES_FILE: _write_bytes(cache / SALE_COMPARABLES_FILE, b"\x1f\x8bfake-gzip"),
    }

    annual = tmp_path / "annual_report.json"
    annual_sha = _write_json(annual, {"generated_at": "2026-01-01T00:00:00+00:00"})
    qa_details = tmp_path / "market_qa_details.json"
    qa_sha = _write_json(qa_details, {"status": "PASS", "issues": []})

    manifest = {
        "built_at": "2026-01-01T00:00:00+00:00",
        "corpus_revision": "2026-01-01T00:00:00+00:00",
        "dataset_version": "v2.0",
        "dataset_hash": "abc",
        "entry_count": 1,
        "entries": [
            {
                "entity_type": "neighborhood",
                "slug": "dardania",
                "path": entry_rel,
                "sha256": entry_sha,
            }
        ],
        "artifact_hashes": artifact_hashes,
        "related_artifacts": {"annual_report": {"sha256": annual_sha}},
        "statistical_qa": {
            "status": "PASS",
            "details_sha256": qa_sha,
            "details": str(qa_details),
        },
        "corpus_meta": {},
        "markets": [],
        "neighborhood_options": [],
    }
    (cache / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    return cache, annual


def _run_verify(cache: Path, annual: Path):
    with (
        patch("groundtruth.release.lookup_cache_dir", return_value=cache),
        patch("groundtruth.release.DEFAULT_ANNUAL_REPORT_PATH", annual),
    ):
        return verify_release_artifacts()


def test_verify_release_artifacts_ok(tmp_path: Path) -> None:
    cache, annual = _valid_bundle(tmp_path)
    lines = _run_verify(cache, annual)
    assert any("lookup_cache_ok" in line for line in lines)
    assert any("annual_report_ok" in line for line in lines)


def test_verify_missing_manifest(tmp_path: Path) -> None:
    cache = tmp_path / "lookup_cache"
    cache.mkdir()
    annual = tmp_path / "annual_report.json"
    annual.write_text("{}", encoding="utf-8")
    with (
        patch("groundtruth.release.lookup_cache_dir", return_value=cache),
        pytest.raises(FileNotFoundError, match="manifest"),
    ):
        verify_release_artifacts()


def test_verify_malformed_manifest_json(tmp_path: Path) -> None:
    cache, annual = _valid_bundle(tmp_path)
    (cache / "manifest.json").write_text("{not-json", encoding="utf-8")
    with (
        patch("groundtruth.release.lookup_cache_dir", return_value=cache),
        patch("groundtruth.release.DEFAULT_ANNUAL_REPORT_PATH", annual),
        pytest.raises(ValueError, match="invalid JSON"),
    ):
        verify_release_artifacts()


def test_verify_missing_artifact_hashes(tmp_path: Path) -> None:
    cache, annual = _valid_bundle(tmp_path)
    manifest = json.loads((cache / "manifest.json").read_text(encoding="utf-8"))
    del manifest["artifact_hashes"]
    (cache / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    with (
        patch("groundtruth.release.lookup_cache_dir", return_value=cache),
        patch("groundtruth.release.DEFAULT_ANNUAL_REPORT_PATH", annual),
        pytest.raises(ValueError, match="artifact_hashes"),
    ):
        verify_release_artifacts()


def test_verify_incorrect_entry_hash(tmp_path: Path) -> None:
    cache, annual = _valid_bundle(tmp_path)
    manifest = json.loads((cache / "manifest.json").read_text(encoding="utf-8"))
    manifest["entries"][0]["sha256"] = "0" * 64
    (cache / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    with (
        patch("groundtruth.release.lookup_cache_dir", return_value=cache),
        patch("groundtruth.release.DEFAULT_ANNUAL_REPORT_PATH", annual),
        pytest.raises(ValueError, match="sha256 mismatch"),
    ):
        verify_release_artifacts()


def test_verify_forbidden_public_field(tmp_path: Path) -> None:
    cache, annual = _valid_bundle(tmp_path)
    bad = _lookup_payload()
    bad["recent_listings"] = [{**_recent(), "description": "call me"}]
    entry_path = cache / "neighborhood" / "dardania.json"
    entry_sha = _write_json(entry_path, bad)
    manifest = json.loads((cache / "manifest.json").read_text(encoding="utf-8"))
    manifest["entries"][0]["sha256"] = entry_sha
    (cache / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    with (
        patch("groundtruth.release.lookup_cache_dir", return_value=cache),
        patch("groundtruth.release.DEFAULT_ANNUAL_REPORT_PATH", annual),
        pytest.raises(ValueError, match="forbidden"),
    ):
        verify_release_artifacts()


def test_verify_schema_mismatch(tmp_path: Path) -> None:
    cache, annual = _valid_bundle(tmp_path)
    entry_path = cache / "neighborhood" / "dardania.json"
    entry_sha = _write_json(entry_path, {"slug": "dardania"})
    manifest = json.loads((cache / "manifest.json").read_text(encoding="utf-8"))
    manifest["entries"][0]["sha256"] = entry_sha
    (cache / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    with (
        patch("groundtruth.release.lookup_cache_dir", return_value=cache),
        patch("groundtruth.release.DEFAULT_ANNUAL_REPORT_PATH", annual),
        pytest.raises(ValueError, match="invalid MarketLookup"),
    ):
        verify_release_artifacts()


def test_verify_missing_entry_file(tmp_path: Path) -> None:
    cache, annual = _valid_bundle(tmp_path)
    (cache / "neighborhood" / "dardania.json").unlink()
    with (
        patch("groundtruth.release.lookup_cache_dir", return_value=cache),
        patch("groundtruth.release.DEFAULT_ANNUAL_REPORT_PATH", annual),
        pytest.raises(FileNotFoundError, match="missing files"),
    ):
        verify_release_artifacts()


def test_verify_requires_annual_related_hash(tmp_path: Path) -> None:
    cache, annual = _valid_bundle(tmp_path)
    manifest = json.loads((cache / "manifest.json").read_text(encoding="utf-8"))
    del manifest["related_artifacts"]
    (cache / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    with (
        patch("groundtruth.release.lookup_cache_dir", return_value=cache),
        patch("groundtruth.release.DEFAULT_ANNUAL_REPORT_PATH", annual),
        pytest.raises(ValueError, match="related_artifacts.annual_report"),
    ):
        verify_release_artifacts()


def test_verify_rejects_inconsistent_corpus_revision(tmp_path: Path) -> None:
    cache, annual = _valid_bundle(tmp_path)
    meta_path = cache / COMPARABLES_META_FILE
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    meta["corpus_revision"] = "other-revision"
    meta_sha = _write_json(meta_path, meta)
    manifest = json.loads((cache / "manifest.json").read_text(encoding="utf-8"))
    manifest["artifact_hashes"][COMPARABLES_META_FILE] = meta_sha
    (cache / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    with (
        patch("groundtruth.release.lookup_cache_dir", return_value=cache),
        patch("groundtruth.release.DEFAULT_ANNUAL_REPORT_PATH", annual),
        pytest.raises(ValueError, match="inconsistent release state"),
    ):
        verify_release_artifacts()
