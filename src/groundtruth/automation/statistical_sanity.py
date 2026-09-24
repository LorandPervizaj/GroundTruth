"""Release-to-release statistical sanity checks with shadow-mode support."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Literal

from groundtruth.config import PROJECT_ROOT

SanityLevel = Literal["GREEN", "YELLOW", "RED"]


@dataclass(frozen=True)
class StatisticalThreshold:
    warning_delta_pct: float = 20.0
    red_delta_pct: float = 45.0
    minimum_sample: int = 100
    coverage_warning_points: float = 8.0
    coverage_red_points: float = 20.0


@dataclass
class StatisticalIssue:
    level: SanityLevel
    metric: str
    message: str
    current: float | int | None
    previous: float | int | None
    delta_pct: float | None = None
    sample_n: int | None = None


@dataclass
class StatisticalSanityResult:
    level: SanityLevel
    shadow_mode: bool
    snapshot: dict[str, Any]
    issues: list[StatisticalIssue] = field(default_factory=list)
    baseline_available: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "level": self.level,
            "shadow_mode": self.shadow_mode,
            "snapshot": self.snapshot,
            "issues": [asdict(issue) for issue in self.issues],
            "baseline_available": self.baseline_available,
        }


def build_statistical_snapshot(
    annual_path: Path | None = None,
    comparables_path: Path | None = None,
    rent_yield_path: Path | None = None,
) -> dict[str, Any]:
    annual = json.loads(
        (annual_path or PROJECT_ROOT / "data" / "api" / "annual_report.json").read_text(
            encoding="utf-8"
        )
    )
    comparables = json.loads(
        (
            comparables_path
            or PROJECT_ROOT / "reports" / "generated" / "lookup_cache" / "comparables_meta.json"
        ).read_text(encoding="utf-8")
    )
    yield_payload = json.loads(
        (rent_yield_path or PROJECT_ROOT / "data" / "api" / "rent_yield.json").read_text(
            encoding="utf-8"
        )
    )
    kpis = annual.get("kpis") or {}
    coverage = annual.get("coverage") or {}
    segments = annual.get("apartment_segments") or {}
    yields = [float(row["gross_yield_pct"]) for row in yield_payload.get("rows") or []]
    return {
        "data_revision": annual.get("data_revision"),
        "total_listings": int(kpis.get("total_listings") or annual.get("total_listings") or 0),
        "rent_count": int(kpis.get("rent_count") or 0),
        "sale_count": int(kpis.get("sale_count") or 0),
        "median_sale_price_per_sqm": kpis.get("median_sale_price_per_sqm"),
        "median_sale_sample_n": int((kpis.get("median_sale_sample") or {}).get("n") or 0),
        "median_rent": kpis.get("median_rent"),
        "median_rent_sample_n": int((kpis.get("median_rent_sample") or {}).get("n") or 0),
        "rent_comparables": int(comparables.get("rent_rows") or 0),
        "sale_comparables": int(comparables.get("sale_rows") or 0),
        "rent_yield_ready_neighborhoods": len(yields),
        "median_gross_yield_pct": sorted(yields)[len(yields) // 2] if yields else None,
        "coverage": {key: coverage.get(key) for key in sorted(coverage)},
        "bedroom_distribution": {
            str(row.get("segment")): int(row.get("listings") or 0)
            for row in segments.get("by_bedrooms") or []
        },
        "property_size_distribution": {
            str(row.get("segment")): int(row.get("listings") or 0)
            for row in segments.get("by_size_band") or []
        },
    }


def evaluate_statistical_sanity(
    current: dict[str, Any],
    previous: dict[str, Any] | None,
    *,
    shadow_mode: bool = True,
    threshold: StatisticalThreshold | None = None,
) -> StatisticalSanityResult:
    policy = threshold or StatisticalThreshold()
    if not previous:
        return StatisticalSanityResult(
            level="GREEN", shadow_mode=shadow_mode, snapshot=current, baseline_available=False
        )
    issues: list[StatisticalIssue] = []
    samples = {
        "median_sale_price_per_sqm": int(current.get("median_sale_sample_n") or 0),
        "median_rent": int(current.get("median_rent_sample_n") or 0),
    }
    metrics = (
        "total_listings",
        "rent_count",
        "sale_count",
        "median_sale_price_per_sqm",
        "median_rent",
        "rent_comparables",
        "sale_comparables",
        "rent_yield_ready_neighborhoods",
        "median_gross_yield_pct",
    )
    for metric in metrics:
        now = current.get(metric)
        before = previous.get(metric)
        if now is None or before in (None, 0):
            continue
        sample_n = samples.get(metric, int(current.get("total_listings") or 0))
        delta = 100.0 * (float(now) - float(before)) / abs(float(before))
        red_limit = policy.red_delta_pct
        warning_limit = policy.warning_delta_pct
        if sample_n < policy.minimum_sample:
            red_limit *= 1.5
            warning_limit *= 1.5
        level: SanityLevel | None = None
        if abs(delta) >= red_limit:
            level = "RED"
        elif abs(delta) >= warning_limit:
            level = "YELLOW"
        if level:
            issues.append(
                StatisticalIssue(
                    level=level,
                    metric=metric,
                    message="release-to-release movement exceeds the sample-aware threshold",
                    current=now,
                    previous=before,
                    delta_pct=round(delta, 2),
                    sample_n=sample_n,
                )
            )
    for metric, now in (current.get("coverage") or {}).items():
        before = (previous.get("coverage") or {}).get(metric)
        if now is None or before is None:
            continue
        drop = float(before) - float(now)
        if drop >= policy.coverage_red_points:
            level = "RED"
        elif drop >= policy.coverage_warning_points:
            level = "YELLOW"
        else:
            continue
        issues.append(
            StatisticalIssue(
                level=level,
                metric=f"coverage.{metric}",
                message="field coverage declined",
                current=now,
                previous=before,
                delta_pct=round(-drop, 2),
            )
        )
    level: SanityLevel = (
        "RED" if any(issue.level == "RED" for issue in issues) else "YELLOW" if issues else "GREEN"
    )
    return StatisticalSanityResult(
        level=level,
        shadow_mode=shadow_mode,
        snapshot=current,
        issues=issues,
        baseline_available=True,
    )
