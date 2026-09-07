"""Persisted checkpoint state for independently re-runnable weekly pipeline stages."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any, Literal

from groundtruth.config import PROJECT_ROOT

StageName = Literal["crawl", "etl", "analytics"]
StageStatus = Literal["pending", "running", "done", "failed", "skipped"]


class WeeklyStage(StrEnum):
    ALL = "all"
    CRAWL = "crawl"
    ETL = "etl"
    ANALYTICS = "analytics"


@dataclass
class SourceCheckpoint:
    source_label: str
    spider: str
    crawl: StageStatus = "pending"
    etl: StageStatus = "pending"
    scrape_run_id: int | None = None
    etl_normalized: int = 0
    error: str | None = None
    updated_at: str | None = None

    def touch(self) -> None:
        self.updated_at = datetime.now(UTC).isoformat()


@dataclass
class WeeklyCheckpoint:
    crawl_week: str
    window_days: int
    analytics: StageStatus = "pending"
    sources: dict[str, SourceCheckpoint] = field(default_factory=dict)
    started_at: str | None = None
    finished_at: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "crawl_week": self.crawl_week,
            "window_days": self.window_days,
            "analytics": self.analytics,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "sources": {k: asdict(v) for k, v in self.sources.items()},
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> WeeklyCheckpoint:
        sources = {k: SourceCheckpoint(**v) for k, v in (data.get("sources") or {}).items()}
        return cls(
            crawl_week=data["crawl_week"],
            window_days=int(data.get("window_days", 7)),
            analytics=data.get("analytics", "pending"),
            sources=sources,
            started_at=data.get("started_at"),
            finished_at=data.get("finished_at"),
        )


def checkpoint_path(crawl_week: str) -> Path:
    base = PROJECT_ROOT / "reports" / "generated" / "weekly" / "checkpoints"
    base.mkdir(parents=True, exist_ok=True)
    return base / f"{crawl_week}.json"


def load_checkpoint(crawl_week: str) -> WeeklyCheckpoint | None:
    path = checkpoint_path(crawl_week)
    if not path.is_file():
        return None
    return WeeklyCheckpoint.from_dict(json.loads(path.read_text(encoding="utf-8")))


def save_checkpoint(checkpoint: WeeklyCheckpoint) -> Path:
    path = checkpoint_path(checkpoint.crawl_week)
    path.write_text(json.dumps(checkpoint.to_dict(), indent=2), encoding="utf-8")
    return path


def ensure_checkpoint(
    crawl_week: str,
    *,
    window_days: int,
    source_jobs: list[tuple[str, str]],
) -> WeeklyCheckpoint:
    existing = load_checkpoint(crawl_week)
    if existing is not None:
        added = False
        if existing.window_days != window_days:
            # Catch-up with a longer lookback must recrawl, not resume a 7-day run.
            existing.window_days = window_days
            existing.analytics = "pending"
            existing.finished_at = None
            for src in existing.sources.values():
                src.crawl = "pending"
                src.etl = "pending"
                src.scrape_run_id = None
                src.etl_normalized = 0
                src.error = None
                src.touch()
            added = True
        for label, spider in source_jobs:
            if label not in existing.sources:
                existing.sources[label] = SourceCheckpoint(source_label=label, spider=spider)
                added = True
        if added:
            save_checkpoint(existing)
        return existing
    cp = WeeklyCheckpoint(
        crawl_week=crawl_week,
        window_days=window_days,
        started_at=datetime.now(UTC).isoformat(),
    )
    for label, spider in source_jobs:
        cp.sources[label] = SourceCheckpoint(source_label=label, spider=spider)
    save_checkpoint(cp)
    return cp
