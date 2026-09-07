"""Business coverage KPIs — municipality, neighborhood depth, freshness, duplicates."""

from __future__ import annotations

import json
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

import pandas as pd
from sqlalchemy import text
from sqlalchemy.orm import Session

from groundtruth.analytics.corpus import active_corpus_bundle
from groundtruth.analytics.coverage import build_neighborhood_coverage_table
from groundtruth.analytics.cross_dedup import cross_dedup_stats
from groundtruth.analytics.valuation import MIN_COMPARABLES, _confidence_label
from groundtruth.config import PROJECT_ROOT
from groundtruth.models.reference import Neighborhood
from groundtruth.schemas.coverage_analytics import (
    ConfidenceCoverage,
    CoverageAnalyticsSnapshot,
    CoverageOpportunityRow,
    HoldoutEvalSummary,
    MunicipalityCoverageRow,
)

URBAN_DEMAND_WEIGHTS = PROJECT_ROOT / "data" / "reference" / "urban_demand_weights.json"
DEFAULT_HOLDOUT_BASELINE = PROJECT_ROOT / "results" / "baseline.json"
DEFAULT_FRESHNESS_DAYS = 14
HIGH_CONFIDENCE_MIN_COMPS = 80


def load_urban_demand_weights(path: Path | None = None) -> dict[str, float]:
    weights_path = path or URBAN_DEMAND_WEIGHTS
    if not weights_path.is_file():
        return {"Prishtina": 1.0}
    payload = json.loads(weights_path.read_text(encoding="utf-8"))
    raw = payload.get("municipalities") or payload
    weights = {str(k): float(v) for k, v in raw.items() if float(v) > 0}
    total = sum(weights.values())
    if total <= 0:
        return {"Prishtina": 1.0}
    return {k: v / total for k, v in weights.items()}


def load_municipality_population(path: Path | None = None) -> dict[str, int]:
    weights_path = path or URBAN_DEMAND_WEIGHTS
    if not weights_path.is_file():
        return {}
    payload = json.loads(weights_path.read_text(encoding="utf-8"))
    raw = payload.get("population") or {}
    return {str(k): int(v) for k, v in raw.items() if int(v) > 0}


def _projected_confidence_coverage(nh_table: pd.DataFrame) -> ConfidenceCoverage:
    """Rent-comp tier projection across gazetteer neighborhoods."""
    total = len(nh_table) if not nh_table.empty else 0
    if total == 0:
        return ConfidenceCoverage(
            high_pct=0.0,
            medium_pct=0.0,
            insufficient_pct=100.0,
            high_count=0,
            medium_count=0,
            insufficient_count=0,
            neighborhoods_total=0,
        )

    high = medium = insufficient = 0
    for _, row in nh_table.iterrows():
        n = int(row.get("rent_comps") or 0)
        if n < MIN_COMPARABLES:
            insufficient += 1
        elif _confidence_label(n, 0.35) == "High":
            high += 1
        else:
            medium += 1

    return ConfidenceCoverage(
        high_pct=round(100.0 * high / total, 1),
        medium_pct=round(100.0 * medium / total, 1),
        insufficient_pct=round(100.0 * insufficient / total, 1),
        high_count=high,
        medium_count=medium,
        insufficient_count=insufficient,
        neighborhoods_total=total,
    )


def _coverage_opportunity_backlog(
    municipality_rows: list[MunicipalityCoverageRow],
    population: dict[str, int],
) -> list[CoverageOpportunityRow]:
    """Rank municipalities: demand_weight × coverage_gap × population."""
    scored: list[tuple[float, MunicipalityCoverageRow, float, int]] = []
    for row in municipality_rows:
        pop = population.get(row.municipality, 30_000)
        if row.neighborhoods_total > 0:
            ready_ratio = row.neighborhoods_estimate_ready / row.neighborhoods_total
            gap = 1.0 - ready_ratio
        else:
            gap = 1.0 if not row.covered else 0.0
        demand = row.demand_weight_pct / 100.0
        score = demand * gap * (pop / 100_000.0)
        scored.append((score, row, gap, pop))

    scored.sort(key=lambda x: -x[0])
    backlog: list[CoverageOpportunityRow] = []
    for rank, (score, row, gap, pop) in enumerate(scored, start=1):
        backlog.append(
            CoverageOpportunityRow(
                rank=rank,
                municipality=row.municipality,
                opportunity_score=round(score, 3),
                demand_weight_pct=row.demand_weight_pct,
                coverage_gap_pct=round(gap * 100, 1),
                population=pop,
                covered=row.covered,
                neighborhoods_estimate_ready=row.neighborhoods_estimate_ready,
                neighborhoods_total=row.neighborhoods_total,
            )
        )
    return backlog


def _load_holdout_eval_summary(path: Path | None = None) -> HoldoutEvalSummary | None:
    baseline_path = path or DEFAULT_HOLDOUT_BASELINE
    if not baseline_path.is_file():
        return None
    try:
        payload = json.loads(baseline_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    total = int(payload.get("total_rows") or 0)
    evaluated = int(payload.get("evaluated_rows") or 0)
    if total <= 0:
        return None
    skipped = int(payload.get("skipped_rows") or (total - evaluated))
    return HoldoutEvalSummary(
        holdout_path=str(payload.get("holdout_path") or "data/evaluation/valuation_holdout_v2.csv"),
        evaluated_rows=evaluated,
        total_rows=total,
        evaluation_rate_pct=round(100.0 * evaluated / total, 1),
        skipped_rows=skipped,
        mape_pct=payload.get("mape_pct"),
        evaluated_at=payload.get("evaluated_at"),
    )


def _municipality_coverage(
    nh_table: pd.DataFrame,
    city_by_nh_id: dict[int, str],
    weights: dict[str, float],
) -> tuple[float | None, list[MunicipalityCoverageRow]]:
    if nh_table.empty:
        return None, []

    table = nh_table.copy()
    table["municipality"] = table["neighborhood_id"].map(city_by_nh_id).fillna("Unknown")

    city_stats: dict[str, dict[str, Any]] = {}
    for municipality, group in table.groupby("municipality"):
        ready_mask = group["rent_estimate_ready"] | group["sale_estimate_ready"]
        city_stats[str(municipality)] = {
            "neighborhoods_total": len(group),
            "neighborhoods_estimate_ready": int(ready_mask.sum()),
            "covered": bool(ready_mask.any()),
        }

    rows: list[MunicipalityCoverageRow] = []
    weighted_covered = 0.0
    total_weight = 0.0
    for municipality, weight in sorted(weights.items(), key=lambda x: -x[1]):
        stats = city_stats.get(
            municipality,
            {"neighborhoods_total": 0, "neighborhoods_estimate_ready": 0, "covered": False},
        )
        covered = bool(stats["covered"])
        rows.append(
            MunicipalityCoverageRow(
                municipality=municipality,
                demand_weight_pct=round(weight * 100, 1),
                covered=covered,
                neighborhoods_total=int(stats["neighborhoods_total"]),
                neighborhoods_estimate_ready=int(stats["neighborhoods_estimate_ready"]),
            )
        )
        total_weight += weight
        if covered:
            weighted_covered += weight

    pct = round(100.0 * weighted_covered / total_weight, 1) if total_weight else None
    return pct, rows


def _listing_freshness_pct(
    session: Session,
    active: pd.DataFrame,
    *,
    freshness_days: int,
) -> tuple[float | None, float | None, int]:
    """Share of active canonical listings seen within freshness_days."""
    if active.empty:
        return None, None, 0

    cutoff = date.today() - timedelta(days=freshness_days)
    keys = list(
        zip(
            active["source_website"].astype(str),
            active["source_listing_id"].astype(str),
            strict=False,
        )
    )
    # Chunked lifecycle lookup — reuse observation table directly for scale
    fresh = 0
    total = len(keys)
    chunk = 500
    for start in range(0, total, chunk):
        batch = keys[start : start + chunk]
        values = ", ".join(f"(:sw{i}, :id{i})" for i in range(len(batch)))
        params: dict[str, Any] = {"cutoff": cutoff}
        for i, (website, listing_id) in enumerate(batch):
            params[f"sw{i}"] = website
            params[f"id{i}"] = listing_id
        sql = text(
            f"""
            SELECT COUNT(*) AS fresh_count
            FROM (
                SELECT k.source_website, k.source_listing_id,
                       MAX(lo.observed_date) AS last_seen
                FROM (VALUES {values}) AS k(source_website, source_listing_id)
                LEFT JOIN listing_observations lo
                  ON lo.source_website = k.source_website
                 AND lo.source_listing_id = k.source_listing_id
                GROUP BY k.source_website, k.source_listing_id
            ) x
            WHERE x.last_seen IS NOT NULL AND x.last_seen >= :cutoff
            """
        )
        fresh += int(session.execute(sql, params).scalar() or 0)

    fresh_pct = round(100.0 * fresh / total, 1) if total else None
    stale_pct = round(100.0 - fresh_pct, 1) if fresh_pct is not None else None
    return fresh_pct, stale_pct, total


def build_coverage_snapshot(
    session: Session,
    *,
    freshness_days: int = DEFAULT_FRESHNESS_DAYS,
    weights_path: Path | None = None,
) -> CoverageAnalyticsSnapshot:
    nh_table = build_neighborhood_coverage_table(session)
    neighborhoods = session.query(Neighborhood).all()
    city_by_nh_id = {nh.id: nh.city for nh in neighborhoods}

    ready_mask = nh_table["rent_estimate_ready"] | nh_table["sale_estimate_ready"]
    nh_with_min = int(ready_mask.sum()) if not nh_table.empty else 0
    nh_total = len(nh_table)

    weights = load_urban_demand_weights(weights_path)
    population = load_municipality_population(weights_path)
    municipality_pct, municipality_rows = _municipality_coverage(nh_table, city_by_nh_id, weights)
    opportunity_backlog = _coverage_opportunity_backlog(municipality_rows, population)
    confidence_coverage = _projected_confidence_coverage(nh_table)
    holdout_eval = _load_holdout_eval_summary()
    municipalities_covered = sum(1 for row in municipality_rows if row.covered)

    bundle = active_corpus_bundle(session)
    dedup_stats = cross_dedup_stats(bundle.deduped)
    dup_rate = (
        round(100.0 * dedup_stats.duplicates_removed / dedup_stats.raw_listings, 1)
        if dedup_stats.raw_listings
        else None
    )

    fresh_pct, stale_pct, active_n = _listing_freshness_pct(
        session, bundle.active, freshness_days=freshness_days
    )

    corpus_updated_at: str | None = None
    try:
        from groundtruth.analytics.annual_export import corpus_last_updated

        rev = corpus_last_updated(session)
        if rev is not None:
            corpus_updated_at = rev.isoformat()
    except Exception:
        pass

    return CoverageAnalyticsSnapshot(
        evaluated_at=datetime.now(UTC).isoformat(),
        freshness_window_days=freshness_days,
        min_comparables=MIN_COMPARABLES,
        municipality_coverage_pct=municipality_pct,
        municipalities_covered=municipalities_covered,
        municipalities_tracked=len(municipality_rows),
        municipality_rows=municipality_rows,
        opportunity_backlog=opportunity_backlog,
        neighborhoods_total=nh_total,
        neighborhoods_with_min_comparables=nh_with_min,
        neighborhoods_with_min_comparables_pct=round(100.0 * nh_with_min / nh_total, 1)
        if nh_total
        else None,
        neighborhoods_rent_ready=int(nh_table["rent_estimate_ready"].sum())
        if not nh_table.empty
        else 0,
        neighborhoods_sale_ready=int(nh_table["sale_estimate_ready"].sum())
        if not nh_table.empty
        else 0,
        confidence_coverage=confidence_coverage,
        listings_active=active_n,
        listings_fresh_pct=fresh_pct,
        listings_stale_pct=stale_pct,
        duplicate_rate_pct=dup_rate,
        raw_listings=dedup_stats.raw_listings,
        canonical_listings=dedup_stats.canonical_listings,
        duplicates_removed=dedup_stats.duplicates_removed,
        holdout_eval=holdout_eval,
        corpus_updated_at=corpus_updated_at,
    )


def coverage_analytics_snapshot(
    session: Session,
    *,
    freshness_days: int = DEFAULT_FRESHNESS_DAYS,
) -> CoverageAnalyticsSnapshot:
    return build_coverage_snapshot(session, freshness_days=freshness_days)
