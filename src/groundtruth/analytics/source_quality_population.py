"""Load raw-rooted pipeline evidence without active-corpus or priority filters."""

from datetime import datetime, timedelta

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from groundtruth.analytics.source_quality import utc
from groundtruth.analytics.source_quality_models import QualityRecord
from groundtruth.models.etl import InvalidListing
from groundtruth.models.pipeline import NormalizedListing, ParsedListing, RawListing
from groundtruth.schemas.pipeline import NormalizedListingSchema


def pipeline_records(
    session: Session, *, sources: list[str], as_of: datetime, window_days: int
) -> list[QualityRecord]:
    """Read versions within an inclusive raw-ingestion window in one snapshot.

    Callers own transaction isolation. No flush, commit, update, or external calls.
    Processing timestamps are bounded too, so later successful reprocessing cannot
    silently repair an earlier evaluation. Deleted historical rows cannot be restored.
    """
    raw, parsed, normalized = RawListing, ParsedListing, NormalizedListing
    as_of = utc(as_of)
    latest_parsed = (
        select(parsed.id)
        .where(parsed.raw_listing_id == raw.id, parsed.parsed_at <= as_of)
        .order_by(parsed.parsed_at.desc(), parsed.id.desc())
        .limit(1)
        .correlate(raw)
        .scalar_subquery()
    )
    query = (
        select(raw, parsed, normalized)
        .outerjoin(parsed, parsed.id == latest_parsed)
        .outerjoin(
            normalized,
            (normalized.parsed_listing_id == parsed.id) & (normalized.normalized_at <= as_of),
        )
        .where(
            raw.source_website.in_(sources),
            raw.scraped_at >= as_of - timedelta(days=window_days),
            raw.scraped_at <= as_of,
        )
        .order_by(raw.source_website, raw.source_listing_id, raw.scraped_at, raw.id)
    )
    records = []
    # Batches bound the IN predicates and avoid one failure query per listing.
    for batch in session.execute(
        query.execution_options(yield_per=500, autoflush=False)
    ).partitions(500):
        raw_ids = [r.id for r, _, _ in batch]
        parsed_ids = [p.id for _, p, _ in batch if p]
        normalized_ids = [n.id for _, _, n in batch if n]
        failures = list(
            session.scalars(
                select(InvalidListing)
                .execution_options(autoflush=False)
                .where(
                    InvalidListing.created_at <= as_of,
                    or_(
                        InvalidListing.raw_listing_id.in_(raw_ids),
                        InvalidListing.parsed_listing_id.in_(parsed_ids),
                        InvalidListing.normalized_listing_id.in_(normalized_ids),
                    ),
                )
            )
        )
        for r, p, n in batch:
            relevant = [
                f
                for f in failures
                if (
                    (p and f.parsed_listing_id == p.id)
                    or (n and f.normalized_listing_id == n.id)
                    or (
                        f.raw_listing_id == r.id
                        and f.parsed_listing_id is None
                        and f.normalized_listing_id is None
                        and (not p or utc(f.created_at) >= utc(p.parsed_at))
                    )
                )
            ]
            codes = sorted({code for f in relevant for code in f.error_codes})
            last_failure = max(relevant, key=lambda f: (utc(f.created_at), f.id), default=None)
            listing = None
            if n:
                # Read an explicit allowlist: reports never need descriptions or contacts.
                data = {
                    name: getattr(n, name)
                    for name in NormalizedListingSchema.model_fields
                    if hasattr(n, name)
                    and name
                    not in {
                        "description_original",
                        "description_cleaned",
                        "image_urls",
                        "confidence_details",
                    }
                }
                listing = NormalizedListingSchema.model_validate(data)
            elif p:
                data = {
                    name: getattr(p, name)
                    for name in NormalizedListingSchema.model_fields
                    if hasattr(p, name)
                    and name
                    not in {
                        "description_original",
                        "description_cleaned",
                        "image_urls",
                        "confidence_details",
                        "currency",
                    }
                }
                listing = NormalizedListingSchema.model_validate(data)
            records.append(
                QualityRecord(
                    source_name=r.source_website,
                    source_listing_id=r.source_listing_id,
                    observation_id=r.id,
                    observed_at=utc(r.scraped_at),
                    outcome="rejected" if relevant else "accepted" if n else "pending",
                    failure_stage=str(last_failure.stage) if last_failure else None,
                    error_codes=codes,
                    listing=listing,
                    content_hash=r.content_hash,
                )
            )
    return records
