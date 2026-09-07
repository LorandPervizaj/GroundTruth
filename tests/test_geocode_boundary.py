"""Tests for geocode boundary sanity checks."""

from groundtruth.analytics.geocode_boundary import haversine_km, neighborhood_geocode_summary


class TestHaversine:
    def test_same_point_zero(self) -> None:
        assert haversine_km(42.66, 21.16, 42.66, 21.16) == 0.0

    def test_known_distance_approx(self) -> None:
        # ~1° latitude ≈ 111 km
        dist = haversine_km(42.0, 21.0, 43.0, 21.0)
        assert 110 < dist < 112


class TestNeighborhoodGeocodeSummary:
    def test_empty_ids(self) -> None:
        class FakeSession:
            pass

        out = neighborhood_geocode_summary(
            FakeSession(), [], centroid_lat=42.66, centroid_lng=21.16
        )
        assert out["listings_with_coords"] == 0
