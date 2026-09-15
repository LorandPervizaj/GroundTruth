"""Disk-backed lookup cache — instant API boot without corpus warm-up."""

from __future__ import annotations

import json
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from groundtruth.analytics.annual_export import corpus_last_updated
from groundtruth.claims.hashes import sha256_file
from groundtruth.config import get_settings
from groundtruth.datasets.manifest import frozen_dataset_fingerprint, frozen_dataset_version
from groundtruth.gazetteers.canonical import resolve_neighborhood_slug, slugs_for_canonical
from groundtruth.logging import get_logger
from groundtruth.schemas.lookup import CorpusMeta, MarketLookup, NeighborhoodMarketSummary

logger = get_logger(__name__)

_cache_lock = threading.Lock()
_memory: dict[str, dict[str, Any]] = {}
_manifest: dict[str, Any] | None = None
_listing_counts: dict[str, int] = {}
_markets: list[dict[str, Any]] = []
_neighborhood_options: list[dict[str, Any]] = []


def lookup_cache_dir() -> Path:
    return get_settings().reports_generated_dir / "lookup_cache"


def _cache_key(entity_type: str, slug: str) -> str:
    return f"{entity_type}/{slug}"


def _search_listing_count(payload: dict[str, Any]) -> int:
    """All active corpus listings for this entity (every property type)."""
    if payload.get("total_listings") is not None:
        return int(payload["total_listings"])
    pulse = payload.get("pulse") or {}
    apt = int(pulse.get("active_listings") or pulse.get("inventory") or 0)
    sale_types = payload.get("sale_by_property_type") or []
    sale_other = sum(int(row.get("listings") or 0) for row in sale_types)
    return apt + sale_other


def load_lookup_cache_from_disk() -> int:
    """Load precomputed lookup JSON into memory. Returns entry count."""
    global _memory, _manifest, _listing_counts, _markets, _neighborhood_options
    base = lookup_cache_dir()
    manifest_path = base / "manifest.json"
    if not manifest_path.is_file():
        logger.info("lookup_cache_missing", path=str(manifest_path))
        return 0

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    loaded: dict[str, dict[str, Any]] = {}
    counts: dict[str, int] = {}
    for entry in manifest.get("entries", []):
        rel = entry.get("path")
        if not rel:
            continue
        path = base / rel
        if not path.is_file():
            continue
        key = _cache_key(entry["entity_type"], entry["slug"])
        payload = json.loads(path.read_text(encoding="utf-8"))
        loaded[key] = payload
        counts[key] = _search_listing_count(payload)

    with _cache_lock:
        _memory = loaded
        _manifest = manifest
        _listing_counts = counts
        _markets = list(manifest.get("markets") or [])
        _neighborhood_options = list(manifest.get("neighborhood_options") or [])
        if not _neighborhood_options and _markets:
            _neighborhood_options = [
                {
                    "name": m["name"],
                    "rent_listings": int(m.get("rent_listings") or 0),
                    "sale_listings": int(m.get("sale_listings") or 0),
                    "estimate_ready": bool(m.get("estimate_ready", False)),
                    "sale_estimate_ready": int(m.get("sale_listings") or 0) >= 30,
                }
                for m in _markets
                if m.get("name")
            ]

    from groundtruth.analytics.valuation import hydrate_comparables_from_disk

    if manifest.get("corpus_revision"):
        hydrated = hydrate_comparables_from_disk(base, manifest.get("corpus_revision"))
        if hydrated:
            logger.info("comparables_disk_cache_loaded")

    logger.info(
        "lookup_cache_loaded",
        entries=len(loaded),
        built_at=manifest.get("built_at"),
        corpus_revision=manifest.get("corpus_revision"),
    )
    return len(loaded)


def lookup_cache_manifest() -> dict[str, Any] | None:
    with _cache_lock:
        return dict(_manifest) if _manifest else None


def cache_is_loaded() -> bool:
    with _cache_lock:
        return bool(_memory)


def _enrich_lookup_inventory(lookup: MarketLookup, payload: dict[str, Any]) -> MarketLookup:
    total = _search_listing_count(payload)
    if total <= 0:
        return lookup
    if lookup.total_listings == total and lookup.pulse.active_listings == total:
        return lookup
    pulse = lookup.pulse.model_copy(update={"active_listings": total})
    return lookup.model_copy(update={"total_listings": total, "pulse": pulse})


def get_cached_lookup(entity_type: str, slug: str) -> MarketLookup | None:
    with _cache_lock:
        payload = _memory.get(_cache_key(entity_type, slug))
    if payload is None:
        return None
    try:
        lookup = MarketLookup.model_validate(payload)
    except Exception:
        logger.warning("lookup_cache_invalid", entity_type=entity_type, slug=slug)
        return None
    return _enrich_lookup_inventory(lookup, payload)


def get_cached_listing_counts() -> dict[str, int]:
    with _cache_lock:
        return dict(_listing_counts)


def get_cached_markets() -> list[NeighborhoodMarketSummary]:
    with _cache_lock:
        rows = list(_markets)
    out: list[NeighborhoodMarketSummary] = []
    for row in rows:
        try:
            out.append(NeighborhoodMarketSummary.model_validate(row))
        except Exception:
            continue
    return out


def get_cached_neighborhood_options() -> list[dict[str, Any]]:
    with _cache_lock:
        return list(_neighborhood_options)


def corpus_meta_from_cache(session: Session) -> CorpusMeta | None:
    """Fast corpus meta from cache manifest (no full corpus load)."""
    manifest = lookup_cache_manifest()
    if not manifest or "corpus_meta" not in manifest:
        return None
    meta = dict(manifest["corpus_meta"])
    if not meta.get("corpus_updated_at"):
        meta["corpus_updated_at"] = corpus_last_updated(session)
    return CorpusMeta.model_validate(meta)


def _write_lookup_entry(
    base: Path,
    *,
    entity_type: str,
    slug: str,
    payload: dict[str, Any],
    entries: list[dict[str, Any]],
) -> None:
    rel_dir = base / entity_type
    rel_dir.mkdir(exist_ok=True)
    rel_path = f"{entity_type}/{slug}.json"
    path = base / rel_path
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    entries.append(
        {
            "entity_type": entity_type,
            "slug": slug,
            "path": rel_path,
            "sha256": sha256_file(path),
        }
    )


def build_lookup_cache(session: Session) -> Path:
    """Precompute all market lookups for API fast-path. Called from weekly analytics."""
    from groundtruth.analytics.annual_export import DEFAULT_ANNUAL_REPORT_PATH
    from groundtruth.analytics.valuation import (
        COMPARABLES_META_FILE,
        RENT_COMPARABLES_FILE,
        SALE_COMPARABLES_FILE,
        list_neighborhood_options,
        persist_comparables_disk_cache,
        rent_comparables_dataframe,
        sale_comparables_dataframe,
        seed_comparables_cache,
    )
    from groundtruth.models.reference import Complex, District, Neighborhood, Street
    from groundtruth.services.lookup import (
        get_corpus_meta,
        get_market_lookup,
        list_neighborhood_market_summaries,
    )

    base = lookup_cache_dir()
    base.mkdir(parents=True, exist_ok=True)

    revision = corpus_last_updated(session)
    revision_iso = revision.isoformat() if revision else None
    entries: list[dict[str, Any]] = []
    built = 0
    seen_neighborhood_canonical: set[str] = set()

    targets: list[tuple[str, str]] = []
    for nh in session.query(Neighborhood).filter(Neighborhood.slug.isnot(None)).all():
        targets.append(("neighborhood", nh.slug))
    for d in session.query(District).filter(District.slug.isnot(None)).all():
        targets.append(("district", d.slug))
    for s in session.query(Street).filter(Street.slug.isnot(None)).all():
        targets.append(("street", s.slug))
    for c in session.query(Complex).filter(Complex.slug.isnot(None)).all():
        targets.append(("complex", c.slug))

    for entity_type, slug in targets:
        lookup_slug = slug
        if entity_type == "neighborhood":
            lookup_slug = resolve_neighborhood_slug(slug)
            if lookup_slug in seen_neighborhood_canonical:
                continue
            seen_neighborhood_canonical.add(lookup_slug)

        result = get_market_lookup(session, entity_type, lookup_slug)  # type: ignore[arg-type]
        if result is None:
            continue

        payload = result.model_dump(mode="json")
        _write_lookup_entry(
            base, entity_type=entity_type, slug=lookup_slug, payload=payload, entries=entries
        )
        built += 1

        if entity_type == "neighborhood":
            for alias_slug in slugs_for_canonical(lookup_slug):
                if alias_slug == lookup_slug:
                    continue
                alias_payload = dict(payload)
                alias_payload["requested_slug"] = alias_slug
                alias_payload["slug"] = lookup_slug
                _write_lookup_entry(
                    base,
                    entity_type=entity_type,
                    slug=alias_slug,
                    payload=alias_payload,
                    entries=entries,
                )
                built += 1

    corpus_meta = get_corpus_meta(session)
    markets = list_neighborhood_market_summaries(session)
    rent_df = rent_comparables_dataframe(session)
    sale_df = sale_comparables_dataframe(session)
    persist_comparables_disk_cache(base, rent_df, sale_df, revision_iso)
    seed_comparables_cache(revision, rent_df, sale_df)
    neighborhood_options = list_neighborhood_options(session)

    artifact_hashes: dict[str, str] = {}
    for filename in (COMPARABLES_META_FILE, RENT_COMPARABLES_FILE, SALE_COMPARABLES_FILE):
        path = base / filename
        if path.is_file():
            artifact_hashes[filename] = sha256_file(path)

    related_artifacts: dict[str, dict[str, str]] = {}
    if DEFAULT_ANNUAL_REPORT_PATH.is_file():
        related_artifacts["annual_report"] = {
            "sha256": sha256_file(DEFAULT_ANNUAL_REPORT_PATH),
        }

    manifest = {
        "built_at": datetime.now(UTC).isoformat(),
        "corpus_revision": revision_iso,
        # Label from freeze manifest (metadata only — does not lock DB contents).
        "dataset_version": frozen_dataset_version(),
        "dataset_hash": frozen_dataset_fingerprint(),
        "entry_count": built,
        "entries": entries,
        "artifact_hashes": artifact_hashes,
        "related_artifacts": related_artifacts,
        "corpus_meta": corpus_meta.model_dump(mode="json"),
        "markets": [m.model_dump(mode="json") for m in markets],
        "neighborhood_options": neighborhood_options,
    }
    manifest_path = base / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    load_lookup_cache_from_disk()
    logger.info("lookup_cache_built", entries=built, path=str(manifest_path))
    return manifest_path


def stamp_related_artifact_hash(*, key: str, path: Path) -> None:
    """Update lookup manifest related_artifacts after a sibling artifact is written."""
    base = lookup_cache_dir()
    manifest_path = base / "manifest.json"
    if not manifest_path.is_file() or not path.is_file():
        return
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    related = dict(manifest.get("related_artifacts") or {})
    related[key] = {"sha256": sha256_file(path)}
    manifest["related_artifacts"] = related
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")


def resolve_market_lookup(
    session: Session,
    entity_type: str,
    slug: str,
) -> MarketLookup | None:
    """Serve from in-memory precomputed cache only — never load full corpus on API hot path."""
    cached = get_cached_lookup(entity_type, slug)
    if cached is not None:
        return cached

    if entity_type == "neighborhood":
        canonical = resolve_neighborhood_slug(slug)
        if canonical != slug:
            cached = get_cached_lookup(entity_type, canonical)
            if cached is not None:
                data = cached.model_dump()
                data["requested_slug"] = slug
                return MarketLookup.model_validate(data)

    if cache_is_loaded():
        logger.warning("lookup_cache_miss", entity_type=entity_type, slug=slug)
        return None

    # Cache not built yet (dev without weekly analytics) — fall back once, slowly.
    from groundtruth.services.lookup import get_market_lookup

    logger.warning("lookup_cache_empty_fallback", entity_type=entity_type, slug=slug)
    return get_market_lookup(session, entity_type, slug)  # type: ignore[arg-type]
