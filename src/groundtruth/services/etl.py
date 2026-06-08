"""ETL orchestration: raw → parsed → normalized with validation metrics."""

from __future__ import annotations

import time
from decimal import Decimal
from typing import Any

from sqlalchemy.orm import Session

from groundtruth.database.repositories import (
    EtlMetricsRepository,
    InvalidListingRepository,
    NormalizedListingRepository,
    ParsedListingRepository,
    RawListingRepository,
)
from groundtruth.logging import get_logger
from groundtruth.models.enums import ListingType, PipelineStage
from groundtruth.models.pipeline import NormalizedListing, RawListing
from groundtruth.processing.confidence import ConfidenceScorer
from groundtruth.processing.validation import ListingValidator
from groundtruth.schemas.etl import EtlMetricsSchema, FieldExtractionRates, InvalidListingSchema
from groundtruth.schemas.pipeline import NormalizedListingSchema
from groundtruth.services.normalization import NORMALIZATION_VERSION, NormalizationService
from groundtruth.services.parsing import PARSER_VERSION, ParsingService
from groundtruth.services.pipeline import PipelineService

logger = get_logger(__name__)


class EtlService:
    """Run the full ETL pipeline and record quality metrics."""

    def __init__(self, session: Session) -> None:
        self._session = session
        self._raw_repo = RawListingRepository(session)
        self._parsed_repo = ParsedListingRepository(session)
        self._normalized_repo = NormalizedListingRepository(session)
        self._metrics_repo = EtlMetricsRepository(session)
        self._invalid_repo = InvalidListingRepository(session)
        self._pipeline = PipelineService(session)
        self._parser = ParsingService()
        self._normalizer = NormalizationService(session)
        self._validator = ListingValidator()
        self._confidence = ConfidenceScorer()

    def run(
        self,
        *,
        scrape_run_id: int | None = None,
        source: str | None = None,
        skip_existing: bool = True,
        reprocess: bool = False,
    ) -> EtlMetricsSchema:
        """Process raw listings through parse → normalize → validate."""
        started = time.perf_counter()

        if reprocess:
            self._clear_processed(source=source, scrape_run_id=scrape_run_id)
            skip_existing = False

        if scrape_run_id is not None:
            raw_listings = self._raw_repo.list_by_scrape_run(scrape_run_id)
            source_name = source or (raw_listings[0].source_website if raw_listings else "unknown")
        else:
            raw_listings = self._raw_repo.list_unparsed(source_website=source)
            source_name = source or (raw_listings[0].source_website if raw_listings else "unknown")

        counters = {
            "parsed_success": 0,
            "parsed_failed": 0,
            "normalized_success": 0,
            "normalized_failed": 0,
            "validation_failed": 0,
        }
        normalized_entities: list[NormalizedListing] = []

        for raw in raw_listings:
            if skip_existing and self._parsed_repo.exists_for_raw(raw.id):
                continue

            parsed_schema = self._parse_or_record_failure(raw, counters)
            if parsed_schema is None:
                continue

            parsed_entity = self._pipeline.store_parsed(
                parsed_schema,
                raw_listing_id=raw.id,
                scrape_run_id=raw.scrape_run_id,
            )

            try:
                normalized_schema, factors = self._normalizer.normalize(parsed_schema)
                normalized_schema.scraped_at = raw.scraped_at
                is_valid = True
                validation = self._validator.validate(normalized_schema)
                if not validation.is_valid:
                    is_valid = False
                    counters["validation_failed"] += 1
                    self._record_invalid(
                        stage=PipelineStage.VALIDATE,
                        error_codes=[issue.code for issue in validation.issues],
                        field_errors={issue.field: issue.message for issue in validation.issues},
                        message="; ".join(issue.message for issue in validation.issues),
                        scrape_run_id=raw.scrape_run_id,
                        raw_listing_id=raw.id,
                        parsed_listing_id=parsed_entity.id,
                        snapshot=normalized_schema.model_dump(mode="json"),
                    )

                confidence = self._confidence.score(
                    normalized_schema,
                    parsed_schema,
                    factors=factors,
                    is_valid=is_valid,
                )
                normalized_schema.confidence_score = confidence.score
                normalized_schema.confidence_details = confidence.details

                normalized_entity = self._pipeline.normalize_and_store(
                    parsed_schema,
                    parsed_listing_id=parsed_entity.id,
                    scrape_run_id=raw.scrape_run_id,
                    normalized=normalized_schema,
                )
                counters["normalized_success"] += 1
                normalized_entities.append(normalized_entity)
            except Exception as exc:
                counters["normalized_failed"] += 1
                self._record_invalid(
                    stage=PipelineStage.NORMALIZE,
                    error_codes=["normalize_error"],
                    message=str(exc),
                    scrape_run_id=raw.scrape_run_id,
                    raw_listing_id=raw.id,
                    parsed_listing_id=parsed_entity.id,
                    snapshot={"source_listing_id": raw.source_listing_id},
                )
                logger.error(
                    "normalize_failed",
                    raw_listing_id=raw.id,
                    error=str(exc),
                )

        field_rates = self._compute_field_rates(normalized_entities)
        duplicate_candidates = self._count_duplicate_candidates(normalized_entities)
        duration = round(time.perf_counter() - started, 2)

        metrics = EtlMetricsSchema(
            scrape_run_id=scrape_run_id,
            source=source_name,
            parser_version=PARSER_VERSION,
            normalization_version=NORMALIZATION_VERSION,
            total_scraped=len(raw_listings),
            parsed_success=counters["parsed_success"],
            parsed_failed=counters["parsed_failed"],
            normalized_success=counters["normalized_success"],
            normalized_failed=counters["normalized_failed"],
            validation_failed=counters["validation_failed"],
            duplicate_candidates=duplicate_candidates,
            duration_seconds=duration,
            field_rates=field_rates,
        )
        self._metrics_repo.create_from_schema(metrics)
        self._session.commit()

        logger.info("etl_run_complete", metrics=metrics.model_dump(mode="json"))
        return metrics

    def _clear_processed(
        self,
        *,
        source: str | None,
        scrape_run_id: int | None,
    ) -> None:
        from groundtruth.models.pipeline import NormalizedListing, ParsedListing, RawListing

        raw_ids_query = self._session.query(RawListing.id)
        if scrape_run_id is not None:
            raw_ids_query = raw_ids_query.filter(RawListing.scrape_run_id == scrape_run_id)
        if source:
            raw_ids_query = raw_ids_query.filter(RawListing.source_website == source)
        raw_ids = [row[0] for row in raw_ids_query.all()]

        if not raw_ids:
            return

        parsed_ids = [
            row[0]
            for row in self._session.query(ParsedListing.id)
            .filter(ParsedListing.raw_listing_id.in_(raw_ids))
            .all()
        ]
        if parsed_ids:
            self._session.query(NormalizedListing).filter(
                NormalizedListing.parsed_listing_id.in_(parsed_ids)
            ).delete(synchronize_session=False)
            self._session.query(ParsedListing).filter(ParsedListing.id.in_(parsed_ids)).delete(
                synchronize_session=False
            )
        from groundtruth.models.etl import InvalidListing

        invalid_query = self._session.query(InvalidListing)
        if scrape_run_id is not None:
            invalid_query = invalid_query.filter(InvalidListing.scrape_run_id == scrape_run_id)
        invalid_query.delete(synchronize_session=False)
        self._session.flush()

    def _parse_or_record_failure(
        self,
        raw: RawListing,
        counters: dict[str, int],
    ):
        try:
            parsed = self._parser.parse_raw(raw)
            counters["parsed_success"] += 1
            return parsed
        except Exception as exc:
            counters["parsed_failed"] += 1
            self._record_invalid(
                stage=PipelineStage.PARSE,
                error_codes=["parse_error"],
                message=str(exc),
                scrape_run_id=raw.scrape_run_id,
                raw_listing_id=raw.id,
                snapshot={"raw_payload_keys": list((raw.raw_payload or {}).keys())},
            )
            logger.error("parse_failed", raw_listing_id=raw.id, error=str(exc))
            return None

    def _record_invalid(self, **kwargs: Any) -> None:
        schema = InvalidListingSchema(**kwargs)
        self._invalid_repo.create_from_schema(schema)

    def _compute_field_rates(
        self,
        listings: list[NormalizedListing],
    ) -> FieldExtractionRates:
        total = len(listings)
        if total == 0:
            return FieldExtractionRates()

        def pct(count: int) -> float:
            return round(100.0 * count / total, 1)

        price_count = sum(
            1
            for listing in listings
            if (listing.sale_price is not None or listing.rent_price is not None)
        )
        area_count = sum(1 for listing in listings if listing.area_sqm is not None)
        neighborhood_count = sum(1 for listing in listings if listing.neighborhood_id is not None)
        building_count = sum(1 for listing in listings if listing.building_id is not None)
        description_count = sum(
            1 for listing in listings if listing.description_original
        )
        listing_type_count = sum(1 for listing in listings if listing.listing_type is not None)

        return FieldExtractionRates(
            price=pct(price_count),
            area=pct(area_count),
            neighborhood=pct(neighborhood_count),
            building=pct(building_count),
            description=pct(description_count),
            listing_type=pct(listing_type_count),
        )

    def _count_duplicate_candidates(self, listings: list[NormalizedListing]) -> int:
        """In-batch heuristic: same neighborhood, area, bedrooms, and price."""
        signatures: list[tuple[Any, ...]] = []
        duplicates = 0
        for listing in listings:
            price = listing.rent_price if listing.listing_type == ListingType.RENT else listing.sale_price
            if price is None or listing.area_sqm is None:
                continue
            sig = (
                listing.neighborhood_id,
                round(listing.area_sqm, 1),
                listing.bedrooms,
                self._price_bucket(price),
            )
            if sig in signatures:
                duplicates += 1
            else:
                signatures.append(sig)
        return duplicates

    @staticmethod
    def _price_bucket(price: Decimal | str | float) -> int:
        amount = Decimal(str(price))
        return int(amount // Decimal("50")) * 50
