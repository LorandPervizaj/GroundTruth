from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

from groundtruth.crawl import weekly as weekly_mod
from groundtruth.crawl.window import CrawlWindow


def test_concurrent_jobs_of_one_spider_resolve_to_their_own_runs(monkeypatch) -> None:
    runs_by_job: dict[str, int] = {}
    labels_by_job: dict[str, str] = {}

    def fake_subprocess_run(cmd, **_kwargs):
        metadata = json.loads(cmd[cmd.index("--crawl-window") + 1])
        runs_by_job[metadata["crawl_job_id"]] = 177 + len(runs_by_job) * 6
        labels_by_job[metadata["crawl_job_id"]] = metadata["crawl_label"]
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(weekly_mod.subprocess, "run", fake_subprocess_run)
    monkeypatch.setattr(weekly_mod, "_scrape_run_id_for_job", runs_by_job.get)

    window = CrawlWindow.last_n_days(14)
    rent = weekly_mod._run_spider("merrjep", window, crawl_label="merrjep-rent", index="a")
    sale = weekly_mod._run_spider("merrjep", window, crawl_label="merrjep-sale", index="b")

    assert (rent, sale) == (177, 183)
    assert sorted(labels_by_job.values()) == ["merrjep-rent", "merrjep-sale"]


def test_refresh_analytics_stamps_rent_yield_hash(monkeypatch, tmp_path: Path) -> None:
    manifest = tmp_path / "manifest.json"
    manifest.write_text("{}", encoding="utf-8")
    calls: list[str] = []

    class Quiet:
        def print(self, *_a, **_k) -> None:
            return None

    monkeypatch.setattr(
        "groundtruth.analytics.dataframe.normalized_listings_dataframe",
        lambda _s: __import__("pandas").DataFrame(),
    )
    monkeypatch.setattr(
        "groundtruth.analytics.audit.run_audit", lambda *_a, **_k: SimpleNamespace()
    )
    monkeypatch.setattr("groundtruth.analytics.audit.write_audit_artifacts", lambda *_a, **_k: None)
    monkeypatch.setattr(
        "groundtruth.analytics.corpus.write_corpus_artifacts", lambda *_a, **_k: None
    )
    monkeypatch.setattr(
        "groundtruth.analytics.annual_export.export_annual_report",
        lambda *_a, **_k: tmp_path / "annual.json",
    )
    monkeypatch.setattr(
        "groundtruth.services.lookup_cache.build_lookup_cache", lambda *_a, **_k: manifest
    )
    monkeypatch.setattr(
        "groundtruth.services.rent_yield.build_rent_yield_from_lookup_cache",
        lambda: calls.append("build_rent_yield"),
    )
    monkeypatch.setattr(
        "groundtruth.services.lookup_cache.stamp_related_artifact_hash",
        lambda *, key, path: calls.append(f"stamp:{key}"),
    )
    monkeypatch.setattr(
        "groundtruth.analytics.statistical_qa.run_statistical_qa",
        lambda *_a, **_k: calls.append("qa") or ("PASS", {"summary": "s"}),
    )
    monkeypatch.setattr(
        "groundtruth.analytics.source_skew.source_skew_report",
        lambda *_a, **_k: SimpleNamespace(as_dict=lambda: {}),
    )
    (tmp_path / "reports" / "generated").mkdir(parents=True)
    monkeypatch.setattr(weekly_mod, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr("groundtruth.release.verify_release_artifacts", lambda: [])

    weekly_mod.refresh_analytics(MagicMock(), window=CrawlWindow.last_n_days(7), console=Quiet())

    assert calls == ["build_rent_yield", "stamp:rent_yield", "qa"]
