"""Repositories for pipeline stage tables."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from groundtruth.database.repositories.base import BaseRepository
from groundtruth.models.pipeline import NormalizedListing, ParsedListing, RawListing
from groundtruth.schemas.pipeline import (
    NormalizedListingSchema,
    ParsedListingSchema,
    RawListingSchema,
)


class RawListingRepository(BaseRepository[RawListing]):
    """Persistence for immutable raw listings."""

    model = RawListing

    def __init__(self, session: Session) -> None:
        super().__init__(session)

    def create_from_schema(
        self,
        schema: RawListingSchema,
        scrape_run_id: int,
    ) -> RawListing:
        """Persist a raw listing from a Pydantic schema."""
        entity = RawListing(
            scrape_run_id=scrape_run_id,
            source_website=schema.source_website,
            source_listing_id=schema.source_listing_id,
            original_url=schema.original_url,
            content_hash=schema.content_hash,
            spider_version=schema.spider_version,
            raw_payload=schema.raw_payload,
            raw_html=schema.raw_html,
        )
        return self.add(entity)

    def list_by_scrape_run(self, scrape_run_id: int) -> list[RawListing]:
        stmt = (
            select(RawListing)
            .where(RawListing.scrape_run_id == scrape_run_id)
            .order_by(RawListing.id)
        )
        return list(self._session.scalars(stmt).all())

    def list_unparsed(self, source_website: str | None = None) -> list[RawListing]:
        parsed_ids = select(ParsedListing.raw_listing_id)
        stmt = select(RawListing).where(RawListing.id.not_in(parsed_ids))
        if source_website:
            stmt = stmt.where(RawListing.source_website == source_website)
        stmt = stmt.order_by(RawListing.id)
        return list(self._session.scalars(stmt).all())

    def get_by_source(
        self,
        source_website: str,
        source_listing_id: str,
    ) -> list[RawListing]:
        """Return all raw versions for a source listing."""
        stmt = (
            select(RawListing)
            .where(
                RawListing.source_website == source_website,
                RawListing.source_listing_id == source_listing_id,
            )
            .order_by(RawListing.scraped_at.desc())
        )
        return list(self._session.scalars(stmt).all())


class ParsedListingRepository(BaseRepository[ParsedListing]):
    """Persistence for parsed listings."""

    model = ParsedListing

    def __init__(self, session: Session) -> None:
        super().__init__(session)

    def create_from_schema(
        self,
        schema: ParsedListingSchema,
        raw_listing_id: int,
        scrape_run_id: int,
    ) -> ParsedListing:
        """Persist a parsed listing from a Pydantic schema."""
        data = schema.model_dump(exclude={"raw_listing_id", "scrape_run_id"})
        entity = ParsedListing(
            raw_listing_id=raw_listing_id,
            scrape_run_id=scrape_run_id,
            **data,
        )
        return self.add(entity)

    def exists_for_raw(self, raw_listing_id: int) -> bool:
        stmt = select(ParsedListing.id).where(ParsedListing.raw_listing_id == raw_listing_id).limit(1)
        return self._session.scalars(stmt).first() is not None


class NormalizedListingRepository(BaseRepository[NormalizedListing]):
    """Persistence for normalized listings."""

    model = NormalizedListing

    def __init__(self, session: Session) -> None:
        super().__init__(session)

    def create_from_schema(
        self,
        schema: NormalizedListingSchema,
        parsed_listing_id: int,
        scrape_run_id: int,
    ) -> NormalizedListing:
        """Persist a normalized listing from a Pydantic schema."""
        data = schema.model_dump(
            exclude={"parsed_listing_id", "scrape_run_id"},
            mode="json",
        )
        if data.get("image_urls"):
            data["image_urls"] = [str(url) for url in data["image_urls"]]
        entity = NormalizedListing(
            parsed_listing_id=parsed_listing_id,
            scrape_run_id=scrape_run_id,
            **data,
        )
        return self.add(entity)

    def list_active_by_city(self, city: str, limit: int = 1000) -> list[NormalizedListing]:
        """Return active normalized listings for a city."""
        stmt = (
            select(NormalizedListing)
            .where(
                NormalizedListing.city == city,
                NormalizedListing.is_active.is_(True),
            )
            .limit(limit)
        )
        return list(self._session.scalars(stmt).all())
