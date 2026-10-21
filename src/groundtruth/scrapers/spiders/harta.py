"""Conservative public HTML Harta adapter. Live verification is blocked; see Gate 3."""

from __future__ import annotations

import json
from contextlib import suppress
from datetime import UTC, datetime, timedelta
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.parse import urlsplit

import scrapy
from scrapy.downloadermiddlewares.retry import get_retry_request
from scrapy.exceptions import CloseSpider, IgnoreRequest
from twisted.internet.defer import Deferred

from groundtruth.scrapers.harta_contract import (
    INDEX_URL,
    PARSER_VERSION,
    HartaContractError,
    check_access,
    hydration_field,
    in_scope,
    listing_id,
    minimized_property,
    property_from_html,
)
from groundtruth.scrapers.hashing import content_hash
from groundtruth.scrapers.pipelines import RawListingPipeline
from groundtruth.scrapers.spiders.base import BaseRealEstateSpider


class HartaRawListingPipeline(RawListingPipeline):
    """Reuse normal persistence; record bounded successful checks on the same run."""

    def process_item(self, item, spider):
        result = super().process_item(item, spider)
        # This bounded source commits each item, so a later duplicate rollback
        # cannot discard earlier new versions in the inherited pipeline's batch.
        self._session.commit()
        return result

    def close_spider(self, spider):
        # Super commits raw inserts and this metadata together. On rollback/crash
        # neither becomes a false durable checkpoint. No second listing store.
        metadata = dict(self._scrape_run.metadata_ or {})
        metadata["harta_detail_checks"] = spider._detail_checks
        metadata["harta_metrics"] = spider.metrics
        self._scrape_run.metadata_ = metadata
        super().close_spider(spider)


class HartaAccessMiddleware:
    """Fixed identity, hard budget, bounded backoff; challenges never retried."""

    def process_request(self, request, spider):
        path = urlsplit(request.url)
        if (
            path.scheme != "https"
            or path.netloc != "harta.info"
            or not (
                path.path == "/robots.txt"
                or path.path == "/prona/banesa/prishtine"
                or path.path.startswith("/property/")
            )
        ):
            raise IgnoreRequest("Harta URL outside public property contract")
        if spider._blocked or spider.metrics["requests"] >= spider.max_requests:
            spider.crawler.engine.close_spider(spider, "harta_budget_or_access_stop")
            raise IgnoreRequest("Harta request budget/access stop")
        spider.metrics["requests"] += 1

    def process_response(self, request, response, spider):
        spider.metrics["response_bytes"] += len(response.body)
        spider.metrics["responses"] += 1
        try:
            if response.status in {401, 403}:
                raise HartaContractError("Harta access denied")
            check_access(response.text if hasattr(response, "text") else "")
        except HartaContractError:
            spider._blocked = True
            spider.metrics["access_blocks"] += 1
            spider.crawler.engine.close_spider(spider, "harta_access_verification_required")
            raise IgnoreRequest("Harta access verification required") from None
        if response.status == 429:
            spider.metrics["http_429"] += 1
        if response.status in {408, 429, 500, 502, 503, 504}:
            retry = get_retry_request(
                request, spider=spider, reason=str(response.status), max_retry_times=2
            )
            if retry is not None:
                delay = 2 ** retry.meta["retry_times"]
                header = response.headers.get("Retry-After", b"0").decode()
                try:
                    delay = max(delay, float(header))
                except ValueError:
                    with suppress(ValueError, TypeError, OverflowError):
                        delay = max(
                            delay,
                            (parsedate_to_datetime(header) - datetime.now(UTC)).total_seconds(),
                        )
                if delay > 60:
                    # Stop instead of violating a long source cooldown.
                    spider._blocked = True
                    spider.crawler.engine.close_spider(spider, "harta_retry_after_cooldown")
                    raise IgnoreRequest("Harta Retry-After requires later operator retry")
                deferred = Deferred()
                from twisted.internet import reactor

                reactor.callLater(max(0, delay), deferred.callback, retry)
                return deferred
        return response

    def process_exception(self, request, exception, spider):
        spider.metrics["request_failures"] += 1
        # Connection errors use Scrapy's bounded retry middleware.
        return None


class HartaSpider(BaseRealEstateSpider):
    name = source_website = "harta"
    spider_version = PARSER_VERSION
    allowed_domains = ["harta.info"]
    custom_settings = {
        "ROBOTSTXT_OBEY": True,
        "CONCURRENT_REQUESTS": 2,
        "CONCURRENT_REQUESTS_PER_DOMAIN": 2,
        "DOWNLOAD_DELAY": 1.0,
        "DOWNLOAD_TIMEOUT": 20,
        "RETRY_TIMES": 2,
        "RETRY_HTTP_CODES": [],
        "AUTOTHROTTLE_ENABLED": True,
        "AUTOTHROTTLE_TARGET_CONCURRENCY": 1.0,
        "COOKIES_ENABLED": False,
        "USER_AGENT": "GroundTruthResearch/0.1 (authorized public property research)",
        "DOWNLOAD_MAXSIZE": 2_000_000,
        "ITEM_PIPELINES": {
            "groundtruth.scrapers.pipelines.ContentHashPipeline": 100,
            "groundtruth.scrapers.spiders.harta.HartaRawListingPipeline": 300,
        },
        "DOWNLOADER_MIDDLEWARES": {
            "groundtruth.scrapers.middlewares.BrowserFingerprintMiddleware": None,
            "groundtruth.scrapers.middlewares.UserAgentRotationMiddleware": None,
            "groundtruth.scrapers.middlewares.AdaptiveRetryMiddleware": None,
            "scrapy.downloadermiddlewares.retry.RetryMiddleware": 550,
            "groundtruth.scrapers.spiders.harta.HartaAccessMiddleware": 600,
        },
    }

    def __init__(
        self,
        max_listings="75",
        max_pages="1",
        max_requests="110",
        recheck_days="7",
        report_path="reports/generated/harta_crawl_report.json",
        known=None,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self.limit = int(max_listings)
        self.max_pages, self.max_requests = int(max_pages), int(max_requests)
        self.recheck_days = int(recheck_days)
        if not (
            1 <= self.limit <= 1000
            and 1 <= self.max_pages <= 100
            and 1 <= self.max_requests <= 2000
            and self.recheck_days >= 1
        ):
            raise ValueError("Harta requires positive bounded crawl budgets")
        self.known = known or {}
        self.report_path = Path(report_path)
        self._seen = set()
        self._detail_checks = {}
        self._blocked = False
        self._scheduled = 0
        self._pages = 0
        self.started_at = datetime.now(UTC)
        self.metrics = dict.fromkeys(
            [
                "requests",
                "responses",
                "response_bytes",
                "request_failures",
                "http_429",
                "discovered",
                "eligible",
                "excluded",
                "new",
                "changed",
                "unchanged",
                "due",
                "detail_requests",
                "detail_success",
                "removed",
                "parse_failures",
                "access_blocks",
            ],
            0,
        )

    @classmethod
    def from_crawler(cls, crawler, *args, **kwargs):
        spider = super().from_crawler(crawler, *args, **kwargs)
        from sqlalchemy import select

        from groundtruth.database.session import get_session_factory
        from groundtruth.models.pipeline import RawListing
        from groundtruth.models.scrape_run import ScrapeRun

        # Existing immutable raw versions are the checkpoint authority: a crashed
        # uncommitted item cannot cause a later run to skip an unstored property.
        with get_session_factory()() as session:
            rows = session.execute(
                select(RawListing.source_listing_id, RawListing.raw_payload, RawListing.scraped_at)
                .where(RawListing.source_website == "harta")
                .order_by(RawListing.scraped_at.desc())
                .limit(10000)
            )
            for key, payload, at in rows:
                spider.known.setdefault(key, (payload.get("summary_fingerprint"), at))
            # Later successful re-verifications may not insert a raw version
            # (same content hash). Read their run metadata without rewriting raw.
            runs = session.scalars(
                select(ScrapeRun)
                .where(ScrapeRun.spider_name == "harta")
                .order_by(ScrapeRun.started_at.desc())
                .limit(100)
            )
            for run in runs:
                for key, check in (run.metadata_ or {}).get("harta_detail_checks", {}).items():
                    if key not in spider.known:
                        continue
                    at = datetime.fromisoformat(check["checked_at"])
                    if at > spider.known[key][1].replace(tzinfo=UTC):
                        spider.known[key] = (check["summary_fingerprint"], at)
        return spider

    async def start(self):
        yield scrapy.Request(INDEX_URL, callback=self.parse_index_page)

    def parse_index_page(self, response):
        self._pages += 1
        try:
            props = hydration_field(response.text, "listings")
            if not isinstance(props, list):
                raise HartaContractError("Harta listings is not an array")
        except (HartaContractError, ValueError):
            self.metrics["parse_failures"] += 1
            raise CloseSpider("harta_discovery_contract_error") from None
        if not props:
            # The observed category page is inconsistent with the map inventory.
            raise CloseSpider("harta_empty_discovery_unverified")
        for p in props:
            self.metrics["discovered"] += 1
            if not isinstance(p, dict) or not in_scope(p):
                self.metrics["excluded"] += 1
                continue
            self.metrics["eligible"] += 1
            try:
                key = listing_id(p)
            except HartaContractError:
                self.metrics["parse_failures"] += 1
                continue
            if key in self._seen:
                continue
            self._seen.add(key)
            summary = {
                k: p.get(k)
                for k in (
                    "id",
                    "title",
                    "city",
                    "property_type",
                    "listing_type",
                    "price",
                    "sqft",
                    "bedrooms",
                    "bathrooms",
                    "updated_at",
                )
            }
            fingerprint = content_hash(raw_payload=summary)
            previous = self.known.get(key)
            if previous is None:
                reason = "new"
            elif previous[0] != fingerprint:
                reason = "changed"
            elif datetime.now(UTC) - previous[1].replace(tzinfo=UTC) >= timedelta(
                days=self.recheck_days
            ):
                reason = "due"
            else:
                self.metrics["unchanged"] += 1
                continue
            if self._scheduled >= self.limit:
                break
            self.metrics[reason] += 1
            self._scheduled += 1
            self.metrics["detail_requests"] += 1
            yield scrapy.Request(
                "https://harta.info/property/" + key,
                callback=self.parse_listing_page,
                meta={
                    "source_id": key,
                    "summary_fingerprint": fingerprint,
                    "handle_httpstatus_list": [404, 410],
                },
            )
        # No source pagination contract was observed. Do not fabricate page URLs
        # or infer removal from absence in this bounded/possibly partial index.

    def parse_listing_page(self, response):
        if response.status in {404, 410}:
            self.metrics["removed"] += 1
            return
        try:
            prop = property_from_html(response.text)
            if listing_id(prop) != response.meta["source_id"] or not in_scope(prop):
                raise HartaContractError("Harta identity/scope changed")
            payload = {
                "property": minimized_property(prop),
                "summary_fingerprint": response.meta["summary_fingerprint"],
            }
        except (HartaContractError, ValueError, TypeError):
            self.metrics["parse_failures"] += 1
            return
        self.metrics["detail_success"] += 1
        self._detail_checks[listing_id(prop)] = {
            "checked_at": datetime.now(UTC).isoformat(),
            "summary_fingerprint": response.meta["summary_fingerprint"],
        }
        yield self.build_listing_item(
            source_listing_id=listing_id(prop), original_url=response.url, raw_payload=payload
        )

    def closed(self, reason):
        self.report_path.parent.mkdir(parents=True, exist_ok=True)
        self.report_path.write_text(
            json.dumps(
                {
                    "source": "harta",
                    "started_at": self.started_at.isoformat(),
                    "ended_at": datetime.now(UTC).isoformat(),
                    "finish_reason": reason,
                    "metrics": self.metrics,
                    "coverage": "bounded public category page; pagination unverified",
                    "live_pilot_verified": False,
                },
                indent=2,
            ),
            encoding="utf-8",
        )
