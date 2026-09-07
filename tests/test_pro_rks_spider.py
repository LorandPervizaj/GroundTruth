"""Tests for Pro Real Estate spider helpers."""

from groundtruth.scrapers.pro_rks_api import (
    category_allowed,
    properties_index_url,
)
from groundtruth.scrapers.spiders.pro_rks import ProRksSpider


def test_sale_index_url() -> None:
    url = properties_index_url(listing_type="sale")
    assert "forSale=true" in url
    assert "d41787fe-44f1-4e81-87cf-4f4e4614ba0a" in url


def test_rent_index_url() -> None:
    url = properties_index_url(listing_type="rent", page=2)
    assert "forRent=true" in url
    assert "page=2" in url


def test_category_filter_excludes_land() -> None:
    allowed = frozenset({"apartment", "home", "unit"})
    assert not category_allowed(["land"], allowed)
    assert category_allowed(["apartment"], allowed)


def test_spider_start_modes() -> None:
    import asyncio

    async def _modes() -> set[str]:
        spider = ProRksSpider(listing_type="both")
        found: set[str] = set()
        async for req in spider.start():
            found.add(req.meta["listing_type"])
        return found

    assert asyncio.run(_modes()) == {"sale", "rent"}
