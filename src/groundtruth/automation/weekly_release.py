"""Canonical GroundTruth weekly research-to-verified-release operation."""

from __future__ import annotations

import json
import subprocess
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any

from rich.console import Console

from groundtruth.automation.models import PipelineRunResult, utc_now
from groundtruth.config import PROJECT_ROOT


def source_git_sha() -> str:
    result = subprocess.run(
        ["git", "rev-parse", "--short=12", "HEAD"],
        cwd=PROJECT_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip() if result.returncode == 0 else "unknown"


def make_release_id(now: datetime | None = None, *, git_sha: str | None = None) -> str:
    current = now or utc_now()
    iso = current.isocalendar()
    return f"{iso.year}-W{iso.week:02d}-{git_sha or source_git_sha()}"


def _default_output_path(run_id: str) -> Path:
    return PROJECT_ROOT / "reports" / "generated" / "weekly" / "runs" / f"{run_id}.json"


def _write_result(result: PipelineRunResult, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(result.to_dict(), indent=2), encoding="utf-8")
    temporary.replace(path)


def run_weekly_release(
    *,
    days: int = 7,
    force: bool = True,
    output_path: Path | None = None,
    console: Console | None = None,
    weekly_runner: Callable[..., Any] | None = None,
    verifier: Callable[[], list[str]] | None = None,
) -> PipelineRunResult:
    """Run the existing weekly pipeline and fail closed on release verification."""
    from groundtruth.crawl.weekly import run_weekly_pipeline
    from groundtruth.release import verify_release_artifacts

    out = console or Console()
    started = utc_now()
    sha = source_git_sha()
    release_id = make_release_id(started, git_sha=sha)
    run_id = f"{release_id}-{started.strftime('%Y%m%dT%H%M%SZ')}"
    result = PipelineRunResult(
        run_id=run_id,
        release_id=release_id,
        started_at=started.isoformat(),
        requested_days=days,
    )
    destination = output_path or _default_output_path(run_id)
    _write_result(result, destination)

    weekly = weekly_runner or run_weekly_pipeline
    verify = verifier or verify_release_artifacts
    try:
        stage = result.stage("weekly_pipeline")
        stage.start()
        _write_result(result, destination)
        report = weekly(days=days, force=force, stage="all", resume=True, console=out)
        stage.counts = {
            "sources": len(report.sources),
            "sources_failed": sum(1 for item in report.sources if item.error),
            "normalized": sum(item.etl_normalized for item in report.sources),
        }
        stage.details["window"] = {
            "start": str(report.window.window_start),
            "end": str(report.window.window_end),
        }
        stage.finish("passed")
        _write_result(result, destination)

        stage = result.stage("release_verify")
        stage.start()
        _write_result(result, destination)
        stage.details["checks"] = verify()
        stage.finish("passed")
        result.outcome = "verified"
    except Exception as exc:
        if result.stages and result.stages[-1].status == "running":
            result.stages[-1].finish("failed", error=str(exc))
        result.outcome = "failed"
        raise
    finally:
        result.finished_at = utc_now().isoformat()
        _write_result(result, destination)
        out.print(f"[bold]Pipeline run record:[/bold] {destination}")
    return result
