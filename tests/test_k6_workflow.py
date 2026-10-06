import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_PATH = ROOT / ".github" / "workflows" / "k6.yml"
SCRIPT_PATH = ROOT / "tests" / "load" / "k6_public_api.js"
WRAPPER_PATH = ROOT / "scripts" / "performance" / "k6.ps1"
TARGET_PATH = ROOT / "scripts" / "performance" / "start-local-test-target.ps1"
COMPOSE_PATH = ROOT / "docker-compose.yml"


def _workflow() -> tuple[dict, str]:
    text = WORKFLOW_PATH.read_text(encoding="utf-8")
    return yaml.safe_load(text), text


def _triggers(workflow: dict) -> dict:
    # PyYAML reads the bare key `on` as boolean True.
    triggers = workflow.get("on", workflow.get(True))
    return triggers if isinstance(triggers, dict) else {name: None for name in triggers}


def test_k6_workflow_runs_on_safe_local_target() -> None:
    workflow, text = _workflow()
    triggers = _triggers(workflow)

    assert {"pull_request", "push", "schedule", "workflow_dispatch"} <= set(triggers)
    assert workflow["permissions"] == {"contents": "read"}

    job = workflow["jobs"]["performance"]
    assert job["runs-on"] == "ubuntu-latest"
    assert job["env"]["BASE_URL"] == "http://127.0.0.1:8000"
    assert job["services"]["postgres"]["image"] == "postgis/postgis:16-3.4"

    assert "azurecontainerapps.io" not in text
    assert "GROUNDTRUTH_GITHUB_TOKEN" not in text


def test_k6_workflow_pins_k6_and_runs_the_public_read_suite() -> None:
    workflow, _ = _workflow()
    steps = workflow["jobs"]["performance"]["steps"]

    install = next(step for step in steps if step.get("name") == "Install k6")
    assert install["uses"] == "grafana/setup-k6-action@v1.2.1"
    assert install["with"]["k6-version"] == "2.3.0"

    run = next(step for step in steps if step.get("name") == "Run k6 public-read suite")
    assert "tests/load/k6_public_api.js" in run["run"]
    assert 'K6_PROFILE="$K6_PROFILE"' in run["run"]
    assert "--summary-export" in run["run"]


def test_k6_workflow_reruns_when_local_tooling_changes() -> None:
    workflow, _ = _workflow()
    triggers = _triggers(workflow)
    for event in ("pull_request", "push"):
        paths = triggers[event]["paths"]
        assert "scripts/performance/**" in paths
        assert "tests/load/**" in paths


def test_k6_script_covers_representative_cached_reads_and_thresholds() -> None:
    text = SCRIPT_PATH.read_text(encoding="utf-8")

    for path in (
        "/api/health",
        "/api/meta",
        "/api/markets",
        "/api/lookup/neighborhood/ulpiana",
        "/",
    ):
        assert path in text

    assert 'checks: ["rate>0.99"]' in text
    assert 'http_req_failed: ["rate<0.01"]' in text
    assert '"p(95)<750"' in text
    assert '"p(99)<1500"' in text


def test_k6_script_does_not_load_write_endpoints() -> None:
    text = SCRIPT_PATH.read_text(encoding="utf-8")
    for path in ("/api/valuate", "/api/contact", "/api/feedback", "/api/events", "/api/alerts"):
        assert path not in text
    assert '"POST"' not in text


def test_perf_database_is_disposable_and_separate_from_research() -> None:
    compose = yaml.safe_load(COMPOSE_PATH.read_text(encoding="utf-8"))
    perf = compose["services"]["postgres-perf"]

    assert perf["profiles"] == ["perf"]
    assert perf["tmpfs"] == ["/var/lib/postgresql/data"]
    assert "volumes" not in perf
    assert perf["ports"] == ["127.0.0.1:15434:5432"]
    assert perf["environment"]["POSTGRES_DB"] == "groundtruth_perf"
    assert perf["container_name"] != compose["services"]["postgres"]["container_name"]


def test_local_target_never_uses_research_configuration() -> None:
    text = TARGET_PATH.read_text(encoding="utf-8")

    assert "@127.0.0.1:15434/$Database" in text
    assert "GROUNDTRUTH_ENV_FILE   = ''" in text
    assert "15432" not in text
    assert "MetrikResearch" not in text
    assert "postgres-perf" in text


def test_k6_results_directory_is_gitignored() -> None:
    wrapper = WRAPPER_PATH.read_text(encoding="utf-8")
    gitignore = (ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()

    assert "'.tmp\\k6'" in wrapper
    assert ".tmp/" in gitignore


def _run_wrapper(*args: str) -> subprocess.CompletedProcess[str]:
    pwsh = shutil.which("pwsh")
    if pwsh is None:
        pytest.skip("PowerShell 7 (pwsh) is not installed")
    return subprocess.run(
        [pwsh, "-NoProfile", "-NonInteractive", "-File", str(WRAPPER_PATH), "smoke", *args],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )


@pytest.mark.parametrize(
    ("args", "message"),
    [
        (("-BaseUrl", "http://example.com"), "non-local host"),
        (("-BaseUrl", "https://ca-metrik-api.example.azurecontainerapps.io"), "non-local host"),
        (
            ("-BaseUrl", "https://ca-metrik-api.example.azurecontainerapps.io", "-AllowRemote"),
            "Azure production",
        ),
        (("-BaseUrl", "ftp://127.0.0.1"), "absolute http(s) URL"),
    ],
)
def test_k6_wrapper_refuses_unsafe_targets(args: tuple[str, ...], message: str) -> None:
    result = _run_wrapper(*args)

    assert result.returncode == 2
    assert message in result.stdout + result.stderr
