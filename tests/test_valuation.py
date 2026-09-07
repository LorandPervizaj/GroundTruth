"""Tests for rent valuation engine v0.1."""

import pandas as pd

from groundtruth.analytics.stats import comparable_area_weights, weighted_average
from groundtruth.analytics.valuation import (
    MIN_COMPARABLES,
    _assess,
    _confidence_label,
    area_bucket_sqm,
    area_match_bounds,
    select_comparables,
)


def _synthetic_comparables(
    n: int = 50, neighborhood_id: int = 5, area: float = 78.0
) -> pd.DataFrame:
    rng = pd.Series(range(n))
    areas = area + (rng % 7 - 3) * 3
    rents = 4.5 * areas + (rng % 5) * 10
    return pd.DataFrame(
        {
            "source_listing_id": [f"L{i}" for i in range(n)],
            "rent_price": rents,
            "area_sqm": areas,
            "bedrooms": 2,
            "neighborhood_id": neighborhood_id,
            "neighborhood_name": "Ulpiana",
            "property_type": "APARTMENT",
            "is_commercial": False,
            "rent_per_sqm": rents / areas,
        }
    )


class TestAreaBucket:
    def test_62_and_60_share_bucket(self) -> None:
        assert area_bucket_sqm(62) == 60
        assert area_bucket_sqm(60) == 60
        _, lo, hi = area_match_bounds(62)
        assert lo <= 60 <= hi
        assert lo <= 62 <= hi


class TestSelectComparables:
    def test_area_band_filters(self) -> None:
        df = _synthetic_comparables(60)
        comps, method, bedroom, *_ = select_comparables(
            df, neighborhood_id=5, area_sqm=78.0, bedrooms=None, area_tolerance_pct=0.20
        )
        assert len(comps) >= MIN_COMPARABLES
        assert "neighborhood" in method
        assert bedroom is False

    def test_bedroom_stratify_when_enough(self) -> None:
        df = _synthetic_comparables(50, area=78.0)
        comps, method, bedroom, *_ = select_comparables(
            df, neighborhood_id=5, area_sqm=78.0, bedrooms=2, area_tolerance_pct=0.20
        )
        assert bedroom is True
        assert "bedrooms" in method
        assert (comps["bedrooms"] == 2).all()

    def test_bedroom_stratify_skipped_when_thin_sample(self) -> None:
        two_br = _synthetic_comparables(23, area=65.0)
        two_br["bedrooms"] = 2
        other = _synthetic_comparables(37, area=65.0)
        other["bedrooms"] = 1
        df = pd.concat([two_br, other], ignore_index=True)
        comps, method, bedroom, *_ = select_comparables(
            df, neighborhood_id=5, area_sqm=65.0, bedrooms=2, area_tolerance_pct=0.20
        )
        assert bedroom is False
        assert "bedrooms" not in method
        assert len(comps) >= MIN_COMPARABLES


class TestAreaWeighting:
    def test_distant_smaller_listings_count_less(self) -> None:
        close = _synthetic_comparables(35, area=110.0)
        close["rent_per_sqm"] = 4.5
        close["rent_price"] = close["area_sqm"] * 4.5
        distant = _synthetic_comparables(35, area=90.0)
        distant["rent_per_sqm"] = 8.0
        distant["rent_price"] = distant["area_sqm"] * 8.0
        df = pd.concat([close, distant], ignore_index=True)
        weights = comparable_area_weights(df["area_sqm"], 110.0)
        weighted = weighted_average(df["rent_per_sqm"], weights)
        unweighted = float(df["rent_per_sqm"].mean())
        assert weighted < unweighted
        assert weighted < 6.0


class TestAssessment:
    def test_above_comparables(self) -> None:
        assessment, pct, summary = _assess(720, 650, 600, 690, n=36, dataset_version="v1.0")
        assert assessment == "above_comparables"
        assert pct > 0
        assert "36 listings" in summary

    def test_within_comparables(self) -> None:
        assessment, _, _ = _assess(650, 650, 600, 690, n=36, dataset_version="v1.0")
        assert assessment == "within_comparables"


class TestConfidenceLabel:
    def test_large_sample_is_capped_until_calibrated(self) -> None:
        assert _confidence_label(87, 0.4) == "Medium"

    def test_low_below_minimum(self) -> None:
        assert _confidence_label(10, 0.5) == "Low"


class TestComparablesDiskCache:
    def test_persist_and_hydrate(self, tmp_path) -> None:
        import groundtruth.analytics.valuation as valuation_mod
        from groundtruth.analytics.valuation import (
            comparables_cache_ready,
            hydrate_comparables_from_disk,
            persist_comparables_disk_cache,
        )

        valuation_mod._comparables_cache = None
        rent = _synthetic_comparables(5)
        sale = rent.copy()
        revision = "2026-01-01T00:00:00+00:00"
        persist_comparables_disk_cache(tmp_path, rent, sale, revision)
        assert hydrate_comparables_from_disk(tmp_path, revision)
        assert comparables_cache_ready()


class TestCacheOnlyValuation:
    def test_estimate_without_database_session(self) -> None:
        import groundtruth.analytics.valuation as valuation_mod
        from groundtruth.analytics.valuation import estimate_valuation
        from groundtruth.schemas.valuation import ValuationRequest

        valuation_mod._comparables_cache = None
        rent = _synthetic_comparables(50)
        sale = rent.copy()

        result = estimate_valuation(
            None,
            ValuationRequest(valuation_type="rent", neighborhood="Ulpiana", area_sqm=78),
            rent_comparables=rent,
            sale_comparables=sale,
        )
        assert result.neighborhood_name == "Ulpiana"
        assert result.point_estimate_eur > 0

    def test_ensure_rent_per_sqm_on_legacy_cache(self) -> None:
        from groundtruth.analytics.valuation import _ensure_rent_per_sqm

        legacy = _synthetic_comparables(5).drop(columns=["rent_per_sqm"])
        fixed = _ensure_rent_per_sqm(legacy)
        assert "rent_per_sqm" in fixed.columns
        assert fixed["rent_per_sqm"].notna().all()
