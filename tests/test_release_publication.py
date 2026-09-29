import hashlib
import io
import json
import tarfile
from pathlib import Path

import pytest
from typer.testing import CliRunner

from groundtruth.automation.publication import release_tag, verify_bundle, verify_run_result
from groundtruth.commands.research_commands import research_app

RELEASE_ID = "2026-W40-abcdef123456"


def _bundle(
    directory: Path,
    *,
    release_id: str = RELEASE_ID,
    publishable: bool = True,
    extra: dict[str, bytes] | None = None,
) -> Path:
    manifest = {
        "release": {
            "release_id": release_id,
            "publishable": publishable,
            "source_git_sha": "abcdef123456",
            "data_through": "2026-09-28",
        }
    }
    members = {
        "lookup_cache/manifest.json": json.dumps(manifest).encode(),
        "lookup_cache/entries/ulpiana.json": b"{}",
        "data/api/annual_report.json": b"{}",
        "data/api/rent_yield.json": b"{}",
        **(extra or {}),
    }
    directory.mkdir(parents=True, exist_ok=True)
    bundle = directory / f"groundtruth-release-{release_id}.tar.gz"
    with tarfile.open(bundle, "w:gz") as archive:
        for name, content in members.items():
            info = tarfile.TarInfo(name)
            info.size = len(content)
            archive.addfile(info, io.BytesIO(content))
    digest = hashlib.sha256(bundle.read_bytes()).hexdigest()
    bundle.with_name(bundle.name + ".sha256").write_text(
        f"{digest}  {bundle.name}\n", encoding="utf-8"
    )
    return bundle


def _result(path: Path, bundle: Path, outcome: str = "verified") -> Path:
    path.write_text(
        json.dumps(
            {
                "outcome": outcome,
                "release_id": RELEASE_ID,
                "release_bundle": str(bundle),
                "source_git_sha": "abcdef123456",
            }
        ),
        encoding="utf-8",
    )
    return path


def test_verified_bundle_exposes_immutable_identity(tmp_path):
    verified = verify_bundle(_bundle(tmp_path), release_id=RELEASE_ID)
    assert verified.release_tag == f"groundtruth-release-{RELEASE_ID}"
    assert verified.source_git_sha == "abcdef123456"
    assert verified.data_through == "2026-09-28"
    assert len(verified.sha256) == 64


@pytest.mark.parametrize(
    "name",
    [
        "pipeline_state/state.json",
        "backups/research.dump",
        "raw/merrjep.html",
        ".env",
        "data/api/raw_listings.json",
    ],
)
def test_private_paths_are_never_publishable(tmp_path, name):
    bundle = _bundle(tmp_path, extra={name: b"private"})
    with pytest.raises(ValueError, match="non-public"):
        verify_bundle(bundle, release_id=RELEASE_ID)


def test_path_traversal_is_rejected(tmp_path):
    bundle = _bundle(tmp_path, extra={"lookup_cache/../../escape": b"x"})
    with pytest.raises(ValueError, match="unsafe"):
        verify_bundle(bundle, release_id=RELEASE_ID)


def test_checksum_mismatch_is_rejected(tmp_path):
    bundle = _bundle(tmp_path)
    checksum = bundle.with_name(bundle.name + ".sha256")
    checksum.write_text(f"{'0' * 64}  {bundle.name}\n", encoding="utf-8")
    with pytest.raises(ValueError, match="checksum mismatch"):
        verify_bundle(bundle, release_id=RELEASE_ID)


def test_unpublishable_manifest_is_rejected(tmp_path):
    with pytest.raises(ValueError, match="not publishable"):
        verify_bundle(_bundle(tmp_path, publishable=False), release_id=RELEASE_ID)


def test_bundle_must_carry_the_requested_release(tmp_path):
    bundle = _bundle(tmp_path)
    other = "2026-W41-abcdef123456"
    renamed = bundle.rename(bundle.with_name(f"groundtruth-release-{other}.tar.gz"))
    digest = hashlib.sha256(renamed.read_bytes()).hexdigest()
    renamed.with_name(renamed.name + ".sha256").write_text(f"{digest}  {renamed.name}\n")
    with pytest.raises(ValueError, match="manifest release id does not match"):
        verify_bundle(renamed, release_id=other)
    with pytest.raises(ValueError, match="does not match"):
        verify_bundle(renamed, release_id=RELEASE_ID)


def test_release_id_must_be_tag_safe():
    with pytest.raises(ValueError):
        release_tag("2026-W40; rm -rf /")


@pytest.mark.parametrize("outcome", ["failed", "running", None])
def test_failed_runs_are_never_published(tmp_path, outcome):
    bundle = _bundle(tmp_path / "releases")
    result = _result(tmp_path / "run.json", bundle, outcome=outcome)
    with pytest.raises(ValueError, match="not publishable"):
        verify_run_result(result, tmp_path / "releases")


def test_bundle_outside_release_directory_is_rejected(tmp_path):
    bundle = _bundle(tmp_path / "elsewhere")
    result = _result(tmp_path / "run.json", bundle)
    with pytest.raises(ValueError, match="outside"):
        verify_run_result(result, tmp_path / "releases")


def test_publication_candidate_writes_github_outputs(tmp_path, monkeypatch):
    releases = tmp_path / "releases"
    bundle = _bundle(releases)
    result = _result(tmp_path / "run.json", bundle, outcome="warning")
    output = tmp_path / "github_output"
    monkeypatch.setenv("GROUNDTRUTH_RELEASE_OUTPUT_DIR", str(releases))
    invoked = CliRunner().invoke(
        research_app,
        ["publication-candidate", "--result", str(result), "--github-output", str(output)],
    )
    assert invoked.exit_code == 0, invoked.output
    lines = dict(line.split("=", 1) for line in output.read_text().splitlines())
    assert lines["release_tag"] == f"groundtruth-release-{RELEASE_ID}"
    assert lines["bundle"] == str(bundle.resolve())


def test_publication_candidate_fails_closed(tmp_path, monkeypatch):
    releases = tmp_path / "releases"
    result = _result(tmp_path / "run.json", _bundle(releases), outcome="failed")
    output = tmp_path / "github_output"
    monkeypatch.setenv("GROUNDTRUTH_RELEASE_OUTPUT_DIR", str(releases))
    invoked = CliRunner().invoke(
        research_app,
        ["publication-candidate", "--result", str(result), "--github-output", str(output)],
    )
    assert invoked.exit_code == 1
    assert not output.exists()


def test_notify_never_leaks_token_on_failure(monkeypatch):
    def boom(*_args, **_kwargs):
        raise RuntimeError("https://api.telegram.org/botSECRET/sendMessage")

    monkeypatch.setattr("groundtruth.automation.notifications.send_telegram_message", boom)
    invoked = CliRunner().invoke(research_app, ["notify", "research started"])
    assert invoked.exit_code == 0
    assert "SECRET" not in invoked.output
