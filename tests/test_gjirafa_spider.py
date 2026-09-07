"""Tests for Gjirafa spider slug discovery."""

import asyncio

import pytest

from groundtruth.scrapers.spiders.gjirafa import (
    GjirafaRentSpider,
    GjirafaSaleSpider,
    GjirafaSpider,
    build_gjirafa_index_url,
)


def test_slug_allowed_for_apartments_and_houses() -> None:
    spider = GjirafaSpider(categories="banesa,shtepi-vila")
    assert spider._slug_allowed("banesa-123")
    assert spider._slug_allowed("shtepi-vila-5218")
    assert spider._slug_allowed("shtepi-99")
    assert not spider._slug_allowed("objekte-afariste-6484")
    assert not spider._slug_allowed("ara-dhe-ferma-4920")


def test_slug_allowed_for_commercial_and_offices() -> None:
    spider = GjirafaSpider(categories="objekte-afariste,zyre")
    assert spider._slug_allowed("objekte-afariste-6484")
    assert spider._slug_allowed("zyre-12")
    assert not spider._slug_allowed("banesa-123")


def test_skips_land_category_on_detail_page() -> None:
    spider = GjirafaSpider()
    assert spider._is_land_listing({"category": "Ara dhe ferma"})
    assert not spider._is_land_listing({"category": "Banesa"})


def test_sale_index_url_matches_gjirafa_filter() -> None:
    url = build_gjirafa_index_url(page=0, listing_type="sale", category="banesa")
    assert url == (
        "https://listime.gjirafa.com/Top/Patundshmeri?"
        "f=0&sh=Kosove&r=Prishtine&llshp=Shitet&k=Banesa"
    )


def test_house_rent_index_url() -> None:
    url = build_gjirafa_index_url(page=0, listing_type="rent", category="shtepi-vila")
    assert "llshp=Qira" in url
    assert "k=Shtepi/Vila" in url


def test_commercial_and_office_index_urls() -> None:
    commercial = build_gjirafa_index_url(
        page=0, listing_type="sale", category="objekte-afariste"
    )
    office = build_gjirafa_index_url(page=0, listing_type="rent", category="zyre")
    assert "k=Objekte%20Afariste" in commercial
    assert "llshp=Shitet" in commercial
    assert "k=Zyre" in office
    assert "llshp=Qira" in office


def test_sale_index_pagination() -> None:
    url = build_gjirafa_index_url(page=3, listing_type="sale", category="banesa")
    assert "f=3" in url
    assert "llshp=Shitet" in url
    assert "k=Banesa" in url


def test_listing_type_sets_category_start_urls() -> None:
    spider = GjirafaSpider(listing_type="sale", categories="banesa,zyre")
    assert spider.start_urls == [
        "https://listime.gjirafa.com/Top/Patundshmeri?"
        "f=0&sh=Kosove&r=Prishtine&llshp=Shitet&k=Banesa",
        "https://listime.gjirafa.com/Top/Patundshmeri?"
        "f=0&sh=Kosove&r=Prishtine&llshp=Shitet&k=Zyre",
    ]


def test_invalid_listing_type_raises() -> None:
    with pytest.raises(ValueError, match="listing_type"):
        GjirafaSpider(listing_type="bogus")


def test_invalid_category_raises() -> None:
    with pytest.raises(ValueError, match="categories"):
        GjirafaSpider(categories="banesa,not-a-cat")


def test_start_page_sets_index_url() -> None:
    spider = GjirafaSpider(listing_type="sale", start_page="42", categories="banesa")
    assert "f=42" in spider.start_urls[0]
    assert "llshp=Shitet" in spider.start_urls[0]
    assert "k=Banesa" in spider.start_urls[0]


def test_rent_spider_uses_qira_index_urls() -> None:
    spider = GjirafaRentSpider(categories="banesa,zyre")
    assert all("llshp=Qira" in url for url in spider.start_urls)
    assert spider._listing_type == "rent"


def test_sale_spider_uses_shitet_index_urls() -> None:
    spider = GjirafaSaleSpider(categories="banesa,zyre")
    assert all("llshp=Shitet" in url for url in spider.start_urls)
    assert spider._listing_type == "sale"


def test_rent_and_sale_spiders_have_distinct_names() -> None:
    assert GjirafaRentSpider.name == "gjirafa-rent"
    assert GjirafaSaleSpider.name == "gjirafa-sale"


def test_async_start_yields_request_per_category() -> None:
    async def _collect():
        spider = GjirafaSpider(listing_type="rent", start_page="5", categories="banesa,zyre")
        return [req async for req in spider.start()]

    reqs = asyncio.run(_collect())
    assert len(reqs) == 2
    assert reqs[0].meta["page"] == 5
    assert reqs[0].meta["category"] == "banesa"
    assert reqs[1].meta["category"] == "zyre"
