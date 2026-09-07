"""Tests for P2 scraper polish (errors, UAs, monitor helpers, fixtures)."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from scrapy.http import Request, TextResponse
from scrapy.settings import Settings

from groundtruth.scrapers.anti_detect import _CHROME_PROFILES, _FIREFOX_USER_AGENTS, pick_user_agent
from groundtruth.scrapers.errors import ScrapeErrorCode
from groundtruth.scrapers.middlewares import AdaptiveRetryMiddleware
from groundtruth.scrapers.pipelines import RawListingPipeline
from groundtruth.scrapers.spiders.base import BaseRealEstateSpider
from groundtruth.scrapers.spiders.gjirafa import GjirafaSpider


def test_user_agents_are_current_majors() -> None:
    for profile in _CHROME_PROFILES:
        assert "Chrome/138" in profile["user_agent"]
        assert 'v="138"' in profile["sec_ch_ua"]
    for ua in _FIREFOX_USER_AGENTS:
        assert "Firefox/140" in ua
    picked = pick_user_agent()
    assert "Mozilla/5.0" in picked


def test_record_error_taxonomy() -> None:
    class _Tiny(BaseRealEstateSpider):
        name = "tiny"
        source_website = "tiny"

        def parse_index_page(self, response):
            yield from ()

        def parse_listing_page(self, response):
            yield from ()

    spider = _Tiny()
    spider.record_error(ScrapeErrorCode.JSON_DECODE)
    spider.record_error(ScrapeErrorCode.EMPTY_INDEX, count_as_error=False)
    assert spider.errors_count == 1
    assert spider.error_code_counts[ScrapeErrorCode.JSON_DECODE.value] == 1
    assert spider.error_code_counts[ScrapeErrorCode.EMPTY_INDEX.value] == 1


def test_soft_block_records_error_code() -> None:
    spider = GjirafaSpider(max_pages="10", skip_existing="false")
    request = Request("https://listime.gjirafa.com/Top/Patundshmeri?f=0")
    response = TextResponse(
        url=request.url,
        request=request,
        body=b"<html><title>Just a moment...</title><div>cf-browser-verification</div></html>",
        encoding="utf-8",
    )
    response.meta["page"] = 0
    assert list(spider.parse_index_page(response)) == []
    assert spider.error_code_counts[ScrapeErrorCode.SOFT_BLOCK.value] == 1
    assert spider.errors_count == 1


def test_http_429_records_code_without_failing_run() -> None:
    settings = Settings({"RETRY_TIMES": 4, "RETRY_HTTP_CODES": [500]})
    middleware = AdaptiveRetryMiddleware(settings)
    request = Request("https://example.com/listing")
    response = TextResponse(url=request.url, status=429, body=b"slow down", request=request)
    spider = SimpleNamespace(name="test", error_code_counts={}, errors_count=0)

    def record_error(code, *, count_as_error=True):
        spider.error_code_counts[code.value] = spider.error_code_counts.get(code.value, 0) + 1
        if count_as_error:
            spider.errors_count += 1

    spider.record_error = record_error
    result = middleware.process_response(request, response, spider)
    assert hasattr(result, "addCallback")
    from twisted.internet import reactor

    for call in list(reactor.getDelayedCalls()):
        if not call.cancelled:
            call.cancel()
    assert spider.error_code_counts[ScrapeErrorCode.HTTP_429.value] == 1
    assert spider.errors_count == 0


def test_pipeline_includes_error_codes() -> None:
    spider = SimpleNamespace(
        crawler=None,
        error_code_counts={"json_decode": 2},
        _detail_skipped_existing=1,
    )
    snapshot = RawListingPipeline._scrapy_stats_snapshot(spider)
    assert snapshot["error_codes"]["json_decode"] == 2
    assert snapshot["spider"]["detail_skipped_existing"] == 1


def test_contract_fixture_files_exist() -> None:
    root = Path(__file__).resolve().parent / "fixtures"
    expected = [
        root / "gjirafa" / "listing.html",
        root / "merrjep" / "listing.html",
        root / "pro_rks" / "detail.json",
        root / "topia" / "property.json",
        root / "vision" / "property.json",
        root / "myrealestate" / "property.json",
    ]
    for path in expected:
        assert path.is_file(), path


def test_crawl_monitor_known_spiders() -> None:
    import importlib.util

    path = Path(__file__).resolve().parents[1] / "scripts" / "crawl_monitor.py"
    spec = importlib.util.spec_from_file_location("crawl_monitor", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    assert "merrjep" in module.KNOWN_SPIDERS
    assert "pro-rks" in module.KNOWN_SPIDERS
    stopped = {
        "spider": "gjirafa",
        "ts": "2026-07-24T00:00:00+00:00",
        "process_running": False,
        "raw_count": 10,
        "seconds_since_last_scrape": 30,
        "scrape_run_id": 1,
        "scrape_run_status": "COMPLETED",
        "errors_count": 0,
        "error_codes": None,
    }
    assert module.assess(stopped) == "STOPPED"
    assert "gjirafa" in module.log_line(stopped)
