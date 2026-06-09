"""CLI entry point using typer."""

import typer
from rich.console import Console

from groundtruth import __version__
from groundtruth.config import get_settings
from groundtruth.logging import configure_logging, get_logger

app = typer.Typer(
    name="groundtruth",
    help="Kosovo Real Estate Market Analysis platform",
    no_args_is_help=True,
)
console = Console()


@app.callback()
def main() -> None:
    """Initialize logging for all subcommands."""
    configure_logging()
    get_logger("groundtruth.cli").debug("cli_initialized", version=__version__)


@app.command()
def version() -> None:
    """Print the application version."""
    console.print(f"groundtruth v{__version__}")


@app.command()
def config() -> None:
    """Display current configuration (non-sensitive fields)."""
    settings = get_settings()
    console.print(f"Environment:     {settings.app_env}")
    console.print(f"Database:        {settings.database_url}")
    console.print(f"Gazetteer dir:   {settings.gazetteer_dir}")
    console.print(f"Geocoding:       {settings.geocoding_enabled}")
    console.print(f"Dedup threshold: {settings.dedup_fuzzy_threshold}")


db_app = typer.Typer(help="Database management commands")
app.add_typer(db_app, name="db")

etl_app = typer.Typer(help="ETL pipeline commands")
app.add_typer(etl_app, name="etl")

crawl_app = typer.Typer(help="Scraping commands")
app.add_typer(crawl_app, name="crawl")

report_app = typer.Typer(help="Report generation commands")
app.add_typer(report_app, name="report")


@db_app.command("init")
def db_init() -> None:
    """Create all database tables (development only)."""
    from groundtruth.database.session import get_engine
    from groundtruth.models.base import Base

    settings = get_settings()
    if not settings.is_development:
        console.print("[red]db init is only allowed in development[/red]")
        raise typer.Exit(1)

    engine = get_engine()
    Base.metadata.create_all(bind=engine)
    console.print("[green]Database tables created.[/green]")


@etl_app.command("run")
def etl_run(
    scrape_run_id: int | None = typer.Option(None, help="Process a specific scrape run"),
    source: str | None = typer.Option(None, help="Source website filter, e.g. gjirafa"),
    reprocess: bool = typer.Option(False, help="Re-parse and re-normalize existing raw listings"),
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
            from groundtruth.models.pipeline import NormalizedListing

            listings = session.query(NormalizedListing).all()
            record_listing_observations(session, listings)
            session.commit()
            console.print("[green]Market snapshots and listing observations updated.[/green]")

        from groundtruth.analytics.audit import run_audit, write_audit_artifacts
        from datetime import UTC, datetime
        from groundtruth.config import PROJECT_ROOT

        stamp = datetime.now(UTC).strftime("%Y-%m-%d")
        audit_dir = PROJECT_ROOT / "reports" / "generated" / f"audit_{stamp}"
        report = run_audit(session, dedupe=True)
        audit_path = write_audit_artifacts(report, audit_dir)
        session.commit()
        console.print(f"[green]Dataset audit written to {audit_path}[/green]")
    finally:
        session.close()


@crawl_app.command("gjirafa")
def crawl_gjirafa(
    max_listings: int = typer.Option(5000, help="Maximum listings to crawl (0 = unlimited)"),
    max_pages: int = typer.Option(250, help="Maximum index pages to paginate"),
) -> None:
    """Crawl Gjirafa listings and store raw HTML."""
    import logging

    from scrapy.crawler import CrawlerProcess
    from scrapy.utils.log import configure_logging as scrapy_configure_logging
    from scrapy.utils.project import get_project_settings

    scrapy_configure_logging(install_root_handler=False)
    for name in ("scrapy", "scrapy.core.scraper", "scrapy.core.engine", "groundtruth"):
        logging.getLogger(name).setLevel(logging.ERROR)

    settings = get_project_settings()
    settings.set("LOG_LEVEL", "ERROR")
    process = CrawlerProcess(settings)
    process.crawl(
        "gjirafa",
        max_listings=str(max_listings),
        max_pages=str(max_pages),
    )
    console.print(f"[bold]Starting Gjirafa crawl[/bold] (max_listings={max_listings})")
    process.start()
    console.print("[green]Crawl finished. Run `groundtruth etl run` to process new listings.[/green]")


@report_app.command("market")
def report_market() -> None:
    """Generate Market Report v0.1 from normalized listings."""
    from groundtruth.database.session import get_session_factory
    from groundtruth.services.report_service import ReportService

    session = get_session_factory()()
    try:
        path = ReportService().generate_market_report_v01(session)
        console.print(f"[green]Market report written to {path}[/green]")
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


if __name__ == "__main__":
    app()
