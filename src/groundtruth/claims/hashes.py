"""Cryptographic fingerprints for reproducible claims."""

from __future__ import annotations

import hashlib
from pathlib import Path

from sqlalchemy import func
from sqlalchemy.orm import Session

from groundtruth.methodology.version import METHODOLOGY_VERSION
from groundtruth.models.pipeline import NormalizedListing, RawListing
from groundtruth.services.parsing import PARSER_VERSION
from groundtruth.versions import ETL_PIPELINE_VERSION


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def sha256_file(path: Path) -> str:
    content = path.read_bytes()
    return hashlib.sha256(content).hexdigest()


def sha256_sql(sql: str) -> str:
    normalized = " ".join(sql.split()).strip().lower()
    return sha256_text(normalized)


def dataset_fingerprint(session: Session, *, parser_version: str | None = None) -> str:
    """
    Stable hash of the deduped normalized dataset snapshot.

    Uses latest row per source_listing_id: id, price, area, neighborhood_id.
    """
    subq = (
        session.query(
            NormalizedListing.source_listing_id.label("sid"),
            func.max(NormalizedListing.id).label("max_id"),
        )
        .group_by(NormalizedListing.source_listing_id)
        .subquery()
    )
    rows = (
        session.query(NormalizedListing)
        .join(subq, NormalizedListing.id == subq.c.max_id)
        .order_by(NormalizedListing.source_listing_id)
        .all()
    )
    parts = [parser_version or "any"]
    for row in rows:
        price = row.rent_price or row.sale_price
        parts.append(
            f"{row.source_listing_id}|{price}|{row.area_sqm}|{row.neighborhood_id}|{row.parser_version}"
        )
    return sha256_text("\n".join(parts))


def raw_crawl_fingerprint(session: Session) -> str:
    """
    Stable hash of immutable raw payloads (latest row per source_listing_id).

    Anchors temporal reproducibility: what raw HTML existed at fingerprint time.
    """
    subq = (
        session.query(
            RawListing.source_listing_id.label("sid"),
            func.max(RawListing.id).label("max_id"),
        )
        .group_by(RawListing.source_listing_id)
        .subquery()
    )
    rows = (
        session.query(RawListing)
        .join(subq, RawListing.id == subq.c.max_id)
        .order_by(RawListing.source_listing_id)
        .all()
    )
    parts: list[str] = []
    for row in rows:
        parts.append(f"{row.source_listing_id}|{row.content_hash}|{row.scraped_at}")
    return sha256_text("\n".join(parts))


def reproducibility_tuple(
    session: Session,
    *,
    parser_version: str | None = None,
    methodology_version: str | None = None,
    notebook_hash: str = "",
    sql_hash: str = "",
) -> dict[str, str]:
    """Full artifact tuple for claim pinning."""
    return {
        "raw_crawl_hash": raw_crawl_fingerprint(session),
        "etl_version": ETL_PIPELINE_VERSION,
        "parser_version": parser_version or PARSER_VERSION,
        "methodology_version": methodology_version or METHODOLOGY_VERSION,
        "notebook_hash": notebook_hash,
        "sql_hash": sql_hash,
        "dataset_hash": dataset_fingerprint(
            session, parser_version=parser_version or PARSER_VERSION
        ),
    }
