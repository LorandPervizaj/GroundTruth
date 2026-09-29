"""Release artifact CLI commands."""

from __future__ import annotations

import json
from pathlib import Path

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


@release_app.command("verify-bundle")
def release_verify_bundle(
    bundle: Path = typer.Argument(..., help="groundtruth-release-<release_id>.tar.gz"),
    release_id: str = typer.Option(..., help="Exact release id the bundle must carry"),
) -> None:
    """Verify checksum, public-only contents, and manifest identity of one bundle."""
    from groundtruth.automation.publication import verify_bundle

    try:
        verified = verify_bundle(bundle, release_id=release_id)
    except Exception as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(1) from exc
    print(json.dumps(verified.outputs()))
