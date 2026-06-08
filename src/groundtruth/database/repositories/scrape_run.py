"""Repository for scrape run tracking."""

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from groundtruth.database.repositories.base import BaseRepository
from groundtruth.models.enums import ScrapeRunStatus
from groundtruth.models.scrape_run import ScrapeRun


class ScrapeRunRepository(BaseRepository[ScrapeRun]):
    """Persistence operations for scrape runs."""

    model = ScrapeRun

    def __init__(self, session: Session) -> None:
        super().__init__(session)

    def create_run(
        self,
        spider_name: str,
        spider_version: str = "1.0.0",
        metadata: dict | None = None,
    ) -> ScrapeRun:
        """Start a new scrape run."""
        run = ScrapeRun(
            spider_name=spider_name,
            spider_version=spider_version,
            status=ScrapeRunStatus.RUNNING,
            metadata_=metadata,
        )
        return self.add(run)

    def complete_run(
        self,
        run: ScrapeRun,
        *,
        listings_found: int,
        listings_stored: int,
        errors_count: int = 0,
    ) -> ScrapeRun:
        """Mark a scrape run as completed."""
        run.status = ScrapeRunStatus.COMPLETED
        run.finished_at = datetime.now(UTC)
        run.listings_found = listings_found
        run.listings_stored = listings_stored
        run.errors_count = errors_count
        self._session.flush()
        return run

    def fail_run(self, run: ScrapeRun, error_message: str) -> ScrapeRun:
        """Mark a scrape run as failed."""
        run.status = ScrapeRunStatus.FAILED
        run.finished_at = datetime.now(UTC)
        run.error_message = error_message
        self._session.flush()
        return run

    def get_latest_by_spider(self, spider_name: str) -> ScrapeRun | None:
        """Return the most recent scrape run for a spider."""
        stmt = (
            select(ScrapeRun)
            .where(ScrapeRun.spider_name == spider_name)
            .order_by(ScrapeRun.started_at.desc())
            .limit(1)
        )
        return self._session.scalars(stmt).first()
