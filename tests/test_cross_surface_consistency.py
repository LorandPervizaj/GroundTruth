from groundtruth.analytics.cross_surface_consistency import consistency_issues
from groundtruth.schemas.lookup import (
    MarketLookup,
    MarketPulse,
    MetricSample,
    NeighborhoodMarketSummary,
)


def _lookup() -> MarketLookup:
    return MarketLookup(
        entity_type="neighborhood",
        slug="alpha",
        display_name="Alpha",
        pulse=MarketPulse(
            median_sale_psm_eur=1500,
            median_rent_psm_eur=7,
            median_sale_eur=120000,
            median_rent_eur=550,
            median_sale_sample=MetricSample(n=31, confidence="medium"),
            median_rent_sample=MetricSample(n=12, confidence="medium"),
        ),
    )


def test_public_surfaces_match_canonical_lookup() -> None:
    markets = [
        NeighborhoodMarketSummary(
            slug="alpha",
            name="Alpha",
            rent_listings=12,
            sale_listings=31,
            median_rent_eur=550,
            median_rent_psm_eur=7,
        )
    ]
    yields = [
        {
            "slug": "alpha",
            "median_rent_eur": 550,
            "median_sale_eur": 120000,
            "median_rent_psm": 7,
            "median_sale_psm": 1500,
        }
    ]
    assert consistency_issues([_lookup()], markets, yields) == []


def test_drift_is_reported_by_surface_and_metric() -> None:
    markets = [
        NeighborhoodMarketSummary(
            slug="alpha",
            name="Alpha",
            rent_listings=11,
            sale_listings=31,
            median_rent_eur=500,
            median_rent_psm_eur=7,
        )
    ]
    yields = [{"slug": "alpha", "median_sale_psm": 1490}]
    assert consistency_issues([_lookup()], markets, yields) == [
        "markets:alpha:median_rent",
        "markets:alpha:rent_sample",
        "yield:alpha:median_sale_psm",
    ]
