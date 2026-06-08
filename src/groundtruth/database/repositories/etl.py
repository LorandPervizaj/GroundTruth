"""Repositories for ETL metrics and invalid listings."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from groundtruth.database.repositories.base import BaseRepository
from groundtruth.models.etl import EtlMetrics, InvalidListing
from groundtruth.schemas.etl import EtlMetricsSchema, InvalidListingSchema


class EtlMetricsRepository(BaseRepository[EtlMetrics]):
    model = EtlMetrics

    def __init__(self, session: Session) -> None:
        super().__init__(session)

    def create_from_schema(self, schema: EtlMetricsSchema) -> EtlMetrics:
        field_rates = schema.field_rates
        if hasattr(field_rates, "model_dump"):
            field_rates = field_rates.model_dump()
        entity = EtlMetrics(
            scrape_run_id=schema.scrape_run_id,
            source=schema.source,
            parser_version=schema.parser_version,
            normalization_version=schema.normalization_version,
            total_scraped=schema.total_scraped,
            parsed_success=schema.parsed_success,
            parsed_failed=schema.parsed_failed,
            normalized_success=schema.normalized_success,
            normalized_failed=schema.normalized_failed,
            validation_failed=schema.validation_failed,
            duplicate_candidates=schema.duplicate_candidates,
            duration_seconds=schema.duration_seconds,
            field_rates=field_rates,
        )
        return self.add(entity)

    def get_latest(self, source: str | None = None) -> EtlMetrics | None:
        stmt = select(EtlMetrics).order_by(EtlMetrics.created_at.desc())
        if source:
            stmt = stmt.where(EtlMetrics.source == source)
        return self._session.scalars(stmt).first()


class InvalidListingRepository(BaseRepository[InvalidListing]):
    model = InvalidListing

    def __init__(self, session: Session) -> None:
        super().__init__(session)

    def create_from_schema(self, schema: InvalidListingSchema) -> InvalidListing:
        entity = InvalidListing(**schema.model_dump())
        return self.add(entity)
