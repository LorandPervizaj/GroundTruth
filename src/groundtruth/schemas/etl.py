"""Schemas for ETL metrics and validation."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from groundtruth.models.enums import PipelineStage


class ValidationIssue(BaseModel):
    """A single validation failure on a normalized listing."""

    code: str
    field: str
    message: str
    value: Any = None


class ValidationResult(BaseModel):
    """Outcome of validating a normalized listing."""

    is_valid: bool
    issues: list[ValidationIssue] = Field(default_factory=list)


class FieldExtractionRates(BaseModel):
    """Percentage of listings where a field was successfully extracted."""

    price: float = 0.0
    area: float = 0.0
    neighborhood: float = 0.0
    building: float = 0.0
    description: float = 0.0
    listing_type: float = 0.0


class EtlMetricsSchema(BaseModel):
    """ETL run summary for persistence and reporting."""

    model_config = ConfigDict(from_attributes=True)

    scrape_run_id: int | None = None
    source: str
    parser_version: str
    normalization_version: str
    total_scraped: int = 0
    parsed_success: int = 0
    parsed_failed: int = 0
    normalized_success: int = 0
    normalized_failed: int = 0
    validation_failed: int = 0
    duplicate_candidates: int = 0
    duration_seconds: float | None = None
    field_rates: FieldExtractionRates | dict[str, Any] | None = None
    created_at: datetime | None = None


class InvalidListingSchema(BaseModel):
    """Record for a listing that failed a pipeline stage."""

    scrape_run_id: int | None = None
    raw_listing_id: int | None = None
    parsed_listing_id: int | None = None
    normalized_listing_id: int | None = None
    stage: PipelineStage
    error_codes: list[str]
    field_errors: dict[str, str] | None = None
    message: str | None = None
    snapshot: dict[str, Any] | None = None
