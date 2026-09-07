"""Parse MY Real Estate WordPress estate_property payloads (+ optional detail HTML)."""

from __future__ import annotations

import re
from html import unescape
from typing import Any
from urllib.parse import urljoin

from groundtruth.scrapers.myrealestate_api import (
    CATEGORY_RENT_SLUG,
    CATEGORY_SALE_SLUG,
    DEFAULT_RESIDENTIAL_ACTION_SLUGS,
    PRISHTINA_CITY_SLUG,
)

_TAG_RE = re.compile(r"<[^>]+>")
_PRICE_AREA_RE = re.compile(
    r'class="[^"]*price_area[^"]*"[^>]*>\s*(?:&euro;|&#8364;|[€$])?\s*([\d][\d\s.,]*)',
    re.I,
)
_PRICE_META_RE = re.compile(
    r'<meta[^>]+(?:property|name)=["\'](?:product:price:amount|og:price:amount)["\'][^>]+'
    r'content=["\']([\d.,]+)["\']',
    re.I,
)
_PRICE_META_RE_ALT = re.compile(
    r'<meta[^>]+content=["\']([\d.,]+)["\'][^>]+(?:property|name)=["\']'
    r'(?:product:price:amount|og:price:amount)["\']',
    re.I,
)
_AREA_RE = re.compile(r"(\d+(?:[.,]\d+)?)\s*m\s*[²2]", re.I)
_BEDROOM_RE = re.compile(
    r"(\d+)\s*(?:\+\s*1\s*)?(?:dhoma\s+gjumi|dhoma|bedroom)",
    re.I,
)
_UPLOAD_IMG_RE = re.compile(
    r'(https?://[^"\'>\s]+/wp-content/uploads/[^"\'>\s]+\.(?:jpe?g|png|webp))',
    re.I,
)

_ACTION_TYPE_MAP = {
    "banes": "apartment",
    "shtepi": "house",
    "penthouse": "apartment",
    "villa": "villa",
}


def strip_html(text: str | None) -> str | None:
    if not text:
        return None
    cleaned = unescape(_TAG_RE.sub(" ", text))
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned or None


def _rendered(prop: dict[str, Any], field: str) -> str | None:
    value = prop.get(field)
    if isinstance(value, dict):
        return strip_html(value.get("rendered"))
    if isinstance(value, str):
        return strip_html(value)
    return None


def class_slug(class_list: list[str] | None, prefix: str) -> str | None:
    needle = f"{prefix}-"
    for cls in class_list or []:
        if isinstance(cls, str) and cls.startswith(needle):
            return cls[len(needle) :]
    return None


def is_prishtina(prop: dict[str, Any]) -> bool:
    slug = class_slug(prop.get("class_list"), "property_city")
    return slug == PRISHTINA_CITY_SLUG


def is_residential(
    prop: dict[str, Any],
    *,
    allowed_actions: frozenset[str] | None = None,
) -> bool:
    allowed = allowed_actions or DEFAULT_RESIDENTIAL_ACTION_SLUGS
    slug = class_slug(prop.get("class_list"), "property_action_category")
    return bool(slug and slug in allowed)


def listing_type_from_classes(class_list: list[str] | None) -> str | None:
    category = class_slug(class_list, "property_category")
    if category == CATEGORY_RENT_SLUG:
        return "rent"
    if category == CATEGORY_SALE_SLUG:
        return "sale"
    return None


def _normalize_price_token(raw: str) -> float | None:
    cleaned = re.sub(r"[^\d.,]", "", raw)
    if not cleaned:
        return None
    # European thousands: 155.000 or 155,000 → 155000; decimals keep last separator.
    if cleaned.count(".") > 1 or (cleaned.count(".") == 1 and cleaned.count(",") == 0 and
                                  len(cleaned.split(".")[-1]) == 3):
        cleaned = cleaned.replace(".", "")
    cleaned = cleaned.replace(",", "")
    try:
        return float(cleaned)
    except ValueError:
        return None


def parse_price_from_html(html: str | None) -> float | None:
    if not html:
        return None
    match = _PRICE_AREA_RE.search(html)
    if match:
        value = _normalize_price_token(match.group(1))
        if value is not None:
            return value
    for pattern in (_PRICE_META_RE, _PRICE_META_RE_ALT):
        meta = pattern.search(html)
        if meta:
            value = _normalize_price_token(meta.group(1))
            if value is not None:
                return value
    return None


def extract_image_urls(*, prop: dict[str, Any], detail_html: str | None = None) -> list[str]:
    """Collect gallery/featured image URLs from REST links + detail HTML."""
    urls: list[str] = []

    def _add(url: str | None) -> None:
        if not url:
            return
        absolute = urljoin("https://myrealestate-ks.com/", url.strip())
        if absolute not in urls:
            urls.append(absolute)

    links = prop.get("_links") or {}
    featured = links.get("wp:featuredmedia")
    if isinstance(featured, list):
        for entry in featured:
            if not isinstance(entry, dict):
                continue
            for key in ("source_url", "href"):
                candidate = entry.get(key)
                if isinstance(candidate, str) and "/wp-content/uploads/" in candidate:
                    _add(candidate)

    yoast = prop.get("yoast_head_json") or {}
    for image in yoast.get("og_image") or []:
        if isinstance(image, dict):
            _add(image.get("url"))

    for match in _UPLOAD_IMG_RE.finditer(detail_html or ""):
        _add(match.group(1))

    return urls


def _area_from_text(*parts: str | None) -> float | None:
    for part in parts:
        if not part:
            continue
        match = _AREA_RE.search(part)
        if match:
            try:
                return float(match.group(1).replace(",", "."))
            except ValueError:
                continue
    return None


def _bedrooms_from_text(*parts: str | None) -> int | None:
    for part in parts:
        if not part:
            continue
        match = _BEDROOM_RE.search(part)
        if match:
            try:
                return int(match.group(1))
            except ValueError:
                continue
    return None


def parse_myrealestate_property(
    prop: dict[str, Any],
    *,
    detail_html: str | None = None,
    allowed_actions: frozenset[str] | None = None,
    prishtina_only: bool = True,
) -> dict[str, Any] | None:
    """Normalize estate_property REST item; return None when filtered out."""
    if not is_residential(prop, allowed_actions=allowed_actions):
        return None
    if prishtina_only and not is_prishtina(prop):
        return None

    class_list = prop.get("class_list") or []
    listing_type = listing_type_from_classes(class_list)
    action_slug = class_slug(class_list, "property_action_category")
    area_slug = class_slug(class_list, "property_area")

    title = _rendered(prop, "title")
    description_html = (prop.get("content") or {}).get("rendered")
    description_text = strip_html(description_html)

    price = parse_price_from_html(detail_html)
    sale_price = None
    rent_price = None
    if listing_type == "sale":
        sale_price = price
    elif listing_type == "rent":
        rent_price = price

    area_sqm = _area_from_text(title, description_text)
    bedrooms = _bedrooms_from_text(title, description_text)

    neighborhood = area_slug.replace("-", " ").title() if area_slug else None

    return {
        "wp_id": prop.get("id"),
        "slug": str(prop.get("slug") or ""),
        "link": prop.get("link"),
        "title": title,
        "description_html": description_html,
        "description_text": description_text,
        "listing_type": listing_type,
        "property_type_slug": action_slug,
        "property_type": _ACTION_TYPE_MAP.get(action_slug or "", "other"),
        "sale_price": sale_price,
        "rent_price": rent_price,
        "area_sqm": area_sqm,
        "bedrooms": bedrooms,
        "bathrooms": None,
        "neighborhood": neighborhood,
        "city": "Prishtina",
        "published_at": prop.get("date"),
        "modified_at": prop.get("modified"),
        "image_urls": extract_image_urls(prop=prop, detail_html=detail_html),
        "category_slug": class_slug(class_list, "property_category"),
        "area_slug": area_slug,
    }
