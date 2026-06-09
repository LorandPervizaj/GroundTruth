"""Dry-run parser KPIs on raw listings without writing to DB."""

from __future__ import annotations

from decimal import Decimal

from groundtruth.database.session import get_session_factory
from groundtruth.models.pipeline import RawListing
from groundtruth.processing.validation import ListingValidator
from groundtruth.services.normalization import NormalizationService
from groundtruth.services.parsing import ParsingService

session = get_session_factory()()
parser = ParsingService()
normalizer = NormalizationService(session)
validator = ListingValidator()

total = 0
has_price = 0
has_area = 0
has_neighborhood = 0
invalid = 0

for raw in session.query(RawListing).filter_by(source_website="gjirafa").yield_per(200):
    total += 1
    parsed = parser.parse_raw(raw)
    normalized, _ = normalizer.normalize(parsed)
    price = normalized.rent_price if parsed.listing_type and parsed.listing_type.value == "rent" else normalized.sale_price
    if price is not None:
        has_price += 1
    if normalized.area_sqm is not None:
        has_area += 1
    if normalized.neighborhood_id is not None:
        has_neighborhood += 1
    if not validator.validate(normalized).is_valid:
        invalid += 1

session.close()

print(f"total={total}")
print(f"price_coverage={100*has_price/total:.1f}%")
print(f"area_coverage={100*has_area/total:.1f}%")
print(f"neighborhood_coverage={100*has_neighborhood/total:.1f}%")
print(f"invalid_rate={100*invalid/total:.1f}%")
