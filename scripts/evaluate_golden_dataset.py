"""CLI wrapper for versioned golden dataset evaluation."""

from __future__ import annotations

import csv
from datetime import UTC, datetime
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from groundtruth.golden.evaluate import (
    GOLDEN_DIR,
    evaluate_golden_file,
    latest_golden_file,
    load_baseline,
)
from groundtruth.services.parsing import PARSER_VERSION

app = typer.Typer()
console = Console()
SCORES_PATH = GOLDEN_DIR / "parser_scores.csv"


def _append_score(version: str, evaluation) -> None:
    GOLDEN_DIR.mkdir(parents=True, exist_ok=True)
    write_header = not SCORES_PATH.exists()
    with SCORES_PATH.open("a", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(
            fh,
            fieldnames=["recorded_at", "parser_version", "golden_version", "score", "neighborhood", "price", "area", "overall"],
        )
        if write_header:
            writer.writeheader()
        writer.writerow(
            {
                "recorded_at": datetime.now(UTC).isoformat(),
                "parser_version": PARSER_VERSION,
                "golden_version": version,
                "score": round(evaluation.overall * 100, 1),
                "neighborhood": round(evaluation.neighborhood * 100, 1),
                "price": round(evaluation.price * 100, 1),
                "area": round(evaluation.area * 100, 1),
                "overall": round(evaluation.overall * 100, 1),
            }
        )


@app.command()
def evaluate(
    input_file: str | None = typer.Option(None, help="e.g. data/golden/golden_v1.csv"),
) -> None:
    """Score parser against a versioned golden dataset."""
    path = Path(input_file) if input_file else latest_golden_file()
    if path is None or not path.exists():
        console.print("[yellow]No golden dataset found. Label golden_v1_candidates.csv first.[/yellow]")
        raise typer.Exit(0)

    result = evaluate_golden_file(path)
    if result is None:
        console.print(f"[yellow]No verified rows in {path}[/yellow]")
        raise typer.Exit(0)

    table = Table(title=f"Golden evaluation — {path.name} (parser {PARSER_VERSION}, n={result.total})")
    table.add_column("Field")
    table.add_column("Accuracy", justify="right")
    for field, value in result.as_dict().items():
        table.add_row(field, f"{value * 100:.1f}%")
    console.print(table)

    version = path.stem.replace("golden_", "")
    _append_score(version, result)


if __name__ == "__main__":
    app()
