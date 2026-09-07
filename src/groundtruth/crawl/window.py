"""Time-bounded crawl windows for weekly incremental ingestion."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Any


@dataclass(frozen=True, slots=True)
class CrawlWindow:
    """A bounded date range for incremental crawls (default: past 7 days)."""

    window_start: date
    window_end: date

    @classmethod
    def last_n_days(cls, days: int = 7, *, end: date | None = None) -> CrawlWindow:
        if days < 1:
            raise ValueError("days must be >= 1")
        window_end = end or datetime.now(UTC).date()
        return cls(window_start=window_end - timedelta(days=days - 1), window_end=window_end)

    @property
    def days(self) -> int:
        return (self.window_end - self.window_start).days + 1

    @property
    def crawl_week(self) -> str:
        """ISO week label, e.g. 2026-W24."""
        iso = self.window_end.isocalendar()
        return f"{iso.year}-W{iso.week:02d}"

    @property
    def bucket_month(self) -> str:
        """YYYY-MM partition key (month of window end)."""
        return self.window_end.strftime("%Y-%m")

    @property
    def cutoff_date(self) -> date:
        """Listings on or after this date are in-window."""
        return self.window_start

    def metadata(self) -> dict[str, Any]:
        return crawl_window_metadata(self)


def crawl_window_metadata(window: CrawlWindow) -> dict[str, Any]:
    return {
        "crawl_mode": "weekly",
        "window_days": window.days,
        "window_start": window.window_start.isoformat(),
        "window_end": window.window_end.isoformat(),
        "crawl_week": window.crawl_week,
        "bucket_month": window.bucket_month,
    }


def parse_gjirafa_listing_date(raw: str | None) -> date | None:
    """Parse Gjirafa ``Data`` field (dd/mm/YYYY [HH:MM])."""
    if not raw:
        return None
    text = raw.strip()
    for fmt in ("%d/%m/%Y %H:%M", "%d/%m/%Y"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None
