import json
from pathlib import Path
from unittest.mock import patch

from groundtruth.release import stamp_release_metadata


def test_stamp_release_metadata_is_auditable(tmp_path: Path) -> None:
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps({"corpus_revision": "rev", "dataset_version": "v2"}), encoding="utf-8"
    )
    with patch("groundtruth.release.lookup_cache_dir", return_value=tmp_path):
        stamp_release_metadata(
            release_id="2026-W39-abc",
            data_through="2026-09-23",
            source_git_sha="abc",
            qa_decision="GREEN",
            previous_release_id="2026-W38-old",
        )
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    assert payload["release"]["release_id"] == "2026-W39-abc"
    assert payload["release"]["previous_release_id"] == "2026-W38-old"
    assert payload["release"]["corpus_revision"] == "rev"
