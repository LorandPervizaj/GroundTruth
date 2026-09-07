"""Reproducible valuation evaluation against a frozen holdout set."""

from __future__ import annotations

import csv
import json
import math
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd
from sqlalchemy.orm import Session

from groundtruth.analytics.valuation import (
    MODEL_VERSION,
    estimate_valuation,
    rent_comparables_dataframe,
    sale_comparables_dataframe,
)
from groundtruth.config import PROJECT_ROOT
from groundtruth.datasets.manifest import frozen_dataset_version
from groundtruth.schemas.valuation import ValuationRequest

HOLDOUT_DIR = PROJECT_ROOT / "data" / "evaluation"
DEFAULT_HOLDOUT = HOLDOUT_DIR / "valuation_holdout_v2.csv"
RESULTS_DIR = PROJECT_ROOT / "results"
REPORTS_DIR = PROJECT_ROOT / "reports"

HOLDOUT_FIELDS = [
    "holdout_id",
    "source_website",
    "source_listing_id",
    "valuation_type",
    "municipality",
    "neighborhood",
    "neighborhood_id",
    "area_sqm",
    "bedrooms",
    "property_type",
    "actual_price_eur",
    "stratum",
    "frozen_at",
    "notes",
]

ERROR_BUCKETS = [
    ("≤5%", 0.0, 5.0),
    ("5–10%", 5.0, 10.0),
    ("10–20%", 10.0, 20.0),
    ("20–50%", 20.0, 50.0),
    (">50%", 50.0, math.inf),
]


@dataclass
class ValuationEvalRowResult:
    holdout_id: str
    valuation_type: str
    neighborhood: str
    municipality: str
    area_sqm: float
    actual_price_eur: float
    predicted_price_eur: int | None
    error_eur: float | None
    abs_pct_error: float | None
    confidence_label: str | None
    comparable_count: int | None
    skipped: bool
    skip_reason: str | None = None


@dataclass
class ValuationEvalReport:
    model_version: str
    dataset_version: str
    holdout_path: str
    evaluated_at: str
    total_rows: int
    evaluated_rows: int
    skipped_rows: int
    invalid_rows: int
    evaluation_coverage_pct: float
    mae: float | None
    rmse: float | None
    median_ae: float | None
    mape_pct: float | None
    mdape_pct: float | None
    by_municipality: dict[str, dict[str, float | int]]
    by_valuation_type: dict[str, dict[str, float | int]]
    by_confidence_tier: dict[str, dict[str, float | int]]
    confidence_monotonic: bool | None
    error_distribution: dict[str, int]
    row_results: list[dict[str, Any]] = field(default_factory=list)

    def metrics_dict(self) -> dict[str, float | None]:
        return {
            "mae": self.mae,
            "rmse": self.rmse,
            "median_ae": self.median_ae,
            "mape_pct": self.mape_pct,
            "mdape_pct": self.mdape_pct,
        }

    def as_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload.pop("row_results", None)
        return payload


def load_holdout_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8") as fh:
        return [row for row in csv.DictReader(fh) if (row.get("holdout_id") or "").strip()]


def _parse_float(value: str | None) -> float | None:
    if value is None or not str(value).strip():
        return None
    return float(value)


def _parse_int(value: str | None) -> int | None:
    if value is None or not str(value).strip():
        return None
    return int(float(value))


def _listing_key(row: dict[str, str]) -> tuple[str, str] | None:
    website = (row.get("source_website") or "").strip()
    listing_id = (row.get("source_listing_id") or "").strip()
    if website and listing_id:
        return website, listing_id
    return None


def validate_holdout_row(row: dict[str, str]) -> str | None:
    """Return a stable exclusion reason for invalid evaluation labels."""
    valuation_type = (row.get("valuation_type") or "").strip().lower()
    if valuation_type not in {"rent", "sale"}:
        return "valuation_type must be rent or sale"
    neighborhood = (row.get("neighborhood") or "").strip()
    area_sqm = _parse_float(row.get("area_sqm"))
    actual_price = _parse_float(row.get("actual_price_eur"))
    if not neighborhood or area_sqm is None or actual_price is None:
        return "missing neighborhood, area, or actual price"
    if not 15 <= area_sqm <= 500:
        return "area outside 15-500 m² plausibility range"
    if valuation_type == "rent" and not 50 <= actual_price <= 10_000:
        return "rent price outside €50-€10,000 plausibility range"
    if valuation_type == "sale" and not 5_000 <= actual_price <= 10_000_000:
        return "sale price outside €5,000-€10,000,000 plausibility range"
    return None


def _confidence_is_monotonic(
    metrics: dict[str, dict[str, float | int]],
) -> bool | None:
    ordered = []
    for tier in ("high", "medium", "low"):
        value = metrics.get(tier, {}).get("mape_pct")
        if isinstance(value, int | float):
            ordered.append((tier, float(value)))
    if len(ordered) < 2:
        return None
    return all(left[1] <= right[1] for left, right in zip(ordered, ordered[1:], strict=False))


def _error_distribution(pct_errors: list[float]) -> dict[str, int]:
    counts = {label: 0 for label, _, _ in ERROR_BUCKETS}
    for pct in pct_errors:
        for label, lo, hi in ERROR_BUCKETS:
            if lo <= pct < hi or (hi == math.inf and pct >= lo):
                counts[label] += 1
                break
    return counts


def _median(values: list[float]) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    mid = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[mid]
    return (ordered[mid - 1] + ordered[mid]) / 2


def _aggregate_metrics(
    results: list[ValuationEvalRowResult],
) -> tuple[float | None, float | None, float | None, float | None, float | None]:
    errors = [r.error_eur for r in results if r.error_eur is not None and not r.skipped]
    pct_errors = [r.abs_pct_error for r in results if r.abs_pct_error is not None and not r.skipped]
    if not errors:
        return None, None, None, None, None
    abs_errors = [abs(e) for e in errors]
    mae = sum(abs_errors) / len(abs_errors)
    rmse = math.sqrt(sum(e * e for e in errors) / len(errors))
    median_ae = _median(abs_errors)
    mape = sum(pct_errors) / len(pct_errors) if pct_errors else None
    mdape = _median(pct_errors)
    return mae, rmse, median_ae, mape, mdape


def _group_metrics(
    results: list[ValuationEvalRowResult],
    key_fn,
) -> dict[str, dict[str, float | int]]:
    groups: dict[str, list[ValuationEvalRowResult]] = {}
    for row in results:
        if row.skipped:
            continue
        key = key_fn(row)
        groups.setdefault(key, []).append(row)
    out: dict[str, dict[str, float | int]] = {}
    for key, rows in sorted(groups.items()):
        mae, rmse, median_ae, mape, mdape = _aggregate_metrics(rows)
        out[key] = {
            "n": len(rows),
            "mae": round(mae, 2) if mae is not None else None,
            "rmse": round(rmse, 2) if rmse is not None else None,
            "median_ae": round(median_ae, 2) if median_ae is not None else None,
            "mape_pct": round(mape, 2) if mape is not None else None,
            "mdape_pct": round(mdape, 2) if mdape is not None else None,
        }
    return out


def evaluate_holdout_rows(
    session: Session,
    rows: list[dict[str, str]],
    *,
    holdout_path: Path | str = DEFAULT_HOLDOUT,
    rent_df: pd.DataFrame | None = None,
    sale_df: pd.DataFrame | None = None,
) -> ValuationEvalReport:
    """Run holdout evaluation with optional leave-one-out exclusion."""
    if rent_df is None:
        rent_df = rent_comparables_dataframe(session)
    if sale_df is None:
        sale_df = sale_comparables_dataframe(session)

    row_results: list[ValuationEvalRowResult] = []
    invalid_rows = 0
    for row in rows:
        holdout_id = row["holdout_id"].strip()
        valuation_type = (row.get("valuation_type") or "rent").strip().lower()
        neighborhood = (row.get("neighborhood") or "").strip()
        municipality = (row.get("municipality") or "Prishtina").strip()
        area_sqm = _parse_float(row.get("area_sqm"))
        actual_price = _parse_float(row.get("actual_price_eur"))
        bedrooms = _parse_int(row.get("bedrooms"))

        validation_error = validate_holdout_row(row)
        if validation_error is not None:
            invalid_rows += 1
            row_results.append(
                ValuationEvalRowResult(
                    holdout_id=holdout_id,
                    valuation_type=valuation_type,
                    neighborhood=neighborhood,
                    municipality=municipality,
                    area_sqm=area_sqm or 0.0,
                    actual_price_eur=actual_price or 0.0,
                    predicted_price_eur=None,
                    error_eur=None,
                    abs_pct_error=None,
                    confidence_label=None,
                    comparable_count=None,
                    skipped=True,
                    skip_reason=f"invalid_holdout: {validation_error}",
                )
            )
            continue

        exclude: frozenset[tuple[str, str]] | None = None
        listing_key = _listing_key(row)
        if listing_key is not None:
            exclude = frozenset({listing_key})

        request = ValuationRequest(
            valuation_type="rent" if valuation_type == "rent" else "sale",
            neighborhood=neighborhood,
            area_sqm=area_sqm,
            bedrooms=bedrooms,
        )
        try:
            result = estimate_valuation(
                session,
                request,
                rent_comparables=rent_df,
                sale_comparables=sale_df,
                exclude_listing_keys=exclude,
            )
            predicted = result.point_estimate_eur
            if predicted is None:
                raise ValueError("no point estimate")
            error = float(predicted) - actual_price
            abs_pct = abs(error) / actual_price * 100 if actual_price else None
            row_results.append(
                ValuationEvalRowResult(
                    holdout_id=holdout_id,
                    valuation_type=valuation_type,
                    neighborhood=neighborhood,
                    municipality=municipality,
                    area_sqm=area_sqm,
                    actual_price_eur=actual_price,
                    predicted_price_eur=int(predicted),
                    error_eur=error,
                    abs_pct_error=abs_pct,
                    confidence_label=result.confidence_label,
                    comparable_count=result.comparable_count,
                    skipped=False,
                )
            )
        except Exception as exc:
            row_results.append(
                ValuationEvalRowResult(
                    holdout_id=holdout_id,
                    valuation_type=valuation_type,
                    neighborhood=neighborhood,
                    municipality=municipality,
                    area_sqm=area_sqm,
                    actual_price_eur=actual_price,
                    predicted_price_eur=None,
                    error_eur=None,
                    abs_pct_error=None,
                    confidence_label=None,
                    comparable_count=None,
                    skipped=True,
                    skip_reason=str(exc),
                )
            )

    evaluated = [r for r in row_results if not r.skipped]
    pct_errors = [r.abs_pct_error for r in evaluated if r.abs_pct_error is not None]
    mae, rmse, median_ae, mape, mdape = _aggregate_metrics(row_results)
    by_confidence_tier = _group_metrics(
        evaluated, lambda r: (r.confidence_label or "unknown").lower()
    )

    return ValuationEvalReport(
        model_version=MODEL_VERSION,
        dataset_version=frozen_dataset_version(),
        holdout_path=str(holdout_path),
        evaluated_at=datetime.now(UTC).isoformat(),
        total_rows=len(rows),
        evaluated_rows=len(evaluated),
        skipped_rows=len(row_results) - len(evaluated),
        invalid_rows=invalid_rows,
        evaluation_coverage_pct=round(
            (len(evaluated) / max(1, len(rows) - invalid_rows)) * 100,
            2,
        ),
        mae=round(mae, 2) if mae is not None else None,
        rmse=round(rmse, 2) if rmse is not None else None,
        median_ae=round(median_ae, 2) if median_ae is not None else None,
        mape_pct=round(mape, 2) if mape is not None else None,
        mdape_pct=round(mdape, 2) if mdape is not None else None,
        by_municipality=_group_metrics(evaluated, lambda r: r.municipality),
        by_valuation_type=_group_metrics(evaluated, lambda r: r.valuation_type),
        by_confidence_tier=by_confidence_tier,
        confidence_monotonic=_confidence_is_monotonic(by_confidence_tier),
        error_distribution=_error_distribution([p for p in pct_errors if p is not None]),
        row_results=[asdict(r) for r in row_results],
    )


def evaluate_holdout_file(
    session: Session,
    path: Path,
    *,
    rent_df: pd.DataFrame | None = None,
    sale_df: pd.DataFrame | None = None,
) -> ValuationEvalReport:
    rows = load_holdout_rows(path)
    return evaluate_holdout_rows(session, rows, holdout_path=path, rent_df=rent_df, sale_df=sale_df)


def write_eval_report(
    report: ValuationEvalReport,
    *,
    json_path: Path,
    markdown_path: Path | None = None,
    include_rows: bool = False,
) -> None:
    json_path.parent.mkdir(parents=True, exist_ok=True)
    payload = report.as_dict()
    if include_rows:
        payload["row_results"] = report.row_results
    json_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    if markdown_path is None:
        return

    markdown_path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Valuation evaluation report",
        "",
        f"- **Evaluated at:** {report.evaluated_at}",
        f"- **Model:** DM-002/DM-003 v{report.model_version}",
        f"- **Dataset:** {report.dataset_version}",
        f"- **Holdout:** `{report.holdout_path}`",
        f"- **Rows:** {report.evaluated_rows}/{report.total_rows} evaluated "
        f"({report.skipped_rows} skipped)",
        f"- **Valid-row coverage:** {report.evaluation_coverage_pct}%",
        f"- **Invalid holdout labels:** {report.invalid_rows}",
        f"- **Confidence monotonic:** {report.confidence_monotonic}",
        "",
        "## Overall metrics",
        "",
        "| Metric | Value |",
        "|--------|------:|",
        f"| MAE | {report.mae if report.mae is not None else '—'} |",
        f"| RMSE | {report.rmse if report.rmse is not None else '—'} |",
        f"| Median AE | {report.median_ae if report.median_ae is not None else '—'} |",
        f"| MAPE | {report.mape_pct if report.mape_pct is not None else '—'}% |",
        f"| MdAPE | {report.mdape_pct if report.mdape_pct is not None else '—'}% |",
        "",
    ]
    if report.by_confidence_tier:
        lines.extend(
            [
                "## Error by confidence tier",
                "",
                "| Tier | n | MAPE | MAE |",
                "|------|--:|-----:|----:|",
            ]
        )
        for tier, stats in report.by_confidence_tier.items():
            lines.append(
                f"| {tier} | {stats['n']} | {stats.get('mape_pct', '—')}% | {stats.get('mae', '—')} |"
            )
        lines.append("")
    if report.by_valuation_type:
        lines.extend(
            [
                "## Error by valuation type",
                "",
                "| Type | n | MAPE | MdAPE | MAE |",
                "|------|--:|-----:|------:|----:|",
            ]
        )
        for valuation_type, stats in report.by_valuation_type.items():
            lines.append(
                f"| {valuation_type} | {stats['n']} | "
                f"{stats.get('mape_pct', '—')}% | {stats.get('mdape_pct', '—')}% | "
                f"{stats.get('mae', '—')} |"
            )
        lines.append("")
    if report.by_municipality:
        lines.extend(
            [
                "## Error by municipality",
                "",
                "| Municipality | n | MAPE | MAE |",
                "|--------------|--:|-----:|----:|",
            ]
        )
        for muni, stats in report.by_municipality.items():
            lines.append(
                f"| {muni} | {stats['n']} | {stats.get('mape_pct', '—')}% | {stats.get('mae', '—')} |"
            )
        lines.append("")
    if report.error_distribution:
        lines.extend(["## Error distribution", ""])
        for bucket, count in report.error_distribution.items():
            lines.append(f"- {bucket}: {count}")
        lines.append("")
    markdown_path.write_text("\n".join(lines), encoding="utf-8")


@dataclass
class EvalComparison:
    passed: bool
    improvements: list[str]
    regressions: list[str]
    message: str


def compare_eval_reports(
    baseline: dict[str, Any],
    candidate: dict[str, Any],
    *,
    mape_tolerance_pct: float = 1.0,
    mae_tolerance_pct: float = 5.0,
) -> EvalComparison:
    """Release gate: improve at least one key metric without material regression."""
    key_metrics = ("mape_pct", "mae", "rmse", "median_ae")
    improvements: list[str] = []
    regressions: list[str] = []

    for metric in key_metrics:
        base = baseline.get(metric)
        cand = candidate.get(metric)
        if base is None or cand is None:
            continue
        if cand < base:
            improvements.append(f"{metric}: {base} → {cand}")
        elif cand > base:
            rel = (cand - base) / base * 100 if base else 0.0
            tol = mape_tolerance_pct if metric == "mape_pct" else mae_tolerance_pct
            if rel > tol:
                regressions.append(f"{metric}: {base} → {cand} (+{rel:.1f}%)")

    passed = bool(improvements) and not regressions
    if passed:
        msg = "Candidate improves metrics with no material regression."
    elif regressions:
        msg = "Candidate regresses: " + "; ".join(regressions)
    elif not improvements:
        msg = "Candidate does not improve any key metric."
    else:
        msg = "Comparison inconclusive."
    return EvalComparison(
        passed=passed, improvements=improvements, regressions=regressions, message=msg
    )


def _mdape_from_report(report: dict[str, Any], valuation_type: str | None = None) -> float | None:
    by_type = report.get("by_valuation_type") or {}
    if valuation_type:
        typed = by_type.get(valuation_type) or {}
        if typed.get("mdape_pct") is not None:
            return float(typed["mdape_pct"])
    elif report.get("mdape_pct") is not None:
        return float(report["mdape_pct"])

    rows = report.get("row_results") or []
    pct_errors = [
        float(row["abs_pct_error"])
        for row in rows
        if not row.get("skipped")
        and row.get("abs_pct_error") is not None
        and (valuation_type is None or row.get("valuation_type") == valuation_type)
    ]
    return _median(pct_errors)


def assess_release_readiness(
    report: dict[str, Any],
    *,
    max_rent_mdape_pct: float = 15.0,
    max_sale_mdape_pct: float = 30.0,
    min_evaluated_rows: int = 40,
    min_coverage_pct: float = 90.0,
    require_confidence_monotonic: bool = False,
) -> EvalComparison:
    """Fail closed unless absolute valuation quality gates are met.

    Gates use split rent/sale MdAPE rather than blended mean MAPE: mean MAPE is
    dominated by sale outliers and asking-price bargains, while MdAPE better
    matches what the neighborhood+area comparable model can defensibly claim.
    Confidence monotonicity is optional until confidence tiers are calibrated.
    """
    failures: list[str] = []
    evaluated = int(report.get("evaluated_rows") or 0)
    coverage = float(report.get("evaluation_coverage_pct") or 0)
    invalid = int(report.get("invalid_rows") or 0)
    monotonic = report.get("confidence_monotonic")
    by_type = report.get("by_valuation_type") or {}
    rent_mdape = _mdape_from_report(report, "rent")
    sale_mdape = _mdape_from_report(report, "sale") if "sale" in by_type or any(
        row.get("valuation_type") == "sale" for row in (report.get("row_results") or [])
    ) else None
    has_sale = sale_mdape is not None or "sale" in by_type

    if rent_mdape is None or float(rent_mdape) > max_rent_mdape_pct:
        failures.append(f"rent MdAPE must be <={max_rent_mdape_pct}% (actual: {rent_mdape})")
    if has_sale:
        if sale_mdape is None or float(sale_mdape) > max_sale_mdape_pct:
            failures.append(f"sale MdAPE must be <={max_sale_mdape_pct}% (actual: {sale_mdape})")
    if evaluated < min_evaluated_rows:
        failures.append(f"evaluated rows must be >={min_evaluated_rows} (actual: {evaluated})")
    if coverage < min_coverage_pct:
        failures.append(f"evaluation coverage must be >={min_coverage_pct}% (actual: {coverage}%)")
    if invalid:
        failures.append(f"holdout contains {invalid} invalid label(s)")
    if require_confidence_monotonic and monotonic is not True:
        failures.append("confidence-tier error is not proven monotonic")
    elif monotonic is False:
        failures.append("confidence-tier error is not monotonic")

    passed = not failures
    message = (
        "Valuation release gates passed."
        if passed
        else "Valuation release blocked: " + "; ".join(failures)
    )
    return EvalComparison(
        passed=passed,
        improvements=[],
        regressions=failures,
        message=message,
    )
