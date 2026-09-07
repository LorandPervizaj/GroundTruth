"""Tests for annual PDF generation."""

from datetime import date

import pandas as pd

from groundtruth.analytics.annual_pdf import build_annual_pdf_bytes
from groundtruth.analytics.annual_report import build_annual_report_from_dataframe


def _minimal_payload() -> dict:
    df = pd.DataFrame(
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
        ]
    )
    payload = build_annual_report_from_dataframe(df, cutoff_date=date(2025, 6, 1))
    payload["generated_at"] = "2026-06-12T00:00:00+00:00"
    return payload


def test_build_annual_pdf_bytes() -> None:
    pdf = build_annual_pdf_bytes(_minimal_payload(), lang="en")
    assert pdf.startswith(b"%PDF")
    assert len(pdf) > 5000
