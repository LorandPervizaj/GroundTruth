"""Canonical public metric and population contracts.

Metric IDs are stable semantic identifiers.  Existing ``average_*`` API names
are registered only as deprecated aliases; their statistic remains median.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Literal

Statistic = Literal["count", "median", "percentile", "ratio"]


@dataclass(frozen=True)
class PopulationDefinition:
    population_id: str
    description: str
    transaction_type: str | None
    property_types: tuple[str, ...]
    required_fields: tuple[str, ...]
    validity_filters: tuple[str, ...]
    time_window: str


@dataclass(frozen=True)
class MetricDefinition:
    metric_id: str
    display_name: str
    statistic: Statistic
    unit: str
    population_id: str
    required_fields: tuple[str, ...]
    rounding_rule: str
    minimum_n: int
    confidence_method: str
    percentile: int | None = None
    deprecated_api_aliases: tuple[str, ...] = ()


POPULATIONS: dict[str, PopulationDefinition] = {
    "recent.all": PopulationDefinition(
        "recent.all",
        "Valid canonical listings observed inside the legacy analytical window.",
        None,
        (),
        ("listing_type", "property_type"),
        ("active_corpus_where", "latest_source_row", "cross_portal_primary"),
        "rolling_12_months",
    ),
    "recent.apartment_studio": PopulationDefinition(
        "recent.apartment_studio",
        "Recent valid canonical apartment and studio listings.",
        None,
        ("APARTMENT", "STUDIO"),
        ("listing_type", "property_type"),
        ("active_corpus_where", "latest_source_row", "cross_portal_primary"),
        "rolling_12_months",
    ),
    "recent.sale.apartment_studio": PopulationDefinition(
        "recent.sale.apartment_studio",
        "Recent valid canonical apartment/studio sale listings.",
        "sale",
        ("APARTMENT", "STUDIO"),
        ("sale_price", "area_sqm", "price_per_sqm"),
        ("sale_psm_validation_band",),
        "rolling_12_months",
    ),
    "recent.rent.apartment_studio": PopulationDefinition(
        "recent.rent.apartment_studio",
        "Recent valid canonical apartment/studio rent listings.",
        "rent",
        ("APARTMENT", "STUDIO"),
        ("rent_price", "area_sqm"),
        ("implied_rent_psm_validation_band",),
        "rolling_12_months",
    ),
    "recent.sale.all_property_types": PopulationDefinition(
        "recent.sale.all_property_types",
        "Recent valid canonical sale listings grouped by property type.",
        "sale",
        (),
        ("sale_price",),
        ("sale_psm_validation_band_when_psm_metric",),
        "rolling_12_months",
    ),
    "historical.apartment_studio": PopulationDefinition(
        "historical.apartment_studio",
        "Biweekly listing observations for apartment/studio history.",
        None,
        ("APARTMENT", "STUDIO"),
        ("observation_date", "listing_type"),
        ("minimum_5_per_period",),
        "6_to_12_months",
    ),
    "valuation.sale.comparables": PopulationDefinition(
        "valuation.sale.comparables",
        "Sale comparables passing valuation-specific eligibility rules.",
        "sale",
        ("APARTMENT", "STUDIO"),
        ("sale_price", "area_sqm", "price_per_sqm"),
        ("valuation_sale_bounds", "location_match", "area_match"),
        "valuation_policy_window",
    ),
    "valuation.rent.comparables": PopulationDefinition(
        "valuation.rent.comparables",
        "Rent comparables passing valuation-specific eligibility rules.",
        "rent",
        ("APARTMENT", "STUDIO"),
        ("rent_price", "area_sqm"),
        ("valuation_rent_bounds", "location_match", "area_match"),
        "valuation_policy_window",
    ),
}


def _metric(
    metric_id: str,
    display_name: str,
    statistic: Statistic,
    unit: str,
    population_id: str,
    required_fields: tuple[str, ...],
    rounding_rule: str,
    *,
    minimum_n: int = 10,
    percentile: int | None = None,
    aliases: tuple[str, ...] = (),
) -> MetricDefinition:
    return MetricDefinition(
        metric_id=metric_id,
        display_name=display_name,
        statistic=statistic,
        unit=unit,
        population_id=population_id,
        required_fields=required_fields,
        rounding_rule=rounding_rule,
        minimum_n=minimum_n,
        confidence_method="sample_source_freshness_v1",
        percentile=percentile,
        deprecated_api_aliases=aliases,
    )


METRICS: dict[str, MetricDefinition] = {
    "recent_listing_count": _metric(
        "recent_listing_count",
        "Recent valid listings",
        "count",
        "LISTINGS",
        "recent.all",
        (),
        "integer",
        minimum_n=0,
    ),
    "recent_apartment_count": _metric(
        "recent_apartment_count",
        "Recent apartment listings",
        "count",
        "LISTINGS",
        "recent.apartment_studio",
        (),
        "integer",
        minimum_n=0,
    ),
    "median_sale_psm": _metric(
        "median_sale_psm",
        "Median asking sale price per m²",
        "median",
        "EUR_PER_M2",
        "recent.sale.apartment_studio",
        ("price_per_sqm",),
        "nearest_10_eur",
        aliases=("average_sale_psm_eur",),
    ),
    "median_rent_psm": _metric(
        "median_rent_psm",
        "Median asking rent per m²",
        "median",
        "EUR_PER_M2_MONTH",
        "recent.rent.apartment_studio",
        ("rent_price", "area_sqm"),
        "nearest_1_eur",
        aliases=("average_rent_psm_eur",),
    ),
    "median_sale_eur": _metric(
        "median_sale_eur",
        "Median asking sale price",
        "median",
        "EUR",
        "recent.sale.apartment_studio",
        ("sale_price",),
        "nearest_1000_eur",
    ),
    "median_rent_eur": _metric(
        "median_rent_eur",
        "Median asking monthly rent",
        "median",
        "EUR_MONTH",
        "recent.rent.apartment_studio",
        ("rent_price",),
        "nearest_10_eur",
    ),
    "median_area_sqm": _metric(
        "median_area_sqm",
        "Median observed area",
        "median",
        "M2",
        "recent.apartment_studio",
        ("area_sqm",),
        "nearest_1_m2",
        minimum_n=1,
        aliases=("typical_area_sqm",),
    ),
    "median_bedrooms": _metric(
        "median_bedrooms",
        "Median observed bedroom count",
        "median",
        "BEDROOMS",
        "recent.apartment_studio",
        ("bedrooms",),
        "integer",
        minimum_n=1,
        aliases=("typical_bedrooms",),
    ),
    "median_days_on_market": _metric(
        "median_days_on_market",
        "Median days observed",
        "median",
        "DAYS",
        "recent.apartment_studio",
        ("first_seen", "last_seen"),
        "integer",
        minimum_n=1,
    ),
    "sale_psm_p10": _metric(
        "sale_psm_p10",
        "10th percentile asking sale price per m²",
        "percentile",
        "EUR_PER_M2",
        "recent.sale.apartment_studio",
        ("price_per_sqm",),
        "nearest_10_eur",
        percentile=10,
    ),
    "sale_psm_p50": _metric(
        "sale_psm_p50",
        "50th percentile asking sale price per m²",
        "percentile",
        "EUR_PER_M2",
        "recent.sale.apartment_studio",
        ("price_per_sqm",),
        "nearest_10_eur",
        percentile=50,
    ),
    "sale_psm_p90": _metric(
        "sale_psm_p90",
        "90th percentile asking sale price per m²",
        "percentile",
        "EUR_PER_M2",
        "recent.sale.apartment_studio",
        ("price_per_sqm",),
        "nearest_10_eur",
        percentile=90,
    ),
    "gross_rent_yield": _metric(
        "gross_rent_yield",
        "Gross asking rent yield",
        "ratio",
        "PERCENT_YEAR",
        "recent.apartment_studio",
        ("median_rent_eur", "median_sale_eur"),
        "one_decimal",
        minimum_n=30,
    ),
    "historical_median_sale_psm": _metric(
        "historical_median_sale_psm",
        "Biweekly median asking sale price per m²",
        "median",
        "EUR_PER_M2",
        "historical.apartment_studio",
        ("price_per_sqm",),
        "nearest_10_eur",
        minimum_n=5,
    ),
    "historical_median_rent_eur": _metric(
        "historical_median_rent_eur",
        "Biweekly median asking rent",
        "median",
        "EUR_MONTH",
        "historical.apartment_studio",
        ("rent_price",),
        "nearest_10_eur",
        minimum_n=5,
    ),
}


def metric_definition(metric_id: str) -> MetricDefinition:
    try:
        return METRICS[metric_id]
    except KeyError as exc:
        raise ValueError(f"unknown public metric: {metric_id}") from exc


def population_definition(population_id: str) -> PopulationDefinition:
    try:
        return POPULATIONS[population_id]
    except KeyError as exc:
        raise ValueError(f"unknown metric population: {population_id}") from exc


def validate_registry() -> None:
    valid_units = {
        "LISTINGS",
        "EUR_PER_M2",
        "EUR_PER_M2_MONTH",
        "EUR",
        "EUR_MONTH",
        "M2",
        "BEDROOMS",
        "DAYS",
        "PERCENT_YEAR",
    }
    aliases: set[str] = set()
    for key, definition in METRICS.items():
        if key != definition.metric_id:
            raise ValueError(f"metric key/id mismatch: {key}")
        population_definition(definition.population_id)
        if definition.unit not in valid_units:
            raise ValueError(f"invalid unit for {key}: {definition.unit}")
        if definition.statistic == "median" and "mean" in definition.display_name.lower():
            raise ValueError(f"median metric claims mean: {key}")
        if not definition.rounding_rule:
            raise ValueError(f"missing rounding rule: {key}")
        for alias in definition.deprecated_api_aliases:
            if alias in aliases:
                raise ValueError(f"duplicate deprecated alias: {alias}")
            aliases.add(alias)


def registry_payload() -> dict[str, object]:
    validate_registry()
    return {
        "populations": [asdict(value) for value in POPULATIONS.values()],
        "metrics": [asdict(value) for value in METRICS.values()],
    }
