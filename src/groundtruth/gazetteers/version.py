"""Fingerprint active JSON, YAML and typed market-reference inputs."""

from __future__ import annotations

import hashlib
from pathlib import Path

from groundtruth.config import get_settings

_GAZETTEER_FILES = (
    "neighborhoods.json",
    "districts.json",
    "streets.json",
    "complexes.json",
    "building_aliases.json",
    "draft/prishtina_location_tree.yaml",
    "market_relationships.json",
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


def compute_legacy_gazetteer_version(gazetteer_dir: Path | None = None) -> str:
    """Reproduce historical five-JSON hashes; do not rewrite stored versions."""
    directory = gazetteer_dir or get_settings().gazetteer_dir
    digest = hashlib.sha256()
    for filename in _GAZETTEER_FILES[:5]:
        digest.update(filename.encode("utf8"))
        path = directory / filename
        if path.exists():
            digest.update(path.read_bytes())
    return digest.hexdigest()[:12]
