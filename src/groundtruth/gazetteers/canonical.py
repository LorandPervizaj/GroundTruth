"""Canonical neighborhood names — merge portal variants to one market slug."""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache

from groundtruth.config import get_settings


@dataclass(frozen=True)
class CanonicalNeighborhood:
    canonical_slug: str
    display_name: str
    also_known_as: tuple[str, ...]


@lru_cache(maxsize=1)
def _neighborhood_rows() -> tuple[dict[str, dict], dict[str, str]]:
    path = get_settings().gazetteer_dir / "neighborhoods.json"
    rows: list[dict] = json.loads(path.read_text(encoding="utf-8"))
    by_slug = {row["slug"]: row for row in rows}
    redirect = {
        row["slug"]: row["canonical_slug"]
        for row in rows
        if row.get("canonical_slug") and row["canonical_slug"] != row["slug"]
    }
    return by_slug, redirect


def resolve_neighborhood_slug(slug: str) -> str:
    """Map a neighborhood slug (or merged alias slug) to its canonical slug."""
    _, redirect = _neighborhood_rows()
    return redirect.get(slug, slug)


def canonical_neighborhood_meta(slug: str) -> CanonicalNeighborhood:
    by_slug, redirect = _neighborhood_rows()
    canonical_slug = redirect.get(slug, slug)
    canonical = by_slug.get(canonical_slug)
    if not canonical:
        return CanonicalNeighborhood(canonical_slug=slug, display_name=slug, also_known_as=())

    display = canonical["name"]
    aliases: set[str] = set()
    for alias in canonical.get("aliases", []):
        if alias and alias != display:
            aliases.add(alias)
    for row in by_slug.values():
        if row.get("canonical_slug") == canonical_slug and row["slug"] != canonical_slug:
            if row["name"] != display:
                aliases.add(row["name"])
            for alias in row.get("aliases", []):
                if alias and alias != display:
                    aliases.add(alias)

    return CanonicalNeighborhood(
        canonical_slug=canonical_slug,
        display_name=display,
        also_known_as=tuple(sorted(aliases)),
    )


def slugs_for_canonical(canonical_slug: str) -> list[str]:
    """All neighborhood slugs that resolve to this canonical slug."""
    by_slug, redirect = _neighborhood_rows()
    slugs = [canonical_slug]
    for slug, target in redirect.items():
        if target == canonical_slug:
            slugs.append(slug)
    if canonical_slug not in by_slug:
        return slugs
    return sorted(set(slugs))
