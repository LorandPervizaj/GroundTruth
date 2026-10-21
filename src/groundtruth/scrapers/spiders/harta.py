"""Conservative public HTML Harta adapter. Live verification is blocked; see Gate 3."""

from __future__ import annotations

import json
from contextlib import suppress
from datetime import UTC, datetime, timedelta
from email.utils import parsedate_to_datetime
from pathlib import Path
from time import monotonic
from urllib.parse import urlsplit

import scrapy
from scrapy.downloadermiddlewares.retry import get_retry_request
from scrapy.exceptions import CloseSpider, IgnoreRequest
from twisted.internet.defer import Deferred

from groundtruth.scrapers.harta_contract import (
    DEFAULT_MAX_LISTINGS,
    DEFAULT_MAX_REQUESTS,
    DEFAULT_MAX_SECONDS,
    DEFAULT_RECHECK_DAYS,
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

FINGERPRINT_VERSION = 2


def load_harta_state(session):
    """Two bounded queries, latest row per UUID; no per-listing round trips."""
    from sqlalchemy import func, select

    from groundtruth.models.pipeline import RawListing
    from groundtruth.models.scrape_run import ScrapeRun

    ranks = (
        select(
            RawListing.id,
            func.row_number()
            .over(
                partition_by=RawListing.source_listing_id,
                order_by=(RawListing.scraped_at.desc(), RawListing.id.desc()),
            )
            .label("rank"),
        )
        .where(RawListing.source_website == "harta")
        .subquery()
    )
    rows = session.execute(
        select(
            RawListing.source_listing_id,
            RawListing.scraped_at,
            RawListing.content_hash,
        )
        .join(ranks, ranks.c.id == RawListing.id)
        .where(ranks.c.rank == 1)
        .order_by(RawListing.scraped_at.desc())
        .limit(10000)
    )
    known, hashes = {}, {}
    for key, at, digest in rows:
        known[key] = (None, at)
        hashes[key] = digest
    runs = session.scalars(
        select(ScrapeRun.metadata_)
        .where(ScrapeRun.spider_name == "harta")
        .order_by(ScrapeRun.started_at.desc())
        .limit(100)
    )
    for metadata in runs:
        for key, check in (metadata or {}).get("harta_detail_checks", {}).items():
            if (
                key not in hashes
                or check.get("detail_content_hash") != hashes[key]
                or check.get("fingerprint_version") != FINGERPRINT_VERSION
            ):
                continue
            try:
                at = datetime.fromisoformat(check["checked_at"])
                at = at.replace(tzinfo=UTC) if at.tzinfo is None else at.astimezone(UTC)
                previous = known[key][1]
                previous = previous.replace(tzinfo=UTC) if previous.tzinfo is None else previous
                if at <= datetime.now(UTC) and (known[key][0] is None or at > previous):
                    known[key] = (check["summary_fingerprint"], max(previous, at))
            except (KeyError, ValueError, TypeError):
                continue  # Bad or legacy checkpoint forces a safe detail fetch.
    return known


class HartaRawListingPipeline(RawListingPipeline):
    """Reuse normal persistence; record bounded successful checks on the same run."""

    def process_item(self, item, spider):
        from sqlalchemy import select
        from sqlalchemy.exc import IntegrityError

        from groundtruth.models.pipeline import RawListing
        from groundtruth.schemas.pipeline import RawListingSchema

        schema = RawListingSchema(
            source_website=item["source_website"],
            source_listing_id=item["source_listing_id"],
            original_url=item["original_url"],
            content_hash=item["content_hash"],
            raw_payload=item["raw_payload"],
            spider_version=spider.spider_version,
        )
        # Existing PipelineService/repository, with a savepoint containing any
        # duplicate failure. Avoid the base pipeline's every-100-item commit,
        # which would separate raw content from its checkpoint transaction.
        try:
            with self._session.begin_nested():
                self._pipeline_service.store_raw(schema, spider.scrape_run_id)
            self._items_stored += 1
        except IntegrityError:
            stored = self._session.scalar(
                select(RawListing.id).where(
                    RawListing.source_website == "harta",
                    RawListing.source_listing_id == item["source_listing_id"],
                    RawListing.content_hash == item["content_hash"],
                )
            )
            if stored is None:
                spider.metrics["persistence_failures"] += 1
                raise RuntimeError("Harta raw persistence failed; checkpoint refused") from None
            self._items_skipped += 1
        key = item["source_listing_id"]
        check = spider._detail_checks.get(key)
        if check:
            metadata = dict(self._scrape_run.metadata_ or {})
            checks = dict(metadata.get("harta_detail_checks") or {})
            checks[key] = {
                **check,
                "detail_content_hash": item["content_hash"],
                "fingerprint_version": FINGERPRINT_VERSION,
            }
            metadata["harta_detail_checks"] = checks
            self._scrape_run.metadata_ = metadata
        # Raw version and its checkpoint are committed together after EACH item,
        # including an unchanged detail. A crash before close cannot lose progress.
        self._session.commit()
        return item

    def close_spider(self, spider):
        metadata = dict(self._scrape_run.metadata_ or {})
        metadata["harta_metrics"] = spider.metrics
        metadata["harta_discovery_complete"] = False
        metadata["harta_status"] = spider.run_status()
        metadata["harta_seen_ids"] = sorted(spider._seen)
        metadata["harta_unavailable_observations"] = spider._unavailable
        self._scrape_run.metadata_ = metadata
        self._scrape_run_repo.complete_run(
            self._scrape_run,
            listings_found=spider.listings_found,
            listings_stored=self._items_stored,
            errors_count=spider.errors_count,
        )
        if spider.run_status() != "complete":
            self._scrape_run_repo.fail_run(self._scrape_run, "Harta: " + spider.run_status())
        self._session.commit()
        self._session.close()


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
        if (
            spider._blocked
            or spider.metrics["requests"] >= spider.max_requests
            or monotonic() - spider._started_clock >= spider.max_seconds
        ):
            spider._stop_reason = "budget_exhausted" if not spider._blocked else "blocked_access"
            spider.crawler.engine.close_spider(spider, "harta_budget_or_access_stop")
            raise IgnoreRequest("Harta request budget/access stop")
        spider.metrics["requests"] += 1
        kind = "requests_detail" if path.path.startswith("/property/") else "requests_discovery"
        spider.metrics[kind] += 1
        spider.metrics["requests_retry"] += int(request.meta.get("retry_times", 0) > 0)

    def process_response(self, request, response, spider):
        spider.metrics["response_bytes"] += len(response.body)
        spider.metrics["responses"] += 1
        bucket = (
            f"responses_{response.status}"
            if response.status in {304, 403, 404, 429}
            else (
                "responses_2xx"
                if 200 <= response.status < 300
                else "responses_5xx"
                if response.status >= 500
                else "responses_other"
            )
        )
        spider.metrics[bucket] += 1
        try:
            if response.status in {401, 403}:
                raise HartaContractError("Harta access denied")
            check_access(response.text if hasattr(response, "text") else "")
        except HartaContractError:
            spider._blocked = True
            spider._stop_reason = "blocked_access"
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
                    spider._stop_reason = "retry_after_cooldown"
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
        "CLOSESPIDER_TIMEOUT": DEFAULT_MAX_SECONDS,
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
        max_listings=str(DEFAULT_MAX_LISTINGS),
        max_pages="1",
        max_requests=str(DEFAULT_MAX_REQUESTS),
        max_seconds=str(DEFAULT_MAX_SECONDS),
        recheck_days=str(DEFAULT_RECHECK_DAYS),
        report_path="reports/generated/harta_crawl_report.json",
        known=None,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self.limit = int(max_listings)
        self.max_pages, self.max_requests = int(max_pages), int(max_requests)
        self.max_seconds = int(max_seconds)
        self.recheck_days = int(recheck_days)
        if not (
            1 <= self.limit <= 1000
            and 1 <= self.max_pages <= 100
            and 1 <= self.max_requests <= 2000
            and self.recheck_days >= 1
            and 1 <= self.max_seconds <= 3600
        ):
            raise ValueError("Harta requires positive bounded crawl budgets")
        self.known = known or {}
        self.report_path = Path(report_path)
        self._seen = set()
        self._detail_checks = {}
        self._unavailable = {}
        self._blocked = False
        self._stop_reason = None
        self._started_clock = monotonic()
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
                "requests_detail",
                "requests_discovery",
                "requests_retry",
                "responses_2xx",
                "responses_304",
                "responses_403",
                "responses_404",
                "responses_429",
                "responses_5xx",
                "responses_other",
                "duplicate_ids",
                "persistence_failures",
            ],
            0,
        )

    @classmethod
    def from_crawler(cls, crawler, *args, **kwargs):
        spider = super().from_crawler(crawler, *args, **kwargs)
        crawler.settings.set("CLOSESPIDER_TIMEOUT", spider.max_seconds, priority="spider")
        from groundtruth.database.session import get_session_factory

        with get_session_factory()() as session:
            spider.known = load_harta_state(session)
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
            self._stop_reason = "source_schema_change"
            self.metrics["parse_failures"] += 1
            raise CloseSpider("harta_discovery_contract_error") from None
        if not props:
            # The observed category page is inconsistent with the map inventory.
            self._stop_reason = "empty_scope_unverified"
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
                self.metrics["duplicate_ids"] += 1
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
                    "status",
                    "address",
                    "neighborhood",
                    "latitude",
                    "longitude",
                    "living_area",
                    "surface_area",
                    "price_total",
                    "price_unit",
                    "created_at",
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
                self._stop_reason = "record_budget_reached"
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
            self._unavailable[response.meta["source_id"]] = {
                "http_status": response.status,
                "observed_at": datetime.now(UTC).isoformat(),
            }
            return
        try:
            prop = property_from_html(response.text)
            if listing_id(prop) != response.meta["source_id"] or not in_scope(prop):
                raise HartaContractError("Harta identity/scope changed")
            payload = {
                "property": minimized_property(prop),
            }
        except (HartaContractError, ValueError, TypeError):
            self.metrics["parse_failures"] += 1
            self._stop_reason = "detail_parse_failure"
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
                    "status": self.run_status(),
                    "run_id": self.scrape_run_id,
                    "scope": {
                        "municipality": "Prishtina",
                        "property_types": ["apartment", "studio"],
                        "transactions": ["sale", "monthly_rent"],
                    },
                    "parser_version": PARSER_VERSION,
                    "scoring_policy_version": "1.1.0",
                    "duration_seconds": round(monotonic() - self._started_clock, 3),
                    "discovery_pages": self._pages,
                    "discovery_complete": False,
                    "trusted_total": None,
                    "detail_fetch_avoidance_rate": self.metrics["unchanged"] / len(self._seen)
                    if self._seen
                    else None,
                    "retry_overhead": self.metrics["requests_retry"] / self.metrics["requests"]
                    if self.metrics["requests"]
                    else None,
                    "usable_valid_records": None,
                    "quarantined_records": None,
                    "requests_per_usable_listing": None,
                    "bytes_per_usable_listing": None,
                    "etl_status": "not_run_by_spider; join existing ETL metrics by run_id",
                    "coverage": "bounded public category page; pagination unverified",
                    "live_pilot_verified": False,
                },
                indent=2,
            ),
            encoding="utf-8",
        )

    def run_status(self):
        if self._stop_reason:
            return self._stop_reason
        if self.metrics["persistence_failures"]:
            return "failed_persistence"
        if self.metrics["parse_failures"]:
            return "source_schema_change"
        if self.metrics["request_failures"]:
            return "network_errors_observed"
        return "partial_discovery"  # No complete discovery contract verified yet.
