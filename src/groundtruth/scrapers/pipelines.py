"""Scrapy item pipelines for raw listing persistence."""

import json
from datetime import UTC, datetime
from typing import Any

from itemadapter import ItemAdapter
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm.attributes import flag_modified

from groundtruth.database.repositories import ScrapeRunRepository
from groundtruth.database.session import get_session_factory
from groundtruth.logging import get_logger
from groundtruth.schemas.pipeline import RawListingSchema
from groundtruth.scrapers.hashing import content_hash
from groundtruth.services.pipeline import PipelineService

logger = get_logger(__name__)

_SCRAPY_STATS_KEYS = (
    "downloader/request_count",
    "downloader/response_count",
    "downloader/response_status_count/200",
    "downloader/response_status_count/403",
    "downloader/response_status_count/429",
    "downloader/response_status_count/500",
    "retry/count",
    "retry/max_reached",
    "item_scraped_count",
    "item_dropped_count",
    "finish_reason",
    "elapsed_time_seconds",
)


class ContentHashPipeline:
    """Compute content hash for change detection."""

    def process_item(self, item, spider):
        adapter = ItemAdapter(item)
        payload = adapter.get("raw_payload") or {}
        html = adapter.get("raw_html") or ""
        adapter["content_hash"] = content_hash(raw_payload=payload, raw_html=html)
        adapter["scraped_at"] = datetime.now(UTC).isoformat()
        return item


class RawListingPipeline:
    """Persist raw listings to PostgreSQL without modification."""

    def open_spider(self, spider) -> None:
        self._session_factory = get_session_factory()
        self._session = self._session_factory()
        self._scrape_run_repo = ScrapeRunRepository(self._session)
        self._pipeline_service = PipelineService(self._session)
        self._crawler = getattr(spider, "crawler", None)

        self._scrape_run = self._scrape_run_repo.create_run(
            spider_name=spider.name,
            spider_version=getattr(spider, "spider_version", "1.0.0"),
            metadata=self._spider_metadata(spider),
        )
        spider.scrape_run_id = self._scrape_run.id
        self._items_stored = 0
        self._items_skipped = 0
        self._session.commit()
        logger.debug("raw_pipeline_opened", spider=spider.name, scrape_run_id=self._scrape_run.id)

    @staticmethod
    def _spider_metadata(spider) -> dict:
        metadata: dict = {"source": getattr(spider, "source_website", spider.name)}
        raw_window = getattr(spider, "crawl_window", None)
        if raw_window:
            if isinstance(raw_window, str):
                try:
                    metadata.update(json.loads(raw_window))
                except json.JSONDecodeError:
                    metadata["crawl_window_raw"] = raw_window
            elif isinstance(raw_window, dict):
                metadata.update(raw_window)
        return metadata

    @staticmethod
    def _scrapy_stats_snapshot(spider) -> dict[str, Any]:
        snapshot: dict[str, Any] = {}
        crawler = getattr(spider, "crawler", None)
        stats_collector = getattr(crawler, "stats", None) if crawler is not None else None
        if stats_collector is not None:
            get_value = getattr(stats_collector, "get_value", None)
            if callable(get_value):
                for key in _SCRAPY_STATS_KEYS:
                    value = get_value(key)
                    if value is not None:
                        snapshot[key] = value
            get_stats = getattr(stats_collector, "get_stats", None)
            if callable(get_stats):
                status_counts = {
                    k.removeprefix("downloader/response_status_count/"): v
                    for k, v in get_stats().items()
                    if isinstance(k, str) and k.startswith("downloader/response_status_count/")
                }
                if status_counts:
                    snapshot["response_status_counts"] = status_counts

        spider_extras = {
            "detail_skipped_existing": getattr(spider, "_detail_skipped_existing", None),
            "detail_skipped_too_old": getattr(spider, "_detail_skipped_too_old", None),
            "detail_requests_sent": getattr(spider, "_detail_requests_sent", None),
            "index_empty_pages": getattr(spider, "_index_empty_pages", None),
            "soft_block_hits": getattr(spider, "_soft_block_hits", None),
            "error_codes": getattr(spider, "error_code_counts", None) or None,
        }
        extras = {k: v for k, v in spider_extras.items() if v is not None}
        if extras:
            snapshot["spider"] = extras
            if extras.get("error_codes"):
                snapshot["error_codes"] = extras["error_codes"]
        return snapshot

    def close_spider(self, spider) -> None:
        stats = self._scrapy_stats_snapshot(spider)
        if stats:
            metadata = dict(self._scrape_run.metadata_ or {})
            metadata["scrapy_stats"] = stats
            self._scrape_run.metadata_ = metadata
            flag_modified(self._scrape_run, "metadata_")
        self._scrape_run_repo.complete_run(
            self._scrape_run,
            listings_found=getattr(spider, "listings_found", self._items_stored),
            listings_stored=self._items_stored,
            errors_count=getattr(spider, "errors_count", 0),
        )
        self._session.commit()
        self._session.close()
        logger.warning(
            "raw_pipeline_closed",
            spider=spider.name,
            stored=self._items_stored,
            skipped=self._items_skipped,
            scrapy_stats_keys=list(stats.keys()) if stats else [],
        )

    def process_item(self, item, spider):
        adapter = ItemAdapter(item)
        if not adapter.get("raw_html"):
            logger.warning(
                "raw_html_missing",
                spider=spider.name,
                listing_id=adapter.get("source_listing_id"),
            )
        schema = RawListingSchema(
            source_website=adapter["source_website"],
            source_listing_id=adapter["source_listing_id"],
            original_url=adapter["original_url"],
            content_hash=adapter["content_hash"],
            spider_version=adapter.get("spider_version")
            or getattr(spider, "spider_version", "1.0.0"),
            raw_payload=adapter.get("raw_payload") or {},
            raw_html=adapter.get("raw_html"),
        )
        try:
            self._pipeline_service.store_raw(schema, spider.scrape_run_id)
        except IntegrityError:
            self._session.rollback()
            self._items_skipped += 1
            logger.debug(
                "raw_listing_duplicate_skipped",
                spider=spider.name,
                listing_id=schema.source_listing_id,
            )
            return item

        self._items_stored += 1
        if self._items_stored % 100 == 0:
            self._session.commit()
            logger.warning("crawl_progress", spider=spider.name, stored=self._items_stored)
        return item
