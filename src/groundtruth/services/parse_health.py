"""Parse-failure rate monitoring — catch portal HTML breakage mid-week."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import text
from sqlalchemy.orm import Session

from groundtruth.config import get_settings


@dataclass(frozen=True)
class ParseHealthAlert:
    source: str
    scrape_run_id: int | None
    parse_failure_rate: float
    parsed_failed: int
    total_scraped: int
    threshold: float
    created_at: datetime

    @property
    def message(self) -> str:
        return (
            f"Parse failure rate for {self.source} is {self.parse_failure_rate:.1%} "
            f"({self.parsed_failed}/{self.total_scraped}) — exceeds threshold "
            f"{self.threshold:.1%}"
        )


def check_parse_health(
    session: Session,
    *,
    lookback_days: int = 7,
    threshold: float | None = None,
    min_sample: int = 20,
) -> list[ParseHealthAlert]:
    """Flag sources whose recent ETL runs exceed parse-failure threshold."""
    threshold = threshold if threshold is not None else get_settings().parse_failure_alert_threshold
    cutoff = datetime.now(UTC) - timedelta(days=lookback_days)
    rows = (
        session.execute(
            text(
                """
            SELECT DISTINCT ON (source)
                source,
                scrape_run_id,
                total_scraped,
                parsed_failed,
                created_at
            FROM etl_metrics
            WHERE created_at >= :cutoff
              AND total_scraped >= :min_sample
            ORDER BY source, created_at DESC
            """
            ),
            {"cutoff": cutoff, "min_sample": min_sample},
        )
        .mappings()
        .all()
    )

    alerts: list[ParseHealthAlert] = []
    for row in rows:
        total = int(row["total_scraped"] or 0)
        failed = int(row["parsed_failed"] or 0)
        if total < min_sample:
            continue
        rate = failed / total
        if rate > threshold:
            alerts.append(
                ParseHealthAlert(
                    source=str(row["source"]),
                    scrape_run_id=int(row["scrape_run_id"]) if row["scrape_run_id"] else None,
                    parse_failure_rate=rate,
                    parsed_failed=failed,
                    total_scraped=total,
                    threshold=threshold,
                    created_at=row["created_at"] or datetime.now(UTC),
                )
            )
    return alerts


def assert_parse_health(session: Session, **kwargs) -> None:
    """Raise RuntimeError if any source exceeds parse-failure threshold."""
    alerts = check_parse_health(session, **kwargs)
    if alerts:
        lines = "\n".join(f"  - {a.message}" for a in alerts)
        raise RuntimeError(f"Parse health check failed:\n{lines}")
