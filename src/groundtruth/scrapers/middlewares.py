"""Scrapy downloader middlewares — fingerprint rotation, referer, adaptive retry."""

from __future__ import annotations

import random
from urllib.parse import urlparse

from scrapy import signals
from scrapy.downloadermiddlewares.retry import RetryMiddleware
from scrapy.http import Request, Response
from scrapy.spiders import Spider
from twisted.internet import reactor
from twisted.internet.defer import Deferred

from groundtruth.config import get_settings
from groundtruth.logging import get_logger
from groundtruth.scrapers.anti_detect import build_browser_headers, pick_user_agent
from groundtruth.scrapers.errors import ScrapeErrorCode

logger = get_logger(__name__)


class BrowserFingerprintMiddleware:
    """Apply realistic browser headers (UA, sec-ch-ua, Accept-Language) per request."""

    _JSON_URL_MARKERS = ("/wp-json/", "/api/", ".json")

    def _accept_kind(self, request: Request) -> str:
        if request.meta.get("accept_json"):
            return "json"
        url = request.url.lower()
        if any(marker in url for marker in self._JSON_URL_MARKERS):
            return "json"
        accept = request.headers.get("Accept") or request.headers.get(b"Accept")
        if accept:
            value = (
                accept.decode("utf-8", errors="ignore")
                if isinstance(accept, bytes)
                else str(accept)
            )
            if "application/json" in value:
                return "json"
        return "html"

    def process_request(self, request: Request, spider: Spider):
        if request.meta.get("skip_fingerprint"):
            return None

        accept = self._accept_kind(request)
        referer = request.headers.get("Referer") or request.headers.get(b"Referer")
        if referer and isinstance(referer, bytes):
            referer = referer.decode("utf-8", errors="ignore")

        headers = build_browser_headers(
            referer=referer if isinstance(referer, str) else None,
            accept=accept,
        )
        for key, value in headers.items():
            request.headers[key] = value
        return None


class RefererMiddleware:
    """Set same-site Referer on detail/sub-resource requests."""

    def process_request(self, request: Request, spider: Spider):
        if request.headers.get("Referer") or request.headers.get(b"Referer"):
            return None
        if request.meta.get("page_type") != "detail":
            return None

        parsed = urlparse(request.url)
        origin = f"{parsed.scheme}://{parsed.netloc}/"
        request.headers["Referer"] = origin
        return None


class AdaptiveRetryMiddleware(RetryMiddleware):
    """Retry with exponential backoff + jitter on rate limits and soft blocks."""

    def __init__(self, settings):
        super().__init__(settings)
        self._max_retry_times = settings.getint("RETRY_TIMES", 4)

    def process_response(self, request: Request, response: Response, spider: Spider):
        if request.meta.get("dont_retry"):
            return response

        if response.status in {403, 429}:
            code = (
                ScrapeErrorCode.HTTP_403
                if response.status == 403
                else ScrapeErrorCode.HTTP_429
            )
            record = getattr(spider, "record_error", None)
            if callable(record):
                record(code, count_as_error=False)
            return self._retry_with_backoff(
                request, response, spider, reason=f"http_{response.status}"
            )

        if response.status in self.retry_http_codes:
            reason = getattr(response, "reason", None)
            return self._retry(request, reason, spider) or response

        return response

    def _retry_with_backoff(
        self,
        request: Request,
        response: Response,
        spider: Spider,
        *,
        reason: str,
    ):
        retry_times = request.meta.get("retry_times", 0) + 1
        if retry_times > self._max_retry_times:
            logger.warning(
                "retry_exhausted",
                spider=spider.name,
                url=request.url,
                status=response.status,
                retries=retry_times,
            )
            return response

        delay = min(2.0**retry_times + random.uniform(0.0, 1.0), 30.0)
        logger.info(
            "retry_backoff",
            spider=spider.name,
            url=request.url,
            status=response.status,
            delay_sec=round(delay, 2),
            attempt=retry_times,
        )

        new_request = request.copy()
        new_request.meta["retry_times"] = retry_times
        new_request.dont_filter = True

        # Scrapy ignores meta["download_delay"]; defer the retry so backoff is real.
        deferred: Deferred = Deferred()
        reactor.callLater(delay, deferred.callback, new_request)
        return deferred


class UserAgentRotationMiddleware:
    """Legacy-compatible UA rotation when fingerprint middleware is disabled."""

    def __init__(self) -> None:
        self._settings = get_settings()

    def process_request(self, request: Request, spider: Spider):
        if not self._settings.scrapy_user_agent_rotation:
            return None
        if request.meta.get("skip_fingerprint"):
            request.headers["User-Agent"] = pick_user_agent()
        return None


class StructlogMiddleware:
    """Log request/response lifecycle with structlog."""

    @classmethod
    def from_crawler(cls, crawler):
        middleware = cls()
        crawler.signals.connect(middleware.spider_opened, signal=signals.spider_opened)
        crawler.signals.connect(middleware.spider_closed, signal=signals.spider_closed)
        return middleware

    def spider_opened(self, spider) -> None:
        logger.info("spider_opened", spider=spider.name, fast_mode=get_settings().scrapy_fast_mode)

    def spider_closed(self, spider, reason) -> None:
        logger.info("spider_closed", spider=spider.name, reason=reason)

    def process_response(self, request, response, spider):
        if response.status >= 400:
            logger.warning(
                "http_error",
                spider=spider.name,
                url=request.url,
                status=response.status,
            )
        return response
