"""Release artifact build and verification helpers."""

from __future__ import annotations

import json
from pathlib import Path

from groundtruth.analytics.annual_export import DEFAULT_ANNUAL_REPORT_PATH, export_annual_report
from groundtruth.analytics.valuation import (
    COMPARABLES_META_FILE,
    RENT_COMPARABLES_FILE,
    SALE_COMPARABLES_FILE,
)
from groundtruth.claims.hashes import sha256_file
from groundtruth.database.session import get_session_factory
from groundtruth.services.lookup_cache import (
    build_lookup_cache,
    lookup_cache_dir,
    stamp_related_artifact_hash,
)
from groundtruth.services.public_payload import assert_market_lookup_public


def build_release_artifacts() -> tuple[Path, Path]:
    """Build lookup/comparables and statistics artifacts from the current DB."""
    from sqlalchemy import text

    session = get_session_factory()()
    try:
        session.execute(text("SET statement_timeout = '0'"))
        session.execute(text("SET lock_timeout = '0'"))
        lookup_manifest = build_lookup_cache(session)
        annual_path = export_annual_report(session)
    finally:
        session.close()
    stamp_related_artifact_hash(key="annual_report", path=annual_path)
    return lookup_manifest, annual_path


def _read_json(path: Path) -> dict:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid JSON in {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"expected JSON object in {path}")
    return payload


def _require_sha256(expected: object, path: Path, *, context: str) -> None:
    if not isinstance(expected, str) or len(expected) != 64:
        raise ValueError(f"{context}: missing or invalid sha256 for {path}")
    actual = sha256_file(path)
    if actual != expected:
        raise ValueError(f"{context}: sha256 mismatch for {path} (manifest != file)")


def verify_release_artifacts() -> list[str]:
    """Validate required public release artifacts and return status lines.

    Checks presence, manifest structure, content hashes, JSON validity,
    MarketLookup schema, and forbidden public listing fields.
    """
    out: list[str] = []
    base = lookup_cache_dir()
    manifest_path = base / "manifest.json"
    if not manifest_path.is_file():
        raise FileNotFoundError(f"missing lookup cache manifest: {manifest_path}")
    manifest = _read_json(manifest_path)

    entries = manifest.get("entries")
    if not isinstance(entries, list) or not entries:
        raise ValueError("lookup cache manifest has no entries")
    if not manifest.get("built_at"):
        raise ValueError("lookup cache manifest missing built_at")

    artifact_hashes = manifest.get("artifact_hashes")
    if not isinstance(artifact_hashes, dict) or not artifact_hashes:
        raise ValueError(
            "lookup cache manifest missing artifact_hashes — rebuild with "
            "`groundtruth release build-artifacts`"
        )

    missing = []
    for i, entry in enumerate(entries):
        if not isinstance(entry, dict):
            raise ValueError(f"lookup cache entries[{i}] must be an object")
        rel = entry.get("path")
        if not rel or not isinstance(rel, str):
            missing.append("<missing path>")
            continue
        path = base / rel
        if not path.is_file():
            missing.append(rel)
            continue
        _require_sha256(entry.get("sha256"), path, context=f"entries[{i}] path={rel}")
        payload = _read_json(path)
        assert_market_lookup_public(payload, context=f"lookup entry {rel}")

    if missing:
        raise FileNotFoundError(
            f"lookup cache references missing files ({len(missing)}): {missing[:5]}"
        )

    for filename in (COMPARABLES_META_FILE, RENT_COMPARABLES_FILE, SALE_COMPARABLES_FILE):
        path = base / filename
        if not path.is_file():
            raise FileNotFoundError(f"missing comparables artifact: {path}")
        if path.stat().st_size <= 0:
            raise ValueError(f"empty comparables artifact: {path}")
        _require_sha256(
            artifact_hashes.get(filename),
            path,
            context=f"artifact_hashes[{filename}]",
        )

    # Meta is plain JSON; rent/sale payloads are gzip-compressed JSON tables.
    meta_payload = _read_json(base / COMPARABLES_META_FILE)
    if not isinstance(meta_payload, dict):
        raise ValueError(f"invalid comparables meta: {base / COMPARABLES_META_FILE}")

    annual_path = DEFAULT_ANNUAL_REPORT_PATH
    if not annual_path.is_file():
        raise FileNotFoundError(f"missing annual report artifact: {annual_path}")
    annual_payload = _read_json(annual_path)
    if not annual_payload.get("generated_at"):
        raise ValueError("annual report missing generated_at")

    related = manifest.get("related_artifacts") or {}
    annual_meta = related.get("annual_report") if isinstance(related, dict) else None
    if not isinstance(annual_meta, dict) or not annual_meta.get("sha256"):
        raise ValueError(
            "lookup cache manifest missing related_artifacts.annual_report.sha256 — "
            "rebuild with `groundtruth release build-artifacts`"
        )
    _require_sha256(
        annual_meta.get("sha256"),
        annual_path,
        context="related_artifacts[annual_report]",
    )

    meta_revision = meta_payload.get("corpus_revision")
    manifest_revision = manifest.get("corpus_revision")
    if meta_revision and manifest_revision and meta_revision != manifest_revision:
        raise ValueError(
            "inconsistent release state: comparables corpus_revision "
            f"({meta_revision!r}) != lookup manifest ({manifest_revision!r})"
        )

    out.append(f"lookup_cache_ok entries={len(entries)} path={manifest_path}")
    out.append(f"annual_report_ok path={annual_path}")
    return out
