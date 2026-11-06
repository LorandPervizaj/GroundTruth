"""Generate a complete PR file/provenance inventory without modifying artifacts."""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import subprocess
from pathlib import Path

PRODUCTION = "889184ff8a24ac0dacd87433cc71a5405bd23b7b"
SAFETY_START = "92b05c887ec084fff8af718784bcfbe3e423a0a4"


def git(root, *args):
    return subprocess.check_output(["git", "-C", str(root), *args])


def category(path):
    if path.startswith(("reports/generated/lookup_cache/", "data/api/")):
        return "frozen_public_data"
    if path.startswith("web/"):
        return "frontend"
    if path.startswith("reports/research/"):
        return "existing_groundtruth_research"
    if path.startswith((".github/", "scripts/performance")) or path in {
        "pyproject.toml",
        "uv.lock",
        ".dockerignore",
    }:
        return "ci_tooling"
    if path.startswith(("tests/", "release/")):
        return "tests_fixtures"
    if path.startswith("docs/"):
        return "documentation"
    if path.startswith(
        (
            "deploy/",
            "scripts/azure/",
            "scripts/automation/",
            "src/groundtruth/automation/deployment",
            "src/groundtruth/automation/azure_publication",
            "src/groundtruth/automation/staging",
        )
    ):
        return "publication_deployment_safety"
    if any(x in path for x in ("gazetteer", "location", "neighborhood")):
        return "location_gazetteer"
    if any(x in path for x in ("harta", "source_quality", "parsing", "parser", "price", "portals")):
        return "source_quality_parsing"
    if path.startswith(
        ("src/groundtruth/api/", "src/groundtruth/services/", "alembic/")
    ) or path in {
        "Dockerfile",
        "src/groundtruth/config.py",
        "src/groundtruth/startup.py",
        "src/groundtruth/cli.py",
        "src/groundtruth/release.py",
        "scripts/docker-entrypoint.sh",
        "scripts/load_gazetteers.py",
    }:
        return "table_serving_compatibility"
    if path.startswith(("src/", "scripts/", "data/")):
        return "existing_groundtruth_research"
    return "unexpected_requires_review"


REASONS = {
    "frozen_public_data": "Preserve the historical frozen serving release, never regenerate to satisfy CI.",
    "frontend": "Preserve the preferred already-serving Metrik frontend.",
    "ci_tooling": "Reproducible validation/build tooling and independently closed activation gates.",
    "tests_fixtures": "Regression/fixture evidence, including historical release verification tools; not deployment entrypoints.",
    "documentation": "Review provenance, operating boundaries, historical evidence or release instructions.",
    "publication_deployment_safety": "Explicit approval, immutable provenance, scoped deployment/staging and verified recovery.",
    "location_gazetteer": "Retain existing location hierarchy and resolver behavior inherited by the serving baseline.",
    "source_quality_parsing": "Retain earlier research/source normalization and quality work.",
    "table_serving_compatibility": "Retain durable Table backend, API contracts and guarded disposable-cache serving behavior.",
    "existing_groundtruth_research": "Preserve earlier GroundTruth functionality rather than overwrite unmerged intended work.",
    "unexpected_requires_review": "Must be investigated before readiness.",
}


def build_inventory(root, base="origin/master", head="HEAD"):
    head = git(root, "rev-parse", head).decode().strip()
    base = git(root, "rev-parse", base).decode().strip()
    paths = (
        git(root, "diff", "--name-only", "--no-renames", f"{base}...{head}").decode().splitlines()
    )
    provenance = {}
    commits = {}
    log = git(root, "log", "-m", "--format=%x1e%H%x1f%s", "--name-only", f"{base}..{head}").decode()
    ancestors = set(git(root, "rev-list", PRODUCTION).decode().splitlines())
    for block in log.split("\x1e"):
        if not block.strip():
            continue
        first, *names = block.strip().splitlines()
        sha, title = first.split("\x1f", 1)
        commits[sha] = {"sha": sha, "title": title, "predates_remediation": sha in ancestors}
        for name in names:
            if name.strip():
                provenance.setdefault(name.strip(), set()).add(sha)

    requests = [(ref, path) for path in paths for ref in (base, PRODUCTION, head)]
    response = subprocess.run(
        ["git", "-C", str(root), "cat-file", "--batch"],
        input="".join(f"{ref}:{path}\n" for ref, path in requests).encode(),
        capture_output=True,
        check=True,
    )
    stream, contents = io.BytesIO(response.stdout), {}
    for ref, path in requests:
        header = stream.readline().decode().strip()
        if header.endswith(" missing"):
            contents[(ref, path)] = None
        else:
            size = int(header.rsplit(" ", 1)[1])
            contents[(ref, path)] = hashlib.sha256(stream.read(size)).hexdigest()
            stream.read(1)

    rows = []
    for path in paths:
        kind = category(path)
        hashes = {
            "master": contents[(base, path)],
            "production": contents[(PRODUCTION, path)],
            "head": contents[(head, path)],
        }
        origins = sorted(provenance.get(path, set()))
        historical = hashes["production"] is not None and hashes["production"] == hashes["head"]
        rows.append(
            {
                "path": path,
                "category": kind,
                "originating_commits": origins,
                "predates_remediation": historical,
                "inclusion_reason": REASONS[kind],
                "runtime_changes_vs_master": kind
                in {
                    "frontend",
                    "table_serving_compatibility",
                    "location_gazetteer",
                    "source_quality_parsing",
                    "existing_groundtruth_research",
                    "publication_deployment_safety",
                },
                "runtime_differs_from_production": hashes["production"] != hashes["head"]
                and kind not in {"documentation", "tests_fixtures"},
                "public_release_contents_change_vs_production": kind == "frozen_public_data"
                and hashes["production"] != hashes["head"],
                "required_for_publication_patch": kind
                in {"publication_deployment_safety", "table_serving_compatibility", "ci_tooling"},
                "required_to_preserve_historical_integration": historical,
                "verification": "SHA256 production comparison"
                if historical
                else "Full final-tree regression/CI plus origin review; see COMPLETION_20261106.md",
                "sha256": hashes,
            }
        )
    return {
        "snapshot_head": head,
        "remote_master": base,
        "production_source": PRODUCTION,
        "safety_start": SAFETY_START,
        "merge_base": git(root, "merge-base", base, head).decode().strip(),
        "file_count": len(rows),
        "commits": sorted(commits.values(), key=lambda c: c["sha"]),
        "files": rows,
        "unexplained": [
            r["path"]
            for r in rows
            if r["category"] == "unexpected_requires_review" or not r["originating_commits"]
        ],
    }


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    p.add_argument("--output", required=True, type=Path)
    args = p.parse_args()
    result = build_inventory(args.root)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"files": result["file_count"], "unexplained": result["unexplained"]}))


if __name__ == "__main__":
    main()
