"""Scrapy downloader middlewares."""

import random

from scrapy import signals
from scrapy.downloadermiddlewares.useragent import UserAgentMiddleware

from groundtruth.config import get_settings
from groundtruth.logging import get_logger

logger = get_logger(__name__)

_DEFAULT_USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:123.0) Gecko/20100101 Firefox/123.0",
]


class UserAgentRotationMiddleware(UserAgentMiddleware):
    """Rotate user agents when enabled in settings."""

    def __init__(self, user_agent: str = "") -> None:
        super().__init__(user_agent)
        self._settings = get_settings()
        self._agents = _DEFAULT_USER_AGENTS

    def process_request(self, request, spider):
        if self._settings.scrapy_user_agent_rotation:
            request.headers["User-Agent"] = random.choice(self._agents)
        return super().process_request(request, spider)


class StructlogMiddleware:
    """Log request/response lifecycle with structlog."""

    @classmethod
    def from_crawler(cls, crawler):
        middleware = cls()
        crawler.signals.connect(middleware.spider_opened, signal=signals.spider_opened)
        crawler.signals.connect(middleware.spider_closed, signal=signals.spider_closed)
        return middleware

    def spider_opened(self, spider) -> None:
        logger.info("spider_opened", spider=spider.name)

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
