"""Append listing observations after each ETL run."""

from __future__ import annotations

from datetime import date

from sqlalchemy.orm import Session

from groundtruth.logging import get_logger
from groundtruth.models.listing_observation import ListingObservation
from groundtruth.models.pipeline import NormalizedListing

logger = get_logger(__name__)


def record_listing_observations(
    session: Session,
    listings: list[NormalizedListing],
    *,
    observed_date: date | None = None,
) -> int:
    """Persist one observation per unique source listing for the ETL day."""
    observed_date = observed_date or date.today()
    session.query(ListingObservation).filter_by(observed_date=observed_date).delete(
        synchronize_session=False
    )

    latest: dict[str, NormalizedListing] = {}
    for listing in sorted(listings, key=lambda row: row.id):
        latest[listing.source_listing_id] = listing

    count = 0
    for listing in latest.values():
        session.add(
            ListingObservation(
                source_website=listing.source_website,
                source_listing_id=listing.source_listing_id,
                normalized_listing_id=listing.id,
                observed_date=observed_date,
                listing_type=listing.listing_type,
                sale_price=listing.sale_price,
                rent_price=listing.rent_price,
                area_sqm=listing.area_sqm,
                is_active=listing.is_active,
                confidence_score=listing.confidence_score,
                parser_version=listing.parser_version,
                original_url=listing.original_url,
            )
        )
        count += 1

    session.flush()
    logger.info("listing_observations_recorded", count=count, date=str(observed_date))
    return count
