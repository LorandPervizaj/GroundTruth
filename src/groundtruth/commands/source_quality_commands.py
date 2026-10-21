"""Operator-facing private quality reports; weights are recommendations only."""

import json
from datetime import datetime
from pathlib import Path

import typer
from pydantic import TypeAdapter, ValidationError
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from groundtruth.analytics.source_quality import build_report, utc, write_report
from groundtruth.analytics.source_quality_models import QualityPolicy, QualityRecord
from groundtruth.analytics.source_quality_population import pipeline_records
from groundtruth.config import PROJECT_ROOT
from groundtruth.portals.registry import all_portal_names

source_quality_app = typer.Typer(help="Private source-quality diagnostics (recommendations only)")


@source_quality_app.command("report")
def quality_report(
    as_of: datetime = typer.Option(
        ...,
        formats=[
            "%Y-%m-%d",
            "%Y-%m-%dT%H:%M:%S",
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%dT%H:%M:%S%z",
            "%Y-%m-%dT%H:%M:%S.%f%z",
        ],
        help="Explicit evaluation timestamp; naive values mean UTC",
    ),
    days: int = typer.Option(30, min=1, help="Inclusive raw-ingestion window in days"),
    source: str | None = typer.Option(None, help="One registered source; default: all"),
    segment: bool = typer.Option(False, help="Also report sale, rent, and unknown segments"),
    output: Path = typer.Option(PROJECT_ROOT / "reports/generated/source_quality"),
    fixture: Path | None = typer.Option(
        None, exists=True, dir_okay=False, help="Offline JSON list of QualityRecord inputs"
    ),
    policy_file: Path | None = typer.Option(
        None, exists=True, dir_okay=False, help="Versioned QualityPolicy JSON overrides"
    ),
) -> None:
    """Evaluate all ingestion outcomes without changing any pipeline decisions."""
    sources = sorted(all_portal_names())
    if source:
        if source not in sources:
            raise typer.BadParameter(
                "Unknown source; choose a registered portal", param_hint="--source"
            )
        sources = [source]
    as_of = utc(as_of)
    try:
        policy = (
            QualityPolicy.model_validate_json(policy_file.read_text(encoding="utf-8"))
            if policy_file
            else QualityPolicy()
        )
        if fixture:
            records = TypeAdapter(list[QualityRecord]).validate_json(
                fixture.read_text(encoding="utf-8")
            )
        else:
            from groundtruth.database.session import get_session_factory

            with get_session_factory()() as session, session.begin():
                # A stable, read-only PostgreSQL snapshot, with no automatic commit helper.
                session.execute(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY"))
                records = pipeline_records(session, sources=sources, as_of=as_of, window_days=days)
        report = build_report(
            records, sources=sources, as_of=as_of, window_days=days, segment=segment, policy=policy
        )
        if not report.listings:
            typer.echo("No source data in the requested evaluation window.", err=True)
            raise typer.Exit(1)
        write_report(report, output)
    except (OSError, ValueError, ValidationError, json.JSONDecodeError) as exc:
        # Validation errors can contain input payloads; never print those.
        typer.echo(
            f"Quality report input/output failed ({type(exc).__name__}). Check fixture, policy, timestamp, and output path.",
            err=True,
        )
        raise typer.Exit(1) from None
    except SQLAlchemyError:
        typer.echo(
            "Quality report database unavailable or incompatible; no database changes made.",
            err=True,
        )
        raise typer.Exit(1) from None
    typer.echo(
        f"Wrote {len(report.sources)} source/segment summaries and {len(report.listings)} listing assessments to {output}"
    )
