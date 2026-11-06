"""Versioned, strict input and output contracts for private source diagnostics."""

from datetime import datetime
from math import isfinite
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from groundtruth.schemas.pipeline import NormalizedListingSchema

CRITERIA = (
    "validity",
    "completeness",
    "location",
    "consistency",
    "freshness",
    "historical_reliability",
)


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class QualityPolicy(Contract):
    version: str = "1.1.0"
    weights: dict[str, float] = Field(
        default_factory=lambda: dict(
            zip(CRITERIA, (0.25, 0.20, 0.25, 0.15, 0.10, 0.05), strict=True)
        )
    )
    unknown_imputation: float = Field(50, ge=0, le=100)
    freshness_days: int = Field(180, gt=0)
    minimum_sample: int = Field(30, ge=1)
    minimum_coverage: float = Field(0.90, ge=0, le=1)
    minimum_location_verification: float = Field(0.80, ge=0, le=1)
    minimum_processed_fraction: float = Field(0.95, ge=0, le=1)
    minimum_weight: float = Field(0.75, gt=0, le=1)
    maximum_weight: float = Field(1.25, ge=1)
    duplicate_threshold: float = Field(85, gt=0, le=100)

    @model_validator(mode="after")
    def valid_weights(self):
        if (
            set(self.weights) != set(CRITERIA)
            or any(v < 0 for v in self.weights.values())
            or abs(sum(self.weights.values()) - 1) > 1e-9
        ):
            raise ValueError("Criterion weights must contain exactly six criteria and sum to 1")
        return self


class Verification(Contract):
    """Explicit independent evidence, never inferred from parser diagnostics."""

    evidence_id: str = Field(min_length=1)
    checked_at: datetime
    origin: Literal["source", "parser"]
    correct: bool
    kind: Literal["location", "historical", "consistency"]


class QualityRecord(Contract):
    source_name: str = Field(min_length=1)
    source_listing_id: str = Field(min_length=1)
    observation_id: int = Field(ge=0)
    observed_at: datetime
    outcome: Literal["accepted", "rejected", "pending"]
    failure_stage: Literal["parse", "normalize", "validate"] | None = None
    error_codes: list[str] = Field(default_factory=list)
    listing: NormalizedListingSchema | None = None
    verification: list[Verification] = Field(default_factory=list)
    content_hash: str | None = None
    source_updated_at: datetime | None = None
    first_seen_at: datetime | None = None
    last_seen_at: datetime | None = None
    active_verified_at: datetime | None = None
    publication_date_basis: Literal["source_declared", "proxy", "unknown"] = "unknown"

    @model_validator(mode="after")
    def valid_listing(self):
        if self.listing:
            if (self.listing.source_website, self.listing.source_listing_id) != (
                self.source_name,
                self.source_listing_id,
            ):
                raise ValueError("Listing identity must match its quality record")
            for name in (
                "area_sqm",
                "sale_price",
                "rent_price",
                "price_per_sqm",
                "latitude",
                "longitude",
            ):
                value = getattr(self.listing, name)
                if value is not None and not isfinite(float(value)):
                    raise ValueError(f"Non-finite {name}")
        evidence_keys = [(v.kind, v.evidence_id) for v in self.verification]
        if len(evidence_keys) != len(set(evidence_keys)):
            raise ValueError("Duplicate verification evidence")
        if self.outcome == "accepted" and self.listing is None:
            raise ValueError("Accepted records require listing evidence")
        return self


class ListingAssessment(Contract):
    source_name: str
    source_listing_id: str
    observation_id: int
    segment: str
    outcome: str
    scores: dict[str, float | None]
    quality_score: float = Field(ge=0, le=100)
    observed_criterion_coverage: float = Field(ge=0, le=1)
    location_precision_score: float | None
    location_verification_status: str
    freshness_basis: str
    freshness_evidence: dict[str, str | None]
    error_codes: list[str]
    error_origin: str


class SourceAssessment(Contract):
    source_name: str
    segment: str
    records_examined: int
    unique_source_listing_count: int
    accepted_count: int
    rejected_count: int
    pending_count: int
    repeated_observation_count: int
    within_source_content_duplicate_count: int
    cross_portal_duplicate_listing_count: int
    cross_portal_comparable_count: int
    validity_score: float | None
    completeness_score: float | None
    location_score: float | None
    location_precision_score: float | None
    location_verification_status: str
    consistency_score: float | None
    freshness_score: float | None
    historical_reliability_score: float | None
    unknown_criteria: list[str]
    criterion_sample_counts: dict[str, int]
    observed_criterion_coverage: float
    source_quality_score: float | None
    score_status: str
    proposed_weight: float
    weight_status: str
    eligibility_reason: list[str]
    error_code_counts: dict[str, int]
    error_origin_counts: dict[str, int]


class QualityReport(Contract):
    report_version: str = "1.1.0"
    scoring_policy_version: str
    generated_at: datetime
    evaluation_as_of: datetime
    evaluation_window: dict[str, datetime]
    population: str = "raw_versions_observed_in_window; latest_per_source_listing; all_outcomes"
    input_fingerprint: str
    scoring_policy: QualityPolicy
    sources: list[SourceAssessment]
    listings: list[ListingAssessment]
