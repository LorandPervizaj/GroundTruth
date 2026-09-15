"""Release artifact CLI commands."""

from __future__ import annotations

import typer
from rich.console import Console

console = Console()
release_app = typer.Typer(help="Production release artifact checks")


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
