"""Rent-yield cache must tolerate read-only production mounts."""

from __future__ import annotations

import contextlib
from pathlib import Path

from groundtruth.services.rent_yield import write_rent_yield_cache


def test_write_rent_yield_cache_tolerates_readonly(tmp_path: Path, monkeypatch) -> None:
    target = tmp_path / "api" / "rent_yield.json"
    target.parent.mkdir(parents=True)
    target.write_text("{}", encoding="utf-8")
    target.chmod(0o444)
    # Also make parent read-only so open('w') fails on Windows/Linux similarly.
    with contextlib.suppress(OSError):
        target.parent.chmod(0o555)

    # Should not raise even when the filesystem rejects the write.
    write_rent_yield_cache([{"slug": "ulpiana", "gross_yield_pct": 5.0}], path=target)

    # Restore perms for cleanup on Windows.
    try:
        target.parent.chmod(0o755)
        target.chmod(0o644)
    except OSError:
        pass
