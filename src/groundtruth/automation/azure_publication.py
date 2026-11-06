"""Publish a verified data bundle and dispatch the existing Azure workflow."""

from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path

from groundtruth.automation.deployment_source import production_preflight
from groundtruth.automation.publication import verify_run_result
from groundtruth.claims.hashes import sha256_file
from groundtruth.config import PROJECT_ROOT

REPOSITORY = "LorandPervizaj/GroundTruth"
WORKFLOW = "weekly-release-deploy.yml"


def gh(*args: str) -> str:
    result = subprocess.run(
        ["gh", *args], cwd=PROJECT_ROOT, capture_output=True, text=True, timeout=1800
    )
    if result.returncode:
        # Do not echo subprocess output, which can contain credentials.
        raise RuntimeError(f"GitHub operation failed: {args[0]}; exit {result.returncode}")
    return result.stdout.strip()


def require_publication_enabled() -> None:
    """Both repository and protected-environment gates must explicitly allow writes."""
    from groundtruth.automation.deployment import require

    for scope, name in (
        ("actions/variables", "METRIK_PUBLICATION_ENABLED"),
        ("environments/azure-beta/variables", "METRIK_ENV_PUBLICATION_ENABLED"),
    ):
        row = json.loads(gh("api", f"repos/{REPOSITORY}/{scope}/{name}"))
        require(
            isinstance(row, dict) and row.get("value") == "true",
            "Publication is disabled by the operator gate",
        )


def publish_and_dispatch(
    result_path: Path,
    release_dir: Path,
    *,
    approval_path: Path | None = None,
    approval_sha256: str | None = None,
) -> dict:
    """Publish only against an explicit reviewed source/tooling approval.

    All remote reads and compatibility checks precede any release/tag mutation.
    The data release tag identifies research provenance; serving code is an
    independent immutable workflow input. No master/default-branch fallback.
    """
    import base64
    import hashlib

    from groundtruth.automation.deployment import require
    from groundtruth.automation.deployment_source import load_approval

    require(
        approval_path is not None and bool(approval_sha256),
        "Explicit reviewed publication approval required",
    )
    approval = load_approval(approval_path, approval_sha256)
    require(bool(approval.tooling_ref), "Explicit reviewed workflow branch/tag required")
    require_publication_enabled()
    candidate = verify_run_result(result_path, release_dir)
    require(
        candidate.release_id == approval.release_id
        and candidate.source_git_sha == approval.data_source_sha
        and candidate.sha256 == approval.bundle_sha256,
        "Approved data release/target differs",
    )
    policy_root = Path(__file__).resolve().parents[3]
    policy = json.loads((policy_root / "deploy/production-policy.json").read_text())

    def commit(sha, tree):
        row = json.loads(gh("api", f"repos/{REPOSITORY}/git/commits/{sha}"))
        require(
            row.get("sha") == sha and row.get("tree", {}).get("sha") == tree,
            "Reviewed commit/tree identity differs",
        )

    def content(path, sha):
        row = json.loads(gh("api", f"repos/{REPOSITORY}/contents/{path}?ref={sha}"))
        require(row.get("encoding") == "base64", "Reviewed source unavailable")
        return base64.b64decode(row["content"]).replace(b"\r\n", b"\n")

    commit(approval.serving_sha, approval.serving_tree)
    commit(approval.tooling_sha, approval.tooling_tree)
    from urllib.parse import quote

    def verify_workflow_ref():
        row = json.loads(
            gh("api", f"repos/{REPOSITORY}/commits/{quote(approval.tooling_ref, safe='')}")
        )
        require(
            row.get("sha") == approval.tooling_sha, "Workflow ref moved from reviewed tooling SHA"
        )

    verify_workflow_ref()
    compare = json.loads(
        gh(
            "api",
            f"repos/{REPOSITORY}/compare/{policy['minimum_serving_sha']}...{approval.serving_sha}",
        )
    )
    require(
        compare.get("status") in {"ahead", "identical"}, "Serving revision would regress production"
    )
    for name, digest in policy["protected_files"].items():
        require(
            hashlib.sha256(content(name, approval.serving_sha)).hexdigest() == digest,
            f"Unsupported backend/startup/artifact interface: {name}",
        )
    require(
        b'"/api/deployment"' in content("src/groundtruth/api/app.py", approval.serving_sha),
        "Missing candidate identity interface",
    )
    # Tooling must equal the locally reviewed bytes, not an old or mutable workflow.
    for name in [
        ".github/workflows/weekly-release-deploy.yml",
        "scripts/azure/safe_deploy.py",
        "scripts/azure/make_approval.py",
        "scripts/release/install-verified-release.sh",
        "scripts/azure/cache_guard.template.py.txt",
        "deploy/production-policy.json",
        "src/groundtruth/automation/deployment.py",
        "src/groundtruth/automation/deployment_source.py",
        "src/groundtruth/automation/deployment_smoke.py",
    ]:
        require(
            content(name, approval.tooling_sha)
            == (policy_root / name).read_bytes().replace(b"\r\n", b"\n"),
            f"Unreviewed deployment tooling: {name}",
        )
    # The data target must exist before release creation. It is not the serving SHA.
    row = json.loads(gh("api", f"repos/{REPOSITORY}/commits/{approval.data_source_sha}"))
    require(row.get("sha") == approval.data_source_sha, "Invalid release target/data source")
    production_preflight(policy, approval.expected_state)
    releases = json.loads(
        gh("api", "--paginate", "--slurp", f"repos/{REPOSITORY}/releases?per_page=100")
    )
    existing = next(
        (r for page in releases for r in page if r["tag_name"] == candidate.release_tag), None
    )
    if existing is None:
        refs = json.loads(
            gh("api", f"repos/{REPOSITORY}/git/matching-refs/tags/{candidate.release_tag}")
        )
        require(
            not any(r["ref"] == f"refs/tags/{candidate.release_tag}" for r in refs),
            "Tag already exists without release",
        )
        with tempfile.TemporaryDirectory() as folder:
            notes = Path(folder) / "notes.md"
            notes.write_text(
                f"DATA_SOURCE_SHA: {approval.data_source_sha}\nSERVING_SOURCE_SHA: {approval.serving_sha}\nDATA_RELEASE_ID: {approval.release_id}\nBundle SHA256: {candidate.sha256}\n",
                encoding="utf-8",
            )
            gh(
                "release",
                "create",
                candidate.release_tag,
                str(candidate.bundle),
                str(candidate.checksum),
                "--repo",
                REPOSITORY,
                "--target",
                approval.data_source_sha,
                "--draft",
                "--title",
                candidate.release_tag,
                "--notes-file",
                str(notes),
            )
    remote = json.loads(
        gh(
            "release",
            "view",
            candidate.release_tag,
            "--repo",
            REPOSITORY,
            "--json",
            "assets,isDraft,url,targetCommitish",
        )
    )
    require(
        {a["name"] for a in remote["assets"]} == {candidate.bundle.name, candidate.checksum.name},
        "Release assets differ",
    )
    # Resolve annotated/lightweight tag commit; targetCommitish may be a branch label.
    tag = json.loads(gh("api", f"repos/{REPOSITORY}/commits/{candidate.release_tag}"))
    require(tag.get("sha") == approval.data_source_sha, "Invalid data release target")
    with tempfile.TemporaryDirectory() as folder:
        gh("release", "download", candidate.release_tag, "--repo", REPOSITORY, "--dir", folder)
        require(
            sha256_file(Path(folder) / candidate.bundle.name) == candidate.sha256,
            "Uploaded bundle checksum differs",
        )
        require(
            (Path(folder) / candidate.checksum.name).read_bytes()
            == candidate.checksum.read_bytes(),
            "Uploaded checksum differs",
        )
    if remote["isDraft"]:
        gh("release", "edit", candidate.release_tag, "--repo", REPOSITORY, "--draft=false")
    verify_workflow_ref()
    gh(
        "workflow",
        "run",
        WORKFLOW,
        "--repo",
        REPOSITORY,
        "--ref",
        approval.tooling_ref,
        "-f",
        f"tooling_source_sha={approval.tooling_sha}",
        "-f",
        f"tooling_tree_sha={approval.tooling_tree}",
        "-f",
        f"release_tag={candidate.release_tag}",
        "-f",
        f"serving_source_sha={approval.serving_sha}",
        "-f",
        f"serving_tree_sha={approval.serving_tree}",
        "-f",
        f"expected_state={approval.expected_state}",
        "-f",
        "approve_deployment=true",
    )
    return {
        "status": "deployment_requested",
        "release_tag": candidate.release_tag,
        "release_url": remote["url"],
        "serving_git_sha": approval.serving_sha,
        "data_source_sha": approval.data_source_sha,
        "tooling_sha": approval.tooling_sha,
        "bundle_sha256": candidate.sha256,
    }
