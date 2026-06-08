"""Scrapy item pipelines for raw listing persistence."""

import hashlib
from datetime import UTC, datetime

from itemadapter import ItemAdapter

from groundtruth.database.repositories import ScrapeRunRepository
from groundtruth.database.session import get_session_factory
from groundtruth.logging import configure_logging, get_logger
from groundtruth.schemas.pipeline import RawListingSchema
from groundtruth.services.pipeline import PipelineService

logger = get_logger(__name__)


class ContentHashPipeline:
    """Compute content hash for change detection."""

    def process_item(self, item, spider):
        adapter = ItemAdapter(item)
        payload = adapter.get("raw_payload") or {}
        html = adapter.get("raw_html") or ""
        content = str(payload) + html
        adapter["content_hash"] = hashlib.sha256(content.encode("utf-8")).hexdigest()
        adapter["scraped_at"] = datetime.now(UTC).isoformat()
        return item


class RawListingPipeline:
    """Persist raw listings to PostgreSQL without modification."""

    def open_spider(self, spider) -> None:
        configure_logging()
        self._session_factory = get_session_factory()
        self._session = self._session_factory()
        self._scrape_run_repo = ScrapeRunRepository(self._session)
        self._pipeline_service = PipelineService(self._session)

        self._scrape_run = self._scrape_run_repo.create_run(
            spider_name=spider.name,
            spider_version=getattr(spider, "spider_version", "1.0.0"),
            metadata={"source": getattr(spider, "source_website", spider.name)},
        )
        spider.scrape_run_id = self._scrape_run.id
        self._items_stored = 0
        logger.info("raw_pipeline_opened", spider=spider.name, scrape_run_id=self._scrape_run.id)

    def close_spider(self, spider) -> None:
        self._scrape_run_repo.complete_run(
            self._scrape_run,
            listings_found=getattr(spider, "listings_found", self._items_stored),
            listings_stored=self._items_stored,
            errors_count=getattr(spider, "errors_count", 0),
        )
        self._session.commit()
        self._session.close()
        logger.info("raw_pipeline_closed", spider=spider.name, stored=self._items_stored)

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
            spider_version=adapter.get("spider_version") or getattr(spider, "spider_version", "1.0.0"),
            raw_payload=adapter.get("raw_payload") or {},
            raw_html=adapter.get("raw_html"),
        )
        self._pipeline_service.store_raw(schema, spider.scrape_run_id)
        self._items_stored += 1
        return item
