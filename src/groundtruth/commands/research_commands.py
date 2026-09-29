"""Local research host diagnostics and recovery operations."""

import json
import os
import shutil
import subprocess
import tempfile
from datetime import UTC, datetime
from pathlib import Path

import typer
from alembic.config import Config
from alembic.script import ScriptDirectory
from rich.console import Console
from sqlalchemy import create_engine, text

from groundtruth.automation.state import load_state, pipeline_lock, verified_watermark
from groundtruth.config import PROJECT_ROOT

research_app = typer.Typer(help="Local research host health and backups")


def doctor_checks(*, expected_sha: str | None = None, minimum_free_gb: float = 20) -> dict:
    checks = []

    def check(name, operation):
        try:
            detail = operation()
            checks.append({"name": name, "status": "PASS", "detail": detail})
        except Exception as exc:
            # Connection exceptions can embed credentials. Never serialize them.
            checks.append({"name": name, "status": "FAIL", "detail": type(exc).__name__})

    def git():
        sha = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=PROJECT_ROOT, text=True
        ).strip()
        if expected_sha and sha != expected_sha:
            raise ValueError("unexpected checkout")
        subprocess.run(
            ["git", "ls-remote", "--exit-code", "origin", "refs/heads/master"],
            cwd=PROJECT_ROOT,
            check=True,
            capture_output=True,
            timeout=30,
        )
        return sha

    check("repository", git)
    url = os.getenv("DATABASE_URL")

    def database():
        if not url:
            raise ValueError("DATABASE_URL required")
        engine = create_engine(url, connect_args={"connect_timeout": 10})
        try:
            with engine.connect() as connection:
                return connection.execute(text("SELECT version()")).scalar_one()
        finally:
            engine.dispose()

    check("database", database)

    def query(sql):
        if not url:
            raise ValueError("DATABASE_URL required")
        engine = create_engine(url, connect_args={"connect_timeout": 10})
        try:
            with engine.connect() as connection:
                return connection.execute(text(sql)).scalars().all()
        finally:
            engine.dispose()

    check("postgis", lambda: query("SELECT PostGIS_Full_Version()"))

    def alembic():
        config = Config(str(PROJECT_ROOT / "alembic.ini"))
        config.set_main_option("script_location", str(PROJECT_ROOT / "alembic"))
        heads = set(ScriptDirectory.from_config(config).get_heads())
        current = set(query("SELECT version_num FROM alembic_version"))
        if heads != current:
            raise ValueError("Alembic mismatch")
        return sorted(current)

    check("alembic", alembic)
    for name, key in (
        ("pipeline_state", "GROUNDTRUTH_PIPELINE_STATE_DIR"),
        ("release_output", "GROUNDTRUTH_RELEASE_OUTPUT_DIR"),
        ("backup_directory", "GROUNDTRUTH_BACKUP_DIR"),
    ):

        def directory(key=key):
            target = Path(os.environ[key]).resolve()
            if target.is_relative_to(PROJECT_ROOT.resolve()):
                raise ValueError("durable directory inside checkout")
            with tempfile.TemporaryFile(dir=target) as handle:
                handle.write(b"doctor")
                handle.seek(0)
                assert handle.read() == b"doctor"
            if shutil.disk_usage(target).free < minimum_free_gb * 1024**3:
                raise ValueError("insufficient free disk")
            return str(target)

        check(name, directory)

    def lock():
        with pipeline_lock("doctor"):
            return "available"

    check("pipeline_lock", lock)

    def watermark():
        value = verified_watermark(load_state())
        return str(value) if value else "bootstrap: no verified watermark yet"

    check("verified_watermark", watermark)

    def latest_release():
        release = load_state().get("last_verified_release_id")
        if not release:
            return "bootstrap: no verified release yet"
        path = (
            Path(os.environ["GROUNDTRUTH_RELEASE_OUTPUT_DIR"])
            / f"groundtruth-release-{release}.tar.gz"
        )
        if not path.is_file() or not Path(str(path) + ".sha256").is_file():
            raise ValueError("verified release missing")
        return release

    check("latest_verified_release", latest_release)

    def backup_age():
        backups = list(Path(os.environ["GROUNDTRUTH_BACKUP_DIR"]).glob("*.dump"))
        latest = max(backups, key=lambda p: p.stat().st_mtime)
        age = (datetime.now(UTC).timestamp() - latest.stat().st_mtime) / 3600
        if latest.stat().st_size == 0 or age > 24 * 8:
            raise ValueError("backup missing or older than eight days")
        return {"filename": latest.name, "age_hours": round(age, 2)}

    check("backup_recent", backup_age)
    return {
        "overall": "FAIL" if any(c["status"] == "FAIL" for c in checks) else "PASS",
        "checks": checks,
    }


@research_app.command("doctor")
def doctor(
    json_output: bool = typer.Option(False, "--json"),
    expected_sha: str | None = typer.Option(None),
    minimum_free_gb: float = typer.Option(20, min=1),
) -> None:
    result = doctor_checks(expected_sha=expected_sha, minimum_free_gb=minimum_free_gb)
    if json_output:
        print(json.dumps(result))
    else:
        console = Console()
        for item in result["checks"]:
            console.print(f"{item['name']:26} {item['status']:5} {item['detail']}")
        console.print(f"OVERALL                    {result['overall']}")
    if result["overall"] != "PASS":
        raise typer.Exit(1)


@research_app.command("backup")
def backup(label: str = typer.Option("manual")) -> None:
    from groundtruth.automation.backups import create_backup

    print(create_backup(label=label))
