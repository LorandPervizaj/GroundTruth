"""Internal data quality dashboard — trends from benchmark log and audit artifacts."""

from __future__ import annotations

import csv
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
import typer
from rich.console import Console

from groundtruth.config import PROJECT_ROOT
from groundtruth.services.benchmark_log import BENCHMARK_COLUMNS

app = typer.Typer()
console = Console()
REPORTS = PROJECT_ROOT / "reports" / "generated"
BENCHMARK = REPORTS / "benchmark_log.csv"


def _load_benchmark() -> pd.DataFrame:
    if not BENCHMARK.exists():
        return pd.DataFrame()
    rows: list[dict[str, str]] = []
    with BENCHMARK.open(encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            rows.append({col: row.get(col, "") for col in BENCHMARK_COLUMNS})
    return pd.DataFrame(rows)


def _load_audits() -> pd.DataFrame:
    rows = []
    for audit_dir in sorted(REPORTS.glob("audit_*")):
        missing = audit_dir / "missingness.csv"
        bias = audit_dir / "source_bias.csv"
        if not missing.exists():
            continue
        miss = pd.read_csv(missing)
        row = {"audit_date": audit_dir.name.replace("audit_", "")}
        for _, r in miss.iterrows():
            row[f"missing_{r['field']}"] = r["missing_percent"]
        if bias.exists():
            b = pd.read_csv(bias)
            rent = b[(b["dimension"] == "listing_type") & (b["value"] == "rent")]
            if not rent.empty:
                row["pct_rent"] = rent.iloc[0]["percent"]
        rows.append(row)
    return pd.DataFrame(rows)


def _render_html(benchmark: pd.DataFrame, audits: pd.DataFrame) -> str:
    bench_html = benchmark.tail(10).to_html(index=False) if not benchmark.empty else "<p>No benchmarks</p>"
    audit_html = audits.to_html(index=False) if not audits.empty else "<p>No audits</p>"
    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"/><title>GroundTruth Quality Trends</title>
<style>
body {{ font-family: system-ui, sans-serif; margin: 2rem; }}
table {{ border-collapse: collapse; width: 100%; margin: 1rem 0; font-size: 0.9rem; }}
th, td {{ border: 1px solid #ddd; padding: 0.4rem 0.6rem; }}
th {{ background: #f5f5f5; }}
</style></head><body>
<h1>GroundTruth — Internal Data Quality Dashboard</h1>
<p>Generated {datetime.now(UTC).isoformat()}</p>
<h2>ETL benchmark trend (latest 10 runs)</h2>
{bench_html}
<h2>Audit missingness trend</h2>
{audit_html}
<p><em>For yourself before users. See docs/METHODOLOGY.md for interpretation.</em></p>
</body></html>"""


@app.command()
def dashboard(
    output: Path = typer.Option(REPORTS / "quality_trends.html"),
) -> None:
    """Aggregate benchmark_log and audit artifacts into one HTML page."""
    benchmark = _load_benchmark()
    audits = _load_audits()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(_render_html(benchmark, audits), encoding="utf-8")
    console.print(f"[green]Quality dashboard written to {output}[/green]")
    if not benchmark.empty:
        latest = benchmark.iloc[-1]
        console.print(
            f"  Latest: invalid={latest.get('invalid_rate_pct', '?')}% "
            f"nh={latest.get('coverage_neighborhood', '?')}% "
            f"area={latest.get('coverage_area', '?')}%"
        )


if __name__ == "__main__":
    app()
