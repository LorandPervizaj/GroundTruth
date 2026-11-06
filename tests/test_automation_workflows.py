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
    assert deploy["with"]["release_tag"] == "${{ needs.research.outputs.release_tag }}"
    assert deploy["with"]["serving_source_sha"] == "${{ inputs.serving_source_sha }}"
    assert deploy["with"]["expected_state"] == "${{ inputs.expected_state }}"
    assert _triggers(workflow)["workflow_dispatch"]["inputs"]["deploy"]["default"] is False
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
        "Validate immutable approval inputs",
        "Verify exact data bundle and independent source approval",
        "Install verified data into serving build context",
        "Verify approved baseline before build",
        "Build and verify reviewed serving image",
        "Trivy release gate",
        "Push and prove immutable build identity",
        "Capture deploy validate promote and verify with guarded rollback",
    ]
    indexes = [_step_index(steps, name) for name in order]
    assert indexes == sorted(indexes)
    assert '"$CANDIDATE_IMAGE_DIGEST"' in text
    assert "--revision-weight" not in text  # one tested state-machine owns mutation
    assert "safe_deploy.py apply" in text
    assert "METRIK_DEPLOY_ENABLED" in workflow["jobs"]["deploy"]["if"]
    assert "METRIK_OPERATOR_WINDOW" in workflow["jobs"]["deploy"]["if"]


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


def test_code_deploys_require_an_exact_reviewed_data_release() -> None:
    workflow, text = _workflow("azure-beta-deploy.yml")
    assert set(_triggers(workflow)) == {"workflow_dispatch"}
    assert (
        _triggers(workflow)["workflow_dispatch"]["inputs"]["data_release_tag"]["required"] is True
    )
    assert workflow["jobs"]["deploy"]["uses"] == "./.github/workflows/weekly-release-deploy.yml"
    assert "steps" not in workflow["jobs"]["deploy"]
    assert "az containerapp" not in text
    deploy, _ = _workflow(DEPLOY)
    assert deploy["concurrency"] == {
        "group": "metrik-ca-metrik-api-production",
        "cancel-in-progress": False,
    }


def test_ready_is_not_treated_as_promotion() -> None:
    script = (ROOT / "scripts/azure/wait-for-revision.sh").read_text()
    assert "latestReadyRevisionName" not in script
    assert "promotion_verified=false" in script
    assert "exit 2" in script  # legacy shared-ingress identity shortcut is rejected
    workflow, _ = _workflow(DEPLOY)
    steps = workflow["jobs"]["deploy"]["steps"]
    checkouts = [step for step in steps if step.get("uses", "").startswith("actions/checkout")]
    assert checkouts[0]["with"]["ref"] == "${{ inputs.tooling_source_sha }}"
    assert checkouts[1]["with"]["ref"] == "${{ inputs.serving_source_sha }}"
    assert all(step["with"]["ref"] != "refs/tags/${{ inputs.release_tag }}" for step in checkouts)


def test_smoke_script_runs_on_linux_runners() -> None:
    script = (ROOT / "scripts" / "azure" / "smoke.ps1").read_text(encoding="utf-8")
    assert "$env:TEMP" not in script
    assert "curl.exe -" not in script
    assert "-o NUL" not in script


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


def test_telegram_steps_never_block_research_or_deployment() -> None:
    for name in (DEPLOY, RESEARCH, "groundtruth-weekly-watchdog.yml"):
        workflow, _ = _workflow(name)
        for job in workflow["jobs"].values():
            for step in job.get("steps", []):
                if "telegram" in step.get("name", "").lower():
                    assert step.get("continue-on-error") is True, f"{name}: {step['name']}"


def test_publication_is_default_off_and_requires_environment_review():
    workflow, text = _workflow(RESEARCH)
    assert _triggers(workflow)["workflow_dispatch"]["inputs"]["publish"]["default"] is False
    research = workflow["jobs"]["research"]
    assert research["environment"] == "azure-beta"
    publish = research["steps"][_step_index(research["steps"], "Publish immutable GitHub release")]
    assert "inputs.publish" in publish["if"]
    assert "vars.METRIK_PUBLICATION_ENABLED == 'true'" in publish["if"]


def test_deployment_requires_distinct_repository_and_environment_gates():
    workflow, text = _workflow(DEPLOY)
    job = workflow["jobs"]["deploy"]
    assert "vars.METRIK_DEPLOY_ENABLED == 'true'" in job["if"]
    assert job["env"]["METRIK_DEPLOY_ENABLED"] == "${{ vars.METRIK_ENV_DEPLOY_ENABLED }}"
    assert job["env"]["METRIK_OPERATOR_WINDOW"] == "${{ vars.METRIK_ENV_OPERATOR_WINDOW }}"
    assert 'test "$METRIK_DEPLOY_ENABLED" = true' in text
    assert 'test "$METRIK_OPERATOR_WINDOW" = exclusive' in text
