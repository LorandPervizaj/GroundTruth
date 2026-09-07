"""MY Real Estate (myrealestate-ks.com) WordPress REST helpers."""

from __future__ import annotations

API_BASE = "https://myrealestate-ks.com/wp-json/wp/v2"
WEB_BASE = "https://myrealestate-ks.com"

API_HEADERS = {
    "User-Agent": "MetrikBot/1.0 (+https://github.com/groundtruth)",
    "Accept": "application/json",
}

DEFAULT_PER_PAGE = 100

# property_action_category slugs (residential)
DEFAULT_RESIDENTIAL_ACTION_SLUGS = frozenset({"banes", "shtepi", "penthouse", "villa"})

# property_category: qira = rent, shitje-sq = sale
CATEGORY_RENT_SLUG = "qira"
CATEGORY_SALE_SLUG = "shitje-sq"

# property_city slug for Prishtina listings
PRISHTINA_CITY_SLUG = "prishitne"


def properties_index_url(*, page: int = 1, per_page: int = DEFAULT_PER_PAGE) -> str:
    return f"{API_BASE}/estate_property?per_page={per_page}&page={page}&status=publish"
