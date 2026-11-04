"""No GitHub writes until every independently reviewed identity is verified."""

import base64
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from groundtruth.automation import azure_publication as pub
from groundtruth.automation.deployment import Approval

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def publication(tmp_path, monkeypatch):
    bundle = tmp_path / "groundtruth-release-test.tar.gz"
    bundle.write_bytes(b"verified public data")
    checksum = bundle.with_name(bundle.name + ".sha256")
    checksum.write_text("checksum")
    candidate = SimpleNamespace(
        release_id="test",
        release_tag="groundtruth-release-test",
        bundle=bundle,
        checksum=checksum,
        sha256=pub.sha256_file(bundle),
        data_through="2026-10-25",
        source_git_sha="a" * 40,
    )
    approval = Approval(
        "b" * 40, "c" * 40, "d" * 40, "e" * 40, "a" * 40, "test", candidate.sha256, "f" * 64
    )
    approval = Approval(**{**vars(approval), "tooling_ref": "reviewed-tooling"})
    path = tmp_path / "approval.json"
    path.write_text(json.dumps(vars(approval)))
    monkeypatch.setattr(pub, "verify_run_result", lambda *args: candidate)
    monkeypatch.setattr(pub, "production_preflight", lambda *args: None)
    calls, fault = [], {"mode": ""}

    def gh(*args):
        calls.append(args)
        endpoint = args[-1]
        if args[:1] == ("api",):
            if endpoint.endswith(
                ("/METRIK_PUBLICATION_ENABLED", "/METRIK_ENV_PUBLICATION_ENABLED")
            ):
                return json.dumps(
                    {
                        "value": "false"
                        if fault["mode"] == "publication_off"
                        or (fault["mode"] == "publication_repo_off" and "/actions/" in endpoint)
                        or (fault["mode"] == "publication_env_off" and "/environments/" in endpoint)
                        else "true"
                    }
                )
            if "/git/commits/" in endpoint:
                sha = endpoint.rsplit("/", 1)[1]
                return json.dumps(
                    {
                        "sha": sha,
                        "tree": {
                            "sha": ("c" if sha == approval.serving_sha else "e") * 40
                            if fault["mode"] != "wrong_tree"
                            else "0" * 40
                        },
                    }
                )
            if "/compare/" in endpoint:
                return json.dumps(
                    {"status": "behind" if fault["mode"] == "older_master" else "ahead"}
                )
            if "/contents/" in endpoint:
                file, ref = endpoint.split("/contents/", 1)[1].split("?ref=")
                value = (ROOT / file).read_bytes()
                if fault["mode"] == "missing_backend" and file == "src/groundtruth/config.py":
                    value = b'product_write_backend: Literal["jsonl", "database"]'
                if fault["mode"] == "bad_guard" and file == "src/groundtruth/startup.py":
                    value = b"# guard removed"
                if fault["mode"] == "wrong_tooling" and ref == approval.tooling_sha:
                    value = b"unsafe workflow"
                return json.dumps(
                    {"encoding": "base64", "content": base64.b64encode(value).decode()}
                )
            if "/commits/" in endpoint:
                if endpoint.endswith("/reviewed-tooling"):
                    return json.dumps(
                        {"sha": "0" * 40 if fault["mode"] == "moved_ref" else approval.tooling_sha}
                    )
                return json.dumps({"sha": ("0" if fault["mode"] == "bad_target" else "a") * 40})
            if "matching-refs" in endpoint:
                return "[]"
            return "[[]]"
        if args[:2] == ("release", "view"):
            return json.dumps(
                {
                    "assets": [{"name": bundle.name}, {"name": checksum.name}],
                    "isDraft": True,
                    "url": "https://example.invalid/release",
                    "targetCommitish": "a" * 40,
                }
            )
        if args[:2] == ("release", "download"):
            folder = Path(args[-1])
            (folder / bundle.name).write_bytes(
                b"corrupt" if fault["mode"] == "corrupt" else bundle.read_bytes()
            )
            (folder / checksum.name).write_bytes(checksum.read_bytes())
        return ""

    monkeypatch.setattr(pub, "gh", gh)

    def execute():
        return pub.publish_and_dispatch(
            tmp_path / "result.json",
            tmp_path,
            approval_path=path,
            approval_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
        )

    return execute, calls, fault, path


@pytest.mark.parametrize(
    "fault",
    [
        "older_master",
        "wrong_tree",
        "missing_backend",
        "bad_guard",
        "wrong_tooling",
        "bad_target",
        "moved_ref",
        "publication_off",
        "publication_repo_off",
        "publication_env_off",
    ],
)
def test_invalid_source_or_target_never_publishes(publication, fault):
    execute, calls, mode, _ = publication
    mode["mode"] = fault
    with pytest.raises(ValueError):
        execute()
    assert all(c[0] == "api" for c in calls)


def test_independent_source_and_tooling_sha_are_not_inferred_from_data_tag(publication):
    execute, calls, _, _ = publication
    result = execute()
    assert result["serving_git_sha"] == "b" * 40
    create = next(c for c in calls if c[:2] == ("release", "create"))
    assert create[create.index("--target") + 1] == "a" * 40
    dispatch = next(c for c in calls if c[:2] == ("workflow", "run"))
    assert dispatch[dispatch.index("--ref") + 1] == "reviewed-tooling"
    assert "tooling_source_sha=" + "d" * 40 in dispatch
    assert "serving_source_sha=" + "b" * 40 in dispatch
    assert not any(arg == "master" or "commits/master" in arg for c in calls for arg in c)


def test_corrupt_remote_bundle_stays_draft_and_no_dispatch(publication):
    execute, calls, fault, _ = publication
    fault["mode"] = "corrupt"
    with pytest.raises(ValueError):
        execute()
    assert not any(c[:2] in {("workflow", "run"), ("release", "edit")} for c in calls)


def test_unreviewed_approval_bytes_rejected_before_github(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(pub, "gh", lambda *a: calls.append(a))
    path = tmp_path / "approval.json"
    path.write_text("{}")
    with pytest.raises(ValueError, match="bytes differ"):
        pub.publish_and_dispatch(
            tmp_path / "result", tmp_path, approval_path=path, approval_sha256="0" * 64
        )
    assert not calls


def test_missing_approval_never_falls_back_to_master(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(pub, "gh", lambda *a: calls.append(a))
    with pytest.raises(ValueError, match="approval required"):
        pub.publish_and_dispatch(tmp_path / "result", tmp_path)
    assert not calls
