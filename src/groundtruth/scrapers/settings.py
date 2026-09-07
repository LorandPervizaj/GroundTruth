"""Scrapy project settings."""

from groundtruth.config import get_settings
from groundtruth.scrapers.anti_detect import http11_handlers
from groundtruth.scrapers.profiles import spider_settings

_settings = get_settings()
_html = spider_settings("html")

BOT_NAME = "groundtruth"
SPIDER_MODULES = ["groundtruth.scrapers.spiders"]
NEWSPIDER_MODULE = "groundtruth.scrapers.spiders"

ROBOTSTXT_OBEY = True
CONCURRENT_REQUESTS = _html["CONCURRENT_REQUESTS"]
DOWNLOAD_DELAY = _html["DOWNLOAD_DELAY"]
RANDOMIZE_DOWNLOAD_DELAY = _html["RANDOMIZE_DOWNLOAD_DELAY"]
AUTOTHROTTLE_ENABLED = _html["AUTOTHROTTLE_ENABLED"]
AUTOTHROTTLE_START_DELAY = _html.get("AUTOTHROTTLE_START_DELAY", _settings.scrapy_download_delay)
AUTOTHROTTLE_MAX_DELAY = _html.get("AUTOTHROTTLE_MAX_DELAY", 10.0)
AUTOTHROTTLE_TARGET_CONCURRENCY = _html.get("AUTOTHROTTLE_TARGET_CONCURRENCY", 2.0)

RETRY_ENABLED = True
RETRY_TIMES = 4
RETRY_HTTP_CODES = [403, 408, 429, 500, 502, 503, 504]

DEFAULT_REQUEST_HEADERS = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "sq,en;q=0.9",
}

DOWNLOADER_MIDDLEWARES = {
    "groundtruth.scrapers.middlewares.BrowserFingerprintMiddleware": 350,
    "groundtruth.scrapers.middlewares.RefererMiddleware": 375,
    "groundtruth.scrapers.middlewares.AdaptiveRetryMiddleware": 550,
    "groundtruth.scrapers.middlewares.UserAgentRotationMiddleware": 400,
    "groundtruth.scrapers.middlewares.StructlogMiddleware": 543,
}

ITEM_PIPELINES = {
    "groundtruth.scrapers.pipelines.ContentHashPipeline": 100,
    "groundtruth.scrapers.pipelines.RawListingPipeline": 300,
}

# HTTP/1.1 by default — Playwright only on agency spiders that opt into browser profile.
DOWNLOAD_HANDLERS = http11_handlers()

TWISTED_REACTOR = "twisted.internet.asyncioreactor.AsyncioSelectorReactor"
REACTOR_THREADPOOL_MAXSIZE = 32
DNSCACHE_ENABLED = True
COMPRESSION_ENABLED = True

LOG_LEVEL = _settings.log_level
