"""Autonomous pipeline commands."""

from pathlib import Path

import typer
from rich.console import Console

pipeline_app = typer.Typer(help="Autonomous research-to-release operations")
console = Console()


@pipeline_app.command("weekly-release")
def weekly_release(
    days: int | None = typer.Option(
        None, min=1, max=56, help="Override verified-watermark catch-up interval"
    ),
    force: bool = typer.Option(
        True, "--force/--no-force", help="Run even when weekly state is recent"
    ),
    output: Path | None = typer.Option(None, help="Optional structured run-result path"),
) -> None:
    """Crawl, process, build and verify one candidate weekly release."""
    from groundtruth.automation.weekly_release import run_weekly_release

    result = run_weekly_release(days=days, force=force, output_path=output, console=console)
    console.print(f"[green]Verified release candidate: {result.release_id}[/green]")
