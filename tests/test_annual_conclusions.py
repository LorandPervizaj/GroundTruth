"""Tests for annual report conclusion rules."""

from datetime import date

import pandas as pd

from groundtruth.analytics.annual_conclusions import (
    AnnualConclusionContext,
    build_conclusions,
    build_coverage_narrative,
    build_executive_summary,
    build_insights,
)


def _ctx(**overrides) -> AnnualConclusionContext:
    months = [f"2025-{m:02d}" for m in range(1, 13)]
    volume_by_month = {m: {"rent": 10, "sale": 2} for m in months}
    for m in months[-3:]:
        volume_by_month[m] = {"rent": 20, "sale": 4}
    base = AnnualConclusionContext(
        total=500,
        rent_count=400,
        sale_count=100,
        rent_pct=80.0,
        median_sale_psm=1200.0,
        median_rent=350.0,
        cutoff_date=date(2025, 6, 1),
        coverage={
            "price_pct": 95.0,
            "area_pct": 90.0,
            "neighborhood_pct": 85.0,
            "bedrooms_pct": 80.0,
        },
        sources=[{"source_website": "merrjep", "listings": 300, "rent": 250, "sale": 50}],
        top_neighborhood="Ulpiana",
        top_neighborhood_count=80,
        volume_by_month=volume_by_month,
        sale_psm_by_month={m: 1000.0 + i * 10 for i, m in enumerate(months)},
        work=pd.DataFrame(
            [
                {
                    "neighborhood": "Ulpiana",
                    "listing_type": "sale",
                    "price_per_sqm": 1500.0,
                    "source_listing_id": "a",
                },
                {
                    "neighborhood": "Dardania",
                    "listing_type": "sale",
                    "price_per_sqm": 900.0,
                    "source_listing_id": "b",
                },
            ]
            + [
                {
                    "neighborhood": "Ulpiana",
                    "listing_type": "sale",
                    "price_per_sqm": 1400.0,
                    "source_listing_id": f"x{i}",
                }
                for i in range(20)
            ]
            + [
                {
                    "neighborhood": "Dardania",
                    "listing_type": "sale",
                    "price_per_sqm": 950.0,
                    "source_listing_id": f"y{i}",
                }
                for i in range(20)
            ]
        ),
    )
    return AnnualConclusionContext(**{**base.__dict__, **overrides})


def test_build_insights_bilingual_and_bounded() -> None:
    out = build_insights(_ctx())
    assert 1 <= len(out["sq"]) <= 4
    assert len(out["en"]) == len(out["sq"])
    assert any("qira" in line.lower() or "qiramarrës" in line.lower() for line in out["sq"])
    assert any("rent" in line.lower() or "tenant" in line.lower() for line in out["en"])
    assert not any("korpusi aktiv" in line.lower() for line in out["sq"])


def test_build_conclusions_alias() -> None:
    assert build_conclusions(_ctx()) == build_insights(_ctx())


def test_build_conclusions_empty() -> None:
    out = build_conclusions(
        _ctx(total=0, rent_count=0, sale_count=0, rent_pct=0.0, work=pd.DataFrame())
    )
    assert out["sq"][0].startswith("Nuk ka")


def test_executive_summary_mentions_asking_prices() -> None:
    summary = build_executive_summary(_ctx())
    assert "kërkuese" in summary["sq"].lower() or "portalet" in summary["sq"].lower()
    assert "asking" in summary["en"].lower()


def test_coverage_narrative_plain_language() -> None:
    cov = build_coverage_narrative(_ctx())
    assert "95%" in cov["items"]["sq"][0]
    assert "Price is reported" in cov["items"]["en"][0]


def test_chart_narrative_flags_price_trough() -> None:
    from groundtruth.analytics.annual_conclusions import build_chart_narratives

    months = [f"2025-{m:02d}" for m in range(1, 13)]
    sale_psm = {m: 1200.0 for m in months}
    sale_psm["2025-12"] = 470.0
    ctx = _ctx(sale_psm_by_month=sale_psm)
    chart = build_chart_narratives(ctx, peak_price_month="2025-10")
    assert "2025-12" in chart["en"]["price_insight"]
    assert "artifact" in chart["en"]["price_insight"].lower()
