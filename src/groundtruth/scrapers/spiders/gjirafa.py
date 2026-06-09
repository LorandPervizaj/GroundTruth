"""Gjirafa Patundshmëri spider for listime.gjirafa.com."""

from __future__ import annotations

import re
from collections.abc import Iterable

from scrapy.http import Response

from groundtruth.processing.parsers.gjirafa import parse_listing_html
from groundtruth.scrapers.items import ListingItem
from groundtruth.scrapers.spiders.base import BaseRealEstateSpider

_LISTING_URL_RE = re.compile(
    r"https?://listime\.gjirafa\.com/Shpallje/Patundshmeri/banesa-\d+",
    re.IGNORECASE,
)
_LISTING_PATH_RE = re.compile(r"/Shpallje/Patundshmeri/banesa-\d+", re.IGNORECASE)


class GjirafaSpider(BaseRealEstateSpider):
    """Spider for listime.gjirafa.com real estate listings."""

    name = "gjirafa"
    source_website = "gjirafa"
    spider_version = "1.0.0"
    allowed_domains = ["listime.gjirafa.com", "www.listime.gjirafa.com"]

    start_urls = [
        "https://listime.gjirafa.com/Top/Patundshmeri",
    ]

    custom_settings = {
        "ROBOTSTXT_OBEY": False,
        # Gjirafa serves static HTML — Playwright adds ~50s/page overhead.
        "DOWNLOAD_HANDLERS": {
            "http": "scrapy.core.downloader.handlers.http11.HTTP11DownloadHandler",
            "https": "scrapy.core.downloader.handlers.http11.HTTP11DownloadHandler",
        },
        "AUTOTHROTTLE_ENABLED": False,
        "DOWNLOAD_DELAY": 0.5,
        "CONCURRENT_REQUESTS": 8,
        "CONCURRENT_REQUESTS_PER_DOMAIN": 8,
        "LOG_LEVEL": "WARNING",
    }

    def __init__(self, max_pages: str = "250", max_listings: str = "0", *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._max_pages = int(max_pages)
        self._max_listings = int(max_listings)
        self._detail_requests_sent = 0

    def _at_listing_limit(self) -> bool:
        return self._max_listings > 0 and self._detail_requests_sent >= self._max_listings

    def _is_detail_page(self, response: Response) -> bool:
        if response.meta.get("page_type") == "detail":
            return True
        return bool(_LISTING_PATH_RE.search(response.url))

    def parse_index_page(self, response: Response) -> Iterable:
        if self._at_listing_limit():
            self.logger.info("listing_limit_reached count=%d", self._detail_requests_sent)
            return

        listing_urls: set[str] = set(_LISTING_URL_RE.findall(response.text))
        for path in _LISTING_PATH_RE.findall(response.text):
            listing_urls.add(response.urljoin(path))

        self.logger.info("index_listings_found count=%d url=%s", len(listing_urls), response.url)

        for url in sorted(listing_urls):
            if self._at_listing_limit():
                break
            self._detail_requests_sent += 1
            yield self.request_detail(response, url)

        if self._at_listing_limit():
            return

        current_page = response.meta.get("page", 0)
        if current_page + 1 < self._max_pages:
            next_page = current_page + 1
            next_url = f"{response.urljoin('/Top/Patundshmeri')}?f={next_page}"
            yield response.follow(
                next_url,
                callback=self.parse,
                meta={"page": next_page},
            )

    def parse_listing_page(self, response: Response) -> Iterable[ListingItem]:
        payload = parse_listing_html(response.text, response.url)
        listing_id = payload["source_listing_id"]

        yield self.build_listing_item(
            source_listing_id=listing_id,
            original_url=response.url,
            raw_payload=payload,
            raw_html=response.text,
        )
        if self.listings_found % 100 == 0:
            self.logger.warning(
                "crawl_progress listings=%d requests=%d",
                self.listings_found,
                self._detail_requests_sent,
            )
