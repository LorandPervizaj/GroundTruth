"""Classify invalid listings — don't patch individually, understand the pattern."""

from groundtruth.models.etl import InvalidListing


def classify_invalid_listing(invalid: InvalidListing) -> str:
    """
    Return one of: parser_bug, website_inconsistency, genuinely_invalid.

    Perfect parsers should not guess bad data — website inconsistencies stay flagged.
    """
    snap = invalid.snapshot or {}
    codes = set(invalid.error_codes or [])
    listing_type = snap.get("listing_type")
    sale_price = _float(snap.get("sale_price"))
    rent_price = _float(snap.get("rent_price"))
    area = _float(snap.get("area_sqm"))

    if "area_too_large" in codes and area and area > 10_000:
        return "parser_bug"

    if "price_too_low" in codes and listing_type == "sale" and sale_price is not None:
        if sale_price < 2_000:
            return "website_inconsistency"
        if sale_price < 10_000 and area and area > 20:
            return "parser_bug"

    if "price_per_sqm_too_low" in codes and listing_type == "sale" and sale_price and area:
        if sale_price < 10_000:
            return "website_inconsistency"

    if "area_too_small" in codes and area is not None and area <= 1:
        return "website_inconsistency"

    if "price_too_low" in codes and listing_type == "rent" and rent_price is not None and rent_price < 10:
        return "genuinely_invalid"

    if "normalize_error" in codes or "parse_error" in codes:
        return "parser_bug"

    return "website_inconsistency"


def _float(value) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
