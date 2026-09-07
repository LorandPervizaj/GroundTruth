"""CLI entry point for valuation evaluation (P2 harness)."""

from __future__ import annotations

import json
from pathlib import Path

import typer

from groundtruth.config import PROJECT_ROOT
from groundtruth.database.session import get_session_factory
from groundtruth.evaluation.valuate import (
    DEFAULT_HOLDOUT,
    REPORTS_DIR,
    RESULTS_DIR,
    assess_release_readiness,
    compare_eval_reports,
    evaluate_holdout_file,
    write_eval_report,
)

app = typer.Typer(help="Run valuation evaluation against frozen holdout")


@app.command()
def run(
    holdout: Path = typer.Option(DEFAULT_HOLDOUT, "--holdout", "-h"),
    output: Path = typer.Option(RESULTS_DIR / "candidate.json", "--output", "-o"),
    report: Path | None = typer.Option(
        REPORTS_DIR / "evaluation.md", "--report", help="Write markdown summary"
    ),
    include_rows: bool = typer.Option(False, "--include-rows"),
) -> None:
    """Evaluate current valuation model against holdout and write JSON (+ optional MD)."""
    session = get_session_factory()()
    try:
        result = evaluate_holdout_file(session, holdout)
    finally:
        session.close()
    write_eval_report(result, json_path=output, markdown_path=report, include_rows=include_rows)
    typer.echo(f"Evaluated {result.evaluated_rows}/{result.total_rows} rows")
    typer.echo(f"MAE={result.mae} RMSE={result.rmse} MAPE={result.mape_pct}%")
    typer.echo(f"Wrote {output}")
    if report:
        typer.echo(f"Wrote {report}")


@app.command()
def compare(
    baseline: Path = typer.Option(RESULTS_DIR / "baseline.json", "--baseline", "-b"),
    candidate: Path = typer.Option(RESULTS_DIR / "candidate.json", "--candidate", "-c"),
) -> None:
    """Release gate: candidate must improve a key metric without material regression."""
    if not baseline.is_file():
        raise typer.BadParameter(f"Baseline not found: {baseline}")
    if not candidate.is_file():
        raise typer.BadParameter(f"Candidate not found: {candidate}")
    base = json.loads(baseline.read_text(encoding="utf-8"))
    cand = json.loads(candidate.read_text(encoding="utf-8"))
    verdict = compare_eval_reports(base, cand)
    typer.echo(verdict.message)
    if verdict.improvements:
        typer.echo("Improvements:")
        for line in verdict.improvements:
            typer.echo(f"  + {line}")
    if verdict.regressions:
        typer.echo("Regressions:")
        for line in verdict.regressions:
            typer.echo(f"  - {line}")
    if not verdict.passed:
        raise typer.Exit(code=1)


@app.command()
def gate(
    result: Path = typer.Option(RESULTS_DIR / "candidate.json", "--result", "-r"),
    max_rent_mdape: float = typer.Option(15.0, "--max-rent-mdape"),
    max_sale_mdape: float = typer.Option(30.0, "--max-sale-mdape"),
    min_rows: int = typer.Option(40, "--min-rows"),
    min_coverage: float = typer.Option(90.0, "--min-coverage"),
    require_confidence_monotonic: bool = typer.Option(False, "--require-confidence-monotonic"),
) -> None:
    """Apply absolute product-release gates to an evaluation artifact."""
    if not result.is_file():
        raise typer.BadParameter(f"Evaluation result not found: {result}")
    payload = json.loads(result.read_text(encoding="utf-8"))
    verdict = assess_release_readiness(
        payload,
        max_rent_mdape_pct=max_rent_mdape,
        max_sale_mdape_pct=max_sale_mdape,
        min_evaluated_rows=min_rows,
        min_coverage_pct=min_coverage,
        require_confidence_monotonic=require_confidence_monotonic,
    )
    typer.echo(verdict.message)
    if not verdict.passed:
        raise typer.Exit(code=1)


if __name__ == "__main__":
    app()
