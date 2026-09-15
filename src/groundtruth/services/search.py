"""Unified search across neighborhoods, streets, and complexes."""

from __future__ import annotations

import json
import re
import unicodedata
from functools import lru_cache

from sqlalchemy.orm import Session, joinedload

from groundtruth.analytics.corpus import active_corpus_dataframe
from groundtruth.config import get_settings
from groundtruth.gazetteers.canonical import canonical_neighborhood_meta, resolve_neighborhood_slug
from groundtruth.models.reference import Complex, District, Neighborhood, Street
from groundtruth.schemas.lookup import EntityType, SearchResponse, SearchResult

_MIN_SEARCH_LISTINGS = 10

_STRIP_PREFIX_RE = re.compile(
    r"^(rr\.?|rruga|rrugen|lagja|lagjen|lagjes|te|ne)\s+",
    re.IGNORECASE,
)


def _normalize(text: str) -> str:
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = text.lower().strip()
    text = _STRIP_PREFIX_RE.sub("", text)
    return re.sub(r"\s+", " ", text)


@lru_cache(maxsize=1)
def _load_aliases() -> dict[str, list[tuple[EntityType, str, str, str]]]:
    """Map normalized alias -> (entity_type, slug, display_name, parent_label)."""
    gaz_dir = get_settings().gazetteer_dir
    out: dict[str, list[tuple[EntityType, str, str, str]]] = {}

    nh_path = gaz_dir / "neighborhoods.json"
    if nh_path.exists():
        for row in json.loads(nh_path.read_text(encoding="utf-8")):
            meta = canonical_neighborhood_meta(row["slug"])
            slug = meta.canonical_slug
            name = meta.display_name
            for term in [row["name"], *row.get("aliases", [])]:
                key = _normalize(term)
                out.setdefault(key, []).append(
                    ("neighborhood", slug, name, row.get("city", "Prishtina"))
                )

    dist_path = gaz_dir / "districts.json"
    if dist_path.exists():
        for row in json.loads(dist_path.read_text(encoding="utf-8")):
            slug = row["slug"]
            name = row["name"]
            parent = row.get("neighborhood_slug", "")
            for term in [name, *row.get("aliases", [])]:
                key = _normalize(term)
                out.setdefault(key, []).append(("district", slug, name, parent))

    st_path = gaz_dir / "streets.json"
    if st_path.exists():
        for row in json.loads(st_path.read_text(encoding="utf-8")):
            slug = row["slug"]
            name = row["name"]
            parent = row.get("neighborhood_slug", "")
            for term in [name, *row.get("aliases", [])]:
                key = _normalize(term)
                out.setdefault(key, []).append(("street", slug, name, parent))

    cx_path = gaz_dir / "complexes.json"
    if cx_path.exists():
        for row in json.loads(cx_path.read_text(encoding="utf-8")):
            slug = row["slug"]
            name = row["name"]
            parent = row.get("neighborhood_slug", "")
            for term in [name, *row.get("aliases", [])]:
                key = _normalize(term)
                out.setdefault(key, []).append(("complex", slug, name, parent))

    return out


def _listing_counts(session: Session) -> dict[tuple[EntityType, str], int]:
    """Active corpus listing counts keyed by entity type and slug (all property types).

    Neighborhood counts merge canonical slug variants (e.g. Dragodan → Arbëria) and
    match ``total_listings`` on market lookup payloads.
    """
    from groundtruth.services.lookup_cache import cache_is_loaded, get_cached_listing_counts

    if cache_is_loaded():
        raw = get_cached_listing_counts()
        counts: dict[tuple[EntityType, str], int] = {}
        for key, n in raw.items():
            parts = key.split("/", 1)
            if len(parts) != 2:
                continue
            etype, slug = parts[0], parts[1]
            if etype == "neighborhood":
                canonical = resolve_neighborhood_slug(slug)
                if canonical != slug:
                    continue
                slug = canonical
            counts[(etype, slug)] = int(n)  # type: ignore[misc]
        return counts

    df = active_corpus_dataframe(session)
    counts = {}
    if df.empty:
        return counts

    nh_slugs = {r.id: r.slug for r in session.query(Neighborhood).all()}
    dist_slugs = {r.id: r.slug for r in session.query(District).all()}
    st_slugs = {r.id: r.slug for r in session.query(Street).all()}
    cx_slugs = {r.id: r.slug for r in session.query(Complex).all()}

    grouped = df[df["neighborhood_id"].notna()].groupby("neighborhood_id").size()
    for eid, n in grouped.items():
        slug = nh_slugs.get(int(eid))
        if slug:
            canonical = resolve_neighborhood_slug(slug)
            key = ("neighborhood", canonical)
            counts[key] = counts.get(key, 0) + int(n)

    for col, etype, slug_map in [
        ("district_id", "district", dist_slugs),
        ("street_id", "street", st_slugs),
        ("complex_id", "complex", cx_slugs),
    ]:
        grouped = df[df[col].notna()].groupby(col).size()
        for eid, n in grouped.items():
            slug = slug_map.get(int(eid))
            if slug:
                counts[(etype, slug)] = int(n)  # type: ignore[arg-type]
    return counts


def search_market(session: Session, query: str, limit: int = 10) -> SearchResponse:
    q = query.strip()
    if not q:
        return SearchResponse(query=q, results=[])

    q_norm = _normalize(q)
    single_char = len(q_norm) == 1
    counts = _listing_counts(session)
    aliases = _load_aliases()
    seen: set[tuple[EntityType, str]] = set()
    results: list[SearchResult] = []

    def add(
        etype: EntityType, slug: str, name: str, subtitle: str, reason: str, score: int
    ) -> None:
        key = (etype, slug)
        if key in seen:
            return
        seen.add(key)
        results.append(
            SearchResult(
                entity_type=etype,
                slug=slug,
                display_name=name,
                subtitle=subtitle,
                listings=counts.get(key, 0),
                match_reason=reason,
            )
        )

    scored: list[tuple[int, EntityType, str, str, str, str]] = []

    from groundtruth.services.lookup_cache import cache_is_loaded

    is_cached = cache_is_loaded()

    if not is_cached:
        for nh in session.query(Neighborhood).filter(Neighborhood.city == "Prishtina").all():
            canonical_slug = resolve_neighborhood_slug(nh.slug)
            if canonical_slug != nh.slug:
                continue
            meta = canonical_neighborhood_meta(canonical_slug)
            name_norm = _normalize(meta.display_name)
            if name_norm == q_norm:
                scored.append(
                    (
                        100,
                        "neighborhood",
                        meta.canonical_slug,
                        meta.display_name,
                        "Prishtina",
                        "exact",
                    )
                )
            elif name_norm.startswith(q_norm):
                scored.append(
                    (
                        80,
                        "neighborhood",
                        meta.canonical_slug,
                        meta.display_name,
                        "Prishtina",
                        "prefix",
                    )
                )
            elif q_norm in name_norm:
                scored.append(
                    (
                        60,
                        "neighborhood",
                        meta.canonical_slug,
                        meta.display_name,
                        "Prishtina",
                        "contains",
                    )
                )

        for dist in (
            session.query(District)
            .options(joinedload(District.neighborhood))
            .join(Neighborhood)
            .filter(Neighborhood.city == "Prishtina")
            .all()
        ):
            name_norm = _normalize(dist.name)
            sub = f"{dist.neighborhood.name} · Area" if dist.neighborhood else "District"
            if name_norm == q_norm:
                scored.append((96, "district", dist.slug, dist.name, sub, "exact"))
            elif name_norm.startswith(q_norm) or (not single_char and q_norm in name_norm):
                scored.append((72, "district", dist.slug, dist.name, sub, "prefix"))

        for st in (
            session.query(Street)
            .options(joinedload(Street.neighborhood))
            .join(Neighborhood)
            .filter(Neighborhood.city == "Prishtina")
            .all()
        ):
            name_norm = _normalize(st.name)
            sub = f"{st.neighborhood.name} · Street" if st.neighborhood else "Street"
            if name_norm == q_norm:
                scored.append((95, "street", st.slug, st.name, sub, "exact"))
            elif name_norm.startswith(q_norm) or (not single_char and q_norm in name_norm):
                scored.append((70, "street", st.slug, st.name, sub, "prefix"))

        for cx in (
            session.query(Complex)
            .options(joinedload(Complex.neighborhood), joinedload(Complex.district))
            .join(Neighborhood, Complex.neighborhood_id == Neighborhood.id, isouter=True)
            .filter((Neighborhood.city == "Prishtina") | (Complex.neighborhood_id.is_(None)))
            .all()
        ):
            name_norm = _normalize(cx.name)
            parts = []
            if cx.neighborhood:
                parts.append(cx.neighborhood.name)
            if getattr(cx, "district", None):
                parts.append(cx.district.name)
            sub = " · ".join(parts + ["Complex"]) if parts else "Complex"
            if name_norm == q_norm:
                scored.append((95, "complex", cx.slug, cx.name, sub, "exact"))
            elif name_norm.startswith(q_norm) or q_norm in name_norm:
                scored.append((70, "complex", cx.slug, cx.name, sub, "prefix"))

    for alias_key, entries in aliases.items():
        if q_norm == alias_key:
            match_score = 90
            reason = "alias"
        elif alias_key.startswith(q_norm):
            match_score = 65
            reason = "alias prefix"
        elif not single_char and q_norm in alias_key:
            match_score = 50
            reason = "alias contains"
        else:
            continue
        for etype, slug, name, parent in entries:
            subtitle = {
                "neighborhood": parent or "Prishtina",
                "district": f"{parent} · Area" if parent else "District",
                "street": f"{parent} · Street" if parent else "Street",
                "complex": f"{parent} · Complex" if parent else "Complex",
            }[etype]
            scored.append((match_score, etype, slug, name, subtitle, reason))

    scored.sort(key=lambda x: (-x[0], -counts.get((x[1], x[2]), 0)))
    for _, etype, slug, name, subtitle, reason in scored:
        if counts.get((etype, slug), 0) < _MIN_SEARCH_LISTINGS:
            continue
        add(etype, slug, name, subtitle, reason, 0)
        if len(results) >= limit:
            break

    return SearchResponse(query=q, results=results[:limit])


def run_public_search(q: str) -> SearchResponse:
    """Session-scoped search used by the public API route."""
    from groundtruth.database.session import get_session_factory

    session = get_session_factory()()
    try:
        return search_market(session, q)
    finally:
        session.close()
