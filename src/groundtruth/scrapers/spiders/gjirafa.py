"""Gjirafa Patundshmëri spider for listime.gjirafa.com."""

from __future__ import annotations

import re
from collections.abc import Iterable
from datetime import UTC, date, datetime, timedelta
from urllib.parse import quote, urlencode

import scrapy
from scrapy.http import Response

from groundtruth.crawl.window import parse_gjirafa_listing_date
from groundtruth.processing.parsers.gjirafa import parse_listing_html
from groundtruth.scrapers.errors import ScrapeErrorCode
from groundtruth.scrapers.items import ListingItem
from groundtruth.scrapers.merrjep_resume import load_skip_listing_ids
from groundtruth.scrapers.profiles import spider_settings
from groundtruth.scrapers.spiders.base import BaseRealEstateSpider

_LISTING_PATH_RE = re.compile(
    r"/Shpallje/Patundshmeri/(?P<slug>[a-z]+(?:-[a-z]+)*-\d+)",
    re.IGNORECASE,
)
# Site ``k=`` values for category-filtered indexes (Prishtinë rent/sale).
_GJIRAFA_CATEGORY_K: dict[str, str] = {
    "banesa": "Banesa",
    "shtepi-vila": "Shtepi/Vila",
    "objekte-afariste": "Objekte Afariste",
    "zyre": "Zyre",
}
_DEFAULT_CATEGORIES = tuple(_GJIRAFA_CATEGORY_K)
# Slug prefixes allowed per category key (index ``k=`` already filters; this is a safety net).
_CATEGORY_SLUG_PREFIXES: dict[str, tuple[str, ...]] = {
    "banesa": ("banesa",),
    "shtepi-vila": ("shtepi", "vila"),
    "objekte-afariste": ("objekte-afariste", "objekte"),
    "zyre": ("zyre",),
}
# Land/agricultural slugs — skip (thin data, out of scope).
_EXCLUDED_SLUG_PREFIXES = (
    "ara-dhe-ferma",
    "truall",
    "toke",
    "tok-",
    "parcel",
)
_LAND_CATEGORY_MARKERS = ("ara dhe ferma", "truall", "toke", "tokë", "parcel", "ferm")
_INDEX_PATH = "/Top/Patundshmeri"
_INDEX_ORIGIN = "https://listime.gjirafa.com"
# Gjirafa index filters — category example:
# /Top/Patundshmeri?f=0&sh=Kosove&r=Prishtine&k=Banesa&llshp=Shitet
_INDEX_FILTERS: dict[str, dict[str, str]] = {
    "all": {},
    "sale": {"sh": "Kosove", "r": "Prishtine", "llshp": "Shitet"},
    "rent": {"sh": "Kosove", "r": "Prishtine", "llshp": "Qira"},
}

# Real challenge/block pages — not Cloudflare Insights analytics (`cloudflareinsights.com`).
_SOFT_BLOCK_MARKERS = (
    "cf-browser-verification",
    "cdn-cgi/challenge",
    "__cf_chl",
    "attention required",
    "access denied",
    "just a moment",
    "captcha",
    "request blocked",
    "bot detection",
)


def build_gjirafa_index_url(
    *,
    page: int = 0,
    listing_type: str = "all",
    category: str | None = None,
) -> str:
    """Build a paginated Gjirafa Patundshmeri index URL (optional ``k=`` category)."""
    filters = _INDEX_FILTERS.get(listing_type, _INDEX_FILTERS["all"])
    params: dict[str, str] = {"f": str(page), **filters}
    if category:
        key = category.strip().lower()
        params["k"] = _GJIRAFA_CATEGORY_K.get(key, category.strip())
    # Keep ``/`` in ``k=Shtepi/Vila`` and spaces as ``%20`` to match site URLs.
    return f"{_INDEX_ORIGIN}{_INDEX_PATH}?{urlencode(params, quote_via=quote, safe='/')}"


class GjirafaSpiderBase(BaseRealEstateSpider):
    """Shared crawl logic for listime.gjirafa.com (Prishtinë rent/sale indexes)."""

    source_website = "gjirafa"
    spider_version = "1.2.0"
    allowed_domains = ["listime.gjirafa.com", "www.listime.gjirafa.com"]
    _fixed_listing_type: str | None = None

    custom_settings = {
        **spider_settings("html"),
        "ROBOTSTXT_OBEY": False,
    }

    def __init__(
        self,
        max_pages: str = "250",
        max_listings: str = "0",
        categories: str = "banesa,shtepi-vila,objekte-afariste,zyre",
        listing_type: str = "all",
        start_page: str = "0",
        skip_existing: str = "true",
        skip_existing_days: str = "0",
        max_age_days: str = "0",
        stale_streak_limit: str = "50",
        *args,
        **kwargs,
    ) -> None:
        super().__init__(*args, **kwargs)
        self._max_pages = int(max_pages)
        self._max_listings = int(max_listings)
        self._start_page = max(0, int(start_page))
        self._skip_existing = skip_existing.lower() in ("1", "true", "yes")
        self._skip_existing_days = max(0, int(skip_existing_days))
        self._existing_ids: set[str] = set()
        self._detail_skipped_existing = 0
        self._detail_skipped_too_old = 0
        self._max_age_days = int(max_age_days)
        self._stale_streak_limit = int(stale_streak_limit)
        self._cutoff_date: date | None = None
        if self._max_age_days > 0:
            self._cutoff_date = datetime.now(UTC).date() - timedelta(days=self._max_age_days - 1)
        self._stop_index = False
        self._stale_streak = 0
        self._categories = (
            tuple(c.strip().lower() for c in categories.split(",") if c.strip())
            or _DEFAULT_CATEGORIES
        )
        unknown = [c for c in self._categories if c not in _GJIRAFA_CATEGORY_K]
        if unknown:
            allowed = ", ".join(_GJIRAFA_CATEGORY_K)
            raise ValueError(f"Unknown Gjirafa categories {unknown}. Choose from: {allowed}")
        resolved_type = (
            self._fixed_listing_type
            if self._fixed_listing_type is not None
            else (listing_type.strip().lower() or "all")
        )
        self._listing_type = resolved_type
        if self._listing_type not in _INDEX_FILTERS:
            raise ValueError(f"listing_type must be one of: {', '.join(_INDEX_FILTERS)}")
        self._detail_requests_sent = 0
        self._index_empty_pages = 0
        self._soft_block_hits = 0
        # One filtered index URL per category — denser pages, less skip work.
        self.start_urls = [
            build_gjirafa_index_url(
                page=self._start_page,
                listing_type=self._listing_type,
                category=cat,
            )
            for cat in self._categories
        ]
        self._slug_prefixes = tuple(
            prefix
            for cat in self._categories
            for prefix in _CATEGORY_SLUG_PREFIXES.get(cat, (cat,))
        )

    @classmethod
    def from_crawler(cls, crawler, *args, **kwargs):
        spider = super().from_crawler(crawler, *args, **kwargs)
        if spider._skip_existing:
            spider._existing_ids = load_skip_listing_ids(
                source_website="gjirafa",
                within_days=spider._skip_existing_days,
            )
            spider.logger.warning(
                "skip_existing enabled — %d gjirafa ids to skip (within_days=%d)",
                len(spider._existing_ids),
                spider._skip_existing_days,
            )
        if spider._start_page > 0:
            spider.logger.warning(
                "crawl_resume start_page=%d listing_type=%s",
                spider._start_page,
                spider._listing_type,
            )
        return spider

    async def start(self):
        """Scrapy 2.13+ entry — one request per category index (resume via start_page)."""
        for url, category in zip(self.start_urls, self._categories, strict=True):
            yield scrapy.Request(
                url,
                callback=self.parse,
                meta={"page": self._start_page, "category": category},
                dont_filter=True,
            )

    def _at_listing_limit(self) -> bool:
        return self._max_listings > 0 and self._detail_requests_sent >= self._max_listings

    def _slug_allowed(self, slug: str) -> bool:
        slug_lower = slug.lower()
        if any(slug_lower.startswith(prefix) for prefix in _EXCLUDED_SLUG_PREFIXES):
            return False
        return any(slug_lower.startswith(f"{prefix}-") for prefix in self._slug_prefixes)

    def _is_land_listing(self, payload: dict) -> bool:
        category = (payload.get("category") or "").lower()
        return any(marker in category for marker in _LAND_CATEGORY_MARKERS)

    def _is_detail_page(self, response: Response) -> bool:
        if response.meta.get("page_type") == "detail":
            return True
        return bool(_LISTING_PATH_RE.search(response.url))

    def _looks_like_soft_block(self, response: Response) -> bool:
        body = (response.text or "").lower()
        return any(marker in body for marker in _SOFT_BLOCK_MARKERS)

    def parse_index_page(self, response: Response) -> Iterable:
        if self._stop_index:
            self.logger.info("index_stop reason=stale_published_dates url=%s", response.url)
            return
        if self._at_listing_limit():
            self.logger.info("listing_limit_reached count=%d", self._detail_requests_sent)
            return

        if self._looks_like_soft_block(response):
            self._soft_block_hits += 1
            self.record_error(ScrapeErrorCode.SOFT_BLOCK)
            self._stop_index = True
            self.logger.warning(
                "index_stop reason=soft_block status=%s bytes=%d url=%s",
                response.status,
                len(response.text or ""),
                response.url,
            )
            return

        listing_urls: set[str] = set()
        for match in _LISTING_PATH_RE.finditer(response.text):
            slug = match.group("slug")
            if not self._slug_allowed(slug):
                continue
            listing_urls.add(response.urljoin(match.group(0)))

        self.logger.info("index_listings_found count=%d url=%s", len(listing_urls), response.url)

        if not listing_urls:
            self._index_empty_pages += 1
            self.record_error(ScrapeErrorCode.EMPTY_INDEX, count_as_error=False)
            self.logger.info(
                "index_stop reason=empty_page page=%s empty_streak=%d url=%s",
                response.meta.get("page", 0),
                self._index_empty_pages,
                response.url,
            )
            return

        for url in sorted(listing_urls):
            if self._at_listing_limit():
                break
            match = _LISTING_PATH_RE.search(url)
            listing_id = match.group("slug") if match else None
            if self._skip_existing and listing_id and listing_id in self._existing_ids:
                self._detail_skipped_existing += 1
                continue
            self._detail_requests_sent += 1
            yield self.request_detail(response, url)

        if self._at_listing_limit():
            return

        current_page = response.meta.get("page", 0)
        category = response.meta.get("category")
        if self._stop_index:
            return
        if current_page + 1 < self._max_pages:
            next_page = current_page + 1
            next_url = build_gjirafa_index_url(
                page=next_page,
                listing_type=self._listing_type,
                category=category,
            )
            yield response.follow(
                next_url,
                callback=self.parse,
                meta={"page": next_page, "category": category},
            )

    def parse_listing_page(self, response: Response) -> Iterable[ListingItem]:
        payload = parse_listing_html(response.text, response.url)
        if self._is_land_listing(payload):
            self.logger.debug("skip_land_listing id=%s", payload.get("source_listing_id"))
            return

        if self._cutoff_date is not None:
            published = parse_gjirafa_listing_date(payload.get("listing_date_raw"))
            if published is not None and published < self._cutoff_date:
                self._detail_skipped_too_old += 1
                self._stale_streak += 1
                if self._stale_streak >= self._stale_streak_limit:
                    self._stop_index = True
                    self.logger.warning(
                        "index_stop reason=stale_published_dates streak=%d cutoff=%s",
                        self._stale_streak,
                        self._cutoff_date,
                    )
                return
            if published is not None:
                self._stale_streak = 0

        listing_id = payload["source_listing_id"]

        yield self.build_listing_item(
            source_listing_id=listing_id,
            original_url=response.url,
            raw_payload=payload,
            raw_html=response.text,
        )
        if self.listings_found % 100 == 0:
            self.logger.warning(
                "crawl_progress listings=%d requests=%d skipped_existing=%d",
                self.listings_found,
                self._detail_requests_sent,
                self._detail_skipped_existing,
            )

    def closed(self, reason: str) -> None:
        self.logger.warning(
            "gjirafa_crawl_complete spider=%s listing_type=%s listings=%d detail_requests=%d "
            "skipped_existing=%d skipped_too_old=%d cutoff=%s stopped_index=%s reason=%s",
            self.name,
            self._listing_type,
            self.listings_found,
            self._detail_requests_sent,
            self._detail_skipped_existing,
            self._detail_skipped_too_old,
            self._cutoff_date,
            self._stop_index,
            reason,
        )


class GjirafaRentSpider(GjirafaSpiderBase):
    """Gjirafa Prishtinë rent index (llshp=Qira)."""

    name = "gjirafa-rent"
    _fixed_listing_type = "rent"


class GjirafaSaleSpider(GjirafaSpiderBase):
    """Gjirafa Prishtinë sale index (llshp=Shitet)."""

    name = "gjirafa-sale"
    _fixed_listing_type = "sale"


class GjirafaSpider(GjirafaSpiderBase):
    """Legacy combined spider — prefer gjirafa-rent / gjirafa-sale for parallel weekly runs."""

    name = "gjirafa"
