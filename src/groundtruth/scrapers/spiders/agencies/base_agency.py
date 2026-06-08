"""Base class for real estate agency website spiders."""

from groundtruth.scrapers.spiders.base import BaseRealEstateSpider


class BaseAgencySpider(BaseRealEstateSpider):
    """Common behavior for agency sites (often JS-rendered)."""

    custom_settings = {
        "PLAYWRIGHT_DEFAULT_NAVIGATION_TIMEOUT": 30_000,
    }

    use_playwright: bool = True

    def start_requests(self):
        """Use Playwright for agency sites when enabled."""
        import scrapy

        for url in self.start_urls:
            meta: dict = {}
            if self.use_playwright:
                meta["playwright"] = True
                meta["playwright_include_page"] = False
            yield scrapy.Request(url, meta=meta, callback=self.parse)
