"""Verify exact reviewed serving source independently from data provenance."""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
from pathlib import Path

from groundtruth.automation.deployment import (
    Approval,
    compatible,
    fingerprint,
    require,
    stable_state,
)


def production_preflight(policy: dict, expected: str) -> None:
    """Read-only baseline check before creating or publishing a GitHub release."""

    def read(*args):
        result = subprocess.run(
            [
                shutil.which("az") or "az",
                "containerapp",
                *args,
                "-g",
                policy["resource_group"],
                "-n",
                policy["app_name"],
                "-o",
                "json",
            ],
            capture_output=True,
            text=True,
            timeout=60,
        )
        require(result.returncode == 0, "Production readback unavailable; publication forbidden")
        return json.loads(result.stdout)

    app = read("show")
    revisions = {r["name"]: r for r in read("revision", "list", "--all")}
    require(app["id"].lower() == policy["app_id"].lower(), "Wrong publication target")
    require(
        app["properties"]["configuration"]["activeRevisionsMode"] == "Multiple",
        "Wrong revision mode",
    )
    state = stable_state(app, revisions)
    require(fingerprint(state) == expected, "Production approval became stale before publication")
    for name, template in state["serving"].items():
        compatible(template, policy)
        require(
            revisions[name]["properties"].get("healthState") == "Healthy"
            and revisions[name]["properties"].get("active") is True,
            "Unhealthy publication baseline",
        )


def git(root: Path, *args: str) -> str:
    result = subprocess.run(["git", *args], cwd=root, capture_output=True, text=True, timeout=60)
    require(result.returncode == 0, "Source identity check failed")
    return result.stdout.strip()


def verify_source(root: Path, policy: dict, sha: str, tree: str) -> None:
    require(git(root, "rev-parse", "HEAD") == sha, "Incorrect checked-out serving SHA")
    require(git(root, "rev-parse", "HEAD^{tree}") == tree, "Reviewed serving tree mismatch")
    require(
        not git(root, "status", "--porcelain", "--untracked-files=all"),
        "Serving source has unreviewed tracked or untracked files",
    )
    git(root, "merge-base", "--is-ancestor", policy["minimum_serving_sha"], sha)
    for name, digest in policy["protected_files"].items():
        require(
            hashlib.sha256((root / name).read_bytes().replace(b"\r\n", b"\n")).hexdigest()
            == digest,
            f"Backend/startup/artifact contract changed: {name}",
        )
    # Candidate must implement authenticated worker identity, not just the old metadata endpoint.
    text = (root / "src/groundtruth/api/app.py").read_text()
    require(
        '"/api/deployment"' in text and "cache_guard_verified" in text,
        "Serving source lacks deployment identity interface",
    )


def load_approval(path: Path, expected_hash: str) -> Approval:
    raw = path.read_bytes()
    require(hashlib.sha256(raw).hexdigest() == expected_hash, "Reviewed approval bytes differ")
    approval = Approval(**json.loads(raw))
    approval.validate()
    return approval
