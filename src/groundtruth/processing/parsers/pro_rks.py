"""Parse Pro Real Estate API JSON payloads."""

from __future__ import annotations

import re
from datetime import date, datetime
from html import unescape
from typing import Any

from groundtruth.scrapers.pro_rks_api import image_url

_TAG_RE = re.compile(r"<[^>]+>")
_MEDIA_PATH_DATE_RE = re.compile(r"media/(\d{4})-(\d{2})/")


def strip_html(text: str | None) -> str | None:
    if not text:
        return None
    cleaned = unescape(_TAG_RE.sub(" ", text))
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned or None


def _parse_api_datetime(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    text = str(value).strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def extract_listing_date(prop: dict[str, Any]) -> date | None:
    """Best-effort listing date from Pro-RKS API (property has no createdAt).

    Prefer earliest image ``createdAt``; fall back to ``media/YYYY-MM/`` path dates.
    """
    images = prop.get("images") or []
    timestamps: list[datetime] = []
    path_dates: list[date] = []
    for image in images:
        if not isinstance(image, dict):
            continue
        parsed = _parse_api_datetime(image.get("createdAt"))
        if parsed is not None:
            timestamps.append(parsed)
        for key in ("original", "lg", "sm"):
            block = image.get(key) or {}
            url = str(block.get("url") or "")
            match = _MEDIA_PATH_DATE_RE.search(url)
            if match:
                try:
                    path_dates.append(date(int(match.group(1)), int(match.group(2)), 1))
                except ValueError:
                    continue
    if timestamps:
        return min(timestamps).date()
    if path_dates:
        return min(path_dates)
    return None


def extract_image_urls(images: list[dict[str, Any]] | None) -> list[str]:
    urls: list[str] = []
    if not images:
        return urls
    for image in images:
        for key in ("original", "lg", "sm"):
            block = image.get(key) or {}
            url = image_url(block.get("url"))
            if url and url not in urls:
                urls.append(url)
    return urls


def nested_name(value: Any) -> str | None:
    if isinstance(value, dict):
        for key in ("title", "name"):
            text = value.get(key)
            if text:
                return str(text).strip()
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def parse_detail_payload(
    detail: dict[str, Any],
    *,
    listing_type_hint: str | None = None,
) -> dict[str, Any]:
    """Normalize API detail response into a stable raw payload dict."""
    prop = detail.get("property") or detail
    agent = detail.get("agent")
    categories = [str(c).lower() for c in (prop.get("category") or [])]
    return {
        "property": prop,
        "agent": agent,
        "related_properties": detail.get("relatedProperties") or [],
        "listing_type_hint": listing_type_hint,
        "slug": str(prop.get("slug") or ""),
        "categories": categories,
        "title": prop.get("title"),
        "title_en": prop.get("title_en"),
        "description_text": strip_html(prop.get("description")),
        "description_en": strip_html(prop.get("description_en")),
        "for_sale": bool(prop.get("forSale")),
        "for_rent": bool(prop.get("forRent")),
        "sell_price": prop.get("sellPrice"),
        "rent_price": prop.get("rentPrice"),
        "surface_m2": prop.get("surfaceM2"),
        "bedrooms": prop.get("numberOfBedRooms"),
        "bathrooms": prop.get("numberOfBathRooms"),
        "floor": prop.get("floor"),
        "total_floors": prop.get("numberOfFloors"),
        "building_year": prop.get("buildingYear"),
        "city_name": nested_name(prop.get("city")),
        "street_name": nested_name(prop.get("street")),
        "address": nested_name(prop.get("address")),
        "complex_name": nested_name(prop.get("complex")),
        "builder_name": nested_name(prop.get("builder")),
        "latitude": prop.get("latitude"),
        "longitude": prop.get("longitude"),
        "furnishing": prop.get("furnishing") or [],
        "heating_system": prop.get("heatingSystem") or [],
        "image_urls": extract_image_urls(prop.get("images")),
        "listing_date": extract_listing_date(prop),
    }
