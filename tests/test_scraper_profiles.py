"""Tests for anti-detection header builder and spider profiles."""

from groundtruth.scrapers.anti_detect import (
    build_api_headers,
    build_browser_headers,
    pick_user_agent,
)
from groundtruth.scrapers.profiles import spider_settings


class TestAntiDetect:
    def test_pick_user_agent_returns_browser_string(self) -> None:
        ua = pick_user_agent()
        assert "Mozilla" in ua

    def test_build_browser_headers_includes_sec_ch_ua_for_chrome(self) -> None:
        headers = build_browser_headers(accept="html")
        assert "User-Agent" in headers
        assert "Accept-Language" in headers
        ua = headers["User-Agent"]
        if isinstance(ua, str) and "Chrome/" in ua:
            assert "Sec-CH-UA" in headers

    def test_build_api_headers_json_accept(self) -> None:
        headers = build_api_headers()
        assert "application/json" in str(headers["Accept"])

    def test_build_browser_headers_with_referer(self) -> None:
        headers = build_browser_headers(referer="https://merrjep.com/", accept="html")
        assert headers["Referer"] == "https://merrjep.com/"
        assert headers["Sec-Fetch-Site"] == "same-origin"


class TestSpiderProfiles:
    def test_html_profile_has_http_handler(self) -> None:
        settings = spider_settings("html")
        handler = settings["DOWNLOAD_HANDLERS"]["https"]
        assert "HTTP11DownloadHandler" in handler

    def test_api_profile_fast_mode_high_concurrency(self, monkeypatch) -> None:
        from groundtruth.config import get_settings

        get_settings.cache_clear()
        monkeypatch.setenv("SCRAPY_FAST_MODE", "true")
        monkeypatch.setenv("SCRAPY_API_CONCURRENT_REQUESTS", "32")
        get_settings.cache_clear()

        settings = spider_settings("api")
        assert settings["CONCURRENT_REQUESTS"] >= 16
        assert settings["DOWNLOAD_DELAY"] == 0.0
        assert settings["AUTOTHROTTLE_ENABLED"] is False

        get_settings.cache_clear()

    def test_api_profile_defaults_to_conservative(self, monkeypatch) -> None:
        from groundtruth.config import get_settings

        get_settings.cache_clear()
        monkeypatch.delenv("SCRAPY_FAST_MODE", raising=False)
        get_settings.cache_clear()

        settings = spider_settings("api")
        assert settings["AUTOTHROTTLE_ENABLED"] is True
        assert settings["DOWNLOAD_DELAY"] == 0.5
        assert settings["CONCURRENT_REQUESTS"] <= 8

        get_settings.cache_clear()

    def test_browser_profile_uses_playwright_options(self) -> None:
        settings = spider_settings("browser")
        assert "PLAYWRIGHT_BROWSER_TYPE" in settings
