"""ETL data-integrity QA using the pipeline's persisted quality metrics."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal

from sqlalchemy import select
from sqlalchemy.orm import Session

from groundtruth.models.etl import EtlMetrics

QualityLevel = Literal["GREEN", "YELLOW", "RED"]


@dataclass(frozen=True)
class DataQualityThreshold:
    minimum_sample: int = 10
    parse_warning_rate: float = 0.1
    parse_red_rate: float = 0.5
    normalize_warning_rate: float = 0.1
    normalize_red_rate: float = 0.3
    validation_warning_rate: float = 0.25
    validation_red_rate: float = 0.6


@dataclass
class DataQualityResult:
    source: str
    level: QualityLevel
    scrape_run_id: int | None
    raw: int = 0
    parsed: int = 0
    normalized: int = 0
    valid: int = 0
    quarantined: int = 0
    duplicate_candidates: int = 0
    parse_failures: int = 0
    normalization_failures: int = 0
    error_breakdown: dict[str, int] = field(default_factory=dict)
    field_rates: dict[str, Any] = field(default_factory=dict)
    reasons: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def classify_data_quality(
    *,
    source: str,
    scrape_run_id: int | None,
    raw: int,
    parsed: int,
    parse_failures: int,
    normalized: int,
    normalization_failures: int,
    validation_failures: int,
    duplicate_candidates: int = 0,
    field_rates: dict[str, Any] | None = None,
    threshold: DataQualityThreshold | None = None,
) -> DataQualityResult:
    policy = threshold or DataQualityThreshold()
    reasons: list[str] = []
    level: QualityLevel = "GREEN"
    parse_denominator = parsed + parse_failures
    normalize_denominator = normalized + normalization_failures
    parse_rate = parse_failures / parse_denominator if parse_denominator else 0.0
    normalize_rate = (
        normalization_failures / normalize_denominator if normalize_denominator else 0.0
    )
    validation_rate = validation_failures / normalized if normalized else 0.0

    if raw >= policy.minimum_sample and normalized == 0:
        level = "RED"
        reasons.append("non-empty raw input produced no normalized records")
    if parse_denominator >= policy.minimum_sample:
        if parse_rate >= policy.parse_red_rate:
            level = "RED"
            reasons.append(f"parse failure rate is {parse_rate:.1%}")
        elif parse_rate >= policy.parse_warning_rate and level == "GREEN":
            level = "YELLOW"
            reasons.append(f"parse failure rate is {parse_rate:.1%}")
    if normalize_denominator >= policy.minimum_sample:
        if normalize_rate >= policy.normalize_red_rate:
            level = "RED"
            reasons.append(f"normalization failure rate is {normalize_rate:.1%}")
        elif normalize_rate >= policy.normalize_warning_rate and level == "GREEN":
            level = "YELLOW"
            reasons.append(f"normalization failure rate is {normalize_rate:.1%}")
    if normalized >= policy.minimum_sample:
        if validation_rate >= policy.validation_red_rate:
            level = "RED"
            reasons.append(f"validation quarantine rate is {validation_rate:.1%}")
        elif validation_rate >= policy.validation_warning_rate and level == "GREEN":
            level = "YELLOW"
            reasons.append(f"validation quarantine rate is {validation_rate:.1%}")

    rates = field_rates or {}
    breakdown = rates.get("error_breakdown") if isinstance(rates, dict) else {}
    return DataQualityResult(
        source=source,
        level=level,
        scrape_run_id=scrape_run_id,
        raw=raw,
        parsed=parsed,
        normalized=normalized,
        valid=max(0, normalized - validation_failures),
        quarantined=validation_failures,
        duplicate_candidates=duplicate_candidates,
        parse_failures=parse_failures,
        normalization_failures=normalization_failures,
        error_breakdown=breakdown if isinstance(breakdown, dict) else {},
        field_rates=rates,
        reasons=reasons,
    )


def collect_data_quality(session: Session, source_results: list[Any]) -> list[DataQualityResult]:
    results: list[DataQualityResult] = []
    for item in source_results:
        if item.scrape_run_id is None:
            continue
        metrics = session.scalar(
            select(EtlMetrics)
            .where(EtlMetrics.scrape_run_id == item.scrape_run_id)
            .order_by(EtlMetrics.created_at.desc())
            .limit(1)
        )
        if metrics is None:
            results.append(
                DataQualityResult(
                    source=item.source,
                    level="RED",
                    scrape_run_id=item.scrape_run_id,
                    reasons=["ETL metrics are missing for the completed crawl"],
                )
            )
            continue
        results.append(
            classify_data_quality(
                source=item.source,
                scrape_run_id=item.scrape_run_id,
                raw=metrics.total_scraped,
                parsed=metrics.parsed_success,
                parse_failures=metrics.parsed_failed,
                normalized=metrics.normalized_success,
                normalization_failures=metrics.normalized_failed,
                validation_failures=metrics.validation_failed,
                duplicate_candidates=metrics.duplicate_candidates,
                field_rates=metrics.field_rates,
            )
        )
    return results
