"""ETL CLI commands."""

from __future__ import annotations

import typer
from rich.console import Console

console = Console()
etl_app = typer.Typer(help="ETL pipeline commands")


@etl_app.command("run")
def etl_run(
    scrape_run_id: int | None = typer.Option(None, help="Process a specific scrape run"),
    source: str | None = typer.Option(None, help="Source website filter, e.g. gjirafa"),
    reprocess: bool = typer.Option(False, help="Re-parse and re-normalize existing raw listings"),
    max_age_months: int = typer.Option(
        12,
        min=0,
        help="Only normalize listings with listing_date within this many months. 0 = no limit.",
    ),
    max_age_days: int = typer.Option(
        0,
        min=0,
        help="Day-based window (overrides months when > 0). Use 7 for weekly ingest.",
    ),
    benchmark_label: str | None = typer.Option(None, help="Label for benchmark log entry"),
) -> None:
    """Run raw → parsed → normalized ETL with validation metrics."""
    from groundtruth.database.session import get_session_factory
    from groundtruth.models.scrape_run import ScrapeRun
    from groundtruth.services.benchmark_log import append_benchmark, ensure_benchmark_log
    from groundtruth.services.etl import EtlService
    from groundtruth.services.etl_report import print_etl_report

    session = get_session_factory()()
    try:
        metrics = EtlService(session).run(
            scrape_run_id=scrape_run_id,
            source=source,
            reprocess=reprocess,
            max_age_months=max_age_months,
            max_age_days=max_age_days,
        )
        print_etl_report(metrics, console)

        scrape_run = None
        if metrics.scrape_run_id:
            scrape_run = session.get(ScrapeRun, metrics.scrape_run_id)
        label = benchmark_label or (
            f"{metrics.normalized_success}_listings" if metrics.normalized_success else "etl_run"
        )
        log_path = append_benchmark(session, metrics, label=label, scrape_run=scrape_run)
        console.print(f"\n[green]Benchmark logged to {log_path}[/green]")
        ensure_benchmark_log()

        from groundtruth.analytics.dataframe import normalized_listings_dataframe
        from groundtruth.analytics.snapshots import generate_market_snapshots

        df = normalized_listings_dataframe(session)
        if not df.empty:
            generate_market_snapshots(session, df)
            from groundtruth.analytics.listing_history import record_listing_observations

            record_listing_observations(session)
            session.commit()
            console.print("[green]Market snapshots and listing observations updated.[/green]")

        from datetime import UTC, datetime

        from groundtruth.analytics.audit import run_audit, write_audit_artifacts
        from groundtruth.config import PROJECT_ROOT

        stamp = datetime.now(UTC).strftime("%Y-%m-%d")
        audit_dir = PROJECT_ROOT / "reports" / "generated" / f"audit_{stamp}"
        report = run_audit(session, dedupe=True)
        audit_path = write_audit_artifacts(report, audit_dir)
        session.commit()
        console.print(f"[green]Dataset audit written to {audit_path}[/green]")

        from groundtruth.analytics.corpus import write_corpus_artifacts

        corpus_dir = PROJECT_ROOT / "reports" / "generated"
        corpus_paths = write_corpus_artifacts(session, corpus_dir)
        console.print("[green]Corpus report updated.[/green]")
        for label, path in corpus_paths.items():
            console.print(f"  {label}: {path}")

        from groundtruth.analytics.annual_export import export_annual_report

        annual_path = export_annual_report(session)
        console.print(f"[green]Annual report cache updated: {annual_path}[/green]")
    finally:
        session.close()


@etl_app.command("health")
def etl_health(
    threshold: float = typer.Option(
        0.10,
        min=0.0,
        max=1.0,
        help="Parse-failure rate threshold (default 10%%)",
    ),
    fail: bool = typer.Option(False, help="Exit non-zero if any source exceeds threshold"),
) -> None:
    """Check per-source parse-failure rates from recent ETL runs."""
    from groundtruth.database.session import get_session_factory
    from groundtruth.services.parse_health import check_parse_health

    session = get_session_factory()()
    try:
        alerts = check_parse_health(session, threshold=threshold)
        if not alerts:
            console.print("[green]All sources within parse-failure threshold.[/green]")
            return
        for alert in alerts:
            console.print(f"[red]{alert.message}[/red]")
        if fail:
            raise typer.Exit(1)
    finally:
        session.close()


@etl_app.command("errors")
def etl_errors() -> None:
    """Show validation error breakdown from all invalid listings."""
    from collections import Counter

    from rich.table import Table

    from groundtruth.database.session import get_session_factory
    from groundtruth.models.etl import InvalidListing
    from groundtruth.processing.invalid_classification import classify_invalid_listing

    session = get_session_factory()()
    try:
        rows = session.query(InvalidListing).all()
        if not rows:
            console.print("[green]No invalid listings.[/green]")
            return

        by_code: Counter[str] = Counter()
        for row in rows:
            for code in row.error_codes or []:
                by_code[code] += 1

        table = Table(title=f"Validation errors ({len(rows)} invalid listings)")
        table.add_column("Error", style="cyan")
        table.add_column("Count", justify="right")
        for code, count in by_code.most_common():
            table.add_row(code, str(count))
        console.print(table)

        by_class = Counter(classify_invalid_listing(row) for row in rows)
        console.print("\n[bold]By classification[/bold]")
        for cat, count in by_class.most_common():
            console.print(f"  {cat}: {count}")
    finally:
        session.close()


@etl_app.command("report")
def etl_report(
    source: str | None = typer.Option(None, help="Filter by source website"),
) -> None:
    """Show the most recent ETL quality report."""
    from groundtruth.database.repositories import EtlMetricsRepository
    from groundtruth.database.session import get_session_factory
    from groundtruth.schemas.etl import EtlMetricsSchema
    from groundtruth.services.etl_report import print_etl_report

    session = get_session_factory()()
    try:
        entity = EtlMetricsRepository(session).get_latest(source=source)
        if entity is None:
            console.print("[yellow]No ETL runs found.[/yellow]")
            raise typer.Exit(0)
        print_etl_report(EtlMetricsSchema.model_validate(entity), console)
    finally:
        session.close()
