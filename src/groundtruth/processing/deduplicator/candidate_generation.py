"""Generate candidate duplicate pairs for scoring."""

from itertools import combinations
from typing import Iterator

from groundtruth.schemas.pipeline import NormalizedListingSchema


def generate_pairs_by_neighborhood(
    listings: list[tuple[int, NormalizedListingSchema]],
) -> Iterator[tuple[int, NormalizedListingSchema, int, NormalizedListingSchema]]:
    """
    Generate candidate pairs grouped by neighborhood.

    Only compares listings within the same neighborhood to limit O(n²) explosion.
    """
    by_neighborhood: dict[int | None, list[tuple[int, NormalizedListingSchema]]] = {}
    for listing_id, listing in listings:
        key = listing.neighborhood_id
        by_neighborhood.setdefault(key, []).append((listing_id, listing))

    for group in by_neighborhood.values():
        if len(group) < 2:
            continue
        for (id_a, a), (id_b, b) in combinations(group, 2):
            yield id_a, a, id_b, b


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
