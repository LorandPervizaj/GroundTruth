"""CLI commands for sensitive-data retention enforcement."""

from __future__ import annotations

import json

import typer
from rich.console import Console

from groundtruth.config import get_settings
from groundtruth.database.session import get_session_factory
from groundtruth.services.retention import enforce_retention

console = Console()
retention_app = typer.Typer(help="Sensitive listing-content retention")


@retention_app.command("purge")
def purge_retained_content(
    apply: bool = typer.Option(
        False,
        "--apply",
        help="Apply the purge. Without this flag the command is a dry run.",
    ),
) -> None:
    """Purge raw content and descriptions older than configured windows."""
    settings = get_settings()
    with get_session_factory()() as session:
        result = enforce_retention(session, settings, dry_run=not apply)
        if apply:
            session.commit()
        else:
            session.rollback()

    console.print_json(json.dumps(result.as_dict()))
    if not apply:
        console.print("[yellow]Dry run only. Re-run with --apply to purge.[/yellow]")
