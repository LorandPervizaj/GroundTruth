"""Mathematical definitions for statistics page metrics (bilingual)."""

from __future__ import annotations

from typing import Any


def build_annual_formulas(*, min_sale_listings: int = 15) -> list[dict[str, Any]]:
    """Return formula cards consumed by the statistics page."""
    n = min_sale_listings
    return [
        {
            "id": "active_corpus",
            "section": "corpus",
            "label": {"sq": "Korpusi aktiv", "en": "Active corpus"},
            "formula": {
                "sq": (
                    "N = |{ listim unik (burim, id) : parser aktiv, datë ≥ cutoff, jo invalid }|"
                ),
                "en": (
                    "N = |{ unique listing (source, id) : active parser, "
                    "date ≥ cutoff, not invalid }|"
                ),
            },
            "used_in": ["kpi_total", "summary"],
        },
        {
            "id": "rent_share",
            "section": "kpi",
            "label": {"sq": "Pjesa e qirasë", "en": "Rent share"},
            "formula": {
                "sq": "rent_% = 100 × N_rent / N",
                "en": "rent_% = 100 × N_rent / N",
            },
            "used_in": ["kpi_rent_share"],
        },
        {
            "id": "median_sale_psm",
            "section": "kpi",
            "label": {"sq": "Mediana shitje €/m²", "en": "Median sale €/m²"},
            "formula": {
                "sq": "median({ sale_priceᵢ / areaᵢ : listing_type = sale, areaᵢ > 0 })",
                "en": "median({ sale_priceᵢ / areaᵢ : listing_type = sale, areaᵢ > 0 })",
            },
            "used_in": ["kpi_median_psm", "sale_price_chart", "rankings"],
        },
        {
            "id": "median_rent",
            "section": "kpi",
            "label": {"sq": "Mediana qira", "en": "Median rent"},
            "formula": {
                "sq": "median({ rent_priceᵢ : listing_type = rent })",
                "en": "median({ rent_priceᵢ : listing_type = rent })",
            },
            "used_in": ["kpi_median_rent", "rent_price_chart", "nh_table"],
        },
        {
            "id": "volume_monthly",
            "section": "chart",
            "label": {"sq": "Volumi mujor", "en": "Monthly volume"},
            "formula": {
                "sq": "count(listings) grupuar sipas muajit(listing_date), veçmas qira / shitje",
                "en": "count(listings) grouped by month(listing_date), rent and sale separately",
            },
            "used_in": ["volume_chart"],
        },
        {
            "id": "sale_psm_monthly",
            "section": "chart",
            "label": {"sq": "€/m² shitje mujore", "en": "Monthly sale €/m²"},
            "formula": {
                "sq": "për çdo muaj m: median(price_per_sqmᵢ | monthᵢ = m, sale)",
                "en": "for each month m: median(price_per_sqmᵢ | monthᵢ = m, sale)",
            },
            "used_in": ["sale_price_chart"],
        },
        {
            "id": "rent_monthly",
            "section": "chart",
            "label": {"sq": "Qira mujore", "en": "Monthly rent"},
            "formula": {
                "sq": "për çdo muaj m: median(rent_priceᵢ | monthᵢ = m, rent)",
                "en": "for each month m: median(rent_priceᵢ | monthᵢ = m, rent)",
            },
            "used_in": ["rent_price_chart"],
        },
        {
            "id": "nh_inventory",
            "section": "chart",
            "label": {"sq": "Inventari sipas lagjes", "en": "Inventory by neighborhood"},
            "formula": {
                "sq": "count(listings) grupuar sipas neighborhood_id",
                "en": "count(listings) grouped by neighborhood_id",
            },
            "used_in": ["nh_chart", "nh_table"],
        },
        {
            "id": "nh_median_psm",
            "section": "table",
            "label": {"sq": "€/m² lagje", "en": "Neighborhood €/m²"},
            "formula": {
                "sq": f"median(price_per_sqm) për lagje; renditja kërkon ≥{n} shitje",
                "en": f"median(price_per_sqm) per neighborhood; rankings require ≥{n} sales",
            },
            "used_in": ["rankings", "nh_table"],
        },
        {
            "id": "field_coverage",
            "section": "quality",
            "label": {"sq": "Mbulimi i fushave", "en": "Field coverage"},
            "formula": {
                "sq": "coverage_field = 100 × count(fieldᵢ ≠ null) / N",
                "en": "coverage_field = 100 × count(fieldᵢ ≠ null) / N",
            },
            "used_in": ["coverage_narrative"],
        },
        {
            "id": "median_definition",
            "section": "method",
            "label": {"sq": "Mediana", "en": "Median"},
            "formula": {
                "sq": "vlera e mesme e renditur (p₅₀); rezistente ndaj ekstremeve",
                "en": "middle value of sorted sample (p₅₀); robust to outliers",
            },
            "used_in": ["all_price_metrics"],
        },
    ]
