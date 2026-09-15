"""CLI commands for Part B — Facebook Marketplace (informal tier)."""

from __future__ import annotations

from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from groundtruth.schemas.facebook import FacebookGroupSample

console = Console()
fb_app = typer.Typer(help="Facebook informal inventory (B0–B3)")


@fb_app.command("decision")
def fb_decision() -> None:
    """Print B0 go/no-go decision (B0)."""
    console.print("[bold]Facebook Marketplace[/bold]")
    console.print("  B1 full scrape:     [yellow]NO-GO[/yellow] (ToS / automation risk)")
    console.print("  Manual import only: [green]allowed[/green]")
    console.print("\n[dim]Policy: docs/FB_MARKETPLACE.md · docs/CRAWL_POLICY.md[/dim]")


@fb_app.command("import")
def fb_import(
    input_file: Path = typer.Argument(..., help="JSONL file of manual Marketplace captures"),
) -> None:
    """Import manual Marketplace listings into informal quarantine (B1)."""
    from groundtruth.services.facebook_import import import_marketplace_jsonl

    if not input_file.exists():
        console.print(f"[red]File not found: {input_file}[/red]")
        raise typer.Exit(1)

    stats = import_marketplace_jsonl(input_file)
    console.print(
        f"[green]Imported {stats['imported']}[/green] "
        f"(skipped {stats['skipped']}, failed {stats['failed']}, total {stats['total']})"
    )
    console.print("[dim]Informal tier — excluded from public medians (B2)[/dim]")


@fb_app.command("sample")
def fb_sample(
    group: str = typer.Option(..., "--group", "-g", help="Group id from registry.json"),
    snippet: str = typer.Option(..., "--snippet", "-s", help="Post text snippet"),
    price: int | None = typer.Option(None, "--price", "-p"),
    listing_type: str = typer.Option("unknown", "--type", "-t"),
    neighborhood: str | None = typer.Option(None, "--neighborhood", "-n"),
    post_url: str | None = typer.Option(None, "--url"),
    area: int | None = typer.Option(None, "--area"),
    bedrooms: int | None = typer.Option(None, "--bedrooms"),
) -> None:
    """Record a manual Facebook group post observation (B3)."""
    from groundtruth.services.facebook_groups import record_group_sample

    sample = FacebookGroupSample(
        group_id=group,
        snippet=snippet,
        price_eur=price,
        listing_type=listing_type,  # type: ignore[arg-type]
        neighborhood_guess=neighborhood,
        post_url=post_url,
        area_sqm=area,
        bedrooms=bedrooms,
    )
    path = record_group_sample(sample)
    console.print(f"[green]Sample recorded[/green] → {path}")


@fb_app.command("report")
def fb_report(
    days: int = typer.Option(90, min=7, max=365, help="Sample window in days"),
) -> None:
    """Summarize informal listings + group samples (B3)."""
    from groundtruth.analytics.facebook_signal import summarize_facebook_signals

    summary = summarize_facebook_signals(sample_days=days)
    table = Table(title="Facebook informal signal (not in public medians)")
    table.add_column("Metric")
    table.add_column("Value")
    table.add_row("Informal Marketplace rows", str(summary["informal_listings"]))
    table.add_row("Group samples", str(summary["group_samples"]))
    table.add_row("Window (days)", str(summary["sample_window_days"]))
    table.add_row("Median rent (€)", str(summary["median_rent_eur"] or "—"))
    table.add_row("Median sale (€)", str(summary["median_sale_eur"] or "—"))
    table.add_row("Rent prices n", str(summary["rent_price_n"]))
    table.add_row("Sale prices n", str(summary["sale_price_n"]))
    console.print(table)

    if summary["top_neighborhood_guesses"]:
        console.print("\n[bold]Top neighborhood guesses[/bold]")
        for nh, count in summary["top_neighborhood_guesses"]:
            console.print(f"  {nh}: {count}")


@fb_app.command("status")
def fb_status() -> None:
    """Counts + policy reminder."""
    from groundtruth.analytics.corpus_filters import INFORMAL_SOURCE_WEBSITES
    from groundtruth.services.facebook_groups import load_group_registry, sample_count
    from groundtruth.services.facebook_import import informal_listing_count

    reg = load_group_registry()
    groups = reg.get("groups", [])
    console.print("[bold]Facebook informal tier[/bold]")
    console.print(f"  Marketplace quarantine: {informal_listing_count()} rows")
    console.print(f"  Group samples (12 mo):  {sample_count()}")
    console.print(f"  Tracked groups:         {len(groups)}")
    console.print(f"  Excluded sources:       {', '.join(sorted(INFORMAL_SOURCE_WEBSITES))}")
    console.print(
        "[dim]B1 full scrape: NO-GO · B3 sampling: GO — see `groundtruth fb decision`[/dim]"
    )
