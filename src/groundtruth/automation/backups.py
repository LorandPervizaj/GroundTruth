"""Local-only custom-format PostgreSQL backups with weekly/monthly retention."""

import os
import re
import subprocess
from datetime import UTC, datetime
from pathlib import Path


def retained_backups(paths: list[Path]) -> set[Path]:
    ordered = sorted(paths, key=lambda p: p.stat().st_mtime, reverse=True)
    weeks, months, keep = set(), set(), set()
    for path in ordered:
        stamp = datetime.fromtimestamp(path.stat().st_mtime, UTC)
        week, month = stamp.strftime("%G-W%V"), stamp.strftime("%Y-%m")
        if week in weeks or len(weeks) < 4:
            weeks.add(week)
            keep.add(path)
        if month not in months and len(months) < 3:
            months.add(month)
            keep.add(path)
    return keep


def create_backup(*, label: str = "manual") -> Path:
    if not re.fullmatch(r"[a-z0-9-]+", label):
        raise ValueError("invalid backup label")
    root = Path(os.environ["GROUNDTRUTH_BACKUP_DIR"])
    root.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    name = f"research-{stamp}-{label}.dump"
    partial, destination = root / (name + ".partial"), root / name
    container = os.environ["GROUNDTRUTH_POSTGRES_CONTAINER"]
    remote = f"/tmp/{name}"
    # The database password stays in the container's environment, not argv/logs.
    subprocess.run(
        [
            "docker",
            "exec",
            container,
            "sh",
            "-c",
            'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc -f "$1"',
            "backup",
            remote,
        ],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["docker", "cp", f"{container}:{remote}", str(partial)], check=True, capture_output=True
    )
    if partial.stat().st_size == 0:
        raise ValueError("empty backup")
    subprocess.run(
        ["docker", "exec", container, "pg_restore", "--list", remote],
        check=True,
        capture_output=True,
    )
    partial.replace(destination)
    subprocess.run(
        ["docker", "exec", container, "rm", "--", remote], check=True, capture_output=True
    )
    paths = list(root.glob("research-*.dump"))
    for path in set(paths) - retained_backups(paths):
        path.unlink()
    return destination
