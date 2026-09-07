"""Tests for MerrJep production detail spider."""

import asyncio
import json

from scrapy.http import HtmlResponse, Request

from groundtruth.scrapers.spiders.merrjep import MerrJepSpider

SAMPLE_PRODUCT = {
    "@type": "Product",
    "name": "Banese ne shitje",
    "description": "Banesë në shitje në Ulpianë. Çmimi: €105,000. 44m²",
    "offers": {"price": 0.0, "priceCurrency": "EUR"},
}

PUBLISHED_SNIPPET = """
<div class="ad-publish-info-area">
    <bdi class="published-date">maj 16 2026</bdi>
    <bdi class="published-time">14:30</bdi>
</div>
"""

SAMPLE_HTML = (
    '<html><script type="application/ld+json">'
    + json.dumps(SAMPLE_PRODUCT)
    + f"</script>{PUBLISHED_SNIPPET}</html>"
)

OLD_PUBLISHED_SNIPPET = """
<div class="ad-publish-info-area">
    <bdi class="published-date">gush 07 2015</bdi>
    <bdi class="published-time">10:42</bdi>
</div>
"""

OLD_SAMPLE_HTML = (
    '<html><script type="application/ld+json">'
    + json.dumps(SAMPLE_PRODUCT)
    + f"</script>{OLD_PUBLISHED_SNIPPET}</html>"
)


class TestMerrJepSpiderResume:
    def test_start_requests_begin_at_start_page(self) -> None:
        spider = MerrJepSpider(
            discovery_only="false",
            archive_only="false",
            index="apartments_rent",
            start_page="130",
        )

        async def collect() -> list:
            return [req async for req in spider.start()]

        requests = asyncio.run(collect())
        assert len(requests) == 1
        assert "Page=130" in requests[0].url
        assert requests[0].meta["page"] == 130


class TestMerrJepSpiderSkipExisting:
    def test_skips_detail_request_for_existing_id(self, monkeypatch) -> None:
        monkeypatch.setattr(
            "groundtruth.scrapers.spiders.merrjep.load_skip_listing_ids",
            lambda **kwargs: {"15838177"},
        )
        spider = MerrJepSpider(
            discovery_only="false",
            archive_only="false",
            skip_existing="true",
        )
        spider._existing_ids = {"15838177"}

        index_html = (
            '<html><a href="/shpallja/banese-ne-shitje/15838177">one</a>'
            '<a href="/shpallja/banese-me-qera/99999999">two</a></html>'
        )
        index_url = (
            "https://www.merrjep.com/shpallje/patundshmeri/banesa/me-qera/prishtine?Page=130"
        )
        response = HtmlResponse(
            url=index_url,
            body=index_html.encode(),
            encoding="utf-8",
            request=Request(index_url, meta={"page": 130}),
        )

        outputs = list(spider.parse_index_page(response))
        request_urls = [r.url for r in outputs if hasattr(r, "url")]

        assert spider._detail_skipped_existing == 1
        assert len(request_urls) == 1
        assert "99999999" in request_urls[0]


class TestMerrJepSpiderDetail:
    def test_parse_listing_page_yields_item(self) -> None:
        spider = MerrJepSpider(
            discovery_only="false",
            archive_only="false",
        )
        url = "https://www.merrjep.com/shpallja/banese-ne-shitje/15838177"
        response = HtmlResponse(
            url=url,
            body=SAMPLE_HTML.encode(),
            encoding="utf-8",
            request=Request(url, meta={"page_type": "detail"}),
        )

        items = list(spider.parse_listing_page(response))

        assert len(items) == 1
        item = items[0]
        assert item["source_website"] == "merrjep"
        assert item["source_listing_id"] == "15838177"
        assert item["raw_payload"]["has_ld_json"] is True
        assert item["raw_payload"]["published_date"] == "2026-05-16"
        assert item["raw_html"] == SAMPLE_HTML


class TestMerrJepSpiderAgeFilter:
    def test_skips_listing_older_than_max_age(self) -> None:
        spider = MerrJepSpider(
            discovery_only="false",
            archive_only="false",
            max_age_months="12",
            stale_streak_limit="3",
        )
        url = "https://www.merrjep.com/shpallja/banese-ne-shitje/15838177"
        response = HtmlResponse(
            url=url,
            body=OLD_SAMPLE_HTML.encode(),
            encoding="utf-8",
            request=Request(url, meta={"page_type": "detail"}),
        )

        items = list(spider.parse_listing_page(response))

        assert items == []
        assert spider._detail_skipped_too_old == 1
        assert spider._stale_streak == 1

    def test_stops_index_after_stale_streak(self) -> None:
        spider = MerrJepSpider(
            discovery_only="false",
            archive_only="false",
            max_age_months="12",
            stale_streak_limit="2",
        )
        url = "https://www.merrjep.com/shpallja/banese-ne-shitje/15838177"
        response = HtmlResponse(
            url=url,
            body=OLD_SAMPLE_HTML.encode(),
            encoding="utf-8",
            request=Request(url, meta={"page_type": "detail"}),
        )

        list(spider.parse_listing_page(response))
        list(spider.parse_listing_page(response))

        assert spider._stop_index is True
