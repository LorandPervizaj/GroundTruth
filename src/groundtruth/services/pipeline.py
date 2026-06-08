"""Orchestrates the raw → parsed → normalized pipeline."""

from sqlalchemy.orm import Session

from groundtruth.database.repositories import (
    NormalizedListingRepository,
    ParsedListingRepository,
    RawListingRepository,
    ScrapeRunRepository,
)
from groundtruth.logging import get_logger
from groundtruth.schemas.pipeline import (
    NormalizedListingSchema,
    ParsedListingSchema,
    RawListingSchema,
)
from groundtruth.services.normalization import NormalizationService

logger = get_logger(__name__)


class PipelineService:
    """Coordinates pipeline stage transitions without overwriting raw data."""

    def __init__(self, session: Session) -> None:
        self._session = session
        self._raw_repo = RawListingRepository(session)
        self._parsed_repo = ParsedListingRepository(session)
        self._normalized_repo = NormalizedListingRepository(session)
        self._scrape_run_repo = ScrapeRunRepository(session)
        self._normalization_service = NormalizationService(session)

    def store_raw(
        self,
        schema: RawListingSchema,
        scrape_run_id: int,
    ):
        """Persist immutable raw listing."""
        entity = self._raw_repo.create_from_schema(schema, scrape_run_id)
        logger.info(
            "raw_listing_stored",
            raw_listing_id=entity.id,
            source=schema.source_website,
            listing_id=schema.source_listing_id,
        )
        return entity

    def store_parsed(
        self,
        schema: ParsedListingSchema,
        raw_listing_id: int,
        scrape_run_id: int,
    ):
        """Persist parsed listing linked to raw source."""
        entity = self._parsed_repo.create_from_schema(
            schema, raw_listing_id, scrape_run_id
        )
        logger.info(
            "parsed_listing_stored",
            parsed_listing_id=entity.id,
            raw_listing_id=raw_listing_id,
        )
        return entity

    def normalize_and_store(
        self,
        parsed: ParsedListingSchema,
        parsed_listing_id: int,
        scrape_run_id: int,
        normalized: NormalizedListingSchema | None = None,
    ):
        """Normalize a parsed listing and persist the result."""
        if normalized is None:
            normalized, _ = self._normalization_service.normalize(parsed)
        normalized_schema = normalized
        entity = self._normalized_repo.create_from_schema(
            normalized_schema,
            parsed_listing_id,
            scrape_run_id,
        )
        logger.info(
            "normalized_listing_stored",
            normalized_listing_id=entity.id,
            parsed_listing_id=parsed_listing_id,
        )
        return entity
