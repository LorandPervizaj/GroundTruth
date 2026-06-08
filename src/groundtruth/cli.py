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
) -> None:
    """Run raw → parsed → normalized ETL with validation metrics."""
    from groundtruth.database.session import get_session_factory
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
