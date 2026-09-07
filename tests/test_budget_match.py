"""Tests for budget-based neighborhood matching."""

from datetime import date

import pandas as pd

from groundtruth.schemas.budget_match import BudgetMatchRequest
from groundtruth.services.budget_match import (
    estimate_apartment_price,
    match_neighborhoods_from_dataframe,
    resolve_target_sqm,
)


def _rent_row(
    nh: str,
    rent: float,
    area: float,
    beds: int,
    listing_id: str,
) -> dict:
    return {
        "source_website": "gjirafa",
        "source_listing_id": listing_id,
        "listing_type": "rent",
        "property_type": "APARTMENT",
        "sale_price": None,
        "rent_price": rent,
        "price_per_sqm": None,
        "area_sqm": area,
        "bedrooms": beds,
        "neighborhood": nh,
        "listing_date": date(2025, 8, 1),
        "listing_price": rent,
    }


def _sale_row(
    nh: str,
    sale: float,
    area: float,
    beds: int,
    listing_id: str,
) -> dict:
    return {
        "source_website": "merrjep",
        "source_listing_id": listing_id,
        "listing_type": "sale",
        "property_type": "APARTMENT",
        "sale_price": sale,
        "rent_price": None,
        "price_per_sqm": sale / area,
        "area_sqm": area,
        "bedrooms": beds,
        "neighborhood": nh,
        "listing_date": date(2025, 8, 1),
        "listing_price": sale,
    }


def test_resolve_target_sqm_respects_bedroom_floor() -> None:
    request = BudgetMatchRequest(
        max_budget_eur=100_000, bedrooms=2, min_area_sqm=50, max_area_sqm=90
    )
    assert resolve_target_sqm(request) == 70.0


def test_estimate_apartment_price_scales_by_target_size() -> None:
    est, psm = estimate_apartment_price(
        median_price=105_000,
        median_area=50,
        median_psm=2_100,
        target_sqm=70,
    )
    assert psm == 2_100
    assert est == 147_000


def test_match_neighborhoods_rent_filters_and_ranks() -> None:
    df = pd.DataFrame(
        [_rent_row("Ulpiana", 400, 60, 2, f"u-{i}") for i in range(3)]
        + [_rent_row("Ulpiana", 550, 65, 2, "u-over")]
        + [_rent_row("Dardania", 350, 70, 2, f"d-{i}") for i in range(4)]
        + [_rent_row("Arbëria", 800, 80, 2, "a-1")]
        + [_rent_row("Arbëria", 850, 85, 2, "a-2")]
        + [_rent_row("Arbëria", 900, 90, 2, "a-3")]
    )
    slug_by_name = {"Ulpiana": "ulpiana", "Dardania": "dardania", "Arbëria": "arberia"}
    request = BudgetMatchRequest(
        listing_type="rent",
        max_budget_eur=500,
        min_area_sqm=55,
        max_area_sqm=80,
        bedrooms=2,
        top_n=5,
    )

    results = match_neighborhoods_from_dataframe(df, request, slug_by_name=slug_by_name)

    names = [r.name for r in results]
    assert "Dardania" in names
    assert "Ulpiana" in names
    assert "Arbëria" not in names
    assert all(r.match_count >= 3 for r in results)
    assert results[0].fit_score >= results[-1].fit_score
    assert results[0].rank == 1
    assert results[0].estimated_target_sqm == 67.5 or results[0].estimated_target_sqm == 68.0


def test_sale_excludes_neighborhood_when_scaled_price_exceeds_budget() -> None:
    """Small median apartments can be in budget while a realistic 2BR size is not."""
    df = pd.DataFrame(
        [_sale_row("Ulpiana", 105_000, 50, 2, f"u-{i}") for i in range(4)]
        + [_sale_row("Sofalia", 86_000, 100, 2, f"s-{i}") for i in range(4)]
    )
    request = BudgetMatchRequest(
        listing_type="sale",
        max_budget_eur=109_990,
        min_area_sqm=50,
        max_area_sqm=90,
        bedrooms=2,
        top_n=5,
    )

    results = match_neighborhoods_from_dataframe(
        df,
        request,
        slug_by_name={"Ulpiana": "ulpiana", "Sofalia": "sofalia"},
    )

    names = [r.name for r in results]
    assert "Sofalia" in names
    assert "Ulpiana" not in names
    assert results[0].name == "Sofalia"
    assert results[0].estimated_price_eur is not None
    assert results[0].estimated_price_eur <= 109_990


def test_match_neighborhoods_sale_includes_yield() -> None:
    rows = [_sale_row("Ulpiana", 90_000, 90, 2, f"s-{i}") for i in range(3)]
    rows += [_rent_row("Ulpiana", 400, 60, 2, f"r-{i}") for i in range(3)]
    df = pd.DataFrame(rows)
    request = BudgetMatchRequest(
        listing_type="sale",
        max_budget_eur=100_000,
        bedrooms=2,
        top_n=3,
    )

    results = match_neighborhoods_from_dataframe(
        df,
        request,
        slug_by_name={"Ulpiana": "ulpiana"},
    )

    assert len(results) == 1
    assert results[0].gross_yield_pct is not None
    assert results[0].gross_yield_pct > 0


def test_match_filters_by_max_price_psm() -> None:
    df = pd.DataFrame(
        [_sale_row("Ulpiana", 100_000, 70, 2, f"u-{i}") for i in range(4)]
        + [_sale_row("Sofalia", 70_000, 70, 2, f"s-{i}") for i in range(4)]
    )
    request = BudgetMatchRequest(
        listing_type="sale",
        max_budget_eur=120_000,
        bedrooms=2,
        max_price_psm_eur=1_200,
        top_n=5,
    )
    results = match_neighborhoods_from_dataframe(
        df,
        request,
        slug_by_name={"Ulpiana": "ulpiana", "Sofalia": "sofalia"},
    )
    names = [r.name for r in results]
    assert "Sofalia" in names
    assert "Ulpiana" not in names


def test_match_neighborhoods_empty_when_no_slug() -> None:
    df = pd.DataFrame([_rent_row("Ulpiana", 400, 60, 2, "u-1")] * 3)
    request = BudgetMatchRequest(listing_type="rent", max_budget_eur=500)

    assert match_neighborhoods_from_dataframe(df, request, slug_by_name={}) == []
