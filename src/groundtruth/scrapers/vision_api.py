"""Vision Real Estate (visionrealestateks.com) WordPress REST helpers."""

from __future__ import annotations

API_BASE = "https://visionrealestateks.com/wp-json/wp/v2"
WEB_BASE = "https://visionrealestateks.com"

API_HEADERS = {
    "User-Agent": "MetrikBot/1.0 (+https://github.com/groundtruth)",
    "Accept": "application/json",
}

DEFAULT_PER_PAGE = 100

# property-types taxonomy slugs (residential)
DEFAULT_RESIDENTIAL_TYPE_SLUGS = frozenset({"banesa", "shtepi"})

# property-statuses: for-rent / for-sale
STATUS_RENT_ID = 27
STATUS_SALE_ID = 28


def properties_index_url(*, page: int = 1, per_page: int = DEFAULT_PER_PAGE) -> str:
    return f"{API_BASE}/properties?per_page={per_page}&page={page}"
