"""MY Real Estate spider — WP REST index + detail HTML for price."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator, Iterable
from typing import Any

import scrapy
from scrapy.http import Response

from groundtruth.processing.parsers.myrealestate import is_prishtina, is_residential
from groundtruth.scrapers.errors import ScrapeErrorCode
from groundtruth.scrapers.merrjep_resume import load_skip_listing_ids
from groundtruth.scrapers.myrealestate_api import (
    API_HEADERS,
    DEFAULT_PER_PAGE,
    DEFAULT_RESIDENTIAL_ACTION_SLUGS,
    properties_index_url,
)
from groundtruth.scrapers.profiles import spider_settings
from groundtruth.scrapers.spiders.base import BaseRealEstateSpider


class MyRealEstateSpider(BaseRealEstateSpider):
    """Crawl myrealestate-ks.com via /wp-json/wp/v2/estate_property."""

    name = "myrealestate"
    source_website = "myrealestate"
    spider_version = "0.1.0-myrealestate"
    allowed_domains = ["myrealestate-ks.com", "www.myrealestate-ks.com"]

    custom_settings = {
        **spider_settings("api"),
        "DEFAULT_REQUEST_HEADERS": API_HEADERS,
    }

    def __init__(
        self,
        max_pages: str = "0",
        max_listings: str = "0",
        prishtina_only: str = "true",
        skip_existing: str = "true",
        skip_existing_days: str = "0",
        *args,
        **kwargs,
    ) -> None:
        super().__init__(*args, **kwargs)
        self._max_pages = int(max_pages)
        self._max_listings = int(max_listings)
        self._prishtina_only = prishtina_only.lower() in ("1", "true", "yes")
        self._skip_existing = skip_existing.lower() in ("1", "true", "yes")
        self._skip_existing_days = max(0, int(skip_existing_days))
        self._existing_ids: set[str] = set()
        self._detail_skipped_existing = 0
        self._seen_slugs: set[str] = set()
        self._detail_requests_sent = 0

    @classmethod
    def from_crawler(cls, crawler, *args, **kwargs):
        spider = super().from_crawler(crawler, *args, **kwargs)
        if spider._skip_existing:
            spider._existing_ids = load_skip_listing_ids(
                source_website=spider.source_website,
                within_days=spider._skip_existing_days,
            )
            spider.logger.warning(
                "skip_existing enabled — %d myrealestate ids to skip (within_days=%d)",
                len(spider._existing_ids),
                spider._skip_existing_days,
            )
        return spider

    async def start(self) -> AsyncIterator[scrapy.Request]:
        yield scrapy.Request(
            properties_index_url(page=1, per_page=DEFAULT_PER_PAGE),
            callback=self.parse_index_page,
            meta={"page": 1},
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
            self.logger.error("myrealestate_index_json_error url=%s", response.url)
            return

        if not isinstance(body, list):
            self.record_error(ScrapeErrorCode.UNEXPECTED_SHAPE)
            return

        for prop in body:
            if self._at_listing_limit():
                break
            if not is_residential(prop, allowed_actions=DEFAULT_RESIDENTIAL_ACTION_SLUGS):
                continue
            if self._prishtina_only and not is_prishtina(prop):
                continue

            slug = str(prop.get("slug") or "")
            if not slug or slug in self._seen_slugs:
                continue
            if self._skip_existing and slug in self._existing_ids:
                self._detail_skipped_existing += 1
                continue
            self._seen_slugs.add(slug)
            self._detail_requests_sent += 1

            link = str(prop.get("link") or f"https://myrealestate-ks.com/properties/{slug}/")
            yield scrapy.Request(
                link,
                callback=self.parse_listing_page,
                meta={"page_type": "detail", "property": prop, "slug": slug},
                dont_filter=True,
            )

        current_page = int(response.meta.get("page", 1))
        total_pages = int(response.headers.get("X-WP-TotalPages", b"1") or 1)

        if self._at_listing_limit():
            return
        if self._max_pages > 0 and current_page >= self._max_pages:
            return
        if current_page >= total_pages:
            return
        if not body:
            self.logger.info("index_stop reason=empty_page page=%d", current_page)
            return

        next_page = current_page + 1
        yield scrapy.Request(
            properties_index_url(page=next_page, per_page=DEFAULT_PER_PAGE),
            callback=self.parse_index_page,
            meta={"page": next_page},
            headers=API_HEADERS,
        )

    def parse_listing_page(self, response: Response) -> Iterable[Any]:
        prop = response.meta.get("property") or {}
        slug = str(response.meta.get("slug") or prop.get("slug") or "")
        payload = {
            "property": prop,
            "prishtina_only": self._prishtina_only,
        }

        yield self.build_listing_item(
            source_listing_id=slug,
            original_url=response.url,
            raw_payload=payload,
            raw_html=response.text,
        )
