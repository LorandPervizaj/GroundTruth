"""Source, worker identity and shell compatibility acceptance boundaries."""

import json
import os
import shutil
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest
from starlette.requests import Request

from groundtruth.automation import deployment_source

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("fault", ["sha", "tree", "dirty", "ancestor", "backend", "identity"])
def test_source_contract_rejects_review_mismatch(tmp_path, monkeypatch, fault):
    policy = {
        "minimum_serving_sha": "a" * 40,
        "protected_files": {"config.py": __import__("hashlib").sha256(b"azure_table").hexdigest()},
    }
    (tmp_path / "config.py").write_text("database" if fault == "backend" else "azure_table")
    app = tmp_path / "src/groundtruth/api/app.py"
    app.parent.mkdir(parents=True)
    app.write_text(
        '"/api/deployment" cache_guard_verified' if fault != "identity" else '"/api/meta"'
    )

    def git(root, *args):
        if args[0] == "merge-base":
            if fault == "ancestor":
                raise ValueError("Not descended from live runtime")
            return ""
        if args[0] == "status":
            return "M config.py" if fault == "dirty" else ""
        return (
            ("0" * 40)
            if fault == ("tree" if "tree" in args[-1] else "sha")
            else ("c" * 40 if "tree" in args[-1] else "b" * 40)
        )

    monkeypatch.setattr(deployment_source, "git", git)
    with pytest.raises(ValueError):
        deployment_source.verify_source(tmp_path, policy, "b" * 40, "c" * 40)


@pytest.mark.parametrize("guard_ok,ready_ok", [(True, True), (False, True), (True, False)])
def test_authenticated_worker_identity_preserves_guard_and_table_health(
    monkeypatch, guard_ok, ready_ok
):
    from groundtruth.api import app as module
    from groundtruth.services import artifact_integrity, readiness

    revision = "ca-metrik-api--candidate"
    monkeypatch.setenv("CONTAINER_APP_REVISION", revision)
    monkeypatch.setenv("METRIK_DEPLOY_SOURCE_SHA", "a" * 40)
    monkeypatch.setenv("METRIK_DEPLOY_DATA_RELEASE_ID", "new-release")
    monkeypatch.setenv("METRIK_DEPLOY_IMAGE", "registry/repo@sha256:" + "1" * 64)
    monkeypatch.setattr(module, "require_ops_access", lambda request: None)
    monkeypatch.setattr(
        module, "get_settings", lambda: SimpleNamespace(product_write_backend="azure_table")
    )
    monkeypatch.setattr(readiness, "evaluate_readiness", lambda settings: {"ok": ready_ok})
    monkeypatch.setattr(
        artifact_integrity, "get_artifact_integrity_state", lambda: SimpleNamespace(verified=True)
    )
    monkeypatch.setattr(
        Path,
        "read_text",
        lambda *a, **k: json.dumps(
            {
                "revision": revision if guard_ok else "old",
                "source_instance_excluded": True,
                "tables_after": 21,
                "head": "h2i3j4k5l6m7",
            }
        ),
    )
    result = module.deployment_identity(Request({"type": "http", "headers": []}))
    assert result.status_code == (200 if guard_ok and ready_ok else 503)
    payload = json.loads(result.body)
    assert payload["revision"] == revision and payload["backend"] == "azure_table"
    assert result.headers["cache-control"] == "no-store"


def test_legacy_bash_false_positive_is_rejected(tmp_path):
    bash = shutil.which("bash")
    if os.name == "nt":
        bash = str(Path.home() / "AppData/Local/Programs/Git/bin/bash.exe")
    if not bash or not Path(bash).exists():
        pytest.skip("Bash unavailable")
    # Reuse the audit scenario: ready candidate, old worker returns the same ID.
    harness = tmp_path / "scenario.sh"
    harness.write_text(
        """az() { echo candidate; }
curl() { echo '{"release_id":"same-data-release"}'; }
export WAIT_ATTEMPTS=1 WAIT_DELAY_SECONDS=0
source scripts/azure/wait-for-revision.sh group app candidate same-data-release
""",
        newline="\n",
    )
    result = subprocess.run(
        [bash, str(harness).replace("\\", "/")],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert result.returncode == 2
    assert "Readiness cannot establish" in result.stderr


def test_workflow_inputs_have_no_silent_defaults():
    import yaml

    workflow = yaml.safe_load((ROOT / ".github/workflows/weekly-release-deploy.yml").read_text())
    triggers = workflow.get("on", workflow.get(True))
    for trigger in ("workflow_dispatch", "workflow_call"):
        for field in ("serving_source_sha", "serving_tree_sha", "expected_state", "release_tag"):
            assert triggers[trigger]["inputs"][field]["required"] is True
    assert workflow["concurrency"]["cancel-in-progress"] is False
    assert "inputs.approve_deployment" in workflow["jobs"]["deploy"]["if"]


def test_guard_generator_changes_only_approved_revision_binding():
    import base64
    import re
    import zlib

    from groundtruth.automation.deployment import cache_guard

    policy = json.loads((ROOT / "deploy/production-policy.json").read_text())
    policy["guard_source"] = (ROOT / "scripts/azure/cache_guard.template.py.txt").read_text()
    command = cache_guard(policy, "ca-metrik-api--new")
    value = re.search(r"b64decode\('([^']+)'\)", command[-1])[1]
    code = zlib.decompress(base64.b64decode(value)).decode()
    assert "'revision': 'ca-metrik-api--new'" in code
    assert "verified_empty_before_alembic" in code and "SQL must never hold submissions" in code
    assert policy["cache_expected"]["forbidden_source_system"] in code
    policy["guard_source"] += "# changed"
    with pytest.raises(ValueError, match="source differs"):
        cache_guard(policy, "ca-metrik-api--new")


def test_pulled_registry_digest_mismatch_is_rejected(monkeypatch):
    """Exercise the real Docker adapter, with only CLI transport mocked."""
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "publication_cli", ROOT / "scripts/azure/safe_deploy.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    expected = "registry.example/metrik@sha256:" + "1" * 64
    wrong = "registry.example/metrik@sha256:" + "2" * 64

    def run(*args):
        if args[1] == "pull":
            return ""
        return json.dumps([{"RepoDigests": [wrong], "Config": {"Labels": {}}}])

    monkeypatch.setattr(module, "run", run)
    with pytest.raises(ValueError, match="digest differs"):
        module.Azure({"app_name": "ca-metrik-api", "resource_group": "example"}).inspect_image(
            expected
        )
