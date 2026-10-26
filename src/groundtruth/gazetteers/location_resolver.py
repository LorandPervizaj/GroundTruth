"""Hierarchical location resolution: city → neighborhood → district → complex."""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache

from groundtruth.gazetteers.location_tree import (
    LocationTree,
    load_location_tree,
    normalize_text,
)
from groundtruth.gazetteers.market_graph import parent_market_slugs

# Complex names that appear in marketing copy (brand names), not as locations.
DESCRIPTION_COMPLEX_FALSE_POSITIVES = frozenset({"ontex"})

# Ambiguous complexes share a marketing name but use different slugs per parent NH.
AMBIGUOUS_COMPLEX_SLUG_BY_PARENT: dict[str, dict[str, str]] = {
    "beni-dona": {
        "ulpiana": "beni-dona",
        "pejton-lakrishte": "benidona",
    },
}


@dataclass
class LocationResolution:
    neighborhood_slug: str | None = None
    district_slug: str | None = None
    complex_slug: str | None = None
    invalid_location: bool = False
    invalid_reason: str | None = None
    match_type: str = "missing"
    vague_nh_only: bool = False
    market_entity_id: str | None = None
    market_subarea_slug: str | None = None
    parent_relationships: tuple[str, ...] = ()
    physical_street_slug: str | None = None
    proximity_mentions: tuple[str, ...] = ()


def location_term_matches(norm: str, term: str) -> bool:
    """Whole-token location assertions; nearby/developer claims are enrichment."""
    for match in re.finditer(r"(?<!\w)" + re.escape(term) + r"(?!\w)", norm):
        prefix = norm[max(0, match.start() - 90) : match.start()]
        if re.search(
            r"(?:afer|prane|perballe|opposite|near|pamje nga|rrug\w* per|\d+\s*min\w* nga|ndertuar nga|ndertim nga|investitor)\s+(?:(?:te|e|i|t|sh|f|m|u|park\w*|shkoll\w*|kompleks\w*)\s+){0,5}$",
            prefix,
        ):
            continue
        if term in {"germia", "germi", "germise"} and re.search(r"park\w*\s+(?:te\s+)?$", prefix):
            continue
        if term in {"germia", "germi", "germise"} and re.match(
            r"\s+park\w*\b", norm[match.end() :]
        ):
            continue
        return True
    return False


@dataclass
class _Hit:
    kind: str
    slug: str
    term: str
    length: int
    neighborhood_slug: str | None = None
    district_slug: str | None = None


def resolve_listing_location(
    resolver: LocationResolver,
    *,
    title: str | None = None,
    neighborhood_raw: str | None = None,
    street_raw: str | None = None,
    complex_raw: str | None = None,
    description: str | None = None,
    city: str | None = None,
) -> LocationResolution:
    """Prefer title/address fields over description to avoid brand-name false positives."""
    original = normalize_text(" ".join(filter(None, [title, description])))
    fields = [title]
    for value in [neighborhood_raw, street_raw, complex_raw]:
        if not value:
            continue
        term = normalize_text(value)
        if (
            original
            and re.search(r"(?<!\w)" + re.escape(term) + r"(?!\w)", original)
            and not location_term_matches(original, term)
        ):
            continue
        if (
            re.fullmatch(r"(?:rruga|rr) [abc]", term)
            and original
            and not location_term_matches(original, term)
        ):
            continue
        fields.append(value)
    structured = " ".join(filter(None, fields))
    structured_res = LocationResolution()
    if structured.strip():
        structured_res = resolver.resolve(structured, city=city)
        if (
            structured_res.neighborhood_slug
            or structured_res.district_slug
            or structured_res.complex_slug
        ) and not structured_res.invalid_location:
            if description:
                refined = resolver.resolve(
                    " ".join(filter(None, [structured, description])), city=city
                )
                if (
                    refined.neighborhood_slug == structured_res.neighborhood_slug
                    and refined.district_slug
                    and not refined.complex_slug
                ):
                    return refined
            return structured_res

    full = " ".join(filter(None, [structured, description]))
    if not full.strip():
        return LocationResolution()

    full_res = resolver.resolve(full, city=city)
    if (
        full_res.complex_slug
        and full_res.complex_slug in DESCRIPTION_COMPLEX_FALSE_POSITIVES
        and structured.strip()
        and not _complex_term_in_text(structured, full_res.complex_slug, resolver)
    ):
        return LocationResolution(
            neighborhood_slug=structured_res.neighborhood_slug,
            district_slug=structured_res.district_slug,
            match_type=structured_res.match_type if structured_res.neighborhood_slug else "missing",
            vague_nh_only=structured_res.vague_nh_only,
        )
    return full_res


def _complex_term_in_text(text: str, complex_slug: str, resolver: LocationResolver) -> bool:
    cx = resolver._tree.complexes.get(complex_slug)
    if not cx:
        return False
    norm = normalize_text(text)
    for term in (cx.name, *cx.aliases):
        t = normalize_text(term)
        if t and len(t) >= 4 and t in norm:
            return True
    return False


class LocationResolver:
    def __init__(self, tree: LocationTree | None = None) -> None:
        self._tree = tree or load_location_tree()
        self._scan_unfiltered = lru_cache(maxsize=16384)(self._scan_unfiltered)

    def resolve(self, text: str, *, city: str | None = None) -> LocationResolution:
        if city and normalize_text(city) not in ("prishtina", "pristina", "prishtine"):
            return LocationResolution()

        norm = normalize_text(text)
        if not norm:
            return LocationResolution()

        hits = self._scan(norm)
        if not hits:
            return LocationResolution(
                proximity_mentions=tuple(
                    sorted(
                        {
                            h.term
                            for h in self._scan_unfiltered(norm)
                            if not location_term_matches(norm, h.term)
                        }
                    )
                )
            )

        complex_hit = self._best(hits, "complex")
        district_hit = self._best(hits, "district")
        nh_hit = self._best(hits, "neighborhood")
        text_nh = self._text_neighborhood_slug(nh_hit, district_hit)

        nh_slug: str | None = None
        district_slug: str | None = None
        complex_slug: str | None = None

        if complex_hit:
            cx = self._tree.complexes[complex_hit.slug]
            if cx.slug in self._tree.ambiguous_complexes:
                valid_parents = self._tree.ambiguous_complexes[cx.slug]
                parent_slug = (
                    text_nh
                    if text_nh in valid_parents
                    else self._parent_in_text(norm, valid_parents)
                )
                if parent_slug is None:
                    return LocationResolution(
                        invalid_location=True,
                        invalid_reason=f"{cx.name} requires parent neighborhood in text",
                        complex_slug=cx.slug,
                    )
                nh_slug = parent_slug
                complex_slug = self._ambiguous_complex_slug(cx.slug, parent_slug)
                cx = self._tree.complexes.get(complex_slug, cx)
            elif text_nh:
                complex_hits = [h for h in hits if h.kind == "complex"]
                under_text = [
                    h
                    for h in complex_hits
                    if self._canonical_neighborhood(self._tree.complexes[h.slug].neighborhood_slug)
                    == text_nh
                ]
                if under_text:
                    chosen = max(under_text, key=lambda h: h.length)
                    cx = self._tree.complexes[chosen.slug]
                    nh_slug = text_nh
                    complex_slug = cx.slug
                elif self._canonical_neighborhood(cx.neighborhood_slug) == text_nh:
                    nh_slug = text_nh
                    complex_slug = cx.slug
                else:
                    nh_slug = text_nh
                    complex_slug = None
                    cx = None
            else:
                nh_slug = cx.neighborhood_slug
                complex_slug = cx.slug
            if cx and cx.district_slug:
                district_slug = cx.district_slug
        if district_hit and not district_slug:
            d = self._tree.districts[district_hit.slug]
            district_slug = d.slug
            nh_slug = nh_slug or self._canonical_neighborhood(d.neighborhood_slug)
        if nh_hit and not nh_slug:
            nh_slug = self._canonical_neighborhood(nh_hit.slug)

        if complex_slug == "royal-mall" and district_slug != "rruga-b":
            district_slug = "rruga-b"
            nh_slug = nh_slug or "matiqan"
        if complex_slug == "royal-city":
            nh_slug = "spitali"
            district_slug = None

        vague = False
        if nh_slug and not district_slug and not complex_slug:
            nh = self._tree.neighborhoods.get(nh_slug)
            if nh and self._only_vague_nh(norm, nh):
                vague = True

        if nh_slug and district_slug:
            d = self._tree.districts.get(district_slug)
            if d and d.neighborhood_slug != nh_slug:
                district_slug = None

        match_type = "missing"
        if complex_slug:
            match_type = "complex"
        elif district_slug:
            match_type = "district"
        elif nh_slug:
            match_type = "neighborhood"

        result = LocationResolution(
            neighborhood_slug=nh_slug,
            district_slug=district_slug,
            complex_slug=complex_slug,
            match_type=match_type,
            vague_nh_only=vague,
        )
        subarea = district_slug or (nh_slug if parent_market_slugs(nh_slug) else None)
        result.market_subarea_slug = subarea
        result.parent_relationships = parent_market_slugs(subarea) or (
            (nh_slug,) if subarea and nh_slug else ()
        )
        result.market_entity_id = (
            ("market_subarea:" + subarea)
            if subarea
            else ("market_neighborhood:" + nh_slug)
            if nh_slug
            else None
        )
        road = re.search(r"\b(?:adresa|adresen|rruga fizike)\s+(?:rruga|rr)\s+([abc])\b", norm)
        if road:
            result.physical_street_slug = "rruga-" + road[1]
        result.proximity_mentions = tuple(
            sorted(
                {
                    h.term
                    for h in self._scan_unfiltered(norm)
                    if not location_term_matches(norm, h.term)
                }
            )
        )
        return result

    def _scan(self, norm: str) -> list[_Hit]:
        hits = self._scan_unfiltered(norm)
        result = []
        for hit in hits:
            if not location_term_matches(norm, hit.term):
                continue
            if (
                hit.kind == "complex"
                and hit.slug in {"royal-mall", "maxi-24", "fivestar", "tregtia"}
                and not re.search(
                    r"\b(?:(?:ne )?kompleks(?:in|i|it)?|brenda kompleks(?:it)?|ne objekt(?:in)?|banesat e)\s+"
                    + re.escape(hit.term)
                    + r"\b",
                    norm,
                )
            ):
                continue
            result.append(hit)
        return result

    def _scan_unfiltered(self, norm: str) -> list[_Hit]:
        hits: list[_Hit] = []
        for slug, nh in self._tree.neighborhoods.items():
            for term in (nh.name, slug, *nh.aliases):
                t = normalize_text(term)
                if t and f" {t} " in f" {norm} ":
                    hits.append(_Hit("neighborhood", slug, t, len(t)))
        for slug, gs in self._tree.gazetteer_to_neighborhood.items():
            t = normalize_text(slug.replace("-", " "))
            if t and f" {t} " in f" {norm} ":
                hits.append(_Hit("neighborhood", gs, t, len(t)))
        for slug, d in self._tree.districts.items():
            for term in (d.name, slug.replace("-", " "), *d.aliases):
                t = normalize_text(term)
                if not t or len(t) < 3:
                    continue
                if f" {t} " in f" {norm} ":
                    hits.append(
                        _Hit("district", slug, t, len(t), neighborhood_slug=d.neighborhood_slug)
                    )
        for slug, cx in self._tree.complexes.items():
            for term in (cx.name, *cx.aliases):
                t = normalize_text(term)
                if not t or len(t) < 4:
                    continue
                if f" {t} " in f" {norm} ":
                    hits.append(
                        _Hit(
                            "complex",
                            slug,
                            t,
                            len(t),
                            neighborhood_slug=cx.neighborhood_slug,
                            district_slug=cx.district_slug,
                        )
                    )
        return hits

    def _best(self, hits: list[_Hit], kind: str) -> _Hit | None:
        filtered = [h for h in hits if h.kind == kind]
        if not filtered:
            return None
        return max(filtered, key=lambda h: h.length)

    def _canonical_neighborhood(self, slug: str) -> str:
        return self._tree.gazetteer_to_neighborhood.get(slug, slug)

    def _text_neighborhood_slug(
        self,
        nh_hit: _Hit | None,
        district_hit: _Hit | None,
    ) -> str | None:
        if nh_hit:
            return self._canonical_neighborhood(nh_hit.slug)
        if district_hit:
            d = self._tree.districts[district_hit.slug]
            return self._canonical_neighborhood(d.neighborhood_slug)
        return None

    def _ambiguous_complex_slug(self, slug: str, parent_slug: str) -> str:
        return AMBIGUOUS_COMPLEX_SLUG_BY_PARENT.get(slug, {}).get(parent_slug, slug)

    def _parent_in_text(self, norm: str, valid_parents: frozenset[str]) -> str | None:
        candidates: list[tuple[int, str]] = []
        for slug in valid_parents:
            nh = self._tree.neighborhoods.get(slug)
            if not nh:
                continue
            for term in (nh.name, slug.replace("-", " "), *nh.aliases):
                t = normalize_text(term)
                if t and len(t) >= 3 and location_term_matches(norm, t):
                    candidates.append((len(t), slug))
            for gs in nh.gazetteer_slugs:
                t = normalize_text(gs.replace("-", " "))
                if t and len(t) >= 3 and location_term_matches(norm, t):
                    candidates.append((len(t), slug))
        if not candidates:
            return None
        return max(candidates)[1]

    def _only_vague_nh(self, norm: str, nh) -> bool:
        for term in nh.vague_terms:
            t = normalize_text(term)
            if t and t in norm:
                for d in self._tree.districts.values():
                    if d.neighborhood_slug != nh.slug:
                        continue
                    for dt in (d.name, *d.aliases):
                        if normalize_text(dt) in norm:
                            return False
                for cx in self._tree.complexes.values():
                    if cx.neighborhood_slug != nh.slug:
                        continue
                    for ct in (cx.name, *cx.aliases):
                        if normalize_text(ct) in norm:
                            return False
                return True
        return False
