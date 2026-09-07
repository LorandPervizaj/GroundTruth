"""Parser for manual Facebook Marketplace captures (B1 — no automated scrape)."""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlparse

from groundtruth.schemas.facebook import FacebookMarketplaceCapture, InformalListingRecord

_EUR_RE = re.compile(
    r"(?:€|EUR)\s*([\d\s.,]+)|([\d\s.,]+)\s*(?:€|EUR)|\b(\d{2,6})\s*(?:eur|euro)\b",
    re.IGNORECASE,
)
_AREA_RE = re.compile(r"(\d{2,3})\s*(?:m2|m²|met(er)?a)", re.IGNORECASE)
_BED_RE = re.compile(r"(\d)\s*\+\s*1|(\d)\s*br\b|(\d)\s*dhoma", re.IGNORECASE)
_RENT_HINT = re.compile(r"\b(qira|qera|rent|me qira)\b", re.IGNORECASE)
_SALE_HINT = re.compile(r"\b(shitje|sale|shes|shitet)\b", re.IGNORECASE)
_FB_ITEM_RE = re.compile(r"/marketplace/item/(\d+)")


def _parse_eur(text: str | None) -> int | None:
    if not text:
        return None
    match = _EUR_RE.search(text)
    if not match:
        digits = re.sub(r"[^\d]", "", text)
        if not digits:
            return None
        value = int(digits)
        return value if 50 <= value <= 5_000_000 else None
    raw = next(g for g in match.groups() if g)
    digits = re.sub(r"[^\d]", "", raw)
    if not digits:
        return None
    value = int(digits)
    return value if 50 <= value <= 5_000_000 else None


def _infer_listing_type(
    explicit: str,
    title: str | None,
    description: str | None,
) -> str:
    if explicit in ("sale", "rent"):
        return explicit
    blob = f"{title or ''} {description or ''}"
    if _RENT_HINT.search(blob):
        return "rent"
    if _SALE_HINT.search(blob):
        return "sale"
    return "unknown"


def _extract_area(title: str | None, description: str | None, area: float | None) -> int | None:
    if area is not None:
        return int(round(area))
    blob = f"{title or ''} {description or ''}"
    match = _AREA_RE.search(blob)
    if match:
        return int(match.group(1))
    return None


def _extract_bedrooms(
    title: str | None, description: str | None, bedrooms: int | None
) -> int | None:
    if bedrooms is not None:
        return bedrooms
    blob = f"{title or ''} {description or ''}"
    match = _BED_RE.search(blob)
    if not match:
        return None
    for group in match.groups():
        if group:
            return int(group)
    return None


def listing_id_from_url(url: str) -> str:
    match = _FB_ITEM_RE.search(url)
    if match:
        return match.group(1)
    path = urlparse(url).path.rstrip("/")
    return path.split("/")[-1] or url


def parse_marketplace_capture(
    capture: FacebookMarketplaceCapture | dict[str, Any],
) -> InformalListingRecord:
    """Normalize a manual Marketplace capture into quarantine-tier record."""
    if not isinstance(capture, FacebookMarketplaceCapture):
        capture = FacebookMarketplaceCapture.model_validate(capture)

    title = capture.title
    description = capture.description
    price = _parse_eur(capture.price_text) or _parse_eur(f"{title or ''} {description or ''}")
    listing_type = _infer_listing_type(capture.listing_type, title, description)
    area = _extract_area(title, description, capture.area_sqm)
    bedrooms = _extract_bedrooms(title, description, capture.bedrooms)
    price_psm = None
    if price is not None and area and area > 0 and listing_type == "sale":
        price_psm = int(round(price / area))

    captured = capture.captured_at.isoformat() if capture.captured_at else None
    if not captured:
        from datetime import date

        captured = date.today().isoformat()

    return InformalListingRecord(
        source_listing_id=listing_id_from_url(capture.url),
        original_url=capture.url,
        title=title,
        description=description,
        listing_type=listing_type,  # type: ignore[arg-type]
        price_eur=price,
        price_per_sqm_eur=price_psm,
        area_sqm=area,
        bedrooms=bedrooms,
        neighborhood_guess=capture.neighborhood_guess,
        captured_at=captured,
        capture_method=capture.capture_method,
    )
