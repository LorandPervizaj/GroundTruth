"""Scrapy project settings."""

from groundtruth.config import get_settings

_settings = get_settings()

BOT_NAME = "groundtruth"
SPIDER_MODULES = ["groundtruth.scrapers.spiders"]
NEWSPIDER_MODULE = "groundtruth.scrapers.spiders"

ROBOTSTXT_OBEY = True
CONCURRENT_REQUESTS = _settings.scrapy_concurrent_requests
DOWNLOAD_DELAY = _settings.scrapy_download_delay
RANDOMIZE_DOWNLOAD_DELAY = True
AUTOTHROTTLE_ENABLED = True
AUTOTHROTTLE_START_DELAY = _settings.scrapy_download_delay
AUTOTHROTTLE_MAX_DELAY = 10.0
AUTOTHROTTLE_TARGET_CONCURRENCY = 2.0

RETRY_ENABLED = True
RETRY_TIMES = 3
RETRY_HTTP_CODES = [500, 502, 503, 504, 408, 429]

DEFAULT_REQUEST_HEADERS = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "sq,en;q=0.9",
}

DOWNLOADER_MIDDLEWARES = {
    "groundtruth.scrapers.middlewares.UserAgentRotationMiddleware": 400,
    "groundtruth.scrapers.middlewares.StructlogMiddleware": 543,
}

ITEM_PIPELINES = {
    "groundtruth.scrapers.pipelines.ContentHashPipeline": 100,
    "groundtruth.scrapers.pipelines.RawListingPipeline": 300,
}

TWISTED_REACTOR = "twisted.internet.asyncioreactor.AsyncioSelectorReactor"
DOWNLOAD_HANDLERS = {
    "http": "scrapy_playwright.handler.ScrapyPlaywrightDownloadHandler",
    "https": "scrapy_playwright.handler.ScrapyPlaywrightDownloadHandler",
}
PLAYWRIGHT_BROWSER_TYPE = "chromium"
PLAYWRIGHT_LAUNCH_OPTIONS = {"headless": True}

LOG_LEVEL = _settings.log_level
