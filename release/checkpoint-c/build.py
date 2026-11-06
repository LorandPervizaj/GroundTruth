"""Build an immutable local image from the clean committed Git archive. Never push."""

import datetime
import hashlib
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent / "output"
OUT.mkdir(exist_ok=True)


def git(*args):
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()


assert not git("status", "--porcelain=v1"), "Commit reviewed source before image build"
sha = git("rev-parse", "HEAD")
archive = OUT / "source.tar"
with archive.open("wb") as stream:
    subprocess.run(["git", "archive", "--format=tar", sha], cwd=ROOT, stdout=stream, check=True)
tag = "metrik-api:checkpoint-c-" + sha[:12]
receipt = dict(
    git_sha=sha,
    branch=git("branch", "--show-current"),
    tag=tag,
    archive_sha256=hashlib.sha256(archive.read_bytes()).hexdigest(),
    source_clean=True,
    pushed=False,
    started_utc=datetime.datetime.now(datetime.UTC).isoformat(),
)
(OUT / "identity.json").write_text(json.dumps(receipt, indent=2))
with archive.open("rb") as source, (OUT / "build.log").open("w", encoding="utf8") as log:
    result = subprocess.run(
        [
            "docker",
            "buildx",
            "build",
            "--load",
            "--provenance=false",
            "--metadata-file",
            str(OUT / "build-metadata.json"),
            "--label",
            "org.opencontainers.image.revision=" + sha,
            "-t",
            tag,
            "-",
        ],
        cwd=ROOT,
        stdin=source,
        stdout=log,
        stderr=subprocess.STDOUT,
    )
receipt["build_exit_code"] = result.returncode
if not result.returncode:
    receipt["image_manifest_digest"] = json.loads((OUT / "build-metadata.json").read_text())[
        "containerimage.digest"
    ]
    receipt["image_config_id"] = json.loads(
        subprocess.check_output(["docker", "image", "inspect", tag])
    )[0]["Id"]
(OUT / "identity.json").write_text(json.dumps(receipt, indent=2))
print(json.dumps(receipt), flush=True)
raise SystemExit(result.returncode)
