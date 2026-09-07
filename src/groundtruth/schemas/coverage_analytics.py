"""Coverage KPI snapshot schema."""

from __future__ import annotations

from pydantic import BaseModel


class MunicipalityCoverageRow(BaseModel):
    municipality: str
    demand_weight_pct: float
    covered: bool
    neighborhoods_total: int
    neighborhoods_estimate_ready: int


class CoverageOpportunityRow(BaseModel):
    """Ranked geographic expansion backlog: demand × coverage gap × population."""

    rank: int
    municipality: str
    opportunity_score: float
    demand_weight_pct: float
    coverage_gap_pct: float
    population: int
    covered: bool
    neighborhoods_estimate_ready: int
    neighborhoods_total: int


class ConfidenceCoverage(BaseModel):
    """Projected rent-valuation confidence tiers across gazetteer neighborhoods."""

    high_pct: float
    medium_pct: float
    insufficient_pct: float
    high_count: int
    medium_count: int
    insufficient_count: int
    neighborhoods_total: int
    high_confidence_target_pct: float = 50.0


class HoldoutEvalSummary(BaseModel):
    """Latest frozen holdout run (from results/baseline.json when present)."""

    holdout_path: str
    evaluated_rows: int
    total_rows: int
    evaluation_rate_pct: float
    skipped_rows: int
    mape_pct: float | None = None
    evaluated_at: str | None = None


class CoverageAnalyticsSnapshot(BaseModel):
    """Business coverage KPIs for ops dashboard and v1.0 gates."""

    evaluated_at: str
    freshness_window_days: int = 14
    min_comparables: int = 30

    municipality_coverage_pct: float | None
    municipality_coverage_target_pct: float = 70.0
    municipalities_covered: int
    municipalities_tracked: int
    municipality_rows: list[MunicipalityCoverageRow]
    opportunity_backlog: list[CoverageOpportunityRow]

    neighborhoods_total: int
    neighborhoods_with_min_comparables: int
    neighborhoods_with_min_comparables_pct: float | None
    neighborhoods_rent_ready: int
    neighborhoods_sale_ready: int

    confidence_coverage: ConfidenceCoverage

    listings_active: int
    listings_fresh_pct: float | None
    listings_stale_pct: float | None
    freshness_target_pct: float = 95.0

    duplicate_rate_pct: float | None
    duplicate_rate_target_pct: float = 8.0
    raw_listings: int
    canonical_listings: int
    duplicates_removed: int

    holdout_eval: HoldoutEvalSummary | None = None

    corpus_updated_at: str | None = None
