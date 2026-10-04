"""Source-specific crawl health collection and classification."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from statistics import median
from typing import Any, Literal

from sqlalchemy import select
from sqlalchemy.orm import Session

from groundtruth.models.enums import ScrapeRunStatus
from groundtruth.models.scrape_run import ScrapeRun

HealthLevel = Literal["GREEN", "YELLOW", "RED"]


@dataclass(frozen=True)
class SourceThreshold:
    minimum_expected: int = 1
    historical_red_ratio: float = 0.1
    historical_yellow_ratio: float = 0.4
    minimum_baseline_for_ratio: int = 20
    error_rate_yellow: float = 0.1
    error_rate_red: float = 0.5


DEFAULT_THRESHOLDS: dict[str, SourceThreshold] = {
    "merrjep-rent": SourceThreshold(minimum_expected=1),
    "merrjep-sale": SourceThreshold(minimum_expected=1),
    "gjirafa-rent": SourceThreshold(minimum_expected=1),
    "gjirafa-sale": SourceThreshold(minimum_expected=1),
    "pro-rks": SourceThreshold(minimum_expected=1),
    "vision": SourceThreshold(minimum_expected=1),
    "topia": SourceThreshold(minimum_expected=1),
    "myrealestate": SourceThreshold(minimum_expected=1),
}


@dataclass
class SourceHealth:
    source: str
    level: HealthLevel
    scrape_run_id: int | None
    listings_found: int = 0
    listings_stored: int = 0
    listings_already_known: int = 0
    errors_count: int = 0
    historical_median: float | None = None
    reasons: list[str] = field(default_factory=list)
    metrics: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def classify_source_health(
    *,
    source: str,
    scrape_run_id: int | None,
    completed: bool,
    listings_found: int,
    listings_stored: int,
    errors_count: int,
    listings_already_known: int = 0,
    historical_counts: list[int] | None = None,
    threshold: SourceThreshold | None = None,
    explicit_error: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> SourceHealth:
    """Classify one crawl.

    Incremental crawls skip listings already in the database, so volume is
    measured as observed listings (stored + already known). ``historical_counts``
    must use the same measure.
    """
    policy = threshold or DEFAULT_THRESHOLDS.get(source, SourceThreshold())
    history = [value for value in (historical_counts or []) if value >= 0]
    baseline = float(median(history)) if history else None
    reasons: list[str] = []
    level: HealthLevel = "GREEN"
    observed = listings_stored + max(0, listings_already_known)
    attempts = listings_found + errors_count
    error_rate = errors_count / attempts if attempts else float(errors_count > 0)

    if not completed or explicit_error:
        level = "RED"
        reasons.append(explicit_error or "crawl did not complete")
    elif observed < policy.minimum_expected:
        if baseline is not None and baseline >= policy.minimum_baseline_for_ratio:
            level = "RED"
            reasons.append("observations collapsed below the source minimum")
        else:
            level = "YELLOW"
            reasons.append("no new observations; historical baseline is insufficient")

    if baseline is not None and baseline >= policy.minimum_baseline_for_ratio:
        ratio = observed / baseline if baseline else 0.0
        if ratio <= policy.historical_red_ratio:
            level = "RED"
            reasons.append(f"volume is {ratio:.1%} of historical median")
        elif ratio <= policy.historical_yellow_ratio and level == "GREEN":
            level = "YELLOW"
            reasons.append(f"volume is {ratio:.1%} of historical median")

    if error_rate >= policy.error_rate_red:
        level = "RED"
        reasons.append(f"error rate is {error_rate:.1%}")
    elif error_rate >= policy.error_rate_yellow and level == "GREEN":
        level = "YELLOW"
        reasons.append(f"error rate is {error_rate:.1%}")

    return SourceHealth(
        source=source,
        level=level,
        scrape_run_id=scrape_run_id,
        listings_found=listings_found,
        listings_stored=listings_stored,
        listings_already_known=max(0, listings_already_known),
        errors_count=errors_count,
        historical_median=baseline,
        reasons=reasons,
        metrics=metadata or {},
    )


def listings_already_known(metadata: dict[str, Any] | None) -> int:
    """Listings the spider saw but skipped because they were already stored."""
    spider_stats = ((metadata or {}).get("scrapy_stats") or {}).get("spider") or {}
    try:
        return max(0, int(spider_stats.get("detail_skipped_existing") or 0))
    except (TypeError, ValueError):
        return 0


def _historical_counts(
    session: Session,
    spider: str,
    current_id: int,
    crawl_label: str | None = None,
    limit: int = 8,
) -> list[int]:
    query = select(ScrapeRun.listings_stored, ScrapeRun.metadata_).where(
        ScrapeRun.spider_name == spider,
        ScrapeRun.id != current_id,
        ScrapeRun.status == ScrapeRunStatus.COMPLETED,
    )
    # Runs from before crawl labels existed cannot be told apart (merrjep rent vs
    # sale); use them only until enough labelled history has accumulated.
    rows: list[Any] = []
    if crawl_label:
        rows = list(
            session.execute(
                query.where(ScrapeRun.metadata_["crawl_label"].astext == crawl_label)
                .order_by(ScrapeRun.finished_at.desc())
                .limit(limit)
            ).all()
        )
    if len(rows) < 3:
        rows = list(
            session.execute(query.order_by(ScrapeRun.finished_at.desc()).limit(limit)).all()
        )
    return [int(stored or 0) + listings_already_known(metadata) for stored, metadata in rows]


def collect_source_health(session: Session, source_results: list[Any]) -> list[SourceHealth]:
    results: list[SourceHealth] = []
    for item in source_results:
        run = session.get(ScrapeRun, item.scrape_run_id) if item.scrape_run_id else None
        if run is None:
            results.append(
                classify_source_health(
                    source=item.source,
                    scrape_run_id=item.scrape_run_id,
                    completed=False,
                    listings_found=0,
                    listings_stored=0,
                    errors_count=0,
                    explicit_error=item.error or "scrape run record is missing",
                )
            )
            continue
        metadata = run.metadata_ or {}
        results.append(
            classify_source_health(
                source=item.source,
                scrape_run_id=run.id,
                completed=run.status == ScrapeRunStatus.COMPLETED,
                listings_found=run.listings_found,
                listings_stored=run.listings_stored,
                errors_count=run.errors_count,
                listings_already_known=listings_already_known(metadata),
                historical_counts=_historical_counts(
                    session, run.spider_name, run.id, crawl_label=metadata.get("crawl_label")
                ),
                explicit_error=item.error or run.error_message,
                metadata=metadata,
            )
        )
    return results
