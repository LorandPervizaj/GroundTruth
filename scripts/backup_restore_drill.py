"""Disposable Postgres backup/restore drill (no production volumes)."""

from __future__ import annotations

import gzip
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORK = ROOT / ".tmp" / "backup_restore_drill"
IMAGE = "postgres:16-alpine"
CONTAINER = f"metrik-backup-drill-{int(time.time())}"
USER = "drill"
PASSWORD = "drill_password"
DB = "groundtruth"


def run(cmd: list[str], **kwargs) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, check=True, **kwargs)


def cleanup() -> None:
    subprocess.run(["docker", "rm", "-f", CONTAINER], check=False, capture_output=True)
    if WORK.exists():
        shutil.rmtree(WORK, ignore_errors=True)


def main() -> int:
    cleanup()
    WORK.mkdir(parents=True, exist_ok=True)
    try:
        print(f"==> Starting disposable Postgres ({IMAGE})")
        run(
            [
                "docker",
                "run",
                "-d",
                "--name",
                CONTAINER,
                "-e",
                f"POSTGRES_USER={USER}",
                "-e",
                f"POSTGRES_PASSWORD={PASSWORD}",
                "-e",
                f"POSTGRES_DB={DB}",
                IMAGE,
            ],
            capture_output=True,
        )
        print("==> Waiting for readiness")
        for _ in range(40):
            ready = subprocess.run(
                ["docker", "exec", CONTAINER, "pg_isready", "-U", USER, "-d", DB],
                capture_output=True,
            )
            if ready.returncode == 0:
                break
            time.sleep(1)
        else:
            raise RuntimeError("Postgres did not become ready")

        print("==> Seeding fixture")
        seed = """
CREATE TABLE product_submissions_drill (
  id serial PRIMARY KEY,
  kind text NOT NULL,
  payload jsonb NOT NULL
);
INSERT INTO product_submissions_drill (kind, payload)
VALUES ('contact', '{"email":"drill@example.com","message":"restore-me"}');
"""
        run(
            ["docker", "exec", "-i", CONTAINER, "psql", "-U", USER, "-d", DB],
            input=seed.encode("utf-8"),
        )

        dump = WORK / "postgres_drill.sql.gz"
        print(f"==> Creating backup at {dump}")
        raw = run(
            [
                "docker",
                "exec",
                CONTAINER,
                "pg_dump",
                "-U",
                USER,
                "-d",
                DB,
                "--no-owner",
                "--no-acl",
            ],
            capture_output=True,
        )
        with gzip.open(dump, "wb") as fh:
            fh.write(raw.stdout)
        with gzip.open(dump, "rb") as fh:
            fh.read(16)
        print("backup_readable_ok")

        print("==> Dropping data and restoring")
        run(
            ["docker", "exec", "-i", CONTAINER, "psql", "-U", USER, "-d", DB],
            input=b"DROP TABLE product_submissions_drill;",
        )
        with gzip.open(dump, "rb") as fh:
            data = fh.read()
        run(
            ["docker", "exec", "-i", CONTAINER, "psql", "-U", USER, "-d", DB],
            input=data,
        )
        count = run(
            [
                "docker",
                "exec",
                CONTAINER,
                "psql",
                "-U",
                USER,
                "-d",
                DB,
                "-Atc",
                "SELECT count(*) FROM product_submissions_drill "
                "WHERE payload->>'email' = 'drill@example.com';",
            ],
            capture_output=True,
            text=True,
        ).stdout.strip()
        if count != "1":
            raise RuntimeError(f"Restore failed, count={count}")
        print(f"Restore OK - recovered row count={count}")

        print("==> Adversarial corrupt backup")
        corrupt = WORK / "postgres_drill_corrupt.sql.gz"
        corrupt.write_text("not-a-gzip", encoding="utf-8")
        try:
            with gzip.open(corrupt, "rb") as fh:
                fh.read()
            raise RuntimeError("Corrupt backup unexpectedly readable")
        except OSError:
            print("Corrupt backup correctly rejected")

        print("BACKUP_RESTORE_DRILL_PASSED")
        return 0
    finally:
        cleanup()


if __name__ == "__main__":
    sys.exit(main())
