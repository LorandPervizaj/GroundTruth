from unittest.mock import MagicMock

from typer.testing import CliRunner

from groundtruth.commands import research_commands as research


def test_doctor_failure_redacts_connection_details(monkeypatch, tmp_path):
    monkeypatch.setenv("DATABASE_URL", "secret-connection-string")
    monkeypatch.setattr(
        research, "create_engine", MagicMock(side_effect=ValueError("secret-connection-string"))
    )
    monkeypatch.setattr(research.subprocess, "check_output", lambda *a, **k: "abc")
    monkeypatch.setattr(research.subprocess, "run", lambda *a, **k: None)
    for key in (
        "GROUNDTRUTH_PIPELINE_STATE_DIR",
        "GROUNDTRUTH_RELEASE_OUTPUT_DIR",
        "GROUNDTRUTH_BACKUP_DIR",
    ):
        monkeypatch.setenv(key, str(tmp_path))
    result = research.doctor_checks(expected_sha="abc", minimum_free_gb=0)
    assert result["overall"] == "FAIL"
    assert "secret-connection-string" not in str(result)
    assert next(c for c in result["checks"] if c["name"] == "database")["status"] == "FAIL"


def test_doctor_json_and_nonzero_exit(monkeypatch):
    monkeypatch.setattr(research, "doctor_checks", lambda **k: {"overall": "FAIL", "checks": []})
    result = CliRunner().invoke(research.research_app, ["doctor", "--json"])
    assert result.exit_code == 1
    assert '"overall": "FAIL"' in result.stdout


def test_retention_preserves_four_weeks_and_three_months(tmp_path):
    import os
    from datetime import UTC, datetime

    from groundtruth.automation.backups import retained_backups

    paths = []
    for stamp in (
        "2026-09-28",
        "2026-09-21",
        "2026-09-14",
        "2026-09-07",
        "2026-09-01",
        "2026-08-31",
        "2026-07-27",
        "2026-06-29",
    ):
        p = tmp_path / stamp
        p.touch()
        epoch = datetime.fromisoformat(stamp).replace(tzinfo=UTC).timestamp()
        os.utime(p, (epoch, epoch))
        paths.append(p)
    retained = retained_backups(paths)
    assert {p.name for p in retained} == {
        "2026-09-28",
        "2026-09-21",
        "2026-09-14",
        "2026-09-07",
        "2026-08-31",
        "2026-07-27",
    }
