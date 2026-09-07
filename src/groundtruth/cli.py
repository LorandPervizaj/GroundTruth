"""CLI entry point using typer."""

from pathlib import Path

import typer
from rich.console import Console

from groundtruth import __version__
from groundtruth.config import PROJECT_ROOT, get_settings
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
    from sqlalchemy.engine import make_url

    settings = get_settings()
    console.print(f"Environment:     {settings.app_env}")
    safe_database_url = make_url(str(settings.database_url)).render_as_string(hide_password=True)
    console.print(f"Database:        {safe_database_url}")
    console.print(f"Gazetteer dir:   {settings.gazetteer_dir}")
    console.print(f"Geocoding:       {settings.geocoding_enabled}")
    console.print(f"Dedup threshold: {settings.dedup_fuzzy_threshold}")


db_app = typer.Typer(help="Database management commands")
app.add_typer(db_app, name="db")

etl_app = typer.Typer(help="ETL pipeline commands")
app.add_typer(etl_app, name="etl")

reports_app = typer.Typer(help="Public report artifacts")
app.add_typer(reports_app, name="reports")

release_app = typer.Typer(help="Production release artifact checks")
app.add_typer(release_app, name="release")

crawl_app = typer.Typer(help="Scraping commands")
app.add_typer(crawl_app, name="crawl")

report_app = typer.Typer(help="Report generation commands")
app.add_typer(report_app, name="report")

corpus_app = typer.Typer(help="Corpus diagnostics (pre-freeze)")
app.add_typer(corpus_app, name="corpus")

dedup_app = typer.Typer(help="Cross-portal duplicate detection")
app.add_typer(dedup_app, name="dedup")

valuate_app = typer.Typer(help="Fair-market rent valuation (DM-002 v0.1)")
app.add_typer(valuate_app, name="valuate")

analytics_app = typer.Typer(help="Product and ops analytics")
app.add_typer(analytics_app, name="analytics")

evaluation_app = typer.Typer(help="Model evaluation harnesses")
app.add_typer(evaluation_app, name="evaluation")

from groundtruth.commands.facebook import fb_app  # noqa: E402
from groundtruth.commands.retention import retention_app  # noqa: E402

app.add_typer(fb_app, name="fb")
app.add_typer(retention_app, name="retention")


@db_app.command("init")
def db_init() -> None:
    """Initialize a development database through the canonical migrations."""
    from alembic import command
    from alembic.config import Config

    settings = get_settings()
    if not settings.is_development:
        console.print("[red]db init is only allowed in development[/red]")
        raise typer.Exit(1)

    alembic_config = Config(str(PROJECT_ROOT / "alembic.ini"))
    command.upgrade(alembic_config, "head")
    console.print("[green]Database migrated to Alembic head.[/green]")


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


def _run_gjirafa_crawl(
    *,
    spider_name: str,
    listing_type: str,
    max_listings: int,
    max_pages: int,
    categories: str,
    start_page: int,
    skip_existing: bool,
    skip_existing_days: int,
    max_age_days: int,
    crawl_window: str | None,
) -> None:
    """Launch a Gjirafa Scrapy crawl (rent, sale, or legacy combined spider)."""
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
    crawl_kwargs: dict[str, str] = {
        "max_listings": str(max_listings),
        "max_pages": str(max_pages),
        "categories": categories,
        "start_page": str(start_page),
        "skip_existing": "true" if skip_existing else "false",
        "skip_existing_days": str(skip_existing_days),
        "max_age_days": str(max_age_days),
    }
    if spider_name == "gjirafa":
        crawl_kwargs["listing_type"] = listing_type
    if crawl_window:
        crawl_kwargs["crawl_window"] = crawl_window
    process.crawl(spider_name, **crawl_kwargs)
    console.print(
        f"[bold]Starting Gjirafa crawl[/bold] "
        f"(spider={spider_name}, start_page={start_page}, "
        f"skip_existing={skip_existing}, skip_existing_days={skip_existing_days}, "
        f"max_age_days={max_age_days}, categories={categories})"
    )
    process.start()
    console.print(
        "[green]Crawl finished. Run `groundtruth etl run` to process new listings.[/green]"
    )


@crawl_app.command("gjirafa")
def crawl_gjirafa(
    max_listings: int = typer.Option(5000, help="Maximum listings to crawl (0 = unlimited)"),
    max_pages: int = typer.Option(250, help="Maximum index pages to paginate"),
    categories: str = typer.Option(
        "banesa,shtepi-vila,objekte-afariste,zyre",
        help=(
            "Comma-separated Gjirafa categories "
            "(banesa, shtepi-vila, objekte-afariste, zyre) — each gets a filtered k= index"
        ),
    ),
    listing_type: str = typer.Option(
        "all",
        help="Index filter: all | sale (llshp=Shitet) | rent (llshp=Qira), Prishtina only",
    ),
    start_page: int = typer.Option(
        0,
        min=0,
        help="Resume index pagination from this page (f=0 is first page)",
    ),
    skip_existing: bool = typer.Option(
        True,
        "--skip-existing/--no-skip-existing",
        help="Skip detail fetch for listing IDs already in raw_listings",
    ),
    skip_existing_days: int = typer.Option(
        0,
        min=0,
        help="When skip-existing: only skip IDs scraped within N days (0 = skip all forever)",
    ),
    max_age_days: int = typer.Option(
        0,
        min=0,
        help="Skip listings older than this many days (published date). 0 = no day limit.",
    ),
    crawl_window: str | None = typer.Option(
        None,
        "--crawl-window",
        help="Optional JSON metadata (weekly window) stored on the scrape_run",
    ),
) -> None:
    """Crawl Gjirafa listings and store raw HTML (legacy — prefer gjirafa-rent / gjirafa-sale)."""
    _run_gjirafa_crawl(
        spider_name="gjirafa",
        listing_type=listing_type,
        max_listings=max_listings,
        max_pages=max_pages,
        categories=categories,
        start_page=start_page,
        skip_existing=skip_existing,
        skip_existing_days=skip_existing_days,
        max_age_days=max_age_days,
        crawl_window=crawl_window,
    )


@crawl_app.command("gjirafa-rent")
def crawl_gjirafa_rent(
    max_listings: int = typer.Option(5000, help="Maximum listings to crawl (0 = unlimited)"),
    max_pages: int = typer.Option(250, help="Maximum index pages to paginate"),
    categories: str = typer.Option(
        "banesa,shtepi-vila,objekte-afariste,zyre",
        help="Comma-separated Gjirafa categories (each gets a filtered k= index)",
    ),
    start_page: int = typer.Option(0, min=0, help="Resume index pagination from this page"),
    skip_existing: bool = typer.Option(
        True,
        "--skip-existing/--no-skip-existing",
        help="Skip detail fetch for listing IDs already in raw_listings",
    ),
    skip_existing_days: int = typer.Option(
        0,
        min=0,
        help="When skip-existing: only skip IDs scraped within N days (0 = skip all forever)",
    ),
    max_age_days: int = typer.Option(
        0,
        min=0,
        help="Skip listings older than this many days (published date). 0 = no day limit.",
    ),
    crawl_window: str | None = typer.Option(
        None,
        "--crawl-window",
        help="Optional JSON metadata (weekly window) stored on the scrape_run",
    ),
) -> None:
    """Crawl Gjirafa rent listings (Prishtinë, llshp=Qira)."""
    _run_gjirafa_crawl(
        spider_name="gjirafa-rent",
        listing_type="rent",
        max_listings=max_listings,
        max_pages=max_pages,
        categories=categories,
        start_page=start_page,
        skip_existing=skip_existing,
        skip_existing_days=skip_existing_days,
        max_age_days=max_age_days,
        crawl_window=crawl_window,
    )


@crawl_app.command("gjirafa-sale")
def crawl_gjirafa_sale(
    max_listings: int = typer.Option(5000, help="Maximum listings to crawl (0 = unlimited)"),
    max_pages: int = typer.Option(250, help="Maximum index pages to paginate"),
    categories: str = typer.Option(
        "banesa,shtepi-vila,objekte-afariste,zyre",
        help="Comma-separated Gjirafa categories (each gets a filtered k= index)",
    ),
    start_page: int = typer.Option(0, min=0, help="Resume index pagination from this page"),
    skip_existing: bool = typer.Option(
        True,
        "--skip-existing/--no-skip-existing",
        help="Skip detail fetch for listing IDs already in raw_listings",
    ),
    skip_existing_days: int = typer.Option(
        0,
        min=0,
        help="When skip-existing: only skip IDs scraped within N days (0 = skip all forever)",
    ),
    max_age_days: int = typer.Option(
        0,
        min=0,
        help="Skip listings older than this many days (published date). 0 = no day limit.",
    ),
    crawl_window: str | None = typer.Option(
        None,
        "--crawl-window",
        help="Optional JSON metadata (weekly window) stored on the scrape_run",
    ),
) -> None:
    """Crawl Gjirafa sale listings (Prishtinë, llshp=Shitet)."""
    _run_gjirafa_crawl(
        spider_name="gjirafa-sale",
        listing_type="sale",
        max_listings=max_listings,
        max_pages=max_pages,
        categories=categories,
        start_page=start_page,
        skip_existing=skip_existing,
        skip_existing_days=skip_existing_days,
        max_age_days=max_age_days,
        crawl_window=crawl_window,
    )


@crawl_app.command("pro-rks")
def crawl_pro_rks(
    max_listings: int = typer.Option(0, help="Maximum listings to crawl (0 = unlimited)"),
    max_pages: int = typer.Option(0, help="Maximum index pages per mode (0 = all)"),
    listing_type: str = typer.Option(
        "both",
        help="sale | rent | both (Prishtina filtered index)",
    ),
    categories: str = typer.Option(
        "apartment,home,unit",
        help="Residential API categories (land/office/store excluded)",
    ),
    skip_existing: bool = typer.Option(
        True,
        "--skip-existing/--no-skip-existing",
        help="Skip listings already scraped recently",
    ),
    skip_existing_days: int = typer.Option(
        0,
        min=0,
        help="When skip-existing: only skip IDs scraped within N days (0 = skip all forever)",
    ),
    crawl_window: str | None = typer.Option(
        None,
        "--crawl-window",
        help="Optional JSON metadata (weekly window) stored on the scrape_run",
    ),
) -> None:
    """Crawl Pro Real Estate via prod-api.pro-rks.com (sale + rent)."""
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
    crawl_kwargs: dict[str, str] = {
        "max_listings": str(max_listings),
        "max_pages": str(max_pages),
        "listing_type": listing_type,
        "categories": categories,
        "skip_existing": "true" if skip_existing else "false",
        "skip_existing_days": str(skip_existing_days),
    }
    if crawl_window:
        crawl_kwargs["crawl_window"] = crawl_window
    process.crawl("pro-rks", **crawl_kwargs)
    console.print(
        f"[bold]Starting Pro Real Estate crawl[/bold] "
        f"(listing_type={listing_type}, max_pages={max_pages or 'all'}, "
        f"skip_existing_days={skip_existing_days})"
    )
    process.start()
    console.print("[green]Crawl finished. Run `groundtruth etl run --source pro-rks`[/green]")


@crawl_app.command("vision")
def crawl_vision(
    max_listings: int = typer.Option(0, help="Maximum listings to crawl (0 = unlimited)"),
    max_pages: int = typer.Option(0, help="Maximum API pages (0 = all, ~100 listings/page)"),
    prishtina_only: bool = typer.Option(
        True,
        help="Keep only listings in District of Prishtina (residential types only)",
    ),
    skip_existing: bool = typer.Option(
        True,
        "--skip-existing/--no-skip-existing",
        help="Skip listings already scraped recently",
    ),
    skip_existing_days: int = typer.Option(
        0,
        min=0,
        help="When skip-existing: only skip IDs scraped within N days (0 = skip all forever)",
    ),
    crawl_window: str | None = typer.Option(
        None,
        "--crawl-window",
        help="Optional JSON metadata (weekly window) stored on the scrape_run",
    ),
) -> None:
    """Crawl Vision Real Estate via visionrealestateks.com WordPress REST API."""
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
    crawl_kwargs: dict[str, str] = {
        "max_listings": str(max_listings),
        "max_pages": str(max_pages),
        "prishtina_only": "true" if prishtina_only else "false",
        "skip_existing": "true" if skip_existing else "false",
        "skip_existing_days": str(skip_existing_days),
    }
    if crawl_window:
        crawl_kwargs["crawl_window"] = crawl_window
    process.crawl("vision", **crawl_kwargs)
    console.print(
        f"[bold]Starting Vision Real Estate crawl[/bold] "
        f"(prishtina_only={prishtina_only}, skip_existing_days={skip_existing_days}, "
        f"max_pages={max_pages or 'all'})"
    )
    process.start()
    console.print("[green]Crawl finished. Run `groundtruth etl run --source vision`[/green]")


@crawl_app.command("topia")
def crawl_topia(
    max_listings: int = typer.Option(0, help="Maximum listings to crawl (0 = unlimited)"),
    max_pages: int = typer.Option(0, help="Maximum API pages (0 = all, ~100 listings/page)"),
    prishtina_only: bool = typer.Option(
        True,
        help="Keep only residential listings in Prishtina",
    ),
    skip_existing: bool = typer.Option(
        True,
        "--skip-existing/--no-skip-existing",
        help="Skip listings already scraped recently",
    ),
    skip_existing_days: int = typer.Option(
        0,
        min=0,
        help="When skip-existing: only skip IDs scraped within N days (0 = skip all forever)",
    ),
    crawl_window: str | None = typer.Option(
        None,
        "--crawl-window",
        help="Optional JSON metadata (weekly window) stored on the scrape_run",
    ),
) -> None:
    """Crawl Topia Real Estate via topia-ks.com JSON API."""
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
    crawl_kwargs: dict[str, str] = {
        "max_listings": str(max_listings),
        "max_pages": str(max_pages),
        "prishtina_only": "true" if prishtina_only else "false",
        "skip_existing": "true" if skip_existing else "false",
        "skip_existing_days": str(skip_existing_days),
    }
    if crawl_window:
        crawl_kwargs["crawl_window"] = crawl_window
    process.crawl("topia", **crawl_kwargs)
    console.print(
        f"[bold]Starting Topia crawl[/bold] "
        f"(prishtina_only={prishtina_only}, skip_existing_days={skip_existing_days}, "
        f"max_pages={max_pages or 'all'})"
    )
    process.start()
    console.print("[green]Crawl finished. Run `groundtruth etl run --source topia`[/green]")


@crawl_app.command("myrealestate")
def crawl_myrealestate(
    max_listings: int = typer.Option(0, help="Maximum listings to crawl (0 = unlimited)"),
    max_pages: int = typer.Option(0, help="Maximum API pages (0 = all, ~100 listings/page)"),
    prishtina_only: bool = typer.Option(
        True,
        help="Keep only residential listings in Prishtina",
    ),
    skip_existing: bool = typer.Option(
        True,
        "--skip-existing/--no-skip-existing",
        help="Skip listings already scraped recently",
    ),
    skip_existing_days: int = typer.Option(
        0,
        min=0,
        help="When skip-existing: only skip IDs scraped within N days (0 = skip all forever)",
    ),
    crawl_window: str | None = typer.Option(
        None,
        "--crawl-window",
        help="Optional JSON metadata (weekly window) stored on the scrape_run",
    ),
) -> None:
    """Crawl MY Real Estate via myrealestate-ks.com WordPress REST API."""
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
    crawl_kwargs: dict[str, str] = {
        "max_listings": str(max_listings),
        "max_pages": str(max_pages),
        "prishtina_only": "true" if prishtina_only else "false",
        "skip_existing": "true" if skip_existing else "false",
        "skip_existing_days": str(skip_existing_days),
    }
    if crawl_window:
        crawl_kwargs["crawl_window"] = crawl_window
    process.crawl("myrealestate", **crawl_kwargs)
    console.print(
        f"[bold]Starting MY Real Estate crawl[/bold] "
        f"(prishtina_only={prishtina_only}, skip_existing_days={skip_existing_days}, "
        f"max_pages={max_pages or 'all'})"
    )
    process.start()
    console.print("[green]Crawl finished. Run `groundtruth etl run --source myrealestate`[/green]")


@crawl_app.command("merrjep")
def crawl_merrjep(
    detail: bool = typer.Option(
        False,
        "--detail",
        help="Production crawl: fetch detail pages and persist raw listings to the database.",
    ),
    discovery_only: bool = typer.Option(
        True,
        help="Phase 1: crawl index pages only and write a discovery report (no DB writes).",
    ),
    archive_only: bool = typer.Option(
        False,
        help="Phase 1.5: download detail pages, archive HTML + ld+json, assess schema (no parser).",
    ),
    index: str = typer.Option(
        "apartments_rent",
        help=(
            "MerrJep index filter key(s), comma-separated: "
            "apartments_rent | apartments_sale | houses_rent | houses_sale | "
            "rent | sale | apartments"
        ),
    ),
    max_pages: int = typer.Option(
        0,
        help="Maximum index pages per category URL (0 = unlimited; 50 for discovery gate).",
    ),
    max_listings: int = typer.Option(
        0,
        help="Maximum detail pages (100 for archive_only; 0 = unlimited otherwise).",
    ),
    index_pages_target: int = typer.Option(50, help="Phase 1 gate: minimum index pages"),
    listing_urls_target: int = typer.Option(
        2_400,
        help="Phase 1 gate: expected unique ids (= pages × ~48); pass at 90%% of this",
    ),
    max_duplicate_rate_pct: float = typer.Option(
        12.0,
        help="Phase 1 gate: max pagination overlap duplicate rate (percent; ~9%% observed)",
    ),
    start_page: int = typer.Option(
        1,
        min=1,
        help="Resume detail crawl from this index page (1 = from start).",
    ),
    skip_existing: bool = typer.Option(
        True,
        "--skip-existing/--no-skip-existing",
        help="Skip detail fetches for listing IDs already in raw_listings.",
    ),
    skip_existing_days: int = typer.Option(
        0,
        min=0,
        help="When skip-existing: only skip IDs scraped within N days (0 = skip all forever)",
    ),
    max_age_months: int = typer.Option(
        12,
        min=0,
        help="Skip listings older than this many months (published date). 0 = no limit.",
    ),
    max_age_days: int = typer.Option(
        0,
        min=0,
        help="Day-based cutoff (overrides months when > 0). Use 7 for weekly window.",
    ),
    min_published_year: int = typer.Option(
        0,
        min=0,
        help="Alternative floor by calendar year (used only when max-age-months is 0).",
    ),
    crawl_window: str | None = typer.Option(
        None,
        "--crawl-window",
        help="Optional JSON metadata (weekly window) stored on the scrape_run",
    ),
) -> None:
    """Crawl MerrJep — discovery (Phase 1), archive (Phase 1.5), or detail (production)."""
    import logging

    from scrapy.crawler import CrawlerProcess
    from scrapy.utils.log import configure_logging as scrapy_configure_logging
    from scrapy.utils.project import get_project_settings

    scrapy_configure_logging(install_root_handler=False)
    for name in (
        "scrapy",
        "scrapy.core.scraper",
        "scrapy.core.engine",
        "scrapy.core.engine.Engine",
        "scrapy.downloadermiddlewares",
        "twisted",
        "groundtruth",
    ):
        logging.getLogger(name).setLevel(logging.ERROR)

    settings = get_project_settings()
    settings.set("LOG_LEVEL", "ERROR")
    logging.getLogger().setLevel(logging.ERROR)
    process = CrawlerProcess(settings)
    if detail:
        discovery_only = False
        archive_only = False
    if archive_only:
        discovery_only = False
        if max_listings <= 0:
            max_listings = 100
        if max_pages > 5:
            max_pages = 5  # 3 pages enough for 100 URLs; cap index work
    elif discovery_only and max_pages <= 0:
        max_pages = 50

    crawl_kwargs: dict[str, str] = {
        "max_pages": str(max_pages),
        "max_listings": str(max_listings),
        "discovery_only": "true" if discovery_only else "false",
        "archive_only": "true" if archive_only else "false",
        "index": index,
        "index_pages_target": str(index_pages_target),
        "listing_urls_target": str(listing_urls_target),
        "max_duplicate_rate_pct": str(max_duplicate_rate_pct),
        "start_page": str(start_page),
        "skip_existing": "true" if skip_existing else "false",
        "skip_existing_days": str(skip_existing_days),
        "max_age_months": str(max_age_months),
        "max_age_days": str(max_age_days),
        "min_published_year": str(min_published_year),
    }
    if crawl_window:
        crawl_kwargs["crawl_window"] = crawl_window
    process.crawl("merrjep", **crawl_kwargs)
    if archive_only:
        mode = "archive"
    elif discovery_only:
        mode = "discovery"
    else:
        mode = "detail"
    console.print(
        f"[bold]Starting MerrJep crawl[/bold] mode={mode} index={index} "
        f"max_pages={max_pages} max_listings={max_listings} start_page={start_page} "
        f"skip_existing={skip_existing} skip_existing_days={skip_existing_days} "
        f"max_age_days={max_age_days} max_age_months={max_age_months}"
    )
    process.start()
    if archive_only:
        console.print(
            "[green]Archive crawl finished. "
            "Check reports/generated/merrjep_archive_*/merrjep_archive_report.json[/green]"
        )
    elif discovery_only:
        console.print(
            "[green]Discovery crawl finished. Check reports/generated/merrjep_discovery_*.json[/green]"
        )
    else:
        console.print(
            "[green]Crawl finished. Run `groundtruth etl run --source merrjep` to process listings.[/green]"
        )


@crawl_app.command("weekly")
def crawl_weekly(
    days: int = typer.Option(7, min=1, help="Ingest window in days (default: past 7 days)"),
    force: bool = typer.Option(False, help="Run even if the last weekly crawl was <7 days ago"),
    skip_crawl: bool = typer.Option(
        False,
        help="Refresh analytics only (skip spider crawls; useful after manual fixes)",
    ),
    only: str | None = typer.Option(
        None,
        help="Comma-separated source labels to run (e.g. gjirafa-rent,pro-rks)",
    ),
    stage: str = typer.Option(
        "all",
        help="Pipeline stage: all, crawl, etl, or analytics (independently re-runnable)",
    ),
    resume: bool = typer.Option(
        True,
        help="Skip stages already marked done in this week's checkpoint",
    ),
    no_parallel: bool = typer.Option(
        False,
        help="Disable parallel crawl across sources",
    ),
    trailing_etl: bool | None = typer.Option(
        None,
        "--trailing-etl/--no-trailing-etl",
        help="Normalize each source as its crawl finishes (default: WEEKLY_CRAWL_TRAILING_ETL)",
    ),
) -> None:
    """Run source crawlers, ETL, and analytics — each stage independently re-runnable."""
    from groundtruth.crawl.checkpoints import WeeklyStage
    from groundtruth.crawl.weekly import run_weekly_pipeline

    try:
        run_stage = WeeklyStage(stage.lower())
    except ValueError:
        console.print(f"[red]Invalid stage {stage!r}. Use: all, crawl, etl, analytics[/red]")
        raise typer.Exit(1) from None

    only_sources = [s.strip() for s in only.split(",") if s.strip()] if only else None
    if skip_crawl and run_stage == WeeklyStage.ALL:
        run_stage = WeeklyStage.ANALYTICS

    run_weekly_pipeline(
        days=days,
        force=force,
        skip_crawl=skip_crawl or run_stage == WeeklyStage.ANALYTICS,
        only_sources=only_sources,
        stage=run_stage,
        resume=resume,
        parallel_crawl=not no_parallel,
        trailing_etl=trailing_etl,
        console=console,
    )


@crawl_app.command("ingest")
def crawl_ingest(
    days: int | None = typer.Option(
        None,
        help="Lookback days. Default: days since last crawl (minimum 7).",
    ),
    weeks: int | None = typer.Option(
        None,
        help="Lookback in weeks (1–4). If omitted, you are asked using days since the last scrape.",
    ),
    yes: bool = typer.Option(
        False,
        "--yes",
        "-y",
        help="Skip the confirmation prompt and run ETL + website update",
    ),
    skip_crawl: bool = typer.Option(
        False,
        help="Skip spiders and go straight to the confirmation + ETL/website step",
    ),
    only: str | None = typer.Option(
        None,
        help="Comma-separated source labels to run (e.g. gjirafa-rent,pro-rks)",
    ),
    no_parallel: bool = typer.Option(
        False,
        help="Disable parallel crawl across sources",
    ),
) -> None:
    """Crawl sources, report errors, then confirm before normalize + website update."""
    from groundtruth.crawl.weekly import prompt_ingest_weeks, resolve_ingest_days, run_gated_ingest

    if days is None and weeks is None:
        weeks = prompt_ingest_weeks(console=console)

    try:
        resolved_days = resolve_ingest_days(days=days, weeks=weeks)
    except ValueError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(1) from None

    only_sources = [s.strip() for s in only.split(",") if s.strip()] if only else None
    try:
        run_gated_ingest(
            days=resolved_days,
            skip_crawl=skip_crawl,
            yes=yes,
            only_sources=only_sources,
            parallel_crawl=not no_parallel,
            console=console,
        )
    except typer.Abort:
        console.print("[yellow]Stopped.[/yellow]")
        raise typer.Exit(1) from None


@valuate_app.callback(invoke_without_command=True)
def valuate_rent(
    ctx: typer.Context,
    neighborhood: str = typer.Option(..., "--neighborhood", "-n", help="Neighborhood name or id"),
    area: float = typer.Option(..., "--area", "-a", help="Apartment area in m²"),
    bedrooms: int | None = typer.Option(None, "--bedrooms", "-b"),
    rent: float | None = typer.Option(None, "--rent", "-r", help="Listed rent to assess"),
    json_output: bool = typer.Option(False, "--json", help="Emit machine-readable JSON"),
) -> None:
    """Estimate fair market rent and optionally assess a listing price."""
    if ctx.invoked_subcommand is not None:
        return

    from groundtruth.analytics.valuation import estimate_rent_valuation
    from groundtruth.database.session import get_session_factory
    from groundtruth.schemas.valuation import ValuationRequest

    session = get_session_factory()()
    try:
        result = estimate_rent_valuation(
            session,
            ValuationRequest(
                neighborhood=neighborhood,
                area_sqm=area,
                bedrooms=bedrooms,
                listing_rent_eur=rent,
            ),
        )
    except ValueError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(1) from exc
    finally:
        session.close()

    if json_output:
        console.print(result.model_dump_json(indent=2))
        return

    console.print(
        f"\n[bold]Fair estimate[/bold] — {result.neighborhood_name}, {result.area_sqm:.0f} m²"
    )
    console.print(
        f"  [green]€{result.point_estimate_eur}/month[/green]  (95%: €{result.lower_ci_eur}–{result.upper_ci_eur})"
    )
    console.print("\n[bold]Why?[/bold]")
    for line in result.why_checks:
        console.print(f"  [green]OK[/green] {line}")
    console.print(f"  Weighted comparable rent: €{result.comparable_median_rent_eur}/month")
    if rent is not None and result.negotiation:
        n = result.negotiation
        console.print("\n[bold]Negotiation reference[/bold]")
        console.print(f"  Weighted comparable: €{n.comparable_median_rent_eur}/month")
        console.print(f"  Reasonable range: €{n.negotiation_lo_eur}–{n.negotiation_hi_eur}")
        console.print(f"  Current asking: €{n.listing_rent_eur}/month")
        console.print(f"  Difference: €{n.monthly_difference_eur}/month")
        console.print(f"  {result.assessment_summary}")
    console.print(
        f"\n[bold]Comparable listings[/bold] (showing {len(result.comparables)} of {result.comparable_count}):"
    )
    for i, c in enumerate(result.comparables, 1):
        br = f"{c.bedrooms}BR" if c.bedrooms is not None else "?BR"
        console.print(f"  {i}. {c.area_sqm:.0f} m² · {br} · €{c.rent_eur}/mo")
    console.print(
        f"\n[bold]Sample:[/bold] {result.comparable_count} listings ({result.comparable_method})"
    )
    console.print(f"[bold]Dataset:[/bold] GroundTruth Dataset {result.dataset_version}")
    console.print(f"[bold]Confidence:[/bold] {result.confidence_label}")
    console.print(f"[bold]Method:[/bold] {result.method_summary}")
    for factor in result.excluded_factors:
        console.print(f"  [dim]Excluded: {factor.factor} — {factor.reason}[/dim]")


@app.command("serve")
def serve(
    host: str = typer.Option("127.0.0.1"),
    port: int = typer.Option(8000),
    reload: bool = typer.Option(True, "--reload/--no-reload", help="Reload on code changes"),
    workers: int = typer.Option(1, min=1, help="Worker processes when reload is disabled"),
) -> None:
    """Run Metrik API + static site (development by default)."""
    import socket

    from groundtruth.config import PROJECT_ROOT

    try:
        import uvicorn
    except ImportError as exc:
        console.print("[red]Install web extras: uv sync --extra web[/red]")
        raise typer.Exit(1) from exc

    probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        if probe.connect_ex((host, port)) == 0:
            console.print(
                f"[yellow]Port {port} is already in use. Stop the old server first "
                f"(Task Manager → end Python/uvicorn) or use --port {port + 1}.[/yellow]"
            )
            raise typer.Exit(1)
    finally:
        probe.close()

    settings = get_settings()
    if not settings.is_development and reload:
        console.print("[yellow]Reload is disabled outside development.[/yellow]")
        reload = False

    console.print(f"[green]Metrik at http://{host}:{port}/[/green]")
    console.print(f"[dim]Environment: {settings.app_env}[/dim]")
    uvicorn.run(
        "groundtruth.api.app:app",
        host=host,
        port=port,
        reload=reload,
        reload_dirs=[str(PROJECT_ROOT / "src"), str(PROJECT_ROOT / "web")] if reload else None,
        workers=workers if not reload else 1,
        proxy_headers=not settings.is_development,
        forwarded_allow_ips=settings.forwarded_allow_ips if not settings.is_development else None,
    )


@app.command("serve-production")
def serve_production(
    host: str = typer.Option("0.0.0.0"),
    port: int = typer.Option(8000),
    workers: int = typer.Option(1, min=1, help="Worker processes"),
) -> None:
    """Run the production web server entrypoint (no reload)."""
    import os

    os.environ.setdefault("APP_ENV", "production")
    os.environ.setdefault("LOG_FORMAT", "json")
    os.environ.setdefault("PRODUCT_WRITE_BACKEND", "database")
    if workers > 1:
        console.print(
            "[yellow]Forcing workers=1 — lookup and comparables caches are in-process.[/yellow]"
        )
        workers = 1
    serve(
        host=host,
        port=port,
        reload=False,
        workers=workers,
    )


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


@report_app.command("coverage")
def report_coverage() -> None:
    """Neighborhood rent/sale comparable counts — where data is thin."""
    from rich.table import Table

    from groundtruth.analytics.coverage import build_neighborhood_coverage_table
    from groundtruth.database.session import get_session_factory
    from groundtruth.services.report_service import ReportService

    session = get_session_factory()()
    try:
        table = build_neighborhood_coverage_table(session)
        csv_path, md_path = ReportService().generate_coverage_report(session)

        rent_ready = int(table["rent_estimate_ready"].sum())
        sale_ready = int(table["sale_estimate_ready"].sum())
        console.print(
            f"[bold]Coverage[/bold] — {int(table['rent_comps'].sum())} rent · "
            f"{int(table['sale_comps'].sum())} sale comps "
            f"({rent_ready} rent-ready · {sale_ready} sale-ready NHs)"
        )

        display = table.head(20)
        rich_table = Table(title="Top neighborhoods by rent comps")
        rich_table.add_column("Neighborhood")
        rich_table.add_column("Rent", justify="right")
        rich_table.add_column("Sale", justify="right")
        rich_table.add_column("Rent ready")
        rich_table.add_column("Sale ready")
        for _, row in display.iterrows():
            rich_table.add_row(
                str(row["neighborhood"]),
                str(int(row["rent_comps"])),
                str(int(row["sale_comps"])),
                "yes" if row["rent_estimate_ready"] else "no",
                "yes" if row["sale_estimate_ready"] else "no",
            )
        console.print(rich_table)
        if len(table) > 20:
            console.print(f"[dim]…and {len(table) - 20} more in {csv_path}[/dim]")
        console.print(f"[green]CSV: {csv_path}[/green]")
        console.print(f"[green]Markdown: {md_path}[/green]")
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


@dedup_app.command("report")
def dedup_report(
    output: Path | None = typer.Option(
        None,
        help="Directory for cross_portal_groups.csv (default: data/deduplication)",
    ),
) -> None:
    """Scan active corpus for cross-portal duplicates and export a review register."""
    from groundtruth.analytics.corpus import deduped_corpus_dataframe
    from groundtruth.analytics.cross_dedup import cross_dedup_stats, duplicate_groups_table
    from groundtruth.analytics.listing_lifecycle import (
        cross_time_relist_candidates,
        lifecycle_summary,
    )
    from groundtruth.config import PROJECT_ROOT
    from groundtruth.database.session import get_session_factory

    session = get_session_factory()()
    try:
        raw_df = deduped_corpus_dataframe(session, active_only=True)
        stats = cross_dedup_stats(raw_df)
        lifecycle = lifecycle_summary(session, include_relists=True)
        groups = duplicate_groups_table(raw_df)
        relists = cross_time_relist_candidates(session)
    finally:
        session.close()

    out_dir = output or (PROJECT_ROOT / "data" / "deduplication")
    out_dir.mkdir(parents=True, exist_ok=True)
    groups_path = out_dir / "cross_portal_groups.csv"
    groups.to_csv(groups_path, index=False)
    relists_path = out_dir / "cross_time_relists.csv"
    relists.to_csv(relists_path, index=False)

    console.print("[bold]Cross-portal deduplication[/bold]")
    console.print(f"  Raw listings:        {stats.raw_listings}")
    console.print(f"  Canonical listings:  {stats.canonical_listings}")
    console.print(f"  Duplicate groups:    {stats.cross_portal_groups}")
    console.print(f"  Removed from supply: {stats.duplicates_removed}")
    console.print(f"  Median days on market: {lifecycle.get('median_days_on_market')}")
    console.print(f"  Relist fingerprints: {lifecycle.get('relist_fingerprints')}")
    console.print(f"[green]Wrote {groups_path}[/green]")
    console.print(f"[green]Wrote {relists_path}[/green]")


@corpus_app.command("report")
def corpus_report(
    output: Path | None = typer.Option(None, help="Output directory (default: reports/generated)"),
) -> None:
    """Generate corpus report + coverage matrix. Run after incremental ETL during crawls."""
    from groundtruth.analytics.corpus import write_corpus_artifacts
    from groundtruth.config import PROJECT_ROOT
    from groundtruth.database.session import get_session_factory

    out_dir = output or (PROJECT_ROOT / "reports" / "generated")
    session = get_session_factory()()
    try:
        paths = write_corpus_artifacts(session, out_dir)
    finally:
        session.close()

    console.print("[bold]Corpus report written[/bold]")
    for label, path in paths.items():
        console.print(f"  {label}: {path}")


@reports_app.command("export-annual")
def reports_export_annual(
    output: Path | None = typer.Option(None, help="Output JSON path"),
) -> None:
    """Export cached annual market report JSON for /api/reports/annual_data."""
    from groundtruth.analytics.annual_export import export_annual_report
    from groundtruth.database.session import get_session_factory

    session = get_session_factory()()
    try:
        path = export_annual_report(session, output=output)
    finally:
        session.close()
    console.print(f"[green]Annual report written to {path}[/green]")


@release_app.command("build-artifacts")
def release_build_artifacts() -> None:
    """Build lookup/comparables/statistics artifacts for public deployment."""
    from groundtruth.release import build_release_artifacts

    lookup_manifest, annual_path = build_release_artifacts()
    console.print(f"[green]Lookup cache written: {lookup_manifest}[/green]")
    console.print(f"[green]Annual report written: {annual_path}[/green]")


@release_app.command("verify-artifacts")
def release_verify_artifacts() -> None:
    """Verify required public deployment artifacts exist and are valid."""
    from groundtruth.release import verify_release_artifacts

    try:
        for line in verify_release_artifacts():
            console.print(f"[green]{line}[/green]")
    except Exception as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(1) from exc


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


@analytics_app.command("product")
def analytics_product(days: int = typer.Option(30, min=1, max=365)) -> None:
    """Print product usage dashboard from stored events."""
    from groundtruth.services.product_metrics import product_analytics_snapshot

    snap = product_analytics_snapshot(days=days)
    console.print(f"[bold]Product analytics — last {snap.window_days} days[/bold]")
    console.print(f"Events: {snap.event_count}")
    console.print(f"DAU (peak): {snap.dau}  WAU: {snap.wau}")
    if snap.repeat_visitor_rate_pct is not None:
        console.print(f"Repeat visitors: {snap.repeat_visitor_rate_pct}%")
    console.print(f"Valuations requested: {snap.valuations_requested}")
    console.print(f"Valuations completed: {snap.valuations_completed}")
    if snap.valuation_success_rate_pct is not None:
        console.print(f"Valuation success rate: {snap.valuation_success_rate_pct}%")
    console.print(f"Market page views: {snap.market_page_views}")
    console.print(f"Searches: {snap.searches_performed}")
    console.print(f"Zero-result searches: {snap.zero_result_searches}")
    if snap.zero_result_rate_pct is not None:
        console.print(f"Zero-result rate: {snap.zero_result_rate_pct}%")
    console.print(f"Rent yield views: {snap.rent_yield_views}")
    console.print(f"Report downloads: {snap.report_downloads}")
    if snap.avg_valuation_response_ms is not None:
        console.print(f"Avg valuation response: {snap.avg_valuation_response_ms} ms")
    if snap.top_neighborhoods:
        console.print("\nTop neighborhoods:")
        for row in snap.top_neighborhoods[:10]:
            console.print(f"  {row.neighborhood}: {row.events}")
    if snap.confidence_tier_counts:
        console.print(f"\nConfidence tiers: {snap.confidence_tier_counts}")
    if snap.listing_type_counts:
        console.print(f"Listing types: {snap.listing_type_counts}")


@analytics_app.command("coverage")
def analytics_coverage(
    freshness_days: int = typer.Option(14, min=1, max=90),
) -> None:
    """Print business coverage KPIs (municipality, NH depth, freshness, duplicates)."""
    from groundtruth.database.session import get_session_factory
    from groundtruth.services.coverage_metrics import coverage_analytics_snapshot

    session = get_session_factory()()
    try:
        snap = coverage_analytics_snapshot(session, freshness_days=freshness_days)
    finally:
        session.close()

    console.print(f"[bold]Coverage KPIs[/bold]  (freshness window: {snap.freshness_window_days}d)")
    if snap.corpus_updated_at:
        console.print(f"Corpus updated: {snap.corpus_updated_at}")
    console.print(
        f"Municipality coverage: {snap.municipality_coverage_pct}% "
        f"(target {snap.municipality_coverage_target_pct}%) "
        f"— {snap.municipalities_covered}/{snap.municipalities_tracked} weighted municipalities"
    )
    console.print(
        f"Neighborhoods ≥{snap.min_comparables} comps: "
        f"{snap.neighborhoods_with_min_comparables}/{snap.neighborhoods_total} "
        f"({snap.neighborhoods_with_min_comparables_pct}%) "
        f"[rent {snap.neighborhoods_rent_ready}, sale {snap.neighborhoods_sale_ready}]"
    )
    console.print(
        f"Listings fresh ≤{snap.freshness_window_days}d: {snap.listings_fresh_pct}% "
        f"(target {snap.freshness_target_pct}%) — {snap.listings_active} active canonical"
    )
    if snap.listings_stale_pct is not None:
        console.print(f"Stale listings: {snap.listings_stale_pct}%")
    console.print(
        f"Duplicate rate: {snap.duplicate_rate_pct}% "
        f"(target <{snap.duplicate_rate_target_pct}%) "
        f"— {snap.duplicates_removed} removed of {snap.raw_listings} raw"
    )
    cc = snap.confidence_coverage
    console.print(
        f"\n[bold]Confidence coverage[/bold] (projected rent, {cc.neighborhoods_total} NH) "
        f"— target high ≥{cc.high_confidence_target_pct}%"
    )
    console.print(
        f"  High: {cc.high_pct}% ({cc.high_count})  "
        f"Medium: {cc.medium_pct}% ({cc.medium_count})  "
        f"Insufficient: {cc.insufficient_pct}% ({cc.insufficient_count})"
    )
    if snap.holdout_eval:
        he = snap.holdout_eval
        console.print(
            f"\n[bold]Holdout evaluation[/bold]: {he.evaluated_rows}/{he.total_rows} "
            f"({he.evaluation_rate_pct}% rate, {he.skipped_rows} skipped)"
        )
        if he.mape_pct is not None:
            console.print(f"  MAPE: {he.mape_pct}%")
    if snap.opportunity_backlog:
        console.print("\n[bold]Coverage opportunity backlog[/bold] (demand × gap × population):")
        for row in snap.opportunity_backlog[:8]:
            flag = "[green]✓[/green]" if row.covered else "[red]✗[/red]"
            console.print(
                f"  #{row.rank} {flag} {row.municipality}: score {row.opportunity_score} "
                f"(demand {row.demand_weight_pct}%, gap {row.coverage_gap_pct}%)"
            )
    if snap.municipality_rows:
        console.print("\nMunicipality breakdown (by demand weight):")
        for row in snap.municipality_rows[:12]:
            flag = "[green]✓[/green]" if row.covered else "[red]✗[/red]"
            console.print(
                f"  {flag} {row.municipality}: {row.demand_weight_pct}% demand, "
                f"{row.neighborhoods_estimate_ready}/{row.neighborhoods_total} NH ready"
            )


@evaluation_app.command("valuate")
def evaluation_valuate(
    holdout: Path = typer.Option(
        Path("data/evaluation/valuation_holdout_v2.csv"),
        "--holdout",
        "-h",
        exists=True,
        readable=True,
    ),
    output: Path = typer.Option(
        Path("results/candidate.json"),
        "--output",
        "-o",
    ),
    report: Path | None = typer.Option(
        Path("reports/evaluation.md"),
        "--report",
        help="Write markdown summary (pass --no-report to skip)",
    ),
    include_rows: bool = typer.Option(False, "--include-rows"),
    no_report: bool = typer.Option(False, "--no-report"),
) -> None:
    """Evaluate valuation model against frozen holdout (MAE, RMSE, MAPE)."""
    from groundtruth.database.session import get_session_factory
    from groundtruth.evaluation.valuate import evaluate_holdout_file, write_eval_report

    session = get_session_factory()()
    try:
        result = evaluate_holdout_file(session, holdout)
    finally:
        session.close()

    md_path = None if no_report else report
    write_eval_report(result, json_path=output, markdown_path=md_path, include_rows=include_rows)
    console.print(f"Evaluated {result.evaluated_rows}/{result.total_rows} rows")
    console.print(
        f"MAE={result.mae} RMSE={result.rmse} Median AE={result.median_ae} MAPE={result.mape_pct}%"
    )
    console.print(f"Wrote {output}")
    if md_path:
        console.print(f"Wrote {md_path}")


@evaluation_app.command("compare")
def evaluation_compare(
    baseline: Path = typer.Option(
        Path("results/baseline.json"),
        "--baseline",
        "-b",
        exists=True,
        readable=True,
    ),
    candidate: Path = typer.Option(
        Path("results/candidate.json"),
        "--candidate",
        "-c",
        exists=True,
        readable=True,
    ),
) -> None:
    """Release gate: candidate must improve a key metric without material regression."""
    import json

    from groundtruth.evaluation.valuate import compare_eval_reports

    base = json.loads(baseline.read_text(encoding="utf-8"))
    cand = json.loads(candidate.read_text(encoding="utf-8"))
    verdict = compare_eval_reports(base, cand)
    console.print(verdict.message)
    if verdict.improvements:
        console.print("[green]Improvements:[/green]")
        for line in verdict.improvements:
            console.print(f"  + {line}")
    if verdict.regressions:
        console.print("[red]Regressions:[/red]")
        for line in verdict.regressions:
            console.print(f"  - {line}")
    if not verdict.passed:
        raise typer.Exit(code=1)


@evaluation_app.command("gate")
def evaluation_gate(
    result: Path = typer.Option(
        Path("results/candidate.json"),
        "--result",
        "-r",
        exists=True,
        readable=True,
    ),
    max_rent_mdape: float = typer.Option(15.0, "--max-rent-mdape"),
    max_sale_mdape: float = typer.Option(30.0, "--max-sale-mdape"),
    min_rows: int = typer.Option(40, "--min-rows"),
    min_coverage: float = typer.Option(90.0, "--min-coverage"),
    require_confidence_monotonic: bool = typer.Option(
        False,
        "--require-confidence-monotonic",
        help="Require High/Medium/Low error ordering (only after calibration).",
    ),
) -> None:
    """Block product release unless absolute valuation quality gates pass."""
    import json

    from groundtruth.evaluation.valuate import assess_release_readiness

    payload = json.loads(result.read_text(encoding="utf-8"))
    verdict = assess_release_readiness(
        payload,
        max_rent_mdape_pct=max_rent_mdape,
        max_sale_mdape_pct=max_sale_mdape,
        min_evaluated_rows=min_rows,
        min_coverage_pct=min_coverage,
        require_confidence_monotonic=require_confidence_monotonic,
    )
    console.print(verdict.message)
    if not verdict.passed:
        raise typer.Exit(code=1)


if __name__ == "__main__":
    app()
