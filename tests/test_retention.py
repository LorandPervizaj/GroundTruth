"""Sensitive-content retention enforcement."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

from groundtruth.config import get_settings
from groundtruth.database.session import get_session_factory
from groundtruth.models.pipeline import NormalizedListing, ParsedListing, RawListing
from groundtruth.models.scrape_run import ScrapeRun
from groundtruth.services.retention import enforce_retention


def test_retention_dry_run_then_purge(require_postgres) -> None:
    now = datetime.now(UTC)
    old = now - timedelta(days=31)
    marker = uuid4().hex
    settings = get_settings().model_copy(
        update={
            "raw_html_retention_days": 30,
            "raw_payload_retention_days": 30,
            "parsed_description_retention_days": 30,
        }
    )
    session = get_session_factory()()
    try:
        run = ScrapeRun(spider_name=f"retention-test-{marker}", started_at=old)
        raw = RawListing(
            scrape_run=run,
            source_website="retention-test",
            source_listing_id=marker,
            original_url=f"https://example.com/{marker}",
            content_hash=marker.ljust(64, "0"),
            raw_payload={"description": "sensitive"},
            raw_html="<p>sensitive</p>",
            scraped_at=old,
        )
        parsed = ParsedListing(
            raw_listing=raw,
            scrape_run=run,
            source_website="retention-test",
            source_listing_id=marker,
            original_url=raw.original_url,
            description_original="sensitive",
            description_cleaned="sensitive",
            parsed_at=old,
        )
        normalized = NormalizedListing(
            parsed_listing=parsed,
            scrape_run=run,
            source_website="retention-test",
            source_listing_id=marker,
            original_url=raw.original_url,
            description_original="sensitive",
            description_cleaned="sensitive",
            normalized_at=old,
        )
        session.add_all([run, raw, parsed, normalized])
        session.flush()

        preview = enforce_retention(session, settings, now=now, dry_run=True)
        assert preview.raw_html_rows >= 1
        assert preview.raw_payload_rows >= 1
        assert preview.parsed_description_rows >= 1
        assert preview.normalized_description_rows >= 1
        assert raw.raw_html is not None

        applied = enforce_retention(session, settings, now=now, dry_run=False)
        session.flush()
        session.refresh(raw)
        session.refresh(parsed)
        session.refresh(normalized)

        assert applied.dry_run is False
        assert raw.raw_html is None
        assert raw.raw_payload == {}
        assert parsed.description_original is None
        assert parsed.description_cleaned is None
        assert normalized.description_original is None
        assert normalized.description_cleaned is None
    finally:
        session.rollback()
        session.close()
