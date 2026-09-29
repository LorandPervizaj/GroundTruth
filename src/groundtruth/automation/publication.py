"""Gate a verified bundle before it leaves the research host or enters deployment."""

from __future__ import annotations

import json
import re
import tarfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from groundtruth.claims.hashes import sha256_file

RELEASE_TAG_PREFIX = "groundtruth-release-"
PUBLISHABLE_OUTCOMES = frozenset({"verified", "warning"})
_PUBLIC_FILES = frozenset({"data/api/annual_report.json", "data/api/rent_yield.json"})
_PUBLIC_DIRECTORIES = frozenset({"data", "data/api"})
_PUBLIC_TREE = "lookup_cache"
_MANIFEST = "lookup_cache/manifest.json"
_RELEASE_ID = re.compile(r"[0-9A-Za-z][0-9A-Za-z._-]{0,99}")


@dataclass(frozen=True)
class VerifiedBundle:
    release_tag: str
    release_id: str
    bundle: Path
    checksum: Path
    sha256: str
    data_through: str
    source_git_sha: str

    def outputs(self) -> dict[str, str]:
        return {
            "release_tag": self.release_tag,
            "release_id": self.release_id,
            "bundle": str(self.bundle),
            "checksum": str(self.checksum),
            "sha256": self.sha256,
            "data_through": self.data_through,
            "source_git_sha": self.source_git_sha,
        }


def release_tag(release_id: str) -> str:
    if not _RELEASE_ID.fullmatch(release_id):
        raise ValueError("release id is not tag-safe")
    return f"{RELEASE_TAG_PREFIX}{release_id}"


def verify_bundle(
    bundle: Path, *, release_id: str, source_git_sha: str | None = None
) -> VerifiedBundle:
    """Require checksum, public-only members, and a publishable manifest for this release."""
    tag = release_tag(release_id)
    if bundle.name != f"{tag}.tar.gz":
        raise ValueError(f"bundle name {bundle.name} does not match {tag}")
    checksum = bundle.with_name(bundle.name + ".sha256")
    if not bundle.is_file() or not checksum.is_file():
        raise ValueError("bundle or checksum is missing")
    expected, _, named = checksum.read_text(encoding="utf-8").strip().partition("  ")
    if named.strip() != bundle.name:
        raise ValueError("checksum names a different file")
    actual = sha256_file(bundle)
    if actual != expected.strip().lower():
        raise ValueError("bundle checksum mismatch")

    names: set[str] = set()
    with tarfile.open(bundle, "r:gz") as archive:
        for member in archive.getmembers():
            path = PurePosixPath(member.name)
            if path.is_absolute() or ".." in path.parts:
                raise ValueError(f"unsafe bundle path: {member.name}")
            if not (member.isfile() or member.isdir()):
                raise ValueError(f"bundle member is not a regular file: {member.name}")
            text = path.as_posix()
            public = (
                path.parts[0] == _PUBLIC_TREE
                or (member.isfile() and text in _PUBLIC_FILES)
                or (member.isdir() and text in _PUBLIC_DIRECTORIES)
            )
            if not public:
                raise ValueError(f"bundle contains a non-public path: {text}")
            names.add(text)
        missing = ({_MANIFEST} | _PUBLIC_FILES) - names
        if missing:
            raise ValueError("bundle is missing " + ", ".join(sorted(missing)))
        handle = archive.extractfile(_MANIFEST)
        if handle is None:
            raise ValueError("bundle manifest is unreadable")
        manifest = json.loads(handle.read().decode("utf-8"))

    release = manifest.get("release") or {}
    if release.get("release_id") != release_id:
        raise ValueError("manifest release id does not match")
    if release.get("publishable") is not True:
        raise ValueError("manifest marks the release as not publishable")
    recorded_sha = str(release.get("source_git_sha") or "")
    if source_git_sha and recorded_sha != source_git_sha:
        raise ValueError("manifest source revision does not match the run")
    return VerifiedBundle(
        release_tag=tag,
        release_id=release_id,
        bundle=bundle,
        checksum=checksum,
        sha256=actual,
        data_through=str(release.get("data_through") or ""),
        source_git_sha=recorded_sha,
    )


def verify_run_result(result_path: Path, release_dir: Path) -> VerifiedBundle:
    """Accept only a verified/warning weekly run whose bundle sits in the release directory."""
    payload = json.loads(result_path.read_text(encoding="utf-8"))
    outcome = payload.get("outcome")
    if outcome not in PUBLISHABLE_OUTCOMES:
        raise ValueError(f"run outcome {outcome!r} is not publishable")
    if not payload.get("release_bundle") or not payload.get("release_id"):
        raise ValueError("run result has no release bundle")
    bundle = Path(payload["release_bundle"]).resolve()
    if not bundle.is_relative_to(release_dir.resolve()):
        raise ValueError("bundle is outside the release directory")
    return verify_bundle(
        bundle,
        release_id=str(payload["release_id"]),
        source_git_sha=payload.get("source_git_sha"),
    )
