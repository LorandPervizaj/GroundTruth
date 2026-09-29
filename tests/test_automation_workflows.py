import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".github" / "workflows"
RESEARCH = "groundtruth-weekly-local.yml"
DEPLOY = "weekly-release-deploy.yml"
RESEARCH_LABELS = ["self-hosted", "Windows", "X64", "groundtruth-research"]


def _workflow(name: str) -> tuple[dict, str]:
    path = WORKFLOWS / name
    text = path.read_text(encoding="utf-8")
    return yaml.safe_load(text), text


def _triggers(workflow: dict) -> dict:
    # PyYAML reads the bare key `on` as boolean True.
    triggers = workflow.get("on", workflow.get(True))
    return triggers if isinstance(triggers, dict) else {name: None for name in triggers}


def _step_index(steps: list[dict], name: str) -> int:
    return next(i for i, step in enumerate(steps) if step.get("name") == name)


def test_research_schedule_is_monday_and_single_replica() -> None:
    bicep = (ROOT / "infra" / "azure" / "research.bicep").read_text(encoding="utf-8")
    assert "param cronExpression string = '0 3 * * 1'" in bicep
    assert "parallelism: 1" in bicep
    assert "replicaCompletionCount: 1" in bicep
    assert "replicaRetryLimit: 1" in bicep
    assert "storageType: 'AzureFile'" in bicep
    assert "storageType: 'EmptyDir'" not in bicep


def test_manual_control_uses_oidc_and_no_client_secret() -> None:
    workflow, text = _workflow("groundtruth-weekly-control.yml")
    assert "workflow_dispatch" in _triggers(workflow)
    assert "id-token: write" in text
    assert "AZURE_CLIENT_ID" in text
    assert "AZURE_CLIENT_SECRET" not in text


def test_research_workflow_runs_only_on_the_dedicated_runner() -> None:
    workflow, _ = _workflow(RESEARCH)
    assert workflow["jobs"]["research"]["runs-on"] == RESEARCH_LABELS
    assert workflow["jobs"]["research"]["if"] == "${{ github.ref == 'refs/heads/master' }}"
    for name, job in workflow["jobs"].items():
        if name != "research":
            assert "groundtruth-research" not in str(job.get("runs-on", ""))


def test_self_hosted_workflows_cannot_run_fork_code() -> None:
    for path in WORKFLOWS.glob("*.yml"):
        workflow = yaml.safe_load(path.read_text(encoding="utf-8"))
        runners = [str(job.get("runs-on", "")) for job in workflow["jobs"].values()]
        if any("self-hosted" in runner for runner in runners):
            assert set(_triggers(workflow)) <= {"workflow_dispatch", "schedule"}, path.name


def test_research_workflow_pins_actions_to_commits() -> None:
    workflow, _ = _workflow(RESEARCH)
    for step in workflow["jobs"]["research"]["steps"]:
        if "uses" in step:
            _, _, ref = step["uses"].partition("@")
            assert re.fullmatch(r"[0-9a-f]{40}", ref), step["uses"]


def test_research_workflow_allows_one_run_at_a_time() -> None:
    workflow, _ = _workflow(RESEARCH)
    assert workflow["concurrency"] == {"group": "groundtruth-weekly", "cancel-in-progress": False}
    assert workflow["permissions"] == {"contents": "read"}
    assert workflow["jobs"]["research"]["permissions"] == {"contents": "write"}


def test_research_workflow_delegates_to_the_canonical_command() -> None:
    _, text = _workflow(RESEARCH)
    assert text.count("'pipeline', 'weekly-release'") == 1
    for rebuilt in ("groundtruth crawl", "groundtruth etl", "release build-artifacts", "scrapy"):
        assert rebuilt not in text


def test_research_workflow_verifies_before_publishing() -> None:
    workflow, _ = _workflow(RESEARCH)
    steps = workflow["jobs"]["research"]["steps"]
    order = [
        "Install locked research environment",
        "Research doctor",
        "Back up research database before the run",
        "Run canonical weekly release",
        "Verify publication candidate",
        "Publish immutable GitHub release",
    ]
    indexes = [_step_index(steps, name) for name in order]
    assert indexes == sorted(indexes)
    assert "--expected-sha" in steps[indexes[1]]["run"]


def test_only_the_verified_bundle_and_checksum_are_published() -> None:
    workflow, _ = _workflow(RESEARCH)
    steps = workflow["jobs"]["research"]["steps"]
    publish = steps[_step_index(steps, "Publish immutable GitHub release")]
    create = next(line for line in publish["run"].splitlines() if "gh release create" in line)
    assert "$env:RELEASE_TAG $env:BUNDLE $env:CHECKSUM --repo" in create
    assert "--clobber" not in publish["run"]
    assert "already exists" in publish["run"]
    assert publish["env"]["BUNDLE"] == "${{ steps.candidate.outputs.bundle }}"
    assert publish["env"]["CHECKSUM"] == "${{ steps.candidate.outputs.checksum }}"


def test_deployment_receives_the_exact_release_tag() -> None:
    workflow, _ = _workflow(RESEARCH)
    deploy = workflow["jobs"]["deploy"]
    assert deploy["needs"] == "research"
    assert deploy["uses"] == f"./.github/workflows/{DEPLOY}"
    assert deploy["with"] == {"release_tag": "${{ needs.research.outputs.release_tag }}"}
    assert "needs.research.result == 'success'" in deploy["if"]
    outputs = workflow["jobs"]["research"]["outputs"]
    assert outputs["release_tag"] == "${{ steps.candidate.outputs.release_tag }}"


def test_deploy_workflow_has_no_schedule_and_requires_a_tag() -> None:
    workflow, text = _workflow(DEPLOY)
    triggers = _triggers(workflow)
    assert set(triggers) == {"workflow_call", "workflow_dispatch"}
    for trigger in triggers.values():
        assert trigger["inputs"]["release_tag"]["required"] is True
    assert "sort_by" not in text
    assert "az storage" not in text
    assert "GROUNDTRUTH_STORAGE_ACCOUNT" not in text


def test_deploy_workflow_verifies_before_deploy_and_has_rollback() -> None:
    workflow, text = _workflow(DEPLOY)
    steps = workflow["jobs"]["deploy"]["steps"]
    order = [
        "Validate exact release tag",
        "Download and verify exact GitHub release",
        "Verify release again at deploy boundary",
        "Build immutable serving image",
        "Trivy scan",
        "Push immutable serving image",
        "Capture current production target",
        "Deploy candidate revision",
        "Verify live production contract",
        "Restore previous production image after failure",
        "Verify rollback",
    ]
    indexes = [_step_index(steps, name) for name in order]
    assert indexes == sorted(indexes)
    assert "find_spec('scrapy') is None" in text
    assert "PREVIOUS_IMAGE" in text
    assert "CANDIDATE_DIGEST" in text
    assert "${RELEASE_ID}-${sha}" in text
    assert "metrik-api:latest" not in text


def test_release_installer_verifies_before_installing() -> None:
    script = (ROOT / "scripts" / "release" / "install-verified-release.sh").read_text(
        encoding="utf-8"
    )
    checks = [
        "^groundtruth-release-",
        "must contain exactly",
        "sha256sum --check --strict",
        "groundtruth release verify-bundle",
        "rm -rf reports/generated/lookup_cache",
    ]
    indexes = [script.index(check) for check in checks]
    assert indexes == sorted(indexes)
    assert "releases/latest" not in script


def test_code_deploys_keep_the_live_data_release() -> None:
    workflow, text = _workflow("azure-beta-deploy.yml")
    steps = workflow["jobs"]["deploy"]["steps"]
    keep = _step_index(steps, "Keep the live verified data release")
    assert _step_index(steps, "Azure login") < keep
    assert keep < _step_index(steps, "Verify release artifacts")
    assert keep < _step_index(steps, "Build, scan tooling absence, push immutable tag")
    run = steps[keep]["run"]
    assert "/api/meta" in run
    assert "scripts/release/install-verified-release.sh" in run
    assert "releases/latest" not in text
    assert (
        _triggers(workflow)["workflow_dispatch"]["inputs"]["data_release_tag"]["required"] is False
    )
    assert 'grep -F "\\"$DATA_RELEASE_ID\\""' in text


def test_workflows_never_echo_notification_secrets() -> None:
    for name in (DEPLOY, RESEARCH, "groundtruth-weekly-control.yml"):
        _, text = _workflow(name)
        assert "set -x" not in text
        assert "echo $TELEGRAM_BOT_TOKEN" not in text
        assert "GROUNDTRUTH_GITHUB_TOKEN" not in text
        assert "client-secret:" not in text
        assert "research.env" not in text.replace(
            "GROUNDTRUTH_ENV_FILE: C:\\MetrikResearch\\config\\research.env", ""
        )
