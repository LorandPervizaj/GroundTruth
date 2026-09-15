"""Backup integrity checks used by restore drills."""

from __future__ import annotations

import gzip
from pathlib import Path


def test_corrupt_gzip_backup_is_detected(tmp_path: Path) -> None:
    bad = tmp_path / "postgres_corrupt.sql.gz"
    bad.write_text("not-a-gzip", encoding="utf-8")
    try:
        with gzip.open(bad, "rb") as fh:
            fh.read(16)
        raised = False
    except OSError:
        raised = True
    assert raised, "corrupt gzip backup must be rejected"


def test_valid_gzip_backup_is_readable(tmp_path: Path) -> None:
    good = tmp_path / "postgres_ok.sql.gz"
    payload = b"-- metrik drill\nSELECT 1;\n"
    with gzip.open(good, "wb") as fh:
        fh.write(payload)
    with gzip.open(good, "rb") as fh:
        assert fh.read() == payload
