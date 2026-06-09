"""Compute a deterministic version hash for gazetteer JSON files."""

from __future__ import annotations

import hashlib
from pathlib import Path

from groundtruth.config import get_settings

_GAZETTEER_FILES = (
    "neighborhoods.json",
    "streets.json",
    "complexes.json",
    "building_aliases.json",
)


def compute_gazetteer_version(gazetteer_dir: Path | None = None) -> str:
    """Return a short hash identifying the current gazetteer file contents."""
    directory = gazetteer_dir or get_settings().gazetteer_dir
    digest = hashlib.sha256()
    for filename in _GAZETTEER_FILES:
        path = directory / filename
        digest.update(filename.encode("utf-8"))
        if path.exists():
            digest.update(path.read_bytes())
    return digest.hexdigest()[:12]
