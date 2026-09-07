"""Topia Real Estate (topia-ks.com) REST API helpers."""

from __future__ import annotations

API_BASE = "https://topia-ks.com/api"
WEB_BASE = "https://topia-ks.com/en"

API_HEADERS = {
    "User-Agent": "MetrikBot/1.0 (+https://github.com/groundtruth)",
    "Accept": "application/json",
}

DEFAULT_PER_PAGE = 100

DEFAULT_RESIDENTIAL_TYPES = frozenset(
    {
        "Apartment",
        "House",
        "Villa",
        "Penthouse",
        "Duplex",
    }
)


def properties_index_url(*, page: int = 1, per_page: int = DEFAULT_PER_PAGE) -> str:
    return f"{API_BASE}/properties?page={page}&per_page={per_page}"


def property_page_url(prop_id: int | str, slug: str) -> str:
    slug = slug.strip("/")
    return f"{WEB_BASE}/property/{prop_id}/{slug}.html"
