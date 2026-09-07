"""Tests for P0/P1 scraper hardening."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

from scrapy.http import HtmlResponse, Request, TextResponse
from scrapy.settings import Settings

from groundtruth.crawl.weekly import _build_crawl_command
from groundtruth.processing.parsers.pro_rks import extract_listing_date
from groundtruth.scrapers.hashing import canonical_payload_text, content_hash
from groundtruth.scrapers.middlewares import AdaptiveRetryMiddleware
from groundtruth.scrapers.pipelines import RawListingPipeline
from groundtruth.scrapers.spiders.gjirafa import GjirafaSpider


def test_canonical_json_hash_is_key_order_stable() -> None:
    left = {"b": 2, "a": {"z": 1, "y": 2}}
    right = {"a": {"y": 2, "z": 1}, "b": 2}
    assert canonical_payload_text(left) == canonical_payload_text(right)
    assert content_hash(raw_payload=left) == content_hash(raw_payload=right)
    assert content_hash(raw_payload=left) != content_hash(raw_payload={"a": 1})


def test_adaptive_retry_returns_deferred_backoff() -> None:
    settings = Settings({"RETRY_TIMES": 4, "RETRY_HTTP_CODES": [500]})
    middleware = AdaptiveRetryMiddleware(settings)
    request = Request("https://example.com/listing")
    response = TextResponse(
        url=request.url,
        status=429,
        body=b"rate limited",
        request=request,
    )
    spider = SimpleNamespace(name="test")
    result = middleware.process_response(request, response, spider)
    assert hasattr(result, "addCallback")

    from twisted.internet import reactor

    delayed = [call for call in reactor.getDelayedCalls() if not call.cancelled]
    assert delayed
    # Cancel scheduled wall-clock wait; assert the deferred path exists.
    for call in delayed:
        call.cancel()
    assert result.called is False
    retry = Request(request.url, meta={"retry_times": 1}, dont_filter=True)
    result.callback(retry)
    assert result.result is retry
    assert retry.meta["retry_times"] == 1
    assert retry.dont_filter is True


def test_pro_rks_listing_date_from_image_created_at() -> None:
    prop = {
        "images": [
            {
                "createdAt": "2026-07-23T15:04:58.747Z",
                "original": {"url": "media/2026-07/a-original.png"},
            },
            {
                "createdAt": "2026-07-20T10:00:00.000Z",
                "original": {"url": "media/2026-07/b-original.png"},
            },
        ]
    }
    assert extract_listing_date(prop).isoformat() == "2026-07-20"


def test_pro_rks_listing_date_falls_back_to_media_path() -> None:
    prop = {
        "images": [
            {"original": {"url": "media/2026-05/sample-original.png"}},
            {"lg": {"url": "media/2026-06/sample-lg.png"}},
        ]
    }
    assert extract_listing_date(prop).isoformat() == "2026-05-01"


def test_gjirafa_stops_on_empty_index() -> None:
    spider = GjirafaSpider(max_pages="10", skip_existing="false")
    request = Request("https://listime.gjirafa.com/Top/Patundshmeri?f=0")
    response = HtmlResponse(
        url=request.url,
        request=request,
        body=b"<html><body><p>No listings here</p></body></html>",
        encoding="utf-8",
    )
    response.meta["page"] = 0
    assert list(spider.parse_index_page(response)) == []
    assert spider._index_empty_pages == 1


def test_gjirafa_detects_soft_block() -> None:
    spider = GjirafaSpider(max_pages="10", skip_existing="false")
    request = Request("https://listime.gjirafa.com/Top/Patundshmeri?f=0")
    response = HtmlResponse(
        url=request.url,
        request=request,
        body=b"<html><title>Just a moment...</title><div>cf-browser-verification</div></html>",
        encoding="utf-8",
    )
    response.meta["page"] = 0
    assert list(spider.parse_index_page(response)) == []
    assert spider._soft_block_hits == 1
    assert spider._stop_index is True


def test_gjirafa_ignores_cloudflare_analytics_beacon() -> None:
    spider = GjirafaSpider(max_pages="10", skip_existing="false")
    request = Request("https://listime.gjirafa.com/Top/Patundshmeri?f=0")
    body = (
        b'<html><script src="https://static.cloudflareinsights.com/beacon.min.js"></script>'
        b'<a href="/Shpallje/Patundshmeri/banesa-12345">listing</a></html>'
    )
    response = HtmlResponse(url=request.url, request=request, body=body, encoding="utf-8")
    response.meta["page"] = 0
    assert spider._looks_like_soft_block(response) is False


def test_weekly_gjirafa_rent_command_uses_dedicated_spider() -> None:
    cmd = _build_crawl_command(
        "gjirafa-rent",
        {
            "max_pages": "20",
            "max_age_days": "7",
            "skip_existing": "true",
            "skip_existing_days": "7",
            "categories": "banesa,zyre",
            "crawl_window": '{"crawl_week":"2026-W36"}',
        },
    )
    assert "gjirafa-rent" in cmd
    assert "--listing-type" not in cmd
    assert "--categories" in cmd
    assert "--max-age-days" in cmd


def test_weekly_command_includes_crawl_window_and_skip_flags() -> None:
    cmd = _build_crawl_command(
        "vision",
        {
            "max_pages": "15",
            "max_age_days": "7",
            "skip_existing": "true",
            "skip_existing_days": "7",
            "prishtina_only": "true",
            "crawl_window": '{"crawl_mode":"weekly","window_days":7}',
        },
    )
    assert "vision" in cmd
    assert "--skip-existing-days" in cmd
    assert "7" in cmd
    assert "--crawl-window" in cmd
    assert '{"crawl_mode":"weekly","window_days":7}' in cmd
    assert "--max-age-days" not in cmd


def test_pipeline_metadata_parses_crawl_window_json() -> None:
    spider = SimpleNamespace(
        name="vision",
        source_website="vision",
        crawl_window='{"crawl_mode":"weekly","window_days":7,"crawl_week":"2026-W30"}',
    )
    metadata = RawListingPipeline._spider_metadata(spider)
    assert metadata["crawl_mode"] == "weekly"
    assert metadata["window_days"] == 7
    assert metadata["crawl_week"] == "2026-W30"


def test_pipeline_scrapy_stats_snapshot() -> None:
    stats = MagicMock()
    stats.get_value.side_effect = lambda key, default=None: {
        "downloader/request_count": 12,
        "retry/count": 2,
        "downloader/response_status_count/429": 1,
    }.get(key, default)
    stats.get_stats.return_value = {
        "downloader/response_status_count/200": 10,
        "downloader/response_status_count/429": 1,
    }
    spider = SimpleNamespace(
        crawler=SimpleNamespace(stats=stats),
        _detail_skipped_existing=3,
        _soft_block_hits=0,
    )
    snapshot = RawListingPipeline._scrapy_stats_snapshot(spider)
    assert snapshot["downloader/request_count"] == 12
    assert snapshot["retry/count"] == 2
    assert snapshot["response_status_counts"]["429"] == 1
    assert snapshot["spider"]["detail_skipped_existing"] == 3
