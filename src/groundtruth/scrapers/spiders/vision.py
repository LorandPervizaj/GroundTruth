"""Vision Real Estate spider — WordPress REST API (RealHomes theme)."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator, Iterable
from typing import Any

import scrapy
from scrapy.http import Response

from groundtruth.processing.parsers.vision import parse_wp_property
from groundtruth.scrapers.errors import ScrapeErrorCode
from groundtruth.scrapers.merrjep_resume import load_skip_listing_ids
from groundtruth.scrapers.profiles import spider_settings
from groundtruth.scrapers.spiders.base import BaseRealEstateSpider
from groundtruth.scrapers.vision_api import (
    API_HEADERS,
    DEFAULT_PER_PAGE,
    DEFAULT_RESIDENTIAL_TYPE_SLUGS,
    properties_index_url,
)


class VisionSpider(BaseRealEstateSpider):
    """Crawl visionrealestateks.com via /wp-json/wp/v2/properties."""

    name = "vision"
    source_website = "vision"
    spider_version = "0.1.0-vision"
    allowed_domains = ["visionrealestateks.com", "www.visionrealestateks.com"]

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
        self._seen_ids: set[str] = set()

    @classmethod
    def from_crawler(cls, crawler, *args, **kwargs):
        spider = super().from_crawler(crawler, *args, **kwargs)
        if spider._skip_existing:
            spider._existing_ids = load_skip_listing_ids(
                source_website=spider.source_website,
                within_days=spider._skip_existing_days,
            )
            spider.logger.warning(
                "skip_existing enabled — %d vision ids to skip (within_days=%d)",
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
        return self._max_listings > 0 and self.listings_found >= self._max_listings

    def _is_detail_page(self, response: Response) -> bool:
        return False

    def parse_listing_page(self, response: Response) -> Iterable[Any]:
        yield from ()

    def parse_index_page(self, response: Response) -> Iterable[scrapy.Request]:
        if self._at_listing_limit():
            return

        try:
            body = json.loads(response.text)
        except json.JSONDecodeError:
            self.record_error(ScrapeErrorCode.JSON_DECODE)
            self.logger.error("vision_index_json_error url=%s", response.url)
            return

        if not isinstance(body, list):
            self.record_error(ScrapeErrorCode.UNEXPECTED_SHAPE)
            self.logger.error("vision_index_unexpected_shape url=%s", response.url)
            return

        for prop in body:
            if self._at_listing_limit():
                break
            if (
                parse_wp_property(
                    prop,
                    allowed_types=DEFAULT_RESIDENTIAL_TYPE_SLUGS,
                    prishtina_only=self._prishtina_only,
                )
                is None
            ):
                continue
            slug = str(prop.get("slug") or "")
            wp_id = str(prop.get("id") or "")
            key = slug or wp_id
            if not key or key in self._seen_ids:
                continue
            if self._skip_existing and key in self._existing_ids:
                self._detail_skipped_existing += 1
                continue
            self._seen_ids.add(key)

            link = str(prop.get("link") or f"https://visionrealestateks.com/property/{slug}/")
            payload = {
                "property": prop,
                "prishtina_only": self._prishtina_only,
            }
            yield self.build_listing_item(
                source_listing_id=slug or wp_id,
                original_url=link,
                raw_payload=payload,
                raw_html=None,
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
