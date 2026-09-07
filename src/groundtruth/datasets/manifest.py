"""Frozen dataset manifest loader."""

from __future__ import annotations

import json
from datetime import datetime
from functools import lru_cache
from typing import Any

from groundtruth.config import PROJECT_ROOT

_DATASETS_DIR = PROJECT_ROOT / "data" / "datasets"


@lru_cache
def load_frozen_dataset_manifest() -> dict[str, Any] | None:
    """Return the newest frozen dataset manifest (prefers v2.0 over v1.0)."""
    candidates = sorted(_DATASETS_DIR.glob("dataset_v*.json"), reverse=True)
    for path in candidates:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if data.get("dataset_version"):
            return data
    return None


def frozen_dataset_version() -> str:
    manifest = load_frozen_dataset_manifest()
    if manifest:
        return str(manifest.get("dataset_version", "live"))
    return "live"


def frozen_dataset_fingerprint() -> str | None:
    manifest = load_frozen_dataset_manifest()
    if not manifest:
        return None
    fingerprints = manifest.get("fingerprints") or {}
    return fingerprints.get("dataset_hash")


def frozen_at() -> datetime | None:
    manifest = load_frozen_dataset_manifest()
    if not manifest or not manifest.get("frozen_at"):
        return None
    raw = manifest["frozen_at"]
    if isinstance(raw, str):
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    return None


def manifest_quality() -> dict[str, Any]:
    manifest = load_frozen_dataset_manifest()
    if not manifest:
        return {}
    return dict(manifest.get("quality") or {})
