"""Resume helpers for MerrJep detail crawls."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import text
from sqlalchemy.orm import Session

from groundtruth.database.session import get_session_factory


def load_skip_listing_ids(
    session: Session | None = None,
    *,
    source_website: str = "merrjep",
    within_days: int = 0,
) -> set[str]:
    """Return listing IDs the crawler should skip.

    * ``within_days=0`` — skip every ID ever stored (legacy ``skip_existing``).
    * ``within_days>0`` — skip only if the latest raw row was scraped within N days;
      older listings are re-fetched so price/status changes are picked up. Unchanged
      content is deduped at insert time via ``content_hash``.
    """
    own_session = session is None
    if own_session:
        session = get_session_factory()()
    try:
        if within_days > 0:
            cutoff = datetime.now(UTC) - timedelta(days=within_days)
            rows = session.execute(
                text(
                    """
                    SELECT source_listing_id
                    FROM raw_listings
                    WHERE source_website = :source
                    GROUP BY source_listing_id
                    HAVING MAX(scraped_at) >= :cutoff
                    """
                ),
                {"source": source_website, "cutoff": cutoff},
            ).scalars()
        else:
            rows = session.execute(
                text(
                    """
                    SELECT DISTINCT source_listing_id
                    FROM raw_listings
                    WHERE source_website = :source
                    """
                ),
                {"source": source_website},
            ).scalars()
        return set(rows)
    finally:
        if own_session:
            session.close()


def load_existing_listing_ids(
    session: Session | None = None,
    *,
    source_website: str = "merrjep",
) -> set[str]:
    """Return all listing IDs already present in raw_listings (legacy helper)."""
    return load_skip_listing_ids(session, source_website=source_website, within_days=0)
