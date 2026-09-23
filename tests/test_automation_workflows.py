from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


def _workflow(name: str) -> tuple[dict, str]:
    path = ROOT / ".github" / "workflows" / name
    text = path.read_text(encoding="utf-8")
    return yaml.safe_load(text), text


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
    assert "workflow_dispatch" in workflow.get("on", workflow.get(True, {}))
    assert "id-token: write" in text
    assert "AZURE_CLIENT_ID" in text
    assert "AZURE_CLIENT_SECRET" not in text


def test_deploy_workflow_verifies_before_deploy_and_has_rollback() -> None:
    _, text = _workflow("weekly-release-deploy.yml")
    verify_index = text.index("Verify release again at deploy boundary")
    deploy_index = text.index("Deploy candidate revision")
    smoke_index = text.index("Verify live production contract")
    rollback_index = text.index("Restore previous production image after failure")
    assert verify_index < deploy_index < smoke_index < rollback_index
    assert "PREVIOUS_IMAGE" in text
    assert "CANDIDATE_DIGEST" in text
    assert "${RELEASE_ID}-${sha}" in text
    assert "metrik-api:latest" not in text


def test_workflows_never_echo_notification_secrets() -> None:
    for name in ("weekly-release-deploy.yml", "groundtruth-weekly-control.yml"):
        _, text = _workflow(name)
        assert "set -x" not in text
        assert "echo $TELEGRAM_BOT_TOKEN" not in text
        assert "client-secret:" not in text
