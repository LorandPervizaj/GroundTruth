"""MerrJep spider — phased: discovery → archive → parser → ETL."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import scrapy
from dateutil.relativedelta import relativedelta
from scrapy.http import Response

from groundtruth.config import PROJECT_ROOT, get_settings
from groundtruth.processing.parsers.merrjep import parse_listing_html
from groundtruth.scrapers.items import ListingItem
from groundtruth.scrapers.merrjep_archive import (
    archive_detail_page,
    build_archive_report,
    write_archive_report,
)
from groundtruth.scrapers.merrjep_discovery import (
    DEFAULT_INDEX_KEY,
    DEFAULT_INDEX_PAGES_TARGET,
    DEFAULT_LISTING_URLS_TARGET,
    DEFAULT_MAX_DUPLICATE_RATE_PCT,
    DEFAULT_START_URLS,
    build_discovery_stats,
    build_page_url,
    category_base_url,
    extract_listing_urls,
    extract_max_page_number,
    listing_id_from_url,
    register_listing_urls,
    resolve_start_urls,
    write_discovery_report,
)
from groundtruth.scrapers.merrjep_resume import load_skip_listing_ids
from groundtruth.scrapers.profiles import spider_settings
from groundtruth.scrapers.spiders.base import BaseRealEstateSpider


class MerrJepSpider(BaseRealEstateSpider):
    """Spider for merrjep.com real estate listings."""

    name = "merrjep"
    source_website = "merrjep"
    spider_version = "0.2.2"
    allowed_domains = ["merrjep.com", "www.merrjep.com"]

    start_urls = list(DEFAULT_START_URLS)

    custom_settings = {
        **spider_settings("html"),
        "ROBOTSTXT_OBEY": True,
    }

    def __init__(
        self,
        max_pages: str = "50",
        max_listings: str = "0",
        discovery_only: str = "true",
        archive_only: str = "false",
        index_pages_target: str = str(DEFAULT_INDEX_PAGES_TARGET),
        listing_urls_target: str = str(DEFAULT_LISTING_URLS_TARGET),
        max_duplicate_rate_pct: str = str(DEFAULT_MAX_DUPLICATE_RATE_PCT),
        index: str = DEFAULT_INDEX_KEY,
        start_page: str = "1",
        skip_existing: str = "true",
        skip_existing_days: str = "0",
        max_age_days: str = "0",
        max_age_months: str = "12",
        min_published_year: str = "0",
        stale_streak_limit: str = "50",
        *args,
        **kwargs,
    ) -> None:
        super().__init__(*args, **kwargs)
        self._index_key = index
        self.start_urls = resolve_start_urls(index)
        self._start_page = max(1, int(start_page))
        self._skip_existing = skip_existing.lower() in ("1", "true", "yes")
        self._skip_existing_days = max(0, int(skip_existing_days))
        self._existing_ids: set[str] = set()
        self._detail_skipped_existing = 0
        self._max_pages = int(max_pages)
        self._max_listings = int(max_listings)
        self._archive_only = archive_only.lower() in ("1", "true", "yes")
        self._discovery_only = (
            discovery_only.lower() in ("1", "true", "yes") and not self._archive_only
        )
        self._index_pages_target = int(index_pages_target)
        self._listing_urls_target = int(listing_urls_target)
        self._max_duplicate_rate_pct = float(max_duplicate_rate_pct)

        self._seen_ids: set[str] = set()
        self._id_to_url: dict[str, str] = {}
        self._category_counts: dict[str, int] = {}
        self._page_yields: list[tuple[int, int]] = []
        self._page_id_samples: list[tuple[int, list[str]]] = []
        self._all_urls: list[str] = []
        self._duplicate_hits = 0
        self._index_pages_crawled = 0
        self._last_page_number = 0
        self._max_page_link_seen: int | None = None
        self._detail_requests_sent = 0
        self._detail_ids_requested: set[str] = set()
        self._category_bases: dict[str, str] = {}
        self._archive_records: list = []
        self._archive_dir: Path | None = None
        self._max_age_days = int(max_age_days)
        self._max_age_months = int(max_age_months)
        self._min_published_year = int(min_published_year)
        self._stale_streak_limit = int(stale_streak_limit)
        self._cutoff_date: date | None = None
        if self._max_age_days > 0:
            self._cutoff_date = datetime.now(UTC).date() - timedelta(days=self._max_age_days - 1)
        elif self._max_age_months > 0:
            self._cutoff_date = datetime.now(UTC).date() - relativedelta(
                months=self._max_age_months
            )
        elif self._min_published_year > 0:
            self._cutoff_date = date(self._min_published_year, 1, 1)
        self._stop_index = False
        self._stale_streak = 0
        self._detail_skipped_too_old = 0

    @classmethod
    def from_crawler(cls, crawler, *args, **kwargs):
        spider = super().from_crawler(crawler, *args, **kwargs)
        if spider._discovery_only or spider._archive_only:
            crawler.settings.set("ITEM_PIPELINES", {}, priority="spider")
        if spider._archive_only:
            settings = get_settings()
            base = Path(settings.reports_generated_dir)
            if not base.is_absolute():
                base = PROJECT_ROOT / base
            stamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
            spider._archive_dir = base / f"merrjep_archive_{stamp}"
        elif spider._skip_existing and not spider._discovery_only:
            spider._existing_ids = load_skip_listing_ids(
                source_website=spider.source_website,
                within_days=spider._skip_existing_days,
            )
            spider.logger.warning(
                "skip_existing enabled — %d ids to skip (within_days=%d)",
                len(spider._existing_ids),
                spider._skip_existing_days,
            )
        return spider

    def _at_listing_limit(self) -> bool:
        return self._max_listings > 0 and self._detail_requests_sent >= self._max_listings

    async def start(self):
        """Begin at ``start_page`` when resuming a long index crawl (Scrapy 2.13+)."""
        for url in self.start_urls:
            category_url = category_base_url(url)
            page = self._start_page
            request_url = build_page_url(category_url, page) if page > 1 else url
            if page > 1:
                self.logger.warning(
                    "crawl_resume start_page=%d url=%s",
                    page,
                    request_url,
                )
            yield scrapy.Request(
                request_url,
                callback=self.parse,
                meta={"page": page, "category_url": category_url},
                dont_filter=True,
            )

    def _is_detail_page(self, response: Response) -> bool:
        if response.meta.get("page_type") == "detail":
            return True
        return listing_id_from_url(response.url) is not None and "/shpallja/" in response.url

    def parse_index_page(self, response: Response) -> Iterable:
        if self._archive_only and self._at_listing_limit():
            return
        if self._stop_index:
            page_num = response.meta.get("page", 1)
            self.logger.warning(
                "index_skip page=%d reason=stale_published_dates cutoff=%s",
                page_num,
                self._cutoff_date,
            )
            return

        category_url = response.meta.get("category_url") or category_base_url(response.url)
        self._category_bases[category_url] = category_url

        page_num = response.meta.get("page", 1)
        self._last_page_number = page_num
        self._index_pages_crawled += 1

        page_max = extract_max_page_number(response.text)
        if page_max is not None:
            self._max_page_link_seen = max(self._max_page_link_seen or 0, page_max)

        listing_urls = extract_listing_urls(response.text, response.url)
        self._all_urls.extend(listing_urls)
        new_on_page, self._duplicate_hits, new_ids = register_listing_urls(
            listing_urls,
            seen_ids=self._seen_ids,
            duplicate_hits=self._duplicate_hits,
            id_to_url=self._id_to_url,
            category_counts=self._category_counts,
        )
        self._page_yields.append((page_num, new_on_page))
        self._page_id_samples.append((page_num, new_ids))

        self.logger.info(
            "index_page page=%d listings_on_page=%d new_on_page=%d unique_total=%d url=%s",
            page_num,
            len(listing_urls),
            new_on_page,
            len(self._seen_ids),
            response.url,
        )

        if self._discovery_only:
            yield from self._follow_index_pages(response, category_url, page_num)
            return

        for url in sorted(listing_urls):
            if self._at_listing_limit():
                break
            listing_id = listing_id_from_url(url)
            if not listing_id or listing_id in self._detail_ids_requested:
                continue
            if self._skip_existing and listing_id in self._existing_ids:
                self._detail_skipped_existing += 1
                continue
            self._detail_ids_requested.add(listing_id)
            self._detail_requests_sent += 1
            yield self.request_detail(response, url)

        if not self._at_listing_limit():
            yield from self._follow_index_pages(response, category_url, page_num)

    def _follow_index_pages(
        self, response: Response, category_url: str, current_page: int
    ) -> Iterable:
        if self._max_pages > 0 and current_page >= self._max_pages:
            return
        if self._archive_only and self._at_listing_limit():
            return
        listing_urls = extract_listing_urls(response.text, response.url)
        if not listing_urls:
            self.logger.info(
                "index_stop reason=empty_page page=%d url=%s",
                current_page,
                response.url,
            )
            return
        next_page = current_page + 1
        next_url = build_page_url(category_url, next_page)
        yield response.follow(
            next_url,
            callback=self.parse,
            meta={"page": next_page, "category_url": category_url},
            dont_filter=True,
        )

    def parse_listing_page(self, response: Response) -> Iterable[ListingItem]:
        if self._archive_only and self._archive_dir is not None:
            listing_id = listing_id_from_url(response.url)
            if not listing_id:
                self.logger.warning("archive_skip_no_id url=%s", response.url)
                return
            record = archive_detail_page(
                listing_id=listing_id,
                url=response.url,
                html=response.text,
                output_dir=self._archive_dir,
            )
            self._archive_records.append(record)
            if len(self._archive_records) % 25 == 0:
                self.logger.info("archive_progress count=%d", len(self._archive_records))
            return

        listing_id = listing_id_from_url(response.url)
        if not listing_id:
            self.logger.warning("detail_skip_no_id url=%s", response.url)
            return

        payload = parse_listing_html(response.text, response.url)
        if self._cutoff_date is not None:
            published_iso = payload.get("published_date")
            if published_iso:
                try:
                    published = date.fromisoformat(str(published_iso))
                except ValueError:
                    published = None
                if published is not None and published < self._cutoff_date:
                    self._detail_skipped_too_old += 1
                    self._stale_streak += 1
                    if self._stale_streak >= self._stale_streak_limit:
                        self._stop_index = True
                        self.logger.warning(
                            "index_stop reason=stale_published_dates streak=%d cutoff=%s",
                            self._stale_streak,
                            self._cutoff_date,
                        )
                    return
                if published is not None:
                    self._stale_streak = 0

        yield self.build_listing_item(
            source_listing_id=str(payload.get("source_listing_id") or listing_id),
            original_url=response.url,
            raw_payload=payload,
            raw_html=response.text,
        )
        if self.listings_found % 100 == 0:
            self.logger.warning(
                "crawl_progress listings=%d requests=%d",
                self.listings_found,
                self._detail_requests_sent,
            )

    def closed(self, reason: str) -> None:
        settings = get_settings()
        out_dir = Path(settings.reports_generated_dir)
        if not out_dir.is_absolute():
            out_dir = PROJECT_ROOT / out_dir

        if self._archive_only and self._archive_dir is not None:
            report = build_archive_report(self._archive_records, archive_dir=self._archive_dir)
            report_path = write_archive_report(report, self._archive_dir)
            status = "PASSED" if report.passed else "FAILED"
            self.logger.warning(
                "archive_complete status=%s pages=%d dir=%s report=%s",
                status,
                report.pages_archived,
                self._archive_dir,
                report_path,
            )
            for key, pct in report.completeness_pct.items():
                self.logger.warning("archive_completeness %s=%.1f%%", key, pct)
            for note in report.notes:
                self.logger.warning("archive_note %s", note)
            return

        if not self._discovery_only:
            self.logger.warning(
                "detail_crawl_complete listings=%d skipped_existing=%d skipped_too_old=%d "
                "cutoff=%s stopped_index=%s errors=%d reason=%s",
                self.listings_found,
                self._detail_skipped_existing,
                self._detail_skipped_too_old,
                self._cutoff_date,
                self._stop_index,
                self.errors_count,
                reason,
            )
            return

        stats = build_discovery_stats(
            start_urls=list(self.start_urls),
            index_pages_crawled=self._index_pages_crawled,
            seen_ids=self._seen_ids,
            duplicate_hits=self._duplicate_hits,
            urls_seen=len(self._all_urls),
            last_page_number=self._last_page_number,
            max_page_link_seen=self._max_page_link_seen,
            index_pages_target=self._index_pages_target,
            listing_urls_target=self._listing_urls_target,
            max_duplicate_rate_pct=self._max_duplicate_rate_pct,
            all_urls=self._all_urls,
            id_to_url=self._id_to_url,
            category_counts=self._category_counts,
            page_yields=self._page_yields,
            page_id_samples=self._page_id_samples,
        )
        report_path = write_discovery_report(stats, out_dir)

        status = "PASSED" if stats.passed else "FAILED"
        self.logger.warning(
            "discovery_complete status=%s pages=%d unique_ids=%d dup_rate=%.2f%% report=%s",
            status,
            stats.index_pages_crawled,
            stats.listing_ids_unique,
            stats.duplicate_rate_pct,
            report_path,
        )
        for note in stats.notes:
            self.logger.warning("discovery_note %s", note)
