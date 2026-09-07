"""Manual Facebook group post sampling (B3)."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from groundtruth.config import PROJECT_ROOT
from groundtruth.schemas.facebook import FacebookGroupSample

REGISTRY_PATH = PROJECT_ROOT / "data" / "sources" / "facebook-groups" / "registry.json"
SAMPLES_DIR = PROJECT_ROOT / "data" / "sources" / "facebook-groups" / "samples"


def load_group_registry(path: Path | None = None) -> dict:
    target = path or REGISTRY_PATH
    if not target.exists():
        return {"groups": []}
    return json.loads(target.read_text(encoding="utf-8"))


def group_name(group_id: str, registry: dict | None = None) -> str | None:
    reg = registry or load_group_registry()
    for group in reg.get("groups", []):
        if group.get("id") == group_id:
            return str(group.get("name") or group_id)
    return None


def record_group_sample(sample: FacebookGroupSample) -> Path:
    """Append one group observation to today's sample file."""
    SAMPLES_DIR.mkdir(parents=True, exist_ok=True)
    day = (sample.sampled_at or datetime.now(UTC)).date().isoformat()
    path = SAMPLES_DIR / f"{day}.jsonl"

    if not sample.group_name:
        sample = sample.model_copy(update={"group_name": group_name(sample.group_id)})

    row = sample.model_dump(mode="json", exclude_none=True)
    if "sampled_at" not in row:
        row["sampled_at"] = datetime.now(UTC).isoformat()

    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    return path


def load_group_samples(*, days: int = 90) -> list[dict]:
    if not SAMPLES_DIR.exists():
        return []
    cutoff = datetime.now(UTC).date().toordinal() - days
    rows: list[dict] = []
    for path in sorted(SAMPLES_DIR.glob("*.jsonl")):
        try:
            day_ord = datetime.fromisoformat(path.stem).date().toordinal()
        except ValueError:
            continue
        if day_ord < cutoff:
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return rows


def sample_count() -> int:
    return len(load_group_samples(days=365))
