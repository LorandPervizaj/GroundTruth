"""Portal crawl CLI commands (Scrapy launchers)."""

from __future__ import annotations

import typer
from rich.console import Console

console = Console()
crawl_app = typer.Typer(help="Scraping commands")


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
