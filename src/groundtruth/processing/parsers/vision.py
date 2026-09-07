"""Parse Vision Real Estate WordPress REST property payloads."""

from __future__ import annotations

import re
from html import unescape
from typing import Any

from groundtruth.scrapers.vision_api import STATUS_RENT_ID, STATUS_SALE_ID

_TAG_RE = re.compile(r"<[^>]+>")

_TYPE_SLUG_MAP = {
    "banesa": "apartment",
    "shtepi": "house",
    "objekte": "other",
    "troje": "land",
    "depo": "commercial",
    "lokale": "commercial",
    "zyre": "commercial",
}


def strip_html(text: str | None) -> str | None:
    if not text:
        return None
    cleaned = unescape(_TAG_RE.sub(" ", text))
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned or None


def _rendered_title(prop: dict[str, Any]) -> str | None:
    title = prop.get("title")
    if isinstance(title, dict):
        return strip_html(title.get("rendered"))
    if isinstance(title, str):
        return strip_html(title)
    return None


def _meta(prop: dict[str, Any]) -> dict[str, Any]:
    return prop.get("property_meta") or {}


def _float_val(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _int_val(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def listing_type_from_statuses(status_ids: list[int] | None) -> str | None:
    if not status_ids:
        return None
    if STATUS_RENT_ID in status_ids:
        return "rent"
    if STATUS_SALE_ID in status_ids:
        return "sale"
    return None


def property_type_slug(prop: dict[str, Any]) -> str | None:
    classes = prop.get("class_list") or []
    for cls in classes:
        if isinstance(cls, str) and cls.startswith("property-type-"):
            return cls.replace("property-type-", "", 1)
    return None


def is_residential(prop: dict[str, Any], *, allowed_types: frozenset[str]) -> bool:
    slug = property_type_slug(prop)
    return bool(slug and slug in allowed_types)


def is_prishtina_district(prop: dict[str, Any]) -> bool:
    address = (_meta(prop).get("REAL_HOMES_property_address") or "").lower()
    if not address:
        return False
    return "district of prishtina" in address or "district of pristina" in address


def parse_wp_property(
    prop: dict[str, Any],
    *,
    allowed_types: frozenset[str] | None = None,
    prishtina_only: bool = True,
) -> dict[str, Any] | None:
    """Normalize a WP /properties item; return None when filtered out."""
    if allowed_types and not is_residential(prop, allowed_types=allowed_types):
        return None
    if prishtina_only and not is_prishtina_district(prop):
        return None

    meta = _meta(prop)
    listing_type = listing_type_from_statuses(prop.get("property-statuses"))
    type_slug = property_type_slug(prop)

    price_raw = meta.get("REAL_HOMES_property_price")
    sale_price = None
    rent_price = None
    if listing_type == "sale":
        sale_price = _float_val(price_raw)
    elif listing_type == "rent":
        rent_price = _float_val(price_raw)

    loc = meta.get("REAL_HOMES_property_location") or {}
    images = meta.get("REAL_HOMES_property_images") or []
    image_urls = []
    for image in images:
        if isinstance(image, dict):
            url = image.get("full_url") or image.get("url")
            if url and url not in image_urls:
                image_urls.append(str(url))

    return {
        "wp_id": prop.get("id"),
        "slug": str(prop.get("slug") or ""),
        "link": prop.get("link"),
        "title": _rendered_title(prop),
        "description_html": (prop.get("content") or {}).get("rendered"),
        "description_text": strip_html((prop.get("content") or {}).get("rendered")),
        "listing_type": listing_type,
        "property_type_slug": type_slug,
        "property_type": _TYPE_SLUG_MAP.get(type_slug or "", "other"),
        "sale_price": sale_price,
        "rent_price": rent_price,
        "area_sqm": _float_val(meta.get("REAL_HOMES_property_size")),
        "bedrooms": _int_val(meta.get("REAL_HOMES_property_bedrooms")),
        "bathrooms": _int_val(meta.get("REAL_HOMES_property_bathrooms")),
        "garage": _int_val(meta.get("REAL_HOMES_property_garage")),
        "year_built": _int_val(meta.get("REAL_HOMES_property_year_built")),
        "address": meta.get("REAL_HOMES_property_address"),
        "latitude": _float_val(loc.get("latitude")),
        "longitude": _float_val(loc.get("longitude")),
        "published_at": prop.get("date"),
        "modified_at": prop.get("modified"),
        "image_urls": image_urls,
        "status_ids": prop.get("property-statuses") or [],
        "city_ids": prop.get("property-cities") or [],
    }
