"""Tests for independent parser KPI reporting."""

from groundtruth.processing.parser_kpis import (
    build_parser_kpi_report,
    coverage_from_field_rates,
)
from groundtruth.schemas.etl import FieldExtractionRates


def test_coverage_kpis_are_independent() -> None:
    rates = FieldExtractionRates(
        price=100.0,
        area=96.8,
        neighborhood=97.1,
        building=62.3,
        heating=3.0,
        furnished=70.0,
    )
    cov = coverage_from_field_rates(rates)
    assert cov.price == 100.0
    assert cov.neighborhood == 97.1
    assert cov.building == 62.3


def test_kpi_report_has_no_composite_score() -> None:
    rates = FieldExtractionRates(price=100.0, area=95.0, neighborhood=98.0)
    report = build_parser_kpi_report(
        rates,
        normalized_count=1000,
        validation_failed=30,
        duplicate_candidates=50,
    )
    assert report.invalid_rate_pct == 3.0
    assert report.duplicate_rate_pct == 5.0
    assert report.coverage.price == 100.0
    dumped = report.model_dump()
    assert "data_quality_score" not in dumped
