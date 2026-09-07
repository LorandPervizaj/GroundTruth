"""Load Prishtina location tree from YAML for hierarchical resolution."""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from groundtruth.config import get_settings
from groundtruth.gazetteers.loader import GazetteerService

STREET_COMPLEX_PARENT_DISTRICTS = frozenset({"rruga-b", "rruga-c"})


@dataclass(frozen=True)
class TreeComplex:
    slug: str
    name: str
    neighborhood_slug: str
    district_slug: str | None
    aliases: tuple[str, ...] = ()
    requires_parent: str | None = None


@dataclass(frozen=True)
class TreeDistrict:
    slug: str
    name: str
    neighborhood_slug: str
    aliases: tuple[str, ...] = ()
    district_type: str = "district"


@dataclass(frozen=True)
class TreeNeighborhood:
    slug: str
    name: str
    aliases: tuple[str, ...] = ()
    gazetteer_slugs: tuple[str, ...] = ()
    vague_terms: tuple[str, ...] = ()


@dataclass
class LocationTree:
    neighborhoods: dict[str, TreeNeighborhood] = field(default_factory=dict)
    districts: dict[str, TreeDistrict] = field(default_factory=dict)
    complexes: dict[str, TreeComplex] = field(default_factory=dict)
    gazetteer_to_neighborhood: dict[str, str] = field(default_factory=dict)
    ambiguous_complexes: dict[str, frozenset[str]] = field(default_factory=dict)


def _terms(*parts: str | None) -> tuple[str, ...]:
    out: list[str] = []
    for part in parts:
        if part:
            out.append(part)
    return tuple(out)


@lru_cache(maxsize=1)
def load_location_tree() -> LocationTree:
    settings = get_settings()
    path = settings.gazetteer_dir / "draft" / "prishtina_location_tree.yaml"
    if not path.exists():
        path = (
            Path(__file__).resolve().parents[3]
            / "data"
            / "gazetteers"
            / "draft"
            / "prishtina_location_tree.yaml"
        )
    raw: dict[str, Any] = yaml.safe_load(path.read_text(encoding="utf-8"))
    tree = LocationTree()

    resolution = raw.get("resolution", {})
    for item in resolution.get("rules", {}).get("ambiguous_complex", []):
        tree.ambiguous_complexes[item["slug"]] = frozenset(item.get("valid_parents", []))

    for nh in raw["city"]["neighborhoods"]:
        slug = nh["slug"]
        gaz_slugs = tuple(nh.get("gazetteer_slugs") or [])
        aliases = tuple(nh.get("aliases") or [])
        vague = (slug, *aliases)
        if slug == "matiqan":
            vague = ("mati", "matiqan", "matican", "matican")
        if slug == "bregu-i-diellit":
            vague = ("bregu", "bregu i diellit", *aliases)
        tree.neighborhoods[slug] = TreeNeighborhood(
            slug=slug,
            name=nh["name"],
            aliases=aliases,
            gazetteer_slugs=gaz_slugs,
            vague_terms=vague,
        )
        for gs in gaz_slugs:
            tree.gazetteer_to_neighborhood[gs] = slug
        tree.gazetteer_to_neighborhood[slug] = slug

        for item in nh.get("districts") or []:
            dslug = item["slug"]
            tree.districts[dslug] = TreeDistrict(
                slug=dslug,
                name=item["name"],
                neighborhood_slug=slug,
                aliases=tuple(item.get("aliases") or ()),
                district_type=item.get("type", "district"),
            )
            for cx in item.get("complexes") or []:
                cslug = cx["slug"]
                tree.complexes[cslug] = TreeComplex(
                    slug=cslug,
                    name=cx["name"],
                    neighborhood_slug=slug,
                    district_slug=dslug,
                    aliases=tuple(cx.get("aliases") or ()),
                    requires_parent=cx.get("requires_parent"),
                )
        for cx in nh.get("complexes_direct") or []:
            cslug = cx["slug"]
            tree.complexes[cslug] = TreeComplex(
                slug=cslug,
                name=cx["name"],
                neighborhood_slug=slug,
                district_slug=None,
                aliases=tuple(cx.get("aliases") or ()),
                requires_parent=cx.get("requires_parent"),
            )

    return tree


def normalize_text(text: str) -> str:
    return GazetteerService._normalize(text)
