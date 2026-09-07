"""Parse Topia Real Estate API property payloads."""

from __future__ import annotations

from typing import Any

from groundtruth.scrapers.topia_api import DEFAULT_RESIDENTIAL_TYPES

_TYPE_MAP = {
    "apartment": "apartment",
    "house": "house",
    "villa": "villa",
    "penthouse": "apartment",
    "duplex": "apartment",
}


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


def _zone_label(zone: Any) -> str | None:
    if isinstance(zone, list):
        parts = [str(z).strip() for z in zone if z]
        return ", ".join(parts) if parts else None
    if isinstance(zone, str) and zone.strip():
        return zone.strip()
    return None


def is_prishtina(prop: dict[str, Any]) -> bool:
    city = str(prop.get("city") or prop.get("division") or "").strip().lower()
    return city == "prishtina"


def is_residential(prop: dict[str, Any], *, allowed_types: frozenset[str] | None = None) -> bool:
    allowed = allowed_types or DEFAULT_RESIDENTIAL_TYPES
    ptype = str(prop.get("type") or "").strip()
    return ptype in allowed


def parse_topia_property(
    prop: dict[str, Any],
    *,
    allowed_types: frozenset[str] | None = None,
    prishtina_only: bool = True,
) -> dict[str, Any] | None:
    """Normalize a Topia /api/properties item; return None when filtered out."""
    if not is_residential(prop, allowed_types=allowed_types):
        return None
    if prishtina_only and not is_prishtina(prop):
        return None

    business_type = str(prop.get("business_type") or "").strip().lower()
    listing_type = business_type if business_type in ("rent", "sale") else None

    price = _float_val(prop.get("price"))
    sale_price = None
    rent_price = None
    if listing_type == "sale":
        sale_price = price or _float_val(prop.get("sale_price"))
    elif listing_type == "rent":
        rent_price = price or _float_val(prop.get("rent_price"))

    type_raw = str(prop.get("type") or "").strip().lower()
    property_type = _TYPE_MAP.get(type_raw, "other")

    images = prop.get("images") or []
    image_urls: list[str] = []
    for image in images:
        if isinstance(image, dict):
            url = image.get("url")
            if url and url not in image_urls:
                image_urls.append(str(url))

    return {
        "topia_id": prop.get("id"),
        "reference": str(prop.get("reference") or ""),
        "slug": str(prop.get("slug") or ""),
        "title": prop.get("name"),
        "description_text": prop.get("description"),
        "listing_type": listing_type,
        "property_type": property_type,
        "property_type_raw": prop.get("type"),
        "sale_price": sale_price,
        "rent_price": rent_price,
        "area_sqm": _float_val(prop.get("gross_area")),
        "bedrooms": _int_val(prop.get("bed_room")),
        "bathrooms": _int_val(prop.get("bath_room")),
        "floor": _int_val(prop.get("floor")),
        "garage": _int_val(prop.get("garage")),
        "year_built": _int_val(prop.get("construction_year")),
        "city": prop.get("city") or prop.get("division"),
        "neighborhood": _zone_label(prop.get("zone")),
        "street": prop.get("street"),
        "latitude": _float_val(prop.get("lat")),
        "longitude": _float_val(prop.get("lng")),
        "published_at": prop.get("created_at"),
        "modified_at": prop.get("updated_at"),
        "image_urls": image_urls,
        "availability": prop.get("availability"),
    }
