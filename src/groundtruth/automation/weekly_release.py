"""Canonical GroundTruth weekly research-to-verified-release operation."""

from __future__ import annotations

import json
import os
import subprocess
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any

from rich.console import Console

from groundtruth.automation.models import PipelineRunResult, utc_now
from groundtruth.automation.state import (
    calculate_lookback_days,
    load_state,
    pipeline_lock,
    save_state,
    verified_watermark,
)
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
    days: int | None = None,
    force: bool = True,
    output_path: Path | None = None,
    console: Console | None = None,
    weekly_runner: Callable[..., Any] | None = None,
    verifier: Callable[[], list[str]] | None = None,
    source_health_runner: Callable[[Any], list[Any]] | None = None,
    data_quality_runner: Callable[[Any], list[Any]] | None = None,
    statistical_runner: Callable[[dict[str, Any]], Any] | None = None,
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
        requested_days=days or 0,
        source_git_sha=sha,
    )
    durable_state = load_state()
    watermark = verified_watermark(durable_state)
    resolved_days = days or calculate_lookback_days(watermark, today=started.date())
    result.requested_days = resolved_days
    result.previous_release_id = durable_state.get("last_verified_release_id")
    destination = output_path or _default_output_path(run_id)
    _write_result(result, destination)

    weekly = weekly_runner or run_weekly_pipeline
    verify = verifier or verify_release_artifacts
    try:
        with pipeline_lock(run_id):
            stage = result.stage("weekly_pipeline")
            stage.start()
            _write_result(result, destination)
            report = weekly(days=resolved_days, force=force, stage="all", resume=True, console=out)
            stage.counts = {
                "sources": len(report.sources),
                "sources_failed": sum(1 for item in report.sources if item.error),
                "normalized": sum(item.etl_normalized for item in report.sources),
            }
            stage.details["window"] = {
                "start": str(report.window.window_start),
                "end": str(report.window.window_end),
            }
            result.data_window_start = str(report.window.window_start)
            result.data_through = str(report.window.window_end)
            stage.finish("passed")
            _write_result(result, destination)

            stage = result.stage("source_health")
            stage.start()
            _write_result(result, destination)
            if source_health_runner is None:
                from groundtruth.automation.source_health import collect_source_health
                from groundtruth.database.session import get_session_factory

                with get_session_factory()() as session:
                    health = collect_source_health(session, report.sources)
            else:
                health = source_health_runner(report)
            health_payload = [item.to_dict() for item in health]
            stage.details["sources"] = health_payload
            stage.counts = {
                "green": sum(item.level == "GREEN" for item in health),
                "yellow": sum(item.level == "YELLOW" for item in health),
                "red": sum(item.level == "RED" for item in health),
            }
            if stage.counts["red"]:
                stage.finish("failed", error="one or more automated sources are RED")
                raise RuntimeError(stage.error)
            stage.finish("warning" if stage.counts["yellow"] else "passed")
            _write_result(result, destination)

            stage = result.stage("data_quality")
            stage.start()
            _write_result(result, destination)
            if data_quality_runner is None:
                from groundtruth.automation.data_quality import collect_data_quality
                from groundtruth.database.session import get_session_factory

                with get_session_factory()() as session:
                    quality = collect_data_quality(session, report.sources)
            else:
                quality = data_quality_runner(report)
            stage.details["sources"] = [item.to_dict() for item in quality]
            stage.counts = {
                "raw": sum(item.raw for item in quality),
                "parsed": sum(item.parsed for item in quality),
                "normalized": sum(item.normalized for item in quality),
                "valid": sum(item.valid for item in quality),
                "quarantined": sum(item.quarantined for item in quality),
                "duplicate_candidates": sum(item.duplicate_candidates for item in quality),
                "yellow": sum(item.level == "YELLOW" for item in quality),
                "red": sum(item.level == "RED" for item in quality),
            }
            if stage.counts["red"]:
                stage.finish("failed", error="ETL data-integrity gate is RED")
                raise RuntimeError(stage.error)
            stage.finish("warning" if stage.counts["yellow"] else "passed")
            _write_result(result, destination)

            stage = result.stage("statistical_sanity", blocking=False)
            stage.start()
            _write_result(result, destination)
            if statistical_runner is None:
                from groundtruth.automation.statistical_sanity import (
                    build_statistical_snapshot,
                    evaluate_statistical_sanity,
                )

                shadow_mode = os.getenv("GROUNDTRUTH_STATISTICAL_QA_SHADOW", "true").lower() in {
                    "1",
                    "true",
                    "yes",
                }
                statistical = evaluate_statistical_sanity(
                    build_statistical_snapshot(),
                    durable_state.get("last_verified_statistics"),
                    shadow_mode=shadow_mode,
                )
            else:
                statistical = statistical_runner(durable_state)
            stage.details.update(statistical.to_dict())
            if statistical.level == "RED" and not statistical.shadow_mode:
                stage.blocking = True
                stage.finish("failed", error="statistical sanity gate is RED")
                raise RuntimeError(stage.error)
            stage.finish("warning" if statistical.level != "GREEN" else "passed")
            _write_result(result, destination)

            stage = result.stage("release_build")
            stage.start()
            _write_result(result, destination)
            from groundtruth.claims.hashes import sha256_file
            from groundtruth.release import create_release_bundle, stamp_release_metadata

            manifest_path = stamp_release_metadata(
                release_id=result.release_id,
                data_through=result.data_through or started.date().isoformat(),
                source_git_sha=sha,
                qa_decision=statistical.level,
                previous_release_id=result.previous_release_id,
            )
            result.release_manifest_sha256 = sha256_file(manifest_path)
            stage.details["manifest"] = str(manifest_path)
            stage.details["manifest_sha256"] = result.release_manifest_sha256
            stage.finish("passed")
            _write_result(result, destination)

            stage = result.stage("release_verify")
            stage.start()
            _write_result(result, destination)
            stage.details["checks"] = verify()
            stage.finish("passed")
            bundle, digest = create_release_bundle(result.release_id)
            result.release_bundle = str(bundle)
            stage.details["bundle"] = str(bundle)
            stage.details["bundle_sha256"] = digest.read_text(encoding="utf-8").split()[0]
            result.outcome = (
                "warning" if any(item.status == "warning" for item in result.stages) else "verified"
            )
            durable_state.update(
                {
                    "last_verified_release_id": result.release_id,
                    "last_verified_run_id": result.run_id,
                    "last_verified_at": utc_now().isoformat(),
                    "last_verified_data_through": result.data_through,
                    "last_verified_statistics": statistical.snapshot,
                }
            )
            save_state(durable_state)
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
