"""Enforce configured retention windows for sensitive listing content."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, or_, select, update
from sqlalchemy.orm import Session

from groundtruth.config import Settings
from groundtruth.models.pipeline import NormalizedListing, ParsedListing, RawListing


@dataclass(frozen=True)
class RetentionResult:
    raw_html_rows: int
    raw_payload_rows: int
    parsed_description_rows: int
    normalized_description_rows: int
    dry_run: bool
    evaluated_at: str

    def as_dict(self) -> dict[str, int | bool | str]:
        return asdict(self)


def _count(session: Session, model: type, condition: object) -> int:
    value = session.scalar(select(func.count()).select_from(model).where(condition))
    return int(value or 0)


def enforce_retention(
    session: Session,
    settings: Settings,
    *,
    now: datetime | None = None,
    dry_run: bool = True,
) -> RetentionResult:
    """Count or purge sensitive content older than configured retention windows."""
    evaluated_at = now or datetime.now(UTC)
    raw_html_cutoff = evaluated_at - timedelta(days=settings.raw_html_retention_days)
    raw_payload_cutoff = evaluated_at - timedelta(days=settings.raw_payload_retention_days)
    description_cutoff = evaluated_at - timedelta(days=settings.parsed_description_retention_days)

    raw_html_condition = (RawListing.scraped_at < raw_html_cutoff) & RawListing.raw_html.is_not(
        None
    )
    raw_payload_condition = (
        (RawListing.scraped_at < raw_payload_cutoff)
        & RawListing.raw_payload.is_not(None)
        & (RawListing.raw_payload != {})
    )
    parsed_description_condition = (ParsedListing.parsed_at < description_cutoff) & or_(
        ParsedListing.description_original.is_not(None),
        ParsedListing.description_cleaned.is_not(None),
    )
    normalized_description_condition = (NormalizedListing.normalized_at < description_cutoff) & or_(
        NormalizedListing.description_original.is_not(None),
        NormalizedListing.description_cleaned.is_not(None),
    )

    counts = {
        "raw_html_rows": _count(session, RawListing, raw_html_condition),
        "raw_payload_rows": _count(session, RawListing, raw_payload_condition),
        "parsed_description_rows": _count(
            session,
            ParsedListing,
            parsed_description_condition,
        ),
        "normalized_description_rows": _count(
            session,
            NormalizedListing,
            normalized_description_condition,
        ),
    }

    if not dry_run:
        session.execute(update(RawListing).where(raw_html_condition).values(raw_html=None))
        session.execute(update(RawListing).where(raw_payload_condition).values(raw_payload={}))
        session.execute(
            update(ParsedListing)
            .where(parsed_description_condition)
            .values(description_original=None, description_cleaned=None)
        )
        session.execute(
            update(NormalizedListing)
            .where(normalized_description_condition)
            .values(description_original=None, description_cleaned=None)
        )

    return RetentionResult(
        **counts,
        dry_run=dry_run,
        evaluated_at=evaluated_at.isoformat(),
    )
