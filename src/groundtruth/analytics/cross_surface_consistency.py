"""Assertions that public surfaces expose the same canonical lookup metrics."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from groundtruth.schemas.lookup import MarketLookup, NeighborhoodMarketSummary


def consistency_issues(
    lookups: Iterable[MarketLookup],
    markets: Iterable[NeighborhoodMarketSummary],
    yield_rows: Iterable[dict[str, Any]],
) -> list[str]:
    """Return deterministic parity violations keyed by canonical neighborhood slug."""
    by_slug = {item.slug: item for item in lookups if item.entity_type == "neighborhood"}
    issues: list[str] = []
    for summary in markets:
        lookup = by_slug.get(summary.slug)
        if lookup is None:
            issues.append(f"markets:{summary.slug}:missing_lookup")
            continue
        pulse = lookup.pulse
        if summary.rent_listings != pulse.median_rent_sample.n:
            issues.append(f"markets:{summary.slug}:rent_sample")
        if summary.sale_listings != pulse.median_sale_sample.n:
            issues.append(f"markets:{summary.slug}:sale_sample")
        if summary.median_rent_eur != pulse.median_rent_eur:
            issues.append(f"markets:{summary.slug}:median_rent")
        if summary.median_rent_psm_eur != pulse.median_rent_psm_eur:
            issues.append(f"markets:{summary.slug}:median_rent_psm")

    for row in yield_rows:
        slug = str(row.get("slug") or "")
        lookup = by_slug.get(slug)
        if lookup is None:
            issues.append(f"yield:{slug}:missing_lookup")
            continue
        pulse = lookup.pulse
        expected = {
            "median_rent_eur": pulse.median_rent_eur,
            "median_sale_eur": pulse.median_sale_eur,
            "median_rent_psm": pulse.median_rent_psm_eur,
            "median_sale_psm": pulse.median_sale_psm_eur,
        }
        for key, value in expected.items():
            actual = row.get(key)
            if actual is not None and value is not None and float(actual) != float(value):
                issues.append(f"yield:{slug}:{key}")
    return sorted(issues)


def assert_consistent_surfaces(
    lookups: Iterable[MarketLookup],
    markets: Iterable[NeighborhoodMarketSummary],
    yield_rows: Iterable[dict[str, Any]],
) -> None:
    issues = consistency_issues(lookups, markets, yield_rows)
    if issues:
        raise ValueError("Cross-surface metric drift: " + ", ".join(issues))
