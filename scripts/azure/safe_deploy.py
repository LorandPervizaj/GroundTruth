"""Explicit maintenance-window deployment CLI; inspect/source/smoke never mutate Azure."""

from __future__ import annotations

import argparse
import base64
import json
import os
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

from groundtruth.automation.deployment import (
    Approval,
    Deployment,
    api_container,
    cache_guard,
    fingerprint,
    require,
    stable_state,
)
from groundtruth.automation.deployment_smoke import smoke
from groundtruth.automation.deployment_source import verify_source


def run(*args: str) -> str:
    command = [shutil.which(args[0]) or args[0], *args[1:]]
    result = subprocess.run(command, capture_output=True, text=True, timeout=180)
    # Never echo CLI stderr: it can include credentials or configuration values.
    require(result.returncode == 0, f"External {args[0]} command failed ({result.returncode})")
    return result.stdout.strip()


class Azure:
    def __init__(self, policy):
        self.policy = policy
        self.target = ("-g", policy["resource_group"], "-n", policy["app_name"])

    def app(self):
        return json.loads(run("az", "containerapp", "show", *self.target, "-o", "json"))

    def revisions(self):
        rows = json.loads(
            run("az", "containerapp", "revision", "list", *self.target, "--all", "-o", "json")
        )
        return {r["name"]: r for r in rows}

    def deploy(self, template):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "candidate.json"
            path.write_text(json.dumps({"properties": {"template": template}}))
            run("az", "containerapp", "update", *self.target, "--yaml", str(path), "-o", "none")

    def wait_ready(self, revision):
        for _ in range(60):
            value = json.loads(
                run(
                    "az",
                    "containerapp",
                    "revision",
                    "show",
                    *self.target,
                    "--revision",
                    revision,
                    "-o",
                    "json",
                )
            )
            p = value["properties"]
            require(
                p.get("provisioningState") != "Failed"
                and p.get("runningState") not in {"Failed", "Degraded"},
                "Candidate failed",
            )
            if p.get("healthState") == "Healthy" and p.get("active") is True and p.get("fqdn"):
                return value
            time.sleep(5)
        raise ValueError("Candidate readiness timed out; not promoted")

    def inspect_image(self, image):
        run("docker", "pull", image)
        config = json.loads(run("docker", "image", "inspect", image))[0]
        require(image in config.get("RepoDigests", []), "Pulled image digest differs")
        return config["Config"].get("Labels", {})

    def smoke(self, url, expected):
        smoke(url, expected, token=os.environ.get("METRIK_DEPLOY_HEALTH_TOKEN", ""))

    def previous_smoke(self, url, release):
        # The old runtime rejects revision-FQDN Host headers. Probe its loopback
        # inside the explicitly selected revision, never the shared ingress URL.
        from urllib.parse import urlparse

        revision = urlparse(url).hostname.split(".")[0]
        require(
            revision.startswith(self.policy["app_name"] + "--"), "Wrong rollback probe revision"
        )
        code = "import json,os,urllib.request\nvalues={}\n"
        code += "for path in ['/api/health','/api/ready','/api/meta']:\n with urllib.request.urlopen('http://127.0.0.1:8000'+path,timeout=20) as r: values[path]=json.load(r)\n"
        code += "print('METRIK_VERIFY_RESULT='+json.dumps({'revision':os.environ.get('CONTAINER_APP_REVISION'),'release_id':values['/api/meta'].get('release_id'),'ok':values['/api/ready'].get('ok'),'health':values['/api/health'].get('status')}))"
        encoded = base64.b64encode(code.encode()).decode()
        command = f"/app/.venv/bin/python -c \"import base64;exec(base64.b64decode('{encoded}'))\""
        output = run(
            "az",
            "containerapp",
            "exec",
            *self.target,
            "--revision",
            revision,
            "--container",
            "metrik-api",
            "--command",
            command,
        )
        lines = [
            s.split("METRIK_VERIFY_RESULT=", 1)[1].strip()
            for s in output.splitlines()
            if s.startswith("METRIK_VERIFY_RESULT=")
        ]
        require(len(lines) == 1, "Rollback worker probe unavailable; no traffic mutation")
        value = json.loads(lines[0])
        require(
            value == {"revision": revision, "release_id": release, "ok": True, "health": "ok"},
            "Rollback worker identity/readiness differs",
        )

    def set_traffic(self, traffic):
        weights = [f"{t['revisionName']}={t['weight']}" for t in traffic]
        run(
            "az",
            "containerapp",
            "ingress",
            "traffic",
            "set",
            *self.target,
            "--revision-weight",
            *weights,
            "-o",
            "none",
        )

    def deactivate(self, revision):
        run(
            "az",
            "containerapp",
            "revision",
            "deactivate",
            *self.target,
            "--revision",
            revision,
            "-o",
            "none",
        )


def policy_at(root):
    policy = json.loads((root / "deploy/production-policy.json").read_text())
    policy["guard_source"] = (root / "scripts/azure/cache_guard.template.py.txt").read_text()
    return policy


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=["inspect", "source", "smoke", "apply", "wait"])
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--source-root", type=Path)
    parser.add_argument("--approval", type=Path)
    parser.add_argument("--image")
    parser.add_argument("--revision")
    parser.add_argument("--url")
    parser.add_argument("--release-id")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    policy = policy_at(args.root)
    cloud = Azure(policy)
    if args.mode == "inspect":
        app, revisions = cloud.app(), cloud.revisions()
        state = stable_state(app, revisions)
        result = {
            "fingerprint": fingerprint(state),
            "traffic": state["traffic"],
            "images": {n: api_container(t)["image"] for n, t in state["serving"].items()},
        }
    elif args.mode == "wait":
        require(bool(args.revision), "Exact revision required")
        revision = cloud.wait_ready(args.revision)
        result = {
            "ready_revision": revision["name"],
            "fqdn": revision["properties"]["fqdn"],
            "promotion_verified": False,
        }
    else:
        require(args.approval is not None, "Explicit reviewed approval required")
        approval = Approval(**json.loads(args.approval.read_text()))
        approval.validate()
        if args.mode == "source":
            verify_source(
                args.source_root or args.root, policy, approval.serving_sha, approval.serving_tree
            )
            result = {
                "source_verified": True,
                "serving_source_sha": approval.serving_sha,
                "serving_tree": approval.serving_tree,
            }
        elif args.mode == "smoke":
            smoke(
                args.url,
                {
                    "revision": args.revision,
                    "serving_source_sha": approval.serving_sha,
                    "image": args.image,
                    "data_release_id": approval.release_id,
                },
                token=os.environ.get("METRIK_DEPLOY_HEALTH_TOKEN", ""),
            )
            result = {"read_only_smoke_passed": True}
        else:
            require(
                os.environ.get("METRIK_DEPLOY_ENABLED") == "true"
                and os.environ.get("METRIK_OPERATOR_WINDOW") == "exclusive",
                "Deployment disabled: protected environment and exclusive operator window required",
            )
            require(
                os.environ.get("GITHUB_ACTIONS") == "true",
                "Out-of-band deployment forbidden; use shared Actions lock",
            )
            require(
                bool(os.environ.get("METRIK_DEPLOY_HEALTH_TOKEN")),
                "Controlled ops-token readback required",
            )
            deployment = Deployment(cloud, policy, approval)
            try:
                result = deployment.apply(
                    args.image, args.revision, cache_guard(policy, args.revision)
                )
            finally:
                args.output.parent.mkdir(parents=True, exist_ok=True)
                args.output.write_text(json.dumps(deployment.receipt, indent=2))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n")


if __name__ == "__main__":
    main()
