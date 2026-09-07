"""Base spider class for all real estate source spiders."""

from __future__ import annotations

from abc import abstractmethod
from collections.abc import Iterable
from datetime import UTC, datetime
from typing import Any

import scrapy
from scrapy.http import Response

from groundtruth.logging import get_logger
from groundtruth.scrapers.errors import ScrapeErrorCode
from groundtruth.scrapers.hashing import content_hash
from groundtruth.scrapers.items import ListingItem

logger = get_logger(__name__)


class BaseRealEstateSpider(scrapy.Spider):
    """
    Base spider providing common infrastructure for all sources.

    Subclasses must implement:
    - source_website: str
    - start_urls or start_requests
    - parse_listing_page (detail extraction)
    - parse_index_page (pagination / listing links)

    Features:
    - Retries and throttling via Scrapy settings
    - User-agent rotation via middleware
    - Structured logging
    - Error recovery with continued crawling
    - Pagination helpers
    """

    source_website: str = ""
    spider_version: str = "1.0.0"
    allowed_domains: list[str] = []
    custom_settings: dict[str, Any] = {}

    listings_found: int = 0
    errors_count: int = 0
    scrape_run_id: int | None = None

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        if not self.source_website:
            raise ValueError(f"{self.__class__.__name__} must define source_website")
        self.error_code_counts: dict[str, int] = {}

    def record_error(
        self,
        code: ScrapeErrorCode,
        *,
        count_as_error: bool = True,
    ) -> None:
        """Increment typed error taxonomy (+ optional scrape_runs.errors_count)."""
        key = code.value
        self.error_code_counts[key] = self.error_code_counts.get(key, 0) + 1
        if count_as_error:
            self.errors_count += 1

    # ------------------------------------------------------------------
    # Abstract hooks — implement per source
    # ------------------------------------------------------------------

    @abstractmethod
    def parse_index_page(self, response: Response) -> Iterable[scrapy.Request]:
        """Parse a listing index page. Yield requests for detail pages or next page."""
        yield from ()

    @abstractmethod
    def parse_listing_page(self, response: Response) -> Iterable[ListingItem]:
        """Parse a listing detail page. Yield ListingItem objects."""
        yield from ()

    # ------------------------------------------------------------------
    # Default entry point
    # ------------------------------------------------------------------

    def parse(self, response: Response) -> Iterable[scrapy.Request | ListingItem]:
        """Route responses to index or detail parser based on page type."""
        if self._is_detail_page(response):
            yield from self._safe_parse(self.parse_listing_page, response)
        else:
            yield from self._safe_parse(self.parse_index_page, response)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _is_detail_page(self, response: Response) -> bool:
        """Override in subclass for source-specific detail page detection."""
        return "detail" in response.meta.get("page_type", "")

    def _safe_parse(self, parser, response: Response) -> Iterable[scrapy.Request | ListingItem]:
        """Wrap parser with error recovery so one bad page doesn't kill the crawl."""
        try:
            yield from parser(response)
        except Exception as exc:
            self.record_error(ScrapeErrorCode.PARSE_EXCEPTION)
            logger.error(
                "parse_error",
                spider=self.name,
                url=response.url,
                error=str(exc),
                code=ScrapeErrorCode.PARSE_EXCEPTION.value,
                exc_info=True,
            )

    def build_listing_item(
        self,
        *,
        source_listing_id: str,
        original_url: str,
        raw_payload: dict[str, Any],
        raw_html: str | None = None,
    ) -> ListingItem:
        """Construct a ListingItem with standard fields populated."""
        item = ListingItem()
        item["source_website"] = self.source_website
        item["spider_version"] = self.spider_version
        item["source_listing_id"] = source_listing_id
        item["original_url"] = original_url
        item["raw_payload"] = raw_payload
        item["raw_html"] = raw_html
        item["content_hash"] = content_hash(raw_payload=raw_payload, raw_html=raw_html)
        item["scraped_at"] = datetime.now(UTC).isoformat()
        self.listings_found += 1
        return item

    def follow_pagination(
        self,
        response: Response,
        css_selector: str,
        callback=None,
    ) -> Iterable[scrapy.Request]:
        """Follow next-page links matching a CSS selector."""
        callback = callback or self.parse
        for href in response.css(css_selector).getall():
            yield response.follow(href, callback=callback)

    def request_detail(
        self,
        response: Response,
        url: str,
        meta: dict[str, Any] | None = None,
    ) -> scrapy.Request:
        """Create a detail page request with standard meta."""
        request_meta = {"page_type": "detail"}
        if meta:
            request_meta.update(meta)
        return response.follow(url, callback=self.parse, meta=request_meta)
