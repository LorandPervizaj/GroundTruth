"""Pro Real Estate (pro-rks.com) REST API helpers."""

from __future__ import annotations

from urllib.parse import urlencode

API_BASE = "https://prod-api.pro-rks.com/v1"
WEB_BASE = "https://www.pro-rks.com"
CDN_BASE = "https://prorealestate.ams3.cdn.digitaloceanspaces.com"

# Prishtinë — matches site filter URLs.
DEFAULT_CITY_ID = "d41787fe-44f1-4e81-87cf-4f4e4614ba0a"

DEFAULT_RESIDENTIAL_CATEGORIES = frozenset({"apartment", "home", "unit", "house", "villa"})
EXCLUDED_CATEGORIES = frozenset({"land", "office", "store", "warehouse", "object"})

API_HEADERS = {
    "Accept": "application/json",
    "Origin": WEB_BASE,
    "Referer": f"{WEB_BASE}/",
}


def properties_index_url(
    *,
    listing_type: str,
    city_id: str = DEFAULT_CITY_ID,
    page: int = 1,
    limit: int = 30,
) -> str:
    """Page-based index — deterministic pagination with totals."""
    params: dict[str, str | int] = {"cities": city_id, "page": page, "limit": limit}
    if listing_type == "sale":
        params["forSale"] = "true"
    elif listing_type == "rent":
        params["forRent"] = "true"
    else:
        raise ValueError(f"listing_type must be sale or rent, got {listing_type!r}")
    return f"{API_BASE}/properties?{urlencode(params)}"


def property_detail_url(slug: str | int) -> str:
    return f"{API_BASE}/properties/{slug}"


def listing_page_url(slug: str | int) -> str:
    return f"{WEB_BASE}/en/shpalljet/{slug}"


def image_url(path: str | None) -> str | None:
    if not path:
        return None
    if path.startswith("http"):
        return path
    return f"{CDN_BASE}/{path.lstrip('/')}"


def category_allowed(categories: list[str] | None, allowed: frozenset[str]) -> bool:
    if not categories:
        return True
    normalized = {c.lower() for c in categories}
    if normalized & EXCLUDED_CATEGORIES:
        return False
    if allowed:
        return bool(normalized & allowed)
    return True
