"""Tests for gated ingest lookback, page scaling, and crawl feedback."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from groundtruth.crawl.checkpoints import SourceCheckpoint, WeeklyCheckpoint
from groundtruth.crawl.weekly import (
    _WEEKLY_MAX_PAGES_API,
    _WEEKLY_MAX_PAGES_HTML,
    _weekly_spider_jobs,
    build_crawl_feedback,
    resolve_ingest_days,
    scaled_max_pages,
)
from groundtruth.crawl.window import CrawlWindow


def test_scaled_max_pages_triples_for_three_weeks() -> None:
    assert scaled_max_pages(_WEEKLY_MAX_PAGES_HTML, 7) == 40
    assert scaled_max_pages(_WEEKLY_MAX_PAGES_HTML, 21) == 120
    assert scaled_max_pages(_WEEKLY_MAX_PAGES_API, 21) == 45


def test_weekly_jobs_use_scaled_pages_for_catch_up() -> None:
    window = CrawlWindow.last_n_days(21)
    jobs = {label: kwargs for label, _spider, kwargs in _weekly_spider_jobs(window)}
    assert jobs["merrjep-rent"]["max_pages"] == "120"
    assert jobs["merrjep-rent"]["index"] == "apartments_rent,houses_rent"
    assert jobs["merrjep-sale"]["index"] == "apartments_sale,houses_sale"
    assert jobs["gjirafa-sale"]["max_age_days"] == "21"
    assert jobs["gjirafa-sale"]["max_pages"] == "60"
    assert "banesa" in jobs["gjirafa-rent"]["categories"]
    assert "zyre" in jobs["gjirafa-rent"]["categories"]
    assert jobs["pro-rks"]["max_pages"] == "45"
    assert jobs["pro-rks"]["skip_existing_days"] == "21"


def test_resolve_ingest_days_weeks_and_conflict() -> None:
    assert resolve_ingest_days(days=21) == 21
    assert resolve_ingest_days(weeks=3) == 21
    try:
        resolve_ingest_days(days=21, weeks=3)
        raise AssertionError("expected ValueError")
    except ValueError as exc:
        assert "only one" in str(exc)
    try:
        resolve_ingest_days(weeks=5)
        raise AssertionError("expected ValueError")
    except ValueError as exc:
        assert "1, 2, 3, or 4" in str(exc)


def test_suggested_ingest_weeks_rounds_up_from_last_scrape(monkeypatch) -> None:
    from groundtruth.crawl.weekly import suggested_ingest_weeks

    last = (datetime.now(UTC) - timedelta(days=19)).isoformat()
    monkeypatch.setattr(
        "groundtruth.crawl.weekly.load_weekly_state",
        lambda: {"last_run_at": last},
    )
    weeks, elapsed = suggested_ingest_weeks()
    assert elapsed == 19
    assert weeks == 3


def test_resolve_ingest_days_uses_last_run(monkeypatch) -> None:
    last = (datetime.now(UTC) - timedelta(days=22)).isoformat()
    monkeypatch.setattr(
        "groundtruth.crawl.weekly.load_weekly_state",
        lambda: {"last_run_at": last},
    )
    assert resolve_ingest_days() == 22


def test_build_crawl_feedback_surfaces_failures(monkeypatch) -> None:
    monkeypatch.setattr(
        "groundtruth.crawl.weekly._scrape_run_stats",
        lambda run_id: (12, 0, None) if run_id == 1 else (0, 3, "boom"),
    )
    checkpoint = WeeklyCheckpoint(
        crawl_week="2026-W34",
        window_days=21,
        sources={
            "gjirafa-rent": SourceCheckpoint(
                source_label="gjirafa-rent",
                spider="gjirafa-rent",
                crawl="done",
                scrape_run_id=1,
            ),
            "topia": SourceCheckpoint(
                source_label="topia",
                spider="topia",
                crawl="failed",
                scrape_run_id=2,
                error="crawl topia exited with code 1",
            ),
        },
    )
    rows = {row["source"]: row for row in build_crawl_feedback(checkpoint)}
    assert rows["gjirafa-rent"]["status"] == "done"
    assert rows["gjirafa-rent"]["listings_stored"] == 12
    assert rows["topia"]["status"] == "failed"
    assert "exited" in (rows["topia"]["error"] or "")


def test_gated_ingest_stops_when_confirm_declined(monkeypatch) -> None:
    from groundtruth.crawl.weekly import WeeklyCrawlReport, run_gated_ingest

    calls: list[str] = []

    def fake_pipeline(**kwargs):
        calls.append(str(kwargs["stage"]))
        window = CrawlWindow.last_n_days(21)
        return WeeklyCrawlReport(window=window, started_at=datetime.now(UTC))

    class QuietConsole:
        def print(self, *_args, **_kwargs) -> None:
            return None

    monkeypatch.setattr("groundtruth.crawl.weekly.run_weekly_pipeline", fake_pipeline)
    monkeypatch.setattr(
        "groundtruth.crawl.weekly.build_crawl_feedback",
        lambda _cp: [
            {
                "source": "gjirafa-rent",
                "spider": "gjirafa-rent",
                "status": "done",
                "scrape_run_id": 1,
                "listings_stored": 4,
                "errors_count": 0,
                "error": None,
            }
        ],
    )
    monkeypatch.setattr(
        "groundtruth.crawl.checkpoints.load_checkpoint",
        lambda _week: WeeklyCheckpoint(crawl_week="2026-W34", window_days=21),
    )

    run_gated_ingest(days=21, confirm=lambda *_args, **_kwargs: False, console=QuietConsole())
    assert calls == ["crawl"]
