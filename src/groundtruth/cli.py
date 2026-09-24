"""CLI entry point using typer."""

from pathlib import Path

import typer
from rich.console import Console

from groundtruth import __version__
from groundtruth.commands.crawl_portals import crawl_app
from groundtruth.commands.etl_commands import etl_app
from groundtruth.commands.pipeline_commands import pipeline_app
from groundtruth.commands.release_commands import release_app
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

app.add_typer(etl_app, name="etl")

reports_app = typer.Typer(help="Public report artifacts")
app.add_typer(reports_app, name="reports")

app.add_typer(release_app, name="release")

app.add_typer(pipeline_app, name="pipeline")

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


@dedup_app.command("benchmark")
def dedup_benchmark(
    labels: Path = typer.Option(
        PROJECT_ROOT / "data" / "deduplication" / "benchmark.csv",
        help="CSV of manually labelled cross-source pairs",
    ),
    output: Path = typer.Option(
        PROJECT_ROOT / "reports" / "generated" / "dedup_benchmark.csv",
        help="Threshold sensitivity output",
    ),
) -> None:
    """Measure dedup precision, recall, blocking recall, and threshold sensitivity."""
    import csv

    from groundtruth.analytics.dedup_benchmark import (
        evaluate_pairs,
        load_benchmark,
        threshold_sensitivity,
    )

    rows = load_benchmark(labels)
    result, details = evaluate_pairs(rows, threshold=get_settings().dedup_fuzzy_threshold)
    sensitivity = threshold_sensitivity(rows)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(sensitivity[0]))
        writer.writeheader()
        writer.writerows(sensitivity)
    errors = output.with_name("dedup_benchmark_errors.csv")
    with errors.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(details[0]))
        writer.writeheader()
        writer.writerows(details)
    console.print(
        f"Precision {result.precision:.1%} · recall {result.recall:.1%} · blocking recall {result.blocking_recall:.1%}"
    )
    console.print(f"[green]Wrote {output} and {errors}[/green]")


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


@corpus_app.command("market-integrity")
def market_integrity_report(
    output: Path | None = typer.Option(None, help="Output directory (default: reports/generated)"),
) -> None:
    """Generate the Stage 1 system-wide market integrity baseline."""
    from groundtruth.analytics.market_integrity import write_market_integrity_artifacts
    from groundtruth.config import PROJECT_ROOT
    from groundtruth.database.session import get_session_factory

    out_dir = output or (PROJECT_ROOT / "reports" / "generated")
    session = get_session_factory()()
    try:
        paths = write_market_integrity_artifacts(session, out_dir)
    finally:
        session.close()

    console.print("[bold]Market integrity baseline written[/bold]")
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


# Compatibility re-exports (moved implementations live in commands/*).
from groundtruth.commands.etl_commands import (  # noqa: E402,F401
    etl_errors,
    etl_health,
    etl_report,
    etl_run,
)
from groundtruth.commands.release_commands import (  # noqa: E402,F401
    release_build_artifacts,
    release_verify_artifacts,
)

if __name__ == "__main__":
    app()
