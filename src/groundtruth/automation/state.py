"""Durable state, verified watermarks, and overlap prevention."""

from __future__ import annotations

import json
import os
import socket
from contextlib import AbstractContextManager
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from groundtruth.config import PROJECT_ROOT

MIN_LOOKBACK_DAYS = 7
MAX_LOOKBACK_DAYS = 56


def state_dir() -> Path:
    configured = os.getenv("GROUNDTRUTH_PIPELINE_STATE_DIR")
    return (
        Path(configured)
        if configured
        else PROJECT_ROOT / "reports" / "generated" / "pipeline_state"
    )


def state_path() -> Path:
    return state_dir() / "state.json"


def load_state(path: Path | None = None) -> dict[str, Any]:
    target = path or state_path()
    if not target.is_file():
        return {}
    payload = json.loads(target.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"pipeline state must be an object: {target}")
    return payload


def save_state(payload: dict[str, Any], path: Path | None = None) -> Path:
    target = path or state_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    temporary.replace(target)
    return target


def calculate_lookback_days(
    watermark: date | None,
    *,
    today: date | None = None,
    minimum: int = MIN_LOOKBACK_DAYS,
    maximum: int = MAX_LOOKBACK_DAYS,
) -> int:
    """Cover from the last verified date with one-day overlap, within safety bounds."""
    current = today or datetime.now(UTC).date()
    if watermark is None:
        return minimum
    required = (current - watermark).days + 1
    return max(minimum, min(maximum, required))


def verified_watermark(payload: dict[str, Any]) -> date | None:
    raw = payload.get("last_verified_data_through")
    return date.fromisoformat(str(raw)) if raw else None


@dataclass
class PipelineLock(AbstractContextManager["PipelineLock"]):
    path: Path
    run_id: str
    acquired: bool = False
    _descriptor: int | None = None

    def __enter__(self) -> PipelineLock:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        body = json.dumps(
            {
                "run_id": self.run_id,
                "pid": os.getpid(),
                "acquired_at": datetime.now(UTC).isoformat(),
            }
        )
        descriptor = os.open(self.path, os.O_CREAT | os.O_RDWR, 0o600)
        try:
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(descriptor, msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            os.close(descriptor)
            raise RuntimeError(f"another weekly release holds {self.path}") from exc
        try:
            metadata = json.loads(body)
            metadata["host"] = socket.gethostname()
            os.ftruncate(descriptor, 0)
            os.write(descriptor, json.dumps(metadata).encode("utf-8"))
            os.fsync(descriptor)
        except BaseException:
            os.close(descriptor)
            raise
        self._descriptor = descriptor
        self.acquired = True
        return self

    def __exit__(self, *args: object) -> None:
        if self.acquired:
            # Never unlink: replacing an inode can allow two independent locks.
            # Closing releases the OS lock, including on abrupt process death.
            os.close(self._descriptor)
            self._descriptor = None
            self.acquired = False


def pipeline_lock(run_id: str, directory: Path | None = None) -> PipelineLock:
    return PipelineLock((directory or state_dir()) / "weekly-release.lock", run_id)
