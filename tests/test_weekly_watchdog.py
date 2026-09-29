import json
import os
import shutil
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
WATCHDOG = ROOT / ".github" / "workflows" / "groundtruth-weekly-watchdog.yml"

FAKE_GH = """#!/usr/bin/env bash
case "$*" in
  *"/jobs"*) printf '%s' "$FAKE_JOB" ;;
  *) printf '%s' "$FAKE_RUN" ;;
esac
"""


def _workflow() -> dict:
    return yaml.safe_load(WATCHDOG.read_text(encoding="utf-8"))


def _run(minutes_ago: int, status: str, conclusion: str | None = None) -> dict:
    created = datetime.now(UTC) - timedelta(minutes=minutes_ago)
    return {
        "id": 7,
        "html_url": "https://github.com/o/r/actions/runs/7",
        "status": status,
        "conclusion": conclusion,
        "created_at": created.strftime("%Y-%m-%dT%H:%M:%SZ"),
    }


def _job(runner: str | None, failed_step: str | None = None) -> dict:
    steps = [{"name": failed_step, "conclusion": "failure"}] if failed_step else []
    return {"name": "research", "runner_name": runner, "steps": steps}


def test_watchdog_runs_on_github_hosted_runner_with_read_only_token() -> None:
    workflow = _workflow()
    assert workflow["permissions"] == {"actions": "read"}
    assert workflow["jobs"]["check"]["runs-on"] == "ubuntu-latest"
    text = WATCHDOG.read_text(encoding="utf-8")
    assert "groundtruth-weekly-local.yml/runs" in text
    assert "set -x" not in text


@pytest.mark.skipif(sys.platform == "win32" or not shutil.which("jq"), reason="needs bash and jq")
@pytest.mark.parametrize(
    ("run", "job", "state", "detail"),
    [
        (None, None, "not_created", "No weekly research run"),
        (_run(300, "completed", "success"), _job("host"), "ok", "succeeded"),
        (
            _run(300, "completed", "failure"),
            _job("host", "Run canonical weekly release"),
            "workflow_failed",
            "at step: Run canonical weekly release",
        ),
        (_run(120, "queued"), _job(None), "runner_offline", "no runner has picked it up"),
        (_run(1500, "completed", "cancelled"), _job(None), "runner_offline", "without any runner"),
        (_run(10, "queued"), _job(None), "ok", "within the 45-minute allowance"),
        (_run(120, "pending"), None, "blocked", "concurrency group"),
        (_run(120, "in_progress"), _job("host"), "ok", "running on host"),
    ],
)
def test_watchdog_classifies_runs(
    tmp_path: Path, run: dict | None, job: dict | None, state: str, detail: str
) -> None:
    script = _workflow()["jobs"]["check"]["steps"][0]["run"]
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    gh = bin_dir / "gh"
    gh.write_text(FAKE_GH, encoding="utf-8")
    gh.chmod(0o755)
    output = tmp_path / "output"
    env = {
        **os.environ,
        "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}",
        "GITHUB_OUTPUT": str(output),
        "GITHUB_STEP_SUMMARY": str(tmp_path / "summary"),
        "GITHUB_REPOSITORY": "o/r",
        "MAX_QUEUE_MINUTES": "45",
        "LOOKBACK_HOURS": "20",
        "FAKE_RUN": json.dumps(run) if run else "",
        "FAKE_JOB": json.dumps(job) if job else "",
    }

    subprocess.run(["bash", "-c", script], env=env, check=True, capture_output=True)

    outputs = dict(line.split("=", 1) for line in output.read_text().splitlines())
    assert outputs["state"] == state
    assert detail in outputs["detail"]
