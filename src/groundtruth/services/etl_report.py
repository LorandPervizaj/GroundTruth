"""Format ETL quality reports for CLI output."""

from rich.console import Console
from rich.table import Table

from groundtruth.processing.parser_kpis import ParserKPIReport
from groundtruth.schemas.etl import EtlMetricsSchema, FieldExtractionRates


def print_etl_report(metrics: EtlMetricsSchema, console: Console | None = None) -> None:
    """Print a human-readable ETL quality report."""
    console = console or Console()
    rates = metrics.field_rates
    if isinstance(rates, dict):
        rates = FieldExtractionRates(**rates)
    elif rates is None:
        rates = FieldExtractionRates()

    kpi_data = rates.parser_kpis or {}
    kpis = ParserKPIReport.model_validate(kpi_data) if kpi_data else None

    console.print("\n[bold]ETL Quality Report[/bold]")
    console.print(f"Source:              {metrics.source}")
    if metrics.scrape_run_id:
        console.print(f"Scrape run:          {metrics.scrape_run_id}")
    console.print(f"Parser version:      {metrics.parser_version}")
    console.print(f"Normalizer version:  {metrics.normalization_version}")
    if metrics.gazetteer_version:
        console.print(f"Gazetteer version:   {metrics.gazetteer_version}")
    console.print(f"Duration:            {metrics.duration_seconds}s")
    if kpis:
        console.print(f"Invalid rate:        {kpis.invalid_rate_pct}%")
        console.print(f"Duplicate rate:      {kpis.duplicate_rate_pct}%")
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

    cov = kpis.coverage if kpis else None
    cov_table = Table(title="Parser KPIs — coverage (this run)")
    cov_table.add_column("Field", style="cyan")
    cov_table.add_column("Coverage", justify="right")
    cov_table.add_row("Price", f"{(cov.price if cov else rates.price)}%")
    cov_table.add_row("Area", f"{(cov.area if cov else rates.area)}%")
    cov_table.add_row("Neighborhood", f"{(cov.neighborhood if cov else rates.neighborhood)}%")
    cov_table.add_row("Building", f"{(cov.building if cov else rates.building)}%")
    cov_table.add_row("Heating", f"{(cov.heating if cov else rates.heating)}%")
    cov_table.add_row("Furnished", f"{(cov.furnished if cov else rates.furnished)}%")
    console.print(cov_table)

    if kpis and kpis.accuracy:
        acc = kpis.accuracy
        console.print()
        acc_table = Table(
            title=f"Parser KPIs — accuracy ({acc.golden_version}, n={acc.sample_size})"
        )
        acc_table.add_column("Field", style="cyan")
        acc_table.add_column("Accuracy", justify="right")
        acc_table.add_row("Price", f"{acc.price}%")
        acc_table.add_row("Area", f"{acc.area}%")
        acc_table.add_row("Neighborhood", f"{acc.neighborhood}%")
        acc_table.add_row("Overall", f"{acc.overall}%")
        console.print(acc_table)

    errors = rates.error_breakdown or {}
    if errors:
        console.print()
        err_table = Table(title="Validation errors")
        err_table.add_column("Error", style="cyan")
        err_table.add_column("Count", justify="right")
        for code, count in sorted(errors.items(), key=lambda x: x[1], reverse=True):
            err_table.add_row(code, str(count))
        console.print(err_table)
