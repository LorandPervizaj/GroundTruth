"""Weekly crawl orchestration: all sources → ETL → analytics refresh."""

from __future__ import annotations

import json
import logging
import math
import os
import subprocess
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from rich.console import Console
from sqlalchemy.orm import Session

from groundtruth.config import PROJECT_ROOT, get_settings
from groundtruth.crawl.checkpoints import (
    WeeklyCheckpoint,
    WeeklyStage,
    checkpoint_path,
    ensure_checkpoint,
    save_checkpoint,
)
from groundtruth.crawl.spider_commands import (
    _WEEKLY_MAX_PAGES_API,  # noqa: F401
    _WEEKLY_MAX_PAGES_GJIRAFA,  # noqa: F401
    _WEEKLY_MAX_PAGES_HTML,  # noqa: F401
    KNOWN_WEEKLY_SPIDERS,  # noqa: F401
    _build_crawl_command,
    _validate_spider_name,
    _weekly_spider_jobs,
    scaled_max_pages,  # noqa: F401
)
from groundtruth.crawl.window import CrawlWindow, crawl_window_metadata
from groundtruth.logging import get_logger

logger = get_logger(__name__)

DEFAULT_WEEKLY_INTERVAL_DAYS = 7
STATE_FILENAME = "weekly_crawl_state.json"


def days_since_last_crawl() -> int | None:
    """Days since the last weekly ingest, or last completed scrape_run."""
    state = load_weekly_state()
    last = state.get("last_run_at")
    if last:
        last_dt = datetime.fromisoformat(last)
        if last_dt.tzinfo is None:
            last_dt = last_dt.replace(tzinfo=UTC)
        elapsed = datetime.now(UTC) - last_dt
        return max(1, elapsed.days)
    return _days_since_last_scrape_run()


def _days_since_last_scrape_run() -> int | None:
    from sqlalchemy import text

    from groundtruth.database.session import get_session_factory

    try:
        with get_session_factory()() as session:
            row = session.execute(
                text("SELECT MAX(finished_at) FROM scrape_runs WHERE finished_at IS NOT NULL")
            ).first()
    except Exception:
        logger.warning("last_scrape_run_lookup_failed", exc_info=True)
        return None
    if not row or row[0] is None:
        return None
    last_dt = row[0]
    if last_dt.tzinfo is None:
        last_dt = last_dt.replace(tzinfo=UTC)
    return max(1, (datetime.now(UTC) - last_dt).days)


def suggested_ingest_weeks(*, max_weeks: int = 4) -> tuple[int, int | None]:
    """Round elapsed time since last crawl up to 1–4 weeks."""
    elapsed = days_since_last_crawl()
    if elapsed is None:
        return 1, None
    weeks = min(max_weeks, max(1, math.ceil(elapsed / DEFAULT_WEEKLY_INTERVAL_DAYS)))
    return weeks, elapsed


def last_crawl_summary() -> tuple[str | None, int | None]:
    """Return (last_run iso timestamp, days ago) for operator prompts."""
    state = load_weekly_state()
    last = state.get("last_run_at")
    elapsed = days_since_last_crawl()
    return (str(last) if last else None, elapsed)


def prompt_ingest_weeks(*, console: Console | None = None) -> int:
    import typer

    out = console or Console()
    suggested, elapsed = suggested_ingest_weeks()
    last, _ = last_crawl_summary()
    if elapsed is None:
        out.print("[yellow]No previous crawl on record.[/yellow] Default lookback: 1 week.")
    else:
        when = last.split("T")[0] if last else "unknown"
        out.print(f"Last crawl: {when} ({elapsed} days ago). Suggested: {suggested} week(s).")
    while True:
        raw = typer.prompt(
            "How many weeks to scrape since the last one? [1/2/3/4]", default=str(suggested)
        )
        try:
            weeks = int(str(raw).strip())
        except (TypeError, ValueError):
            out.print("[red]Enter 1, 2, 3, or 4.[/red]")
            continue
        if weeks not in (1, 2, 3, 4):
            out.print("[red]Enter 1, 2, 3, or 4.[/red]")
            continue
        return weeks


def resolve_ingest_days(*, days: int | None = None, weeks: int | None = None) -> int:
    if days is not None and weeks is not None:
        raise ValueError("Pass only one of days or weeks")
    if days is not None:
        if days < 1:
            raise ValueError("days must be >= 1")
        return days
    if weeks is not None:
        if weeks < 1:
            raise ValueError("weeks must be >= 1")
        if weeks > 4:
            raise ValueError("weeks must be 1, 2, 3, or 4")
        return weeks * DEFAULT_WEEKLY_INTERVAL_DAYS
    elapsed = days_since_last_crawl()
    if elapsed is None:
        return DEFAULT_WEEKLY_INTERVAL_DAYS
    return max(DEFAULT_WEEKLY_INTERVAL_DAYS, elapsed)


@dataclass
class SourceCrawlResult:
    source: str
    spider: str
    scrape_run_id: int | None = None
    listings_stored: int = 0
    etl_normalized: int = 0
    error: str | None = None


@dataclass
class WeeklyCrawlReport:
    window: CrawlWindow
    started_at: datetime
    finished_at: datetime | None = None
    sources: list[SourceCrawlResult] = field(default_factory=list)
    artifact_dir: Path | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            **crawl_window_metadata(self.window),
            "started_at": self.started_at.isoformat(),
            "finished_at": self.finished_at.isoformat() if self.finished_at else None,
            "sources": [
                {
                    "source": s.source,
                    "spider": s.spider,
                    "scrape_run_id": s.scrape_run_id,
                    "listings_stored": s.listings_stored,
                    "etl_normalized": s.etl_normalized,
                    "error": s.error,
                }
                for s in self.sources
            ],
        }


def weekly_state_path() -> Path:
    return PROJECT_ROOT / "reports" / "generated" / "weekly" / STATE_FILENAME


def load_weekly_state() -> dict[str, Any]:
    path = weekly_state_path()
    if not path.is_file():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def save_weekly_state(*, window: CrawlWindow, report: WeeklyCrawlReport) -> Path:
    path = weekly_state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "last_run_at": report.finished_at.isoformat() if report.finished_at else None,
        "last_crawl_week": window.crawl_week,
        "window_end": window.window_end.isoformat(),
        "interval_days": DEFAULT_WEEKLY_INTERVAL_DAYS,
        "report": report.to_dict(),
    }
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path


def is_weekly_due(*, interval_days: int = DEFAULT_WEEKLY_INTERVAL_DAYS) -> bool:
    state = load_weekly_state()
    last = state.get("last_run_at")
    if not last:
        return True
    last_dt = datetime.fromisoformat(last)
    if last_dt.tzinfo is None:
        last_dt = last_dt.replace(tzinfo=UTC)
    elapsed = datetime.now(UTC) - last_dt
    return elapsed.days >= interval_days


def _crawl_subprocess_env() -> dict[str, str]:
    """UTF-8 + quiet scrapy logs; avoids Windows pipe encoding deadlocks."""
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"
    env.setdefault("LOG_LEVEL", "WARNING")
    return env


def _run_spider(spider_name: str, window: CrawlWindow, **kwargs: str) -> int | None:
    """Run one spider in a subprocess; return scrape_run_id from the new run."""
    _validate_spider_name(spider_name)
    kwargs = {
        **kwargs,
        "crawl_window": json.dumps(crawl_window_metadata(window), separators=(",", ":")),
    }
    before_id = _max_scrape_run_id()
    cmd = _build_crawl_command(spider_name, kwargs)
    logger.info("weekly_subprocess_crawl", spider=spider_name, command=cmd)
    result = subprocess.run(
        cmd,
        cwd=PROJECT_ROOT,
        check=False,
        env=_crawl_subprocess_env(),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    if result.returncode != 0:
        raise RuntimeError(f"crawl {spider_name} exited with code {result.returncode}")
    return _latest_scrape_run_id(spider_name, after_id=before_id)


def _close_stale_scrape_runs() -> None:
    from datetime import UTC, datetime

    from sqlalchemy import text

    from groundtruth.database.session import get_session_factory

    now = datetime.now(UTC)
    with get_session_factory()() as session:
        # Fail fast if another session is holding locks on scrape_runs.
        # Weekly crawl can safely continue even when stale-run cleanup is skipped.
        # SET LOCAL so short timeouts do not poison pooled connections used later
        # by analytics / corpus rebuild.
        session.execute(text("SET LOCAL lock_timeout = '3000ms'"))
        session.execute(text("SET LOCAL statement_timeout = '5000ms'"))
        session.execute(
            text(
                """
                UPDATE scrape_runs
                SET status = 'FAILED',
                    finished_at = :now,
                    error_message = 'Closed automatically — stale RUNNING run'
                WHERE status::text = 'RUNNING'
                """
            ),
            {"now": now},
        )
        session.commit()


def _latest_scrape_run_id(spider_name: str, after_id: int = 0) -> int | None:
    from sqlalchemy import text

    from groundtruth.database.session import get_session_factory

    with get_session_factory()() as session:
        row = session.execute(
            text(
                """
                SELECT id FROM scrape_runs
                WHERE spider_name = :spider AND id > :after_id
                ORDER BY id DESC LIMIT 1
                """
            ),
            {"spider": spider_name, "after_id": after_id},
        ).first()
    return int(row[0]) if row else None


def _max_scrape_run_id() -> int:
    from sqlalchemy import text

    from groundtruth.database.session import get_session_factory

    with get_session_factory()() as session:
        row = session.execute(text("SELECT COALESCE(MAX(id), 0) FROM scrape_runs")).first()
    return int(row[0]) if row else 0


def _scrape_run_stats(scrape_run_id: int) -> tuple[int, int, str | None]:
    """Return listings_stored, errors_count, error_message for a scrape run."""
    from sqlalchemy import text

    from groundtruth.database.session import get_session_factory

    with get_session_factory()() as session:
        row = session.execute(
            text(
                """
                SELECT listings_stored, errors_count, error_message
                FROM scrape_runs WHERE id = :id
                """
            ),
            {"id": scrape_run_id},
        ).first()
    if not row:
        return 0, 0, None
    return int(row[0] or 0), int(row[1] or 0), row[2]


def build_crawl_feedback(checkpoint: WeeklyCheckpoint) -> list[dict[str, Any]]:
    """Per-source crawl status for operator review (before ETL)."""
    rows: list[dict[str, Any]] = []
    for label, cp in checkpoint.sources.items():
        stored, err_count, db_err = 0, 0, None
        if cp.scrape_run_id:
            try:
                stored, err_count, db_err = _scrape_run_stats(cp.scrape_run_id)
            except Exception:
                logger.warning("scrape_run_stats_failed", source=label, run_id=cp.scrape_run_id)
        status = cp.crawl
        error = cp.error or db_err
        if status == "done" and err_count > 0:
            status = "ok_with_errors"
        rows.append(
            {
                "source": label,
                "spider": cp.spider,
                "status": status,
                "scrape_run_id": cp.scrape_run_id,
                "listings_stored": stored,
                "errors_count": err_count,
                "error": error,
            }
        )
    return rows


def print_crawl_feedback(rows: list[dict[str, Any]], *, console: Console | None = None) -> None:
    from rich.table import Table

    out = console or Console()
    table = Table(title="Scraper results", show_lines=False)
    table.add_column("Source", style="cyan")
    table.add_column("Status")
    table.add_column("Run", justify="right")
    table.add_column("Stored", justify="right")
    table.add_column("Errors", justify="right")
    table.add_column("Notes")
    failed = 0
    warned = 0
    ok = 0
    for row in rows:
        status = str(row.get("status") or "pending")
        if status == "done":
            ok += 1
            status_cell = "[green]ok[/green]"
        elif status == "ok_with_errors":
            warned += 1
            status_cell = "[yellow]ok (spider errors)[/yellow]"
        elif status == "failed":
            failed += 1
            status_cell = "[red]FAILED[/red]"
        else:
            status_cell = f"[dim]{status}[/dim]"
        note = row.get("error") or ""
        if status == "ok_with_errors" and not note:
            note = f"{row.get('errors_count', 0)} scrapy item/request errors"
        table.add_row(
            str(row["source"]),
            status_cell,
            str(row.get("scrape_run_id") or "—"),
            str(row.get("listings_stored") or 0),
            str(row.get("errors_count") or 0),
            str(note),
        )
    out.print()
    out.print(table)
    out.print(
        f"  [green]{ok} ok[/green]  [yellow]{warned} with spider errors[/yellow]  "
        f"[red]{failed} failed[/red]  ({len(rows)} sources)"
    )
    if failed:
        out.print(
            "[red]Some crawlers failed.[/red] Successful sources can still be normalized. "
            "Failed sources will be skipped until you re-run ingest."
        )
    out.print()


def _etl_source_for_label(label: str) -> str:
    if label.startswith("merrjep"):
        return "merrjep"
    if label.startswith("gjirafa"):
        return "gjirafa"
    return label


def _run_etl_for_run(
    session: Session,
    *,
    scrape_run_id: int,
    source: str,
    window: CrawlWindow,
) -> int:
    from groundtruth.services.etl import EtlService

    metrics = EtlService(session).run(
        scrape_run_id=scrape_run_id,
        source=source,
        skip_existing=False,
        max_age_days=window.days,
    )
    session.commit()
    return metrics.normalized_success


def refresh_analytics(
    session: Session,
    *,
    window: CrawlWindow,
    console: Console | None = None,
) -> None:
    """Update snapshots, observations, corpus, lookup cache, and annual report."""
    logging.getLogger("matplotlib").setLevel(logging.WARNING)
    logging.getLogger("matplotlib.font_manager").setLevel(logging.WARNING)
    from sqlalchemy import text

    from groundtruth.analytics.annual_export import export_annual_report
    from groundtruth.analytics.audit import run_audit, write_audit_artifacts
    from groundtruth.analytics.corpus import write_corpus_artifacts
    from groundtruth.analytics.dataframe import normalized_listings_dataframe
    from groundtruth.analytics.listing_history import record_listing_observations
    from groundtruth.analytics.snapshots import generate_market_snapshots
    from groundtruth.analytics.source_skew import source_skew_report
    from groundtruth.services.lookup_cache import build_lookup_cache

    out = console or Console()
    # Ensure analytics is not limited by short crawl cleanup timeouts.
    session.execute(text("SET statement_timeout = '0'"))
    session.execute(text("SET lock_timeout = '0'"))
    snapshot_date = window.window_end

    df = normalized_listings_dataframe(session)
    if not df.empty:
        generate_market_snapshots(session, df, snapshot_date=snapshot_date)
        record_listing_observations(session, observed_date=snapshot_date)
        session.commit()
        out.print(
            f"[green]Snapshots and observations recorded for {snapshot_date} "
            f"({window.crawl_week}).[/green]"
        )

    stamp = datetime.now(UTC).strftime("%Y-%m-%d")
    audit_dir = PROJECT_ROOT / "reports" / "generated" / f"audit_{stamp}"
    report = run_audit(session, dedupe=True)
    write_audit_artifacts(report, audit_dir)
    session.commit()

    corpus_dir = PROJECT_ROOT / "reports" / "generated"
    write_corpus_artifacts(session, corpus_dir)
    annual_path = export_annual_report(session)

    cache_path = build_lookup_cache(session)
    out.print(f"[green]Lookup cache built ({cache_path}).[/green]")

    from groundtruth.analytics.statistical_qa import run_statistical_qa

    # A real cache build always returns its manifest.  The guard keeps this
    # orchestration function testable with a stubbed cache builder while the
    # release verifier remains the final mandatory gate.
    if cache_path.is_file():
        qa_status, qa_paths = run_statistical_qa(cache_path.parent, cache_path.parent / "_qa")
        out.print(f"[green]Statistical QA: {qa_status} ({qa_paths['summary']}).[/green]")

    skew = source_skew_report(session)
    skew_path = corpus_dir / "source_skew.json"
    skew_path.write_text(json.dumps(skew.as_dict(), indent=2), encoding="utf-8")
    out.print(f"[green]Source skew report: {skew_path}[/green]")
    out.print(f"[green]Corpus and annual report updated ({annual_path}).[/green]")

    from groundtruth.release import verify_release_artifacts

    try:
        for line in verify_release_artifacts():
            out.print(f"[green]{line}[/green]")
    except Exception as exc:
        logger.exception("weekly_release_verify_failed")
        out.print(f"[red]Release artifact verification failed: {exc}[/red]")
        raise


def write_weekly_artifacts(report: WeeklyCrawlReport) -> Path:
    window = report.window
    base = PROJECT_ROOT / "reports" / "generated" / "weekly" / window.bucket_month
    base.mkdir(parents=True, exist_ok=True)
    path = base / f"{window.crawl_week}.json"
    path.write_text(json.dumps(report.to_dict(), indent=2), encoding="utf-8")
    report.artifact_dir = base
    return path


def _run_etl_for_label(
    label: str,
    checkpoint: WeeklyCheckpoint,
    window: CrawlWindow,
    *,
    resume: bool,
    out: Console,
) -> None:
    """Normalize one source immediately after its crawl finishes."""
    from groundtruth.database.session import get_session_factory

    cp = checkpoint.sources[label]
    if cp.crawl != "done" or cp.scrape_run_id is None:
        return
    if resume and cp.etl == "done":
        return
    cp.etl = "running"
    cp.touch()
    save_checkpoint(checkpoint)
    session = get_session_factory()()
    try:
        etl_source = _etl_source_for_label(label)
        cp.etl_normalized = _run_etl_for_run(
            session,
            scrape_run_id=cp.scrape_run_id,
            source=etl_source,
            window=window,
        )
        cp.etl = "done"
        cp.error = None
        cp.touch()
        save_checkpoint(checkpoint)
        out.print(f"    ETL {label}: normalized={cp.etl_normalized}")
    except Exception as exc:
        cp.etl = "failed"
        cp.error = str(exc) or type(exc).__name__
        cp.touch()
        save_checkpoint(checkpoint)
        logger.exception("weekly_etl_failed", source=label)
        out.print(f"    ETL {label}: [red]{cp.error}[/red]")
    finally:
        session.close()


def _run_crawl_jobs(
    jobs: list[tuple[str, str, dict[str, str]]],
    window: CrawlWindow,
    checkpoint: WeeklyCheckpoint,
    *,
    resume: bool,
    parallel: bool,
    trailing_etl: bool = False,
    out: Console,
) -> None:
    pending = [
        (label, spider, kwargs)
        for label, spider, kwargs in jobs
        if not resume
        or checkpoint.sources.get(label, None) is None
        or checkpoint.sources[label].crawl != "done"
    ]

    def _one(label: str, spider: str, kwargs: dict[str, str]) -> tuple[str, int | None, str | None]:
        cp = checkpoint.sources[label]
        cp.crawl = "running"
        cp.touch()
        save_checkpoint(checkpoint)
        try:
            scrape_run_id = _run_spider(spider, window, **kwargs)
            cp.scrape_run_id = scrape_run_id
            cp.crawl = "done" if scrape_run_id else "failed"
            cp.error = None if scrape_run_id else "no scrape_run_id"
            cp.touch()
            save_checkpoint(checkpoint)
            if trailing_etl and cp.crawl == "done":
                _run_etl_for_label(label, checkpoint, window, resume=resume, out=out)
            return label, scrape_run_id, cp.error
        except Exception as exc:
            cp.crawl = "failed"
            cp.error = str(exc) or type(exc).__name__
            cp.touch()
            save_checkpoint(checkpoint)
            return label, None, cp.error

    if not pending:
        return

    workers = get_settings().weekly_crawl_parallel_workers if parallel else 1
    if workers > 1 and len(pending) > 1:
        etl_note = " + trailing ETL" if trailing_etl else ""
        out.print(
            f"  [dim]Parallel crawl across {len(pending)} sources "
            f"(workers={workers}{etl_note})[/dim]"
        )
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {
                pool.submit(_one, label, spider, kwargs): label for label, spider, kwargs in pending
            }
            for fut in as_completed(futures):
                label, scrape_run_id, err = fut.result()
                out.print(
                    f"    {label}: run={scrape_run_id}"
                    + (f" [red]{err}[/red]" if err else " [green]ok[/green]")
                )
    else:
        for label, spider, kwargs in pending:
            out.print(f"  Crawling [cyan]{label}[/cyan]...")
            _, scrape_run_id, err = _one(label, spider, kwargs)
            out.print(f"    run={scrape_run_id}" + (f" [red]{err}[/red]" if err else ""))


def _run_etl_jobs(
    checkpoint: WeeklyCheckpoint,
    window: CrawlWindow,
    *,
    resume: bool,
    only_set: set[str] | None = None,
    out: Console,
) -> None:
    from groundtruth.database.session import get_session_factory
    from groundtruth.services.parse_health import check_parse_health

    for label in checkpoint.sources:
        if only_set and label.lower() not in only_set:
            continue
        _run_etl_for_label(label, checkpoint, window, resume=resume, out=out)

    _advance_lifecycle_from_checkpoint(checkpoint, out=out)

    session = get_session_factory()()
    try:
        alerts = check_parse_health(session)
        for alert in alerts:
            out.print(f"[red bold]PARSE ALERT[/red bold]: {alert.message}")
            logger.error("parse_health_alert", source=alert.source, rate=alert.parse_failure_rate)
    finally:
        session.close()


def _advance_lifecycle_from_checkpoint(
    checkpoint: WeeklyCheckpoint,
    *,
    out: Console,
) -> None:
    """Advance absence only after every crawl variant for a source is healthy."""
    from collections import defaultdict

    from sqlalchemy import select

    from groundtruth.analytics.lifecycle_state import (
        CrawlHealth,
        apply_source_crawl_lifecycle,
        lifecycle_policy_for_source,
        source_crawl_health,
    )
    from groundtruth.database.session import get_session_factory
    from groundtruth.models.pipeline import NormalizedListing

    grouped: dict[str, list[Any]] = defaultdict(list)
    for label, cp in checkpoint.sources.items():
        grouped[_etl_source_for_label(label)].append(cp)

    session = get_session_factory()()
    try:
        for source, checkpoints in grouped.items():
            run_ids = [cp.scrape_run_id for cp in checkpoints if cp.scrape_run_id is not None]
            if not run_ids:
                continue
            health_parts = []
            for cp in checkpoints:
                stored, errors, _ = (
                    _scrape_run_stats(cp.scrape_run_id) if cp.scrape_run_id else (0, 0, None)
                )
                health_parts.append(
                    source_crawl_health(
                        completed=cp.crawl == "done" and cp.etl == "done",
                        listings_stored=stored,
                        errors_count=errors,
                    )
                )
            health = (
                CrawlHealth(True, "all_source_variants_healthy")
                if all(item.healthy for item in health_parts)
                else CrawlHealth(False, ",".join(item.reason for item in health_parts if not item.healthy))
            )
            observed_ids = session.scalars(
                select(NormalizedListing.source_listing_id).where(
                    NormalizedListing.scrape_run_id.in_(run_ids),
                    NormalizedListing.source_website == source,
                )
            ).all()
            counts = apply_source_crawl_lifecycle(
                session,
                source_website=source,
                run_id=max(run_ids),
                observed_listing_ids=observed_ids,
                crawl_health=health,
                policy=lifecycle_policy_for_source(source),
            )
            out.print(f"    Lifecycle {source}: {health.reason} {counts}")
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def run_weekly_pipeline(
    *,
    days: int = DEFAULT_WEEKLY_INTERVAL_DAYS,
    force: bool = False,
    skip_crawl: bool = False,
    only_sources: list[str] | None = None,
    stage: WeeklyStage | Literal["all", "crawl", "etl", "analytics"] = WeeklyStage.ALL,
    resume: bool = True,
    parallel_crawl: bool = True,
    trailing_etl: bool | None = None,
    console: Console | None = None,
) -> WeeklyCrawlReport:
    """Run crawlers, ETL, and analytics — each stage independently re-runnable."""
    out = console or Console()
    only_set = {s.strip().lower() for s in only_sources} if only_sources else None
    run_stage = WeeklyStage(stage) if isinstance(stage, str) else stage

    if not force and not only_set and not is_weekly_due(interval_days=days):
        state = load_weekly_state()
        out.print(
            f"[yellow]Weekly crawl not due yet (last run: {state.get('last_run_at', 'never')}). "
            "Use --force to run anyway.[/yellow]"
        )
        window = CrawlWindow.last_n_days(days)
        return WeeklyCrawlReport(
            window=window,
            started_at=datetime.now(UTC),
            finished_at=datetime.now(UTC),
        )

    window = CrawlWindow.last_n_days(days)
    report = WeeklyCrawlReport(window=window, started_at=datetime.now(UTC))
    jobs = _weekly_spider_jobs(window)
    if only_set:
        jobs = [
            (label, spider, kwargs) for label, spider, kwargs in jobs if label.lower() in only_set
        ]

    checkpoint = ensure_checkpoint(
        window.crawl_week,
        window_days=window.days,
        source_jobs=[(label, spider) for label, spider, _ in jobs],
    )

    out.print(
        f"[bold]Weekly pipeline[/bold] {window.crawl_week} "
        f"({window.window_start} -> {window.window_end}) stage={run_stage.value}"
    )

    try:
        _close_stale_scrape_runs()
    except Exception as exc:
        logger.warning("close_stale_runs_failed", error=str(exc))

    use_trailing = (
        get_settings().weekly_crawl_trailing_etl if trailing_etl is None else trailing_etl
    )
    trailing_etl_active = use_trailing and parallel_crawl and run_stage == WeeklyStage.ALL
    if not skip_crawl and run_stage in (WeeklyStage.ALL, WeeklyStage.CRAWL):
        _run_crawl_jobs(
            jobs,
            window,
            checkpoint,
            resume=resume,
            parallel=parallel_crawl,
            trailing_etl=trailing_etl_active,
            out=out,
        )
        for label, spider, _ in jobs:
            cp = checkpoint.sources.get(label)
            if cp:
                report.sources.append(
                    SourceCrawlResult(
                        source=label,
                        spider=spider,
                        scrape_run_id=cp.scrape_run_id,
                        error=cp.error if cp.crawl == "failed" else None,
                    )
                )

    if run_stage in (WeeklyStage.ALL, WeeklyStage.ETL):
        _run_etl_jobs(checkpoint, window, resume=resume, only_set=only_set, out=out)
        for label, spider, _ in jobs:
            cp = checkpoint.sources.get(label)
            if cp and cp.scrape_run_id:
                existing = next((s for s in report.sources if s.source == label), None)
                if existing:
                    existing.etl_normalized = cp.etl_normalized
                    existing.scrape_run_id = cp.scrape_run_id
                    existing.error = cp.error
                else:
                    report.sources.append(
                        SourceCrawlResult(
                            source=label,
                            spider=spider,
                            scrape_run_id=cp.scrape_run_id,
                            etl_normalized=cp.etl_normalized,
                            error=cp.error if cp.etl == "failed" else None,
                        )
                    )

    if run_stage in (WeeklyStage.ALL, WeeklyStage.ANALYTICS):
        if checkpoint.analytics == "done" and resume and run_stage == WeeklyStage.ANALYTICS:
            out.print(
                "[yellow]Analytics already done for this week (use --no-resume to redo).[/yellow]"
            )
        else:
            checkpoint.analytics = "running"
            save_checkpoint(checkpoint)
            from groundtruth.database.session import get_session_factory

            session = get_session_factory()()
            try:
                refresh_analytics(session, window=window, console=out)
                checkpoint.analytics = "done"
            except Exception as exc:
                checkpoint.analytics = "failed"
                logger.exception("weekly_analytics_failed")
                out.print(f"[red]Analytics failed: {exc}[/red]")
            finally:
                save_checkpoint(checkpoint)
                session.close()

    if run_stage == WeeklyStage.ALL:
        from groundtruth.database.session import get_session_factory
        from groundtruth.services.retention import enforce_retention

        session = get_session_factory()()
        try:
            retention = enforce_retention(
                session,
                get_settings(),
                dry_run=False,
            )
            session.commit()
            logger.info("weekly_retention_complete", **retention.as_dict())
            out.print(
                "[green]Retention enforced:[/green] "
                f"raw_html={retention.raw_html_rows}, "
                f"raw_payload={retention.raw_payload_rows}, "
                f"descriptions="
                f"{retention.parsed_description_rows + retention.normalized_description_rows}"
            )
        except Exception as exc:
            session.rollback()
            logger.exception("weekly_retention_failed")
            out.print(f"[red]Retention failed: {exc}[/red]")
        finally:
            session.close()

    checkpoint.finished_at = datetime.now(UTC).isoformat()
    save_checkpoint(checkpoint)

    report.finished_at = datetime.now(UTC)
    artifact_path = write_weekly_artifacts(report)
    should_mark_complete = run_stage == WeeklyStage.ALL or (
        run_stage == WeeklyStage.ANALYTICS and checkpoint.analytics == "done"
    )
    if should_mark_complete:
        save_weekly_state(window=window, report=report)
    out.print(f"[green]Weekly report: {artifact_path}[/green]")
    out.print(f"[green]Checkpoint: {checkpoint_path(window.crawl_week)}[/green]")
    return report


def _refresh_home_trust_snapshot(out: Console) -> None:
    import runpy

    script = PROJECT_ROOT / "scripts" / "update_home_trust_snapshot.py"
    if not script.is_file():
        out.print(f"[yellow]Home-trust snapshot script missing: {script}[/yellow]")
        return
    runpy.run_path(str(script), run_name="__main__")


def run_gated_ingest(
    *,
    days: int,
    skip_crawl: bool = False,
    yes: bool = False,
    confirm: Callable[..., bool] | None = None,
    only_sources: list[str] | None = None,
    parallel_crawl: bool = True,
    console: Console | None = None,
) -> WeeklyCrawlReport:
    """Crawl all sources, print errors, then optionally ETL + website numbers."""
    import typer

    out = console or Console()
    window = CrawlWindow.last_n_days(days)
    out.print(
        f"[bold]Ingest[/bold] lookback {days} days "
        f"({window.window_start} -> {window.window_end}, {window.crawl_week})"
    )

    if not skip_crawl:
        report = run_weekly_pipeline(
            days=days,
            force=True,
            skip_crawl=False,
            only_sources=only_sources,
            stage=WeeklyStage.CRAWL,
            resume=True,
            parallel_crawl=parallel_crawl,
            console=out,
        )
    else:
        out.print("[yellow]Skipping crawlers (--skip-crawl). Using last checkpoint.[/yellow]")
        report = WeeklyCrawlReport(
            window=window,
            started_at=datetime.now(UTC),
            finished_at=datetime.now(UTC),
        )

    from groundtruth.crawl.checkpoints import load_checkpoint

    checkpoint = load_checkpoint(window.crawl_week)
    if checkpoint is None:
        out.print("[red]No crawl checkpoint found. Nothing to review.[/red]")
        return report

    rows = build_crawl_feedback(checkpoint)
    print_crawl_feedback(rows, console=out)

    successful = sum(1 for r in rows if r["status"] in {"done", "ok_with_errors"})
    if successful == 0 and not skip_crawl:
        out.print(
            "[red]No sources crawled successfully.[/red] "
            "Fix the errors above and re-run ingest before normalizing."
        )
        if not yes:
            return report

    if not yes:
        ask = confirm or typer.confirm
        proceed = ask(
            "Continue to normalization and website update with the new numbers?",
            default=False,
        )
        if not proceed:
            out.print(
                "[yellow]Stopped after crawlers.[/yellow] When you are ready:\n"
                f"  uv run groundtruth crawl ingest --days {days} --skip-crawl"
            )
            return report
    else:
        out.print("[dim]--yes: continuing to normalization and website update.[/dim]")

    report = run_weekly_pipeline(
        days=days,
        force=True,
        skip_crawl=True,
        only_sources=only_sources,
        stage=WeeklyStage.ETL,
        resume=True,
        parallel_crawl=False,
        console=out,
    )
    report = run_weekly_pipeline(
        days=days,
        force=True,
        skip_crawl=True,
        only_sources=only_sources,
        stage=WeeklyStage.ANALYTICS,
        resume=True,
        parallel_crawl=False,
        console=out,
    )
    try:
        _refresh_home_trust_snapshot(out)
        out.print(
            "[green]Website numbers updated (lookup cache + homepage trust snapshot).[/green]"
        )
    except Exception as exc:
        logger.exception("home_trust_snapshot_failed")
        out.print(f"[red]Website snapshot update failed: {exc}[/red]")
        raise
    return report
