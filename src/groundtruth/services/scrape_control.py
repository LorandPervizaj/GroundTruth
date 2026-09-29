"""Owner controls for the GroundTruth weekly research workflow.

Research runs on the local research host through a self-hosted GitHub runner.
The public app only dispatches, inspects, and cancels that one workflow, using
a fine-grained token restricted to this repository with Actions read/write.
It never reaches the research host or its database directly.
"""

from __future__ import annotations

import os
import re
from typing import Any

import httpx

from groundtruth.logging import get_logger

logger = get_logger(__name__)

_API = "https://api.github.com"
_ACTIVE = {"queued", "in_progress", "waiting", "requested", "pending"}
_DEFAULT_REPOSITORY = "LorandPervizaj/GroundTruth"
_DEFAULT_WORKFLOW = "groundtruth-weekly-local.yml"
_REF = "master"
_REPOSITORY_PATTERN = re.compile(r"[A-Za-z0-9-]+/[A-Za-z0-9._-]+")
_WORKFLOW_PATTERN = re.compile(r"[A-Za-z0-9._-]+\.ya?ml")


def scrape_snapshot() -> tuple[bool, str]:
    """Return whether a research run is active, plus a short owner message."""
    try:
        return _snapshot()
    except Exception:
        logger.exception("scrape_status_failed")
        return False, "Could not read the research workflow status."


def start_scrape() -> str:
    if not _configured():
        return _unconfigured()
    try:
        runs, error = _recent_runs()
        if error:
            return error
        active = _active(runs)
        if active:
            return (
                f"A research run is already {active[0].get('status')}.\n{_describe(active[0])}\n"
                "Send /scrape_stop to cancel it first."
            )
        response = _github(
            "POST",
            f"/repos/{_repository()}/actions/workflows/{_workflow()}/dispatches",
            json={"ref": _REF},
        )
    except httpx.HTTPError:
        logger.exception("scrape_start_unreachable")
        return "Could not reach GitHub to start the research workflow."
    if response.status_code == 204:
        return f"Research run requested on {_REF}.\nSend /scrape in a minute to follow it."
    logger.warning("scrape_start_failed", status=response.status_code)
    return f"Could not start the research workflow. GitHub returned {response.status_code}."


def stop_scrape() -> str:
    if not _configured():
        return _unconfigured()
    try:
        runs, error = _recent_runs()
        if error:
            return error
        active = _active(runs)
        if not active:
            return "No research run is active."
        cancelled: list[str] = []
        for run in active:
            response = _github("POST", f"/repos/{_repository()}/actions/runs/{run['id']}/cancel")
            if response.status_code != 202:
                logger.warning("scrape_stop_failed", status=response.status_code, run=run["id"])
                return f"Could not cancel run {run['id']}. GitHub returned {response.status_code}."
            cancelled.append(str(run["id"]))
    except httpx.HTTPError:
        logger.exception("scrape_stop_unreachable")
        return "Could not reach GitHub to cancel the research workflow."
    return "Cancellation requested for run " + ", ".join(cancelled) + "."


def _snapshot() -> tuple[bool, str]:
    if not _configured():
        return False, _unconfigured()
    runs, error = _recent_runs()
    if error:
        return False, error
    if not runs:
        return False, "No research run has been recorded yet."
    active = _active(runs)
    if active:
        return True, "Research is running.\n" + _describe(active[0])
    return False, "No research is running.\nLatest: " + _describe(runs[0])


def _active(runs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [run for run in runs if run.get("status") in _ACTIVE and run.get("id")]


def _describe(run: dict[str, Any]) -> str:
    state = run.get("conclusion") or run.get("status") or "unknown"
    started = run.get("run_started_at") or run.get("created_at") or "unknown time"
    return f"Run {run.get('id')}: {state}, started {started}\n{run.get('html_url', '')}".rstrip()


def _recent_runs() -> tuple[list[dict[str, Any]], str]:
    response = _github(
        "GET",
        f"/repos/{_repository()}/actions/workflows/{_workflow()}/runs",
        params={"per_page": 5},
    )
    if response.status_code != 200:
        logger.warning("scrape_runs_failed", status=response.status_code)
        return [], f"Could not list research runs. GitHub returned {response.status_code}."
    runs = response.json().get("workflow_runs") or []
    return [run for run in runs if isinstance(run, dict)], ""


def _configured() -> bool:
    return bool(
        os.getenv("GROUNDTRUTH_GITHUB_TOKEN", "").strip()
        and _REPOSITORY_PATTERN.fullmatch(_repository())
        and _WORKFLOW_PATTERN.fullmatch(_workflow())
    )


def _unconfigured() -> str:
    return (
        "The research workflow is not configured on this service, "
        "so the bot cannot see or start it."
    )


def _repository() -> str:
    return os.getenv("GROUNDTRUTH_GITHUB_REPOSITORY", "").strip() or _DEFAULT_REPOSITORY


def _workflow() -> str:
    return os.getenv("GROUNDTRUTH_GITHUB_WORKFLOW", "").strip() or _DEFAULT_WORKFLOW


def _github(
    method: str,
    path: str,
    *,
    params: dict[str, Any] | None = None,
    json: dict[str, Any] | None = None,
) -> httpx.Response:
    return httpx.request(
        method,
        f"{_API}{path}",
        params=params,
        json=json,
        headers={
            "Authorization": f"Bearer {os.environ['GROUNDTRUTH_GITHUB_TOKEN'].strip()}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "metrik-owner-bot",
        },
        timeout=20.0,
    )
