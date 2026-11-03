"""Read and validate release assets before building a candidate; no remote writes."""

import argparse
import json
import os
import subprocess
from pathlib import Path

from groundtruth.automation.deployment import Approval, require
from groundtruth.automation.deployment_source import git
from groundtruth.automation.publication import verify_bundle


def main():
    p = argparse.ArgumentParser()
    for name in ("source", "tools", "assets", "output"):
        p.add_argument("--" + name, type=Path, required=True)
    a = p.parse_args()
    tag = os.environ["RELEASE_TAG"]
    release = tag.removeprefix("groundtruth-release-")
    name = f"{tag}.tar.gz"
    require(
        sorted(x.name for x in a.assets.iterdir()) == sorted([name, name + ".sha256"]),
        "Unexpected release assets",
    )
    data = verify_bundle(a.assets / name, release_id=release)
    target = subprocess.run(
        ["gh", "api", f"repos/{os.environ['GITHUB_REPOSITORY']}/commits/{tag}"],
        capture_output=True,
        text=True,
        timeout=60,
    )
    require(
        target.returncode == 0 and json.loads(target.stdout).get("sha") == data.source_git_sha,
        "Release target/data-source identity differs",
    )
    approval = Approval(
        serving_sha=os.environ["SERVING_SOURCE_SHA"],
        serving_tree=os.environ["SERVING_TREE_SHA"],
        tooling_sha=git(a.tools, "rev-parse", "HEAD"),
        tooling_tree=git(a.tools, "rev-parse", "HEAD^{tree}"),
        data_source_sha=data.source_git_sha,
        release_id=data.release_id,
        bundle_sha256=data.sha256,
        expected_state=os.environ["EXPECTED_STATE"],
        tooling_ref=os.environ["GITHUB_REF_NAME"],
    )
    require(
        approval.tooling_sha == os.environ["TOOLING_SOURCE_SHA"]
        and approval.tooling_tree == os.environ["TOOLING_TREE_SHA"],
        "Reviewed tooling SHA/tree differs from checkout",
    )
    approval.validate()
    a.output.write_text(json.dumps(vars(approval), indent=2) + "\n")


if __name__ == "__main__":
    main()
