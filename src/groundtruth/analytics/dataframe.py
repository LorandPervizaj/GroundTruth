"""Load normalized listings from the database into a pandas DataFrame."""

from __future__ import annotations

import pandas as pd
from sqlalchemy.orm import Session

from groundtruth.models.pipeline import NormalizedListing
from groundtruth.models.reference import Neighborhood


def normalized_listings_dataframe(session: Session) -> pd.DataFrame:
    """Export all normalized listings with neighborhood names for analytics."""
    nh_map = {n.id: n.name for n in session.query(Neighborhood).all()}
    listings = session.query(NormalizedListing).all()
    rows = []
    for listing in listings:
        rows.append(
            {
                "source_listing_id": listing.source_listing_id,
                "source_website": listing.source_website,
                "listing_type": listing.listing_type.value if listing.listing_type else None,
                "sale_price": float(listing.sale_price) if listing.sale_price else None,
                "rent_price": float(listing.rent_price) if listing.rent_price else None,
                "price_per_sqm": float(listing.price_per_sqm) if listing.price_per_sqm else None,
                "area_sqm": listing.area_sqm,
                "neighborhood_id": listing.neighborhood_id,
                "neighborhood": nh_map.get(listing.neighborhood_id, ""),
                "city": listing.city,
                "bedrooms": listing.bedrooms,
                "is_new_construction": listing.is_new_construction,
                "is_active": listing.is_active,
                "confidence_score": listing.confidence_score,
                "parser_version": listing.parser_version,
                "gazetteer_version": listing.gazetteer_version,
            }
        )
    return pd.DataFrame(rows)
