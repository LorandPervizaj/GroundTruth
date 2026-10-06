from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_PATH = ROOT / ".github" / "workflows" / "k6.yml"
SCRIPT_PATH = ROOT / "tests" / "load" / "k6_public_api.js"


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
    assert "postgis/postgis:16-3.4" == job["services"]["postgres"]["image"]

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
