"""Append-only benchmark log for crawl performance and ETL quality at scale."""

from __future__ import annotations

import csv
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy.orm import Session

from groundtruth.config import get_settings
from groundtruth.models.pipeline import NormalizedListing
from groundtruth.models.scrape_run import ScrapeRun
from groundtruth.schemas.etl import EtlMetricsSchema, FieldExtractionRates

BENCHMARK_COLUMNS = [
    "recorded_at",
    "label",
    "scrape_run_id",
    "source",
    "listings_stored",
    "crawl_duration_sec",
    "listings_per_sec",
    "etl_duration_sec",
    "parser_version",
    "normalization_version",
    "gazetteer_version",
    "invalid_pct",
    "mean_confidence",
    "coverage_price",
    "coverage_area",
    "coverage_neighborhood",
    "coverage_building",
    "coverage_heating",
    "coverage_furnished",
    "invalid_rate_pct",
    "duplicate_rate_pct",
    "golden_accuracy_overall",
]

BASELINE_277_ROW = {
    "recorded_at": "2026-06-01T00:00:00+00:00",
    "label": "277_baseline",
    "scrape_run_id": "",
    "source": "gjirafa",
    "listings_stored": "277",
    "crawl_duration_sec": "1380",
    "listings_per_sec": "0.20",
    "etl_duration_sec": "",
    "parser_version": "1.2.0",
    "normalization_version": "1.0.0",
    "gazetteer_version": "",
    "invalid_pct": "2.9",
    "mean_confidence": "0.94",
    "coverage_price": "100.0",
    "coverage_area": "95.3",
    "coverage_neighborhood": "98.6",
    "coverage_building": "42.0",
    "coverage_heating": "18.0",
    "coverage_furnished": "37.0",
}


def benchmark_log_path() -> Path:
    return get_settings().reports_generated_dir / "benchmark_log.csv"


def ensure_benchmark_log() -> Path:
    """Create benchmark log with header and 277 baseline row if missing."""
    path = benchmark_log_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        return path

    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=BENCHMARK_COLUMNS)
        writer.writeheader()
        writer.writerow(BASELINE_277_ROW)
    return path


def _mean_confidence(session: Session, scrape_run_id: int | None) -> float | None:
    if scrape_run_id is None:
        return None
    rows = (
        session.query(NormalizedListing.confidence_score)
        .filter(
            NormalizedListing.scrape_run_id == scrape_run_id,
            NormalizedListing.confidence_score.isnot(None),
        )
        .all()
    )
    if not rows:
        return None
    return round(sum(score for (score,) in rows) / len(rows), 3)


def _golden_accuracy_overall(metrics: EtlMetricsSchema) -> str:
    rates = metrics.field_rates
    if rates is None:
        return ""
    kpis = rates.get("parser_kpis") if isinstance(rates, dict) else rates.parser_kpis
    if not kpis:
        return ""
    accuracy = kpis.get("accuracy") if isinstance(kpis, dict) else None
    if not accuracy:
        return ""
    overall = accuracy.get("overall") if isinstance(accuracy, dict) else None
    return str(overall) if overall is not None else ""


def _crawl_duration_sec(scrape_run: ScrapeRun | None) -> float | None:
    if scrape_run is None or scrape_run.finished_at is None:
        return None
    return round((scrape_run.finished_at - scrape_run.started_at).total_seconds(), 1)


def append_benchmark(
    session: Session,
    metrics: EtlMetricsSchema,
    *,
    label: str,
    scrape_run: ScrapeRun | None = None,
) -> Path:
    """Append one benchmark row after an ETL run."""
    path = ensure_benchmark_log()
    rates = metrics.field_rates
    if isinstance(rates, dict):
        rates = FieldExtractionRates(**rates)
    elif rates is None:
        rates = FieldExtractionRates()

    normalized = metrics.normalized_success or 0
    invalid_pct = round(100.0 * metrics.validation_failed / normalized, 1) if normalized else 0.0
    crawl_duration = _crawl_duration_sec(scrape_run)
    listings_stored = scrape_run.listings_stored if scrape_run else metrics.total_scraped
    listings_per_sec = None
    if crawl_duration and crawl_duration > 0 and listings_stored:
        listings_per_sec = round(listings_stored / crawl_duration, 2)

    row = {
        "recorded_at": datetime.now(UTC).isoformat(),
        "label": label,
        "scrape_run_id": str(metrics.scrape_run_id or ""),
        "source": metrics.source,
        "listings_stored": str(listings_stored),
        "crawl_duration_sec": str(crawl_duration or ""),
        "listings_per_sec": str(listings_per_sec or ""),
        "etl_duration_sec": str(metrics.duration_seconds or ""),
        "parser_version": metrics.parser_version,
        "normalization_version": metrics.normalization_version,
        "gazetteer_version": metrics.gazetteer_version or "",
        "invalid_pct": str(invalid_pct),
        "mean_confidence": str(_mean_confidence(session, metrics.scrape_run_id) or ""),
        "coverage_price": str(rates.price),
        "coverage_area": str(rates.area),
        "coverage_neighborhood": str(rates.neighborhood),
        "coverage_building": str(rates.building),
        "coverage_heating": str(rates.heating),
        "coverage_furnished": str(rates.furnished),
        "invalid_rate_pct": str(invalid_pct),
        "duplicate_rate_pct": str(
            round(100.0 * metrics.duplicate_candidates / normalized, 1) if normalized else ""
        ),
        "golden_accuracy_overall": _golden_accuracy_overall(metrics),
    }

    with path.open("a", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=BENCHMARK_COLUMNS)
        writer.writerow(row)
    return path
