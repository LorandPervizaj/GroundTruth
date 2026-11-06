"""Local-only synthetic image build and content verification; never push images."""

import hashlib
import io
import json
import subprocess
import tarfile
from pathlib import Path

from groundtruth.automation.deployment import require
from groundtruth.automation.staging_fixture import digest, verify, write_json


def bundle(fixture: Path, output: Path) -> str:
    verify(fixture)
    # Uncompressed tar has deterministic headers and a digest independent of filesystem mtimes.
    with tarfile.open(output, "w") as archive:
        for path in sorted(p for p in fixture.rglob("*") if p.is_file()):
            data = path.read_bytes()
            entry = tarfile.TarInfo(path.relative_to(fixture).as_posix())
            entry.size, entry.mtime, entry.mode = len(data), 0, 0o644
            archive.addfile(entry, io.BytesIO(data))
    return digest(output)


def verify_context(context: Path) -> dict:
    inventory = json.loads((context / "context-inventory.json").read_text())
    actual = {
        p.relative_to(context).as_posix(): digest(p)
        for p in context.rglob("*")
        if p.is_file() and p.relative_to(context).as_posix() != "context-inventory.json"
    }
    require(inventory == actual, "Build context checksum differs")
    allowed = {
        "src",
        "web",
        "alembic",
        "scripts",
        "data",
        "reports",
        "synthetic",
        "synthetic-inventory.json",
        "Dockerfile",
        "pyproject.toml",
        "uv.lock",
        "README.md",
        "alembic.ini",
        "context-inventory.json",
    }
    require(
        all(p.name in allowed for p in context.iterdir())
        and not any(p.is_symlink() or p.name.startswith(".env") for p in context.rglob("*")),
        "Unexpected/private context input",
    )
    return inventory


def build_and_verify(output: Path, *, runner=subprocess.run) -> dict:
    manifest = verify(output / "fixture")
    inventory = verify_context(output / "context")
    bundle_sha = bundle(output / "fixture", output / "synthetic-release.tar")
    sha = manifest["release"]["source_git_sha"]
    tag = "metrik-synthetic:" + sha
    labels = {
        "org.opencontainers.image.revision": sha,
        "io.metrik.data-source-sha": sha,
        "io.metrik.data-release-id": manifest["release"]["release_id"],
        "io.metrik.bundle-sha256": bundle_sha,
    }
    args = ["docker", "build", "--tag", tag]
    for name, value in labels.items():
        args.extend(["--label", f"{name}={value}"])
    result = runner([*args, str(output / "context")], check=True)
    require(result.returncode == 0, "Synthetic image build failed")
    config = json.loads(
        runner(
            ["docker", "image", "inspect", tag], check=True, capture_output=True, text=True
        ).stdout
    )[0]
    require(
        all(config["Config"]["Labels"].get(k) == v for k, v in labels.items()),
        "Synthetic image labels differ",
    )
    # Network-free, read-only inspection never starts application code or contacts Azure.
    code = """import sys,json,hashlib,pathlib
expected=json.load(sys.stdin)
for name,value in expected.items():
 p=pathlib.Path('/app')/name
 assert p.is_file() and hashlib.sha256(p.read_bytes()).hexdigest()==value, name
for folder in ('data','reports/generated'):
 actual={p.relative_to('/app').as_posix() for p in (pathlib.Path('/app')/folder).rglob('*') if p.is_file()}
 assert actual=={n for n in expected if n.startswith(folder+'/')}, folder
assert not pathlib.Path('/app/.env').exists()
assert not pathlib.Path('/app/.git').exists()
print('synthetic-image-content-verified')
"""
    expected = {
        name: value
        for name, value in inventory.items()
        if name.startswith(("data/", "reports/generated/")) or name == "web/static/home-trust.json"
    }
    inspected = runner(
        [
            "docker",
            "run",
            "--rm",
            "-i",
            "--network",
            "none",
            "--read-only",
            "--entrypoint",
            "/app/.venv/bin/python",
            tag,
            "-c",
            code,
        ],
        input=json.dumps(expected),
        capture_output=True,
        text=True,
        check=True,
    )
    require(
        inspected.stdout.strip() == "synthetic-image-content-verified", "Image content check failed"
    )
    baseline_tag = tag + "-baseline"
    baseline_args = ["docker", "build", "--tag", baseline_tag]
    for name, value in labels.items():
        baseline_args.extend(["--label", f"{name}={value}"])
    runner(
        [*baseline_args, "--label", "io.metrik.stage-role=baseline", str(output / "context")],
        check=True,
    )
    baseline = json.loads(
        runner(
            ["docker", "image", "inspect", baseline_tag], check=True, capture_output=True, text=True
        ).stdout
    )[0]
    require(
        baseline["Id"] != config["Id"]
        and baseline["RootFS"] == config["RootFS"]
        and all(baseline["Config"]["Labels"].get(k) == v for k, v in labels.items()),
        "Baseline must have identical synthetic layers and a distinct immutable identity",
    )
    receipt = {
        "source_sha": sha,
        "synthetic": True,
        "tag": tag,
        "bundle_sha256": bundle_sha,
        "image_config_digest": config["Id"],
        "baseline_tag": baseline_tag,
        "baseline_image_config_digest": baseline["Id"],
        "registry_manifest_digest": None,
        "registry_push_performed": False,
        "context_inventory_sha256": hashlib.sha256(
            json.dumps(inventory, sort_keys=True).encode()
        ).hexdigest(),
        "content_verified": True,
    }
    write_json(output / "image-receipt.json", receipt)
    return receipt
