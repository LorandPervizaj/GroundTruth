"""Independent parser KPIs — separate metrics, no composite score."""

from __future__ import annotations

from pydantic import BaseModel, Field

from groundtruth.golden.evaluate import evaluate_golden_file, latest_golden_file
from groundtruth.schemas.etl import FieldExtractionRates


class ParserCoverageKPIs(BaseModel):
    """Field coverage from an ETL run (extraction success rate)."""

    price: float = 0.0
    area: float = 0.0
    neighborhood: float = 0.0
    building: float = 0.0
    heating: float = 0.0
    furnished: float = 0.0
    listing_type: float = 0.0


class ParserAccuracyKPIs(BaseModel):
    """Field accuracy from golden dataset (verified labels)."""

    price: float = 0.0
    area: float = 0.0
    neighborhood: float = 0.0
    building: float = 0.0
    overall: float = 0.0
    golden_version: str = ""
    sample_size: int = 0


class ParserKPIReport(BaseModel):
    """Full parser KPI report for an ETL run."""

    coverage: ParserCoverageKPIs = Field(default_factory=ParserCoverageKPIs)
    accuracy: ParserAccuracyKPIs | None = None
    invalid_rate_pct: float = 0.0
    duplicate_rate_pct: float = 0.0


def coverage_from_field_rates(rates: FieldExtractionRates) -> ParserCoverageKPIs:
    return ParserCoverageKPIs(
        price=rates.price,
        area=rates.area,
        neighborhood=rates.neighborhood,
        building=rates.building,
        heating=rates.heating,
        furnished=rates.furnished,
        listing_type=rates.listing_type,
    )


def accuracy_from_golden() -> ParserAccuracyKPIs | None:
    path = latest_golden_file()
    if path is None:
        return None
    result = evaluate_golden_file(path)
    if result is None or result.total == 0:
        return None
    return ParserAccuracyKPIs(
        price=round(result.price * 100, 1),
        area=round(result.area * 100, 1),
        neighborhood=round(result.neighborhood * 100, 1),
        building=0.0,
        overall=round(result.overall * 100, 1),
        golden_version=path.stem,
        sample_size=result.total,
    )


def build_parser_kpi_report(
    field_rates: FieldExtractionRates,
    *,
    normalized_count: int,
    validation_failed: int,
    duplicate_candidates: int,
) -> ParserKPIReport:
    coverage = coverage_from_field_rates(field_rates)
    invalid_rate = round(100.0 * validation_failed / normalized_count, 1) if normalized_count else 0.0
    duplicate_rate = (
        round(100.0 * duplicate_candidates / normalized_count, 1) if normalized_count else 0.0
    )
    return ParserKPIReport(
        coverage=coverage,
        accuracy=accuracy_from_golden(),
        invalid_rate_pct=invalid_rate,
        duplicate_rate_pct=duplicate_rate,
    )
