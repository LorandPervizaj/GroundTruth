"""Tests for annual market report payload."""

from datetime import date

import pandas as pd

from groundtruth.analytics.annual_report import build_annual_report_from_dataframe


def _sample_df() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "source_website": "gjirafa",
                "source_listing_id": "a-1",
                "listing_type": "rent",
                "property_type": "APARTMENT",
                "sale_price": None,
                "rent_price": 400.0,
                "price_per_sqm": None,
                "area_sqm": 60.0,
                "bedrooms": 2,
                "neighborhood_id": 1,
                "neighborhood": "Ulpiana",
                "listing_date": date(2025, 8, 1),
                "listing_price": 400.0,
            },
            {
                "source_website": "gjirafa",
                "source_listing_id": "a-2",
                "listing_type": "rent",
                "property_type": "APARTMENT",
                "sale_price": None,
                "rent_price": 500.0,
                "price_per_sqm": None,
                "area_sqm": 70.0,
                "bedrooms": 2,
                "neighborhood_id": 1,
                "neighborhood": "Ulpiana",
                "listing_date": date(2025, 9, 1),
                "listing_price": 500.0,
            },
            {
                "source_website": "merrjep",
                "source_listing_id": "b-1",
                "listing_type": "sale",
                "property_type": "APARTMENT",
                "sale_price": 120_000.0,
                "rent_price": None,
                "price_per_sqm": 1000.0,
                "area_sqm": 120.0,
                "bedrooms": 3,
                "neighborhood_id": 2,
                "neighborhood": "Dardania",
                "listing_date": date(2025, 8, 15),
                "listing_price": 120_000.0,
            },
            {
                "source_website": "merrjep",
                "source_listing_id": "b-2",
                "listing_type": "sale",
                "property_type": "APARTMENT",
                "sale_price": 80_000.0,
                "rent_price": None,
                "price_per_sqm": 800.0,
                "area_sqm": 100.0,
                "bedrooms": 2,
                "neighborhood_id": 2,
                "neighborhood": "Dardania",
                "listing_date": date(2025, 9, 15),
                "listing_price": 80_000.0,
            },
        ]
    )


def test_build_annual_report_deduped_counts_and_medians() -> None:
    payload = build_annual_report_from_dataframe(_sample_df(), cutoff_date=date(2025, 6, 1))

    assert payload["total_listings"] == 4
    assert payload["kpis"]["rent_count"] == 2
    assert payload["kpis"]["sale_count"] == 2
    assert payload["kpis"]["rent_pct"] == 50.0
    assert payload["kpis"]["median_rent"] == 450.0
    assert payload["kpis"]["median_sale_price_per_sqm"] == 900.0
    assert payload["kpis"]["total_sample"]["n"] == 4
    assert payload["kpis"]["sale_sample"]["confidence"] == "insufficient"
    assert payload["kpis"]["median_rent_sample"]["n"] == 2

    assert payload["prices"]["metric"] == "median"
    assert payload["prices"]["counts"] == [1, 1]
    assert payload["prices"]["labels"] == ["2025-08", "2025-09"]
    assert payload["prices"]["values"] == [1000.0, 800.0]

    assert payload["volume"]["labels"] == ["2025-08", "2025-09"]
    assert payload["volume"]["rent"] == [1, 1]
    assert payload["volume"]["sale"] == [1, 1]

    assert payload["methodology"]["date_field"] == "listing_date"
    assert payload["methodology"]["deduped"] is True
    assert isinstance(payload["sources"], list)
    assert payload["neighborhood_table"]
    assert payload["neighborhood_highlights"] == payload["neighborhood_table"][:5]
    assert "price_percentiles" in payload
    assert "sale_price_distribution" in payload
    assert payload["price_percentiles"] is not None
    assert payload["price_percentiles"]["p50_sale_psm"] == 900
    assert payload["price_percentiles"]["n"] == 2
    assert payload["sale_price_distribution"]["listing_type"] == "sale"
    slug_payload = build_annual_report_from_dataframe(
        _sample_df(),
        cutoff_date=date(2025, 6, 1),
        neighborhood_slug_by_name={"Ulpiana": "ulpiana", "Dardania": "dardania"},
    )
    by_name = {r["neighborhood"]: r["slug"] for r in slug_payload["neighborhood_table"]}
    assert by_name["Ulpiana"] == "ulpiana"
    assert by_name["Dardania"] == "dardania"
    rankings = slug_payload["neighborhood_rankings"]
    assert rankings["min_sale_listings"] == 15
    assert "expensive" in rankings
    assert "affordable" in rankings
    assert "conclusions" in payload
    assert len(payload["conclusions"]["sq"]) == len(payload["conclusions"]["en"])
    assert payload["conclusions"]["sq"]
    assert payload["formulas"]
    assert any(f["id"] == "median_sale_psm" for f in payload["formulas"])
    assert "market_insights" in payload
    assert payload["market_insights"]["property_types"]["city"]["top_type"] == "APARTMENT"


def test_build_annual_report_empty() -> None:
    payload = build_annual_report_from_dataframe(pd.DataFrame(), cutoff_date=date(2025, 6, 1))
    assert payload["total_listings"] == 0
    assert payload["volume"]["labels"] == []


def test_apartment_segments_exclude_rent_psm_and_cap_bedrooms() -> None:
    """Sale €/m² must not mix rent price_per_sqm; bedrooms cap at 4+ and drop negatives."""
    df = pd.DataFrame(
        [
            # Rent listings with ~€5–7/m² — must not drag sale median to €10
            {
                "source_website": "gjirafa",
                "source_listing_id": f"r-{i}",
                "listing_type": "rent",
                "property_type": "APARTMENT",
                "sale_price": None,
                "rent_price": 400.0,
                "price_per_sqm": 6.0,
                "area_sqm": 65.0,
                "bedrooms": 2,
                "neighborhood_id": 1,
                "neighborhood": "Pejton",
                "listing_date": date(2025, 8, 1),
                "listing_price": 400.0,
            }
            for i in range(10)
        ]
        + [
            {
                "source_website": "merrjep",
                "source_listing_id": f"s-{i}",
                "listing_type": "sale",
                "property_type": "APARTMENT",
                "sale_price": 120_000.0,
                "rent_price": None,
                "price_per_sqm": 1500.0,
                "area_sqm": 80.0,
                "bedrooms": beds,
                "neighborhood_id": 1,
                "neighborhood": "Pejton",
                "listing_date": date(2025, 8, 15),
                "listing_price": 120_000.0,
            }
            for i, beds in enumerate([2, 2, 2, 5, 12, -1])
        ]
    )
    payload = build_annual_report_from_dataframe(df, cutoff_date=date(2025, 6, 1))
    by_bed = {r["segment"]: r for r in payload["apartment_segments"]["by_bedrooms"]}
    assert "-1 BR" not in by_bed
    assert "12 BR" not in by_bed
    assert "5 BR" not in by_bed
    assert "4+ BR" in by_bed
    assert by_bed["4+ BR"]["listings"] == 2  # 5 and 12
    assert [r["segment"] for r in payload["apartment_segments"]["by_bedrooms"]] == [
        "2 BR",
        "4+ BR",
    ]
    assert [r["segment"] for r in payload["apartment_segments"]["by_size_band"]] == [
        "50-79m²",
        "80-109m²",
    ]
    two = by_bed["2 BR"]
    assert two["median_sale_psm"] == 1500
    assert two["median_sale_psm"] != 10

    by_size = {r["segment"]: r for r in payload["apartment_segments"]["by_size_band"]}
    mid = by_size["50-79m²"]
    assert mid["median_sale_psm"] is None or mid["median_sale_psm"] >= 500
    large = by_size["80-109m²"]
    assert large["median_sale_psm"] == 1500
