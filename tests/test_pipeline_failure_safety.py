"""Pipeline failure safety: verify/analytics/parse-health fail closed where required."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from groundtruth.crawl.window import CrawlWindow
from groundtruth.services.parse_health import ParseHealthAlert, assert_parse_health, check_parse_health


def test_refresh_analytics_reraises_when_release_verify_fails(monkeypatch) -> None:
    """A failed artifact verification must abort the analytics stage (no silent success)."""
    from groundtruth.crawl import weekly as weekly_mod

    calls: list[str] = []

    class Quiet:
        def print(self, *_a, **_k) -> None:
            return None

    session = MagicMock()
    session.execute = MagicMock()

    monkeypatch.setattr(
        "groundtruth.analytics.dataframe.normalized_listings_dataframe",
        lambda _s: __import__("pandas").DataFrame(),
    )
    monkeypatch.setattr("groundtruth.analytics.audit.run_audit", lambda *_a, **_k: SimpleNamespace())
    monkeypatch.setattr("groundtruth.analytics.audit.write_audit_artifacts", lambda *_a, **_k: None)
    monkeypatch.setattr("groundtruth.analytics.corpus.write_corpus_artifacts", lambda *_a, **_k: None)
    monkeypatch.setattr(
        "groundtruth.analytics.annual_export.export_annual_report",
        lambda *_a, **_k: Path("annual.json"),
    )
    monkeypatch.setattr(
        "groundtruth.services.lookup_cache.build_lookup_cache",
        lambda *_a, **_k: Path("cache"),
    )
    monkeypatch.setattr(
        "groundtruth.analytics.source_skew.source_skew_report",
        lambda *_a, **_k: SimpleNamespace(as_dict=lambda: {}),
    )

    def boom():
        calls.append("verify")
        raise RuntimeError("hash mismatch")

    monkeypatch.setattr("groundtruth.release.verify_release_artifacts", boom)

    window = CrawlWindow.last_n_days(7)
    with pytest.raises(RuntimeError, match="hash mismatch"):
        weekly_mod.refresh_analytics(session, window=window, console=Quiet())
    assert calls == ["verify"]


def test_assert_parse_health_raises_on_collapse(monkeypatch) -> None:
    alert = ParseHealthAlert(
        source="gjirafa",
        scrape_run_id=9,
        parse_failure_rate=0.9,
        parsed_failed=90,
        total_scraped=100,
        threshold=0.3,
        created_at=datetime.now(UTC),
    )
    monkeypatch.setattr(
        "groundtruth.services.parse_health.check_parse_health",
        lambda *_a, **_k: [alert],
    )
    with pytest.raises(RuntimeError, match="Parse health check failed"):
        assert_parse_health(MagicMock())


def test_check_parse_health_skips_tiny_samples() -> None:
    """Guard: tiny samples must not trip collapse alerts (min_sample)."""
    session = MagicMock()
    session.execute.return_value.mappings.return_value.all.return_value = [
        {
            "source": "tiny",
            "scrape_run_id": 1,
            "total_scraped": 5,
            "parsed_failed": 5,
            "created_at": datetime.now(UTC),
        }
    ]
    alerts = check_parse_health(session, threshold=0.1, min_sample=20)
    assert alerts == []
