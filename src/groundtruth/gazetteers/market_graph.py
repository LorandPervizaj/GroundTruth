"""Typed product-market relationships, independent of legacy scalar DB parents."""

import json
from functools import lru_cache

from groundtruth.config import get_settings


@lru_cache(maxsize=1)
def load_market_graph() -> dict:
    path = get_settings().gazetteer_dir / "market_relationships.json"
    graph = json.loads(path.read_text(encoding="utf8"))
    for child in graph["parents"]:
        seen = set()
        pending = list(graph["parents"][child])
        while pending:
            node = pending.pop()
            if node == child:
                raise ValueError("Market parent cycle: " + child)
            if node not in seen:
                seen.add(node)
                pending.extend(graph["parents"].get(node, []))
    return graph


def canonical_market_slug(slug: str | None) -> str | None:
    redirects = load_market_graph()["canonical_redirects"]
    return redirects.get(slug, slug)


def parent_market_slugs(slug: str | None) -> tuple[str, ...]:
    return tuple(load_market_graph()["parents"].get(slug, []))


def market_identity_for_reference(kind: str, slug: str) -> str:
    """Interpret legacy records without changing their IDs or foreign keys."""
    graph = load_market_graph()
    key = f"{kind}:{slug}"
    if key in graph.get("entity_redirects", {}):
        return graph["entity_redirects"][key]
    if kind == "market_neighborhood":
        return f"market_neighborhood:{canonical_market_slug(slug)}"
    return key


def market_children(parent_slug: str) -> tuple[dict, ...]:
    """Navigation references share a single canonical entity across parents."""
    graph = load_market_graph()
    return tuple(
        {"entity_id": f"market_subarea:{child}", **graph["entities"][f"market_subarea:{child}"]}
        for child, parents in graph["parents"].items()
        if parent_slug in parents
    )


def distinct_rollup_memberships(rows: list[tuple[str, str]]) -> dict[str, set[str]]:
    """One underlying pricing-unit key may occur in overlapping parent sets.

    Combined totals must use set union, never sum overlapping parent counts.
    """
    memberships: dict[str, set[str]] = {}
    for unit, slug in rows:
        for parent in parent_market_slugs(slug) or (canonical_market_slug(slug),):
            memberships.setdefault(parent, set()).add(unit)
    return memberships
