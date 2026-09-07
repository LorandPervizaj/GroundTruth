"""Pro Real Estate spider — API-first crawl of prod-api.pro-rks.com."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator, Iterable
from typing import Any

import scrapy
from scrapy.http import Response

from groundtruth.scrapers.errors import ScrapeErrorCode
from groundtruth.scrapers.merrjep_resume import load_skip_listing_ids
from groundtruth.scrapers.pro_rks_api import (
    API_HEADERS,
    DEFAULT_CITY_ID,
    DEFAULT_RESIDENTIAL_CATEGORIES,
    category_allowed,
    listing_page_url,
    properties_index_url,
    property_detail_url,
)
from groundtruth.scrapers.profiles import spider_settings
from groundtruth.scrapers.spiders.base import BaseRealEstateSpider


class ProRksSpider(BaseRealEstateSpider):
    """Crawl Pro Real Estate listings via public REST API."""

    name = "pro-rks"
    source_website = "pro-rks"
    spider_version = "0.1.0-pro-rks"
    allowed_domains = ["prod-api.pro-rks.com", "www.pro-rks.com", "pro-rks.com"]

    custom_settings = {
        **spider_settings("api"),
        "DEFAULT_REQUEST_HEADERS": API_HEADERS,
    }

    def __init__(
        self,
        max_pages: str = "0",
        max_listings: str = "0",
        listing_type: str = "both",
        city_id: str = DEFAULT_CITY_ID,
        categories: str = "apartment,home,unit",
        skip_existing: str = "true",
        skip_existing_days: str = "0",
        *args,
        **kwargs,
    ) -> None:
        super().__init__(*args, **kwargs)
        self._max_pages = int(max_pages)
        self._max_listings = int(max_listings)
        self._city_id = city_id
        self._listing_type = listing_type.strip().lower() or "both"
        self._allowed_categories = (
            frozenset(c.strip().lower() for c in categories.split(",") if c.strip())
            or DEFAULT_RESIDENTIAL_CATEGORIES
        )
        self._skip_existing = skip_existing.lower() in ("1", "true", "yes")
        self._skip_existing_days = max(0, int(skip_existing_days))
        self._skip_ids: set[str] = set()
        self._detail_skipped_existing = 0
        self._detail_requests_sent = 0
        self._seen_slugs: set[str] = set()

    @classmethod
    def from_crawler(cls, crawler, *args, **kwargs):
        spider = super().from_crawler(crawler, *args, **kwargs)
        if spider._skip_existing:
            spider._skip_ids = load_skip_listing_ids(
                source_website=spider.source_website,
                within_days=spider._skip_existing_days,
            )
            spider.logger.warning(
                "skip_existing enabled — %d pro-rks ids to skip (within_days=%d)",
                len(spider._skip_ids),
                spider._skip_existing_days,
            )
        return spider

    async def start(self) -> AsyncIterator[scrapy.Request]:
        """Scrapy 2.13+ entry point (start_requests is no longer called)."""
        if self._listing_type == "both":
            modes = ["sale", "rent"]
        elif self._listing_type in ("sale", "rent"):
            modes = [self._listing_type]
        else:
            raise ValueError("listing_type must be sale, rent, or both")

        for mode in modes:
            yield scrapy.Request(
                properties_index_url(
                    listing_type=mode,
                    city_id=self._city_id,
                    page=1,
                    limit=30,
                ),
                callback=self.parse_index_page,
                meta={"listing_type": mode, "page": 1},
                headers=API_HEADERS,
            )

    def _at_listing_limit(self) -> bool:
        return self._max_listings > 0 and self._detail_requests_sent >= self._max_listings

    def _is_detail_page(self, response: Response) -> bool:
        return response.meta.get("page_type") == "detail"

    def parse_index_page(self, response: Response) -> Iterable[scrapy.Request]:
        if self._at_listing_limit():
            return

        try:
            body = json.loads(response.text)
        except json.JSONDecodeError:
            self.record_error(ScrapeErrorCode.JSON_DECODE)
            self.logger.error("index_json_error url=%s", response.url)
            return

        listings = body.get("data") or []
        listing_type = response.meta["listing_type"]

        for item in listings:
            if self._at_listing_limit():
                break
            categories = [str(c).lower() for c in (item.get("category") or [])]
            if not category_allowed(categories, self._allowed_categories):
                continue
            slug = str(item.get("slug") or "")
            if not slug or slug in self._seen_slugs:
                continue
            if self._skip_existing and slug in self._skip_ids:
                self._detail_skipped_existing += 1
                continue
            self._seen_slugs.add(slug)
            self._detail_requests_sent += 1
            yield scrapy.Request(
                property_detail_url(slug),
                callback=self.parse_listing_page,
                meta={"page_type": "detail", "listing_type": listing_type, "slug": slug},
                headers=API_HEADERS,
                dont_filter=True,
            )

        current_page = int(response.meta.get("page", 1))
        pagination = body.get("pagination") or {}
        total_pages = int((pagination.get("total") or 0) or 0)
        has_next = bool(pagination.get("next"))

        if self._at_listing_limit():
            return
        if self._max_pages > 0 and current_page >= self._max_pages:
            return
        if not has_next and total_pages and current_page >= total_pages:
            return
        if not has_next and not listings:
            return

        next_page = current_page + 1
        if total_pages and next_page > total_pages:
            return

        yield scrapy.Request(
            properties_index_url(
                listing_type=listing_type,
                city_id=self._city_id,
                page=next_page,
                limit=30,
            ),
            callback=self.parse_index_page,
            meta={"listing_type": listing_type, "page": next_page},
            headers=API_HEADERS,
        )

    def parse_listing_page(self, response: Response) -> Iterable[Any]:
        try:
            body = json.loads(response.text)
        except json.JSONDecodeError:
            self.record_error(ScrapeErrorCode.JSON_DECODE)
            self.logger.error("detail_json_error url=%s", response.url)
            return

        prop = body.get("property")
        if not prop:
            self.record_error(ScrapeErrorCode.MISSING_PAYLOAD)
            return

        slug = str(response.meta.get("slug") or prop.get("slug") or "")
        listing_type = response.meta.get("listing_type")
        payload = {
            "property": prop,
            "agent": body.get("agent"),
            "related_properties": body.get("relatedProperties") or [],
            "listing_type_hint": listing_type,
        }

        yield self.build_listing_item(
            source_listing_id=slug,
            original_url=listing_page_url(slug),
            raw_payload=payload,
            raw_html=None,
        )

        if self.listings_found % 100 == 0:
            self.logger.warning(
                "crawl_progress listings=%d detail_requests=%d",
                self.listings_found,
                self._detail_requests_sent,
            )
