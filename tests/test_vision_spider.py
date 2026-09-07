"""Tests for Vision Real Estate spider helpers."""

import asyncio

from groundtruth.scrapers.spiders.vision import VisionSpider
from groundtruth.scrapers.vision_api import properties_index_url


def test_properties_index_url() -> None:
    url = properties_index_url(page=2, per_page=50)
    assert "page=2" in url
    assert "per_page=50" in url
    assert url.endswith("/properties?per_page=50&page=2") or "properties" in url


def test_spider_start_yields_first_page() -> None:
    async def _first_url() -> str:
        spider = VisionSpider()
        req = None
        async for r in spider.start():
            req = r
            break
        assert req is not None
        return req.url

    url = asyncio.run(_first_url())
    assert "properties" in url
    assert "page=1" in url
