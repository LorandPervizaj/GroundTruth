"""MerrJep spider stub. Selectors to be implemented."""

from collections.abc import Iterable

from scrapy.http import Response

from groundtruth.scrapers.items import ListingItem
from groundtruth.scrapers.spiders.base import BaseRealEstateSpider


class MerrJepSpider(BaseRealEstateSpider):
    """Spider for merrjep.com real estate listings."""

    name = "merrjep"
    source_website = "merrjep"
    allowed_domains = ["merrjep.com", "www.merrjep.com"]

    start_urls = [
        "https://www.merrjep.com/shpallje/",
    ]

    def parse_index_page(self, response: Response) -> Iterable:
        """TODO: Extract listing links and pagination."""
        self.logger.info("parse_index_page stub", url=response.url)
        return
        yield  # pragma: no cover

    def parse_listing_page(self, response: Response) -> Iterable[ListingItem]:
        """TODO: Extract listing fields into raw payload."""
        self.logger.info("parse_listing_page stub", url=response.url)
        return
        yield  # pragma: no cover
