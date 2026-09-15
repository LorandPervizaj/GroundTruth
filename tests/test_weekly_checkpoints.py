"""Tests for weekly pipeline checkpoint stages."""

from __future__ import annotations

from groundtruth.crawl.checkpoints import (
    ensure_checkpoint,
    load_checkpoint,
    save_checkpoint,
)


def test_checkpoint_roundtrip(tmp_path, monkeypatch) -> None:
    tmp_path / "weekly" / "checkpoints"
    monkeypatch.setattr(
        "groundtruth.crawl.checkpoints.PROJECT_ROOT",
        tmp_path,
    )

    cp = ensure_checkpoint(
        "2026-W25",
        window_days=7,
        source_jobs=[("gjirafa-rent", "gjirafa-rent"), ("merrjep-rent", "merrjep")],
    )
    cp.sources["gjirafa-rent"].crawl = "done"
    cp.sources["gjirafa-rent"].scrape_run_id = 42
    save_checkpoint(cp)

    loaded = load_checkpoint("2026-W25")
    assert loaded is not None
    assert loaded.sources["gjirafa-rent"].scrape_run_id == 42
    assert loaded.sources["gjirafa-rent"].crawl == "done"


def test_checkpoint_resets_when_window_days_change(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("groundtruth.crawl.checkpoints.PROJECT_ROOT", tmp_path)

    cp = ensure_checkpoint(
        "2026-W34",
        window_days=7,
        source_jobs=[("gjirafa-rent", "gjirafa-rent")],
    )
    cp.sources["gjirafa-rent"].crawl = "done"
    cp.sources["gjirafa-rent"].scrape_run_id = 9
    save_checkpoint(cp)

    loaded = ensure_checkpoint(
        "2026-W34",
        window_days=21,
        source_jobs=[("gjirafa-rent", "gjirafa-rent"), ("merrjep-rent", "merrjep")],
    )
    assert loaded.window_days == 21
    assert loaded.sources["gjirafa-rent"].crawl == "pending"
    assert loaded.sources["gjirafa-rent"].scrape_run_id is None
    assert loaded.sources["merrjep-rent"].spider == "merrjep"
    assert loaded.analytics == "pending"
