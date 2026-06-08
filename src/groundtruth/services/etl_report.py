"""Format ETL quality reports for CLI output."""

from rich.console import Console
from rich.table import Table

from groundtruth.schemas.etl import EtlMetricsSchema, FieldExtractionRates


def print_etl_report(metrics: EtlMetricsSchema, console: Console | None = None) -> None:
    """Print a human-readable ETL quality report."""
    console = console or Console()
    rates = metrics.field_rates
    if isinstance(rates, dict):
        rates = FieldExtractionRates(**rates)
    elif rates is None:
        rates = FieldExtractionRates()

    console.print("\n[bold]ETL Quality Report[/bold]")
    console.print(f"Source:              {metrics.source}")
    if metrics.scrape_run_id:
        console.print(f"Scrape run:          {metrics.scrape_run_id}")
    console.print(f"Parser version:      {metrics.parser_version}")
    console.print(f"Normalizer version:  {metrics.normalization_version}")
    console.print(f"Duration:            {metrics.duration_seconds}s")
    console.print()

    table = Table(title="Pipeline throughput")
    table.add_column("Stage", style="cyan")
    table.add_column("Count", justify="right")
    table.add_row("Listings scraped", str(metrics.total_scraped))
    table.add_row("Parsed OK", str(metrics.parsed_success))
    table.add_row("Parse failed", str(metrics.parsed_failed))
    table.add_row("Normalized OK", str(metrics.normalized_success))
    table.add_row("Normalize failed", str(metrics.normalized_failed))
    table.add_row("Invalid (validation)", str(metrics.validation_failed))
    table.add_row("Duplicate candidates", str(metrics.duplicate_candidates))
    console.print(table)
    console.print()

    rates_table = Table(title="Field extraction rates")
    rates_table.add_column("Field", style="cyan")
    rates_table.add_column("Rate", justify="right")
    rates_table.add_row("Price extracted", f"{rates.price}%")
    rates_table.add_row("Area extracted", f"{rates.area}%")
    rates_table.add_row("Neighborhood extracted", f"{rates.neighborhood}%")
    rates_table.add_row("Building extracted", f"{rates.building}%")
    rates_table.add_row("Description extracted", f"{rates.description}%")
    rates_table.add_row("Listing type extracted", f"{rates.listing_type}%")
    console.print(rates_table)
