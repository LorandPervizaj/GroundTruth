"""Run Phase C forensic dataset audit and write HTML + CSV artifacts."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import typer
from rich.console import Console

from groundtruth.analytics.audit import run_audit, write_audit_artifacts
from groundtruth.config import PROJECT_ROOT
from groundtruth.database.session import get_session_factory

app = typer.Typer()
console = Console()
REPORTS_DIR = PROJECT_ROOT / "reports" / "generated"


@app.command()
def audit(
    output_dir: Path | None = typer.Option(None, help="Output directory for report artifacts"),
    include_duplicates: bool = typer.Option(False, help="Analyze all normalized rows (no dedupe)"),
) -> None:
    """Generate missingness, cardinality, anomaly, and distribution audit report."""
    stamp = datetime.now(UTC).strftime("%Y-%m-%d")
    out = output_dir or REPORTS_DIR / f"audit_{stamp}"

    session = get_session_factory()()
    try:
        report = run_audit(session, dedupe=not include_duplicates)
        html_path = write_audit_artifacts(report, out)
        console.print(f"[green]Audit report written to {html_path}[/green]")
        console.print(f"  Missingness top gap: {report.missingness.iloc[0]['field']} "
                      f"({report.missingness.iloc[0]['missing_percent']}%)")
        console.print(f"  Duplicate groups (>=2): {len(report.duplicate_groups)}")
        if not report.anomalies.empty:
            console.print(f"  Z-score anomalies: {len(report.anomalies)}")
    finally:
        session.close()


if __name__ == "__main__":
    app()
