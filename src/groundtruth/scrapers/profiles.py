"""Scrapy setting profiles — conservative default vs fast research mode."""

from __future__ import annotations

from typing import Any, Literal

from groundtruth.config import get_settings
from groundtruth.scrapers.anti_detect import http11_handlers

ProfileName = Literal["api", "html", "browser"]

_BASE_PERFORMANCE: dict[str, Any] = {
    "REACTOR_THREADPOOL_MAXSIZE": 32,
    "DNSCACHE_ENABLED": True,
    "DNSCACHE_SIZE": 10000,
    "DOWNLOAD_TIMEOUT": 30,
    "COMPRESSION_ENABLED": True,
    "COOKIES_ENABLED": True,
    "REDIRECT_ENABLED": True,
    "REDIRECT_MAX_TIMES": 5,
    "RETRY_ENABLED": True,
    "RETRY_TIMES": 4,
    "RETRY_HTTP_CODES": [403, 408, 429, 500, 502, 503, 504],
    "DOWNLOAD_FAIL_ON_DNF": False,
}


def _conservative_html_settings() -> dict[str, Any]:
    settings = get_settings()
    return {
        **_BASE_PERFORMANCE,
        "DOWNLOAD_HANDLERS": http11_handlers(),
        "ROBOTSTXT_OBEY": True,
        "AUTOTHROTTLE_ENABLED": True,
        "AUTOTHROTTLE_START_DELAY": settings.scrapy_download_delay,
        "AUTOTHROTTLE_MAX_DELAY": 10.0,
        "AUTOTHROTTLE_TARGET_CONCURRENCY": 2.0,
        "DOWNLOAD_DELAY": settings.scrapy_download_delay,
        "RANDOMIZE_DOWNLOAD_DELAY": True,
        "CONCURRENT_REQUESTS": settings.scrapy_concurrent_requests,
        "CONCURRENT_REQUESTS_PER_DOMAIN": settings.scrapy_concurrent_requests,
        "LOG_LEVEL": "WARNING",
    }


def _fast_html_settings() -> dict[str, Any]:
    settings = get_settings()
    concurrent = max(settings.scrapy_html_concurrent_requests, 8)
    per_domain = max(concurrent // 2, 4)
    delay = max(settings.scrapy_html_download_delay, 0.0)
    return {
        **_BASE_PERFORMANCE,
        "DOWNLOAD_HANDLERS": http11_handlers(),
        "ROBOTSTXT_OBEY": True,
        "AUTOTHROTTLE_ENABLED": delay > 0,
        "AUTOTHROTTLE_START_DELAY": delay or 0.25,
        "AUTOTHROTTLE_MAX_DELAY": 3.0,
        "AUTOTHROTTLE_TARGET_CONCURRENCY": float(per_domain),
        "DOWNLOAD_DELAY": delay,
        "RANDOMIZE_DOWNLOAD_DELAY": True,
        "CONCURRENT_REQUESTS": concurrent,
        "CONCURRENT_REQUESTS_PER_DOMAIN": per_domain,
        "LOG_LEVEL": "WARNING",
    }


def _conservative_api_settings() -> dict[str, Any]:
    settings = get_settings()
    return {
        **_BASE_PERFORMANCE,
        "DOWNLOAD_HANDLERS": http11_handlers(),
        "ROBOTSTXT_OBEY": False,
        "AUTOTHROTTLE_ENABLED": True,
        "AUTOTHROTTLE_START_DELAY": 0.5,
        "AUTOTHROTTLE_MAX_DELAY": 5.0,
        "AUTOTHROTTLE_TARGET_CONCURRENCY": 2.0,
        "DOWNLOAD_DELAY": 0.5,
        "RANDOMIZE_DOWNLOAD_DELAY": True,
        "CONCURRENT_REQUESTS": settings.scrapy_concurrent_requests,
        "CONCURRENT_REQUESTS_PER_DOMAIN": settings.scrapy_concurrent_requests,
        "LOG_LEVEL": "WARNING",
    }


def _fast_api_settings() -> dict[str, Any]:
    settings = get_settings()
    concurrent = max(settings.scrapy_api_concurrent_requests, 16)
    per_domain = max(concurrent // 2, 8)
    return {
        **_BASE_PERFORMANCE,
        "DOWNLOAD_HANDLERS": http11_handlers(),
        "ROBOTSTXT_OBEY": False,
        "AUTOTHROTTLE_ENABLED": False,
        "DOWNLOAD_DELAY": 0.0,
        "RANDOMIZE_DOWNLOAD_DELAY": False,
        "CONCURRENT_REQUESTS": concurrent,
        "CONCURRENT_REQUESTS_PER_DOMAIN": per_domain,
        "LOG_LEVEL": "WARNING",
    }


def _browser_settings() -> dict[str, Any]:
    """Playwright profile for JS-heavy agency sites only."""
    settings = get_settings()
    return {
        **_BASE_PERFORMANCE,
        "AUTOTHROTTLE_ENABLED": True,
        "AUTOTHROTTLE_START_DELAY": settings.scrapy_download_delay,
        "AUTOTHROTTLE_MAX_DELAY": 15.0,
        "AUTOTHROTTLE_TARGET_CONCURRENCY": 1.0,
        "DOWNLOAD_DELAY": settings.scrapy_download_delay,
        "RANDOMIZE_DOWNLOAD_DELAY": True,
        "CONCURRENT_REQUESTS": min(settings.scrapy_concurrent_requests, 2),
        "CONCURRENT_REQUESTS_PER_DOMAIN": 1,
        "PLAYWRIGHT_BROWSER_TYPE": "chromium",
        "PLAYWRIGHT_LAUNCH_OPTIONS": {"headless": True},
        "PLAYWRIGHT_DEFAULT_NAVIGATION_TIMEOUT": 30_000,
        "LOG_LEVEL": "WARNING",
    }


def spider_settings(profile: ProfileName) -> dict[str, Any]:
    """Return Scrapy custom_settings for the given transport profile."""
    fast = get_settings().scrapy_fast_mode
    if profile == "api":
        return _fast_api_settings() if fast else _conservative_api_settings()
    if profile == "html":
        return _fast_html_settings() if fast else _conservative_html_settings()
    return _browser_settings()
