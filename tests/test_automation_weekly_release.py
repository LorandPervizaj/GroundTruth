from datetime import UTC, date, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

from groundtruth.automation.weekly_release import make_release_id, run_weekly_release


def test_release_id_uses_iso_week() -> None:
    assert make_release_id(datetime(2026, 9, 23, tzinfo=UTC), git_sha="abc123") == "2026-W39-abc123"


def test_weekly_release_records_verified_result(tmp_path: Path) -> None:
    report = SimpleNamespace(
        sources=[SimpleNamespace(error=None, etl_normalized=12)],
        window=SimpleNamespace(window_start=date(2026, 9, 15), window_end=date(2026, 9, 22)),
    )
    output = tmp_path / "run.json"
    result = run_weekly_release(
        days=8,
        output_path=output,
        weekly_runner=lambda **_: report,
        verifier=lambda: ["ok"],
    )
    assert result.outcome == "verified"
    assert [stage.status for stage in result.stages] == ["passed", "passed"]
    assert output.is_file()


def test_weekly_release_records_verification_failure(tmp_path: Path) -> None:
    report = SimpleNamespace(
        sources=[],
        window=SimpleNamespace(window_start=date(2026, 9, 15), window_end=date(2026, 9, 22)),
    )

    def fail() -> list[str]:
        raise ValueError("hash mismatch")

    with pytest.raises(ValueError, match="hash mismatch"):
        run_weekly_release(
            output_path=tmp_path / "failed.json",
            weekly_runner=lambda **_: report,
            verifier=fail,
        )
