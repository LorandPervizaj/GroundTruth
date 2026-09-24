"""Machine-readable automation result models."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from typing import Any, Literal

StageStatus = Literal["pending", "running", "passed", "warning", "failed", "skipped"]


def utc_now() -> datetime:
    return datetime.now(UTC)


@dataclass
class StageResult:
    name: str
    status: StageStatus = "pending"
    started_at: str | None = None
    finished_at: str | None = None
    duration_seconds: float | None = None
    blocking: bool = True
    counts: dict[str, int | float] = field(default_factory=dict)
    details: dict[str, Any] = field(default_factory=dict)
    error: str | None = None

    def start(self) -> None:
        self.status = "running"
        self.started_at = utc_now().isoformat()

    def finish(self, status: StageStatus, *, error: str | None = None) -> None:
        end = utc_now()
        self.finished_at = end.isoformat()
        self.status = status
        self.error = error
        if self.started_at:
            start = datetime.fromisoformat(self.started_at)
            self.duration_seconds = round((end - start).total_seconds(), 3)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class PipelineRunResult:
    run_id: str
    release_id: str
    started_at: str
    requested_days: int
    source_git_sha: str | None = None
    data_window_start: str | None = None
    data_through: str | None = None
    previous_release_id: str | None = None
    release_manifest_sha256: str | None = None
    release_bundle: str | None = None
    stages: list[StageResult] = field(default_factory=list)
    finished_at: str | None = None
    outcome: Literal["running", "verified", "warning", "failed"] = "running"

    def stage(self, name: str, *, blocking: bool = True) -> StageResult:
        result = StageResult(name=name, blocking=blocking)
        self.stages.append(result)
        return result

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
