"""Generate candidate duplicate pairs for scoring."""

from collections.abc import Iterator
from itertools import combinations
from typing import Any

from groundtruth.analytics.listing_fingerprint import coarse_block_key
from groundtruth.schemas.pipeline import NormalizedListingSchema


def _listing_block_key(listing: NormalizedListingSchema) -> tuple[Any, ...] | None:
    """Blocking key from normalized listing fields."""
    import pandas as pd

    row = {
        "listing_type": listing.listing_type.value if listing.listing_type else None,
        "neighborhood_id": listing.neighborhood_id,
        "area_sqm": listing.area_sqm,
        "bedrooms": listing.bedrooms,
        "rent_price": float(listing.rent_price) if listing.rent_price else None,
        "sale_price": float(listing.sale_price) if listing.sale_price else None,
    }
    return coarse_block_key(pd.Series(row))


def generate_pairs_blocked(
    listings: list[tuple[int, NormalizedListingSchema]],
) -> Iterator[tuple[int, NormalizedListingSchema, int, NormalizedListingSchema]]:
    """
    Generate candidate pairs within coarse blocks (neighborhood + area + price band).

    Avoids O(n²) full-corpus comparison; only compares within small blocks.
    """
    blocks: dict[tuple[Any, ...], list[tuple[int, NormalizedListingSchema]]] = {}
    for listing_id, listing in listings:
        key = _listing_block_key(listing)
        if key is None:
            continue
        blocks.setdefault(key, []).append((listing_id, listing))

    for group in blocks.values():
        if len(group) < 2:
            continue
        for (id_a, a), (id_b, b) in combinations(group, 2):
            yield id_a, a, id_b, b


def generate_pairs_by_neighborhood(
    listings: list[tuple[int, NormalizedListingSchema]],
) -> Iterator[tuple[int, NormalizedListingSchema, int, NormalizedListingSchema]]:
    """
    Generate candidate pairs grouped by neighborhood.

    Uses block keys within each neighborhood to limit pairwise comparisons.
    """
    by_neighborhood: dict[int | None, list[tuple[int, NormalizedListingSchema]]] = {}
    for listing_id, listing in listings:
        key = listing.neighborhood_id
        by_neighborhood.setdefault(key, []).append((listing_id, listing))

    for group in by_neighborhood.values():
        yield from generate_pairs_blocked(group)


def generate_pairs_by_price_band(
    listings: list[tuple[int, NormalizedListingSchema]],
    band_pct: float = 0.10,
) -> Iterator[tuple[int, NormalizedListingSchema, int, NormalizedListingSchema]]:
    """
    Generate candidate pairs where prices are within a percentage band.

    Useful as a secondary pass when neighborhood is unknown.
    """
    priced = [
        (lid, listing)
        for lid, listing in listings
        if (listing.sale_price or listing.rent_price) is not None
    ]
    for i, (id_a, a) in enumerate(priced):
        price_a = float(a.sale_price or a.rent_price or 0)
        for id_b, b in priced[i + 1 :]:
            price_b = float(b.sale_price or b.rent_price or 0)
            if price_a == 0 or price_b == 0:
                continue
            diff = abs(price_a - price_b) / max(price_a, price_b)
            if diff <= band_pct and a.neighborhood_id == b.neighborhood_id:
                yield id_a, a, id_b, b
