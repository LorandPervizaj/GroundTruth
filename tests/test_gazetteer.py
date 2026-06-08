"""Unit tests for gazetteer loader."""

import pytest

from groundtruth.gazetteers.loader import GazetteerService


class TestGazetteerService:
    def test_fuzzy_complex_match(self, gazetteer_service: GazetteerService) -> None:
        match = gazetteer_service.match_complex("te Mati 1")
        assert match is not None
        assert match.slug == "mati-1"

    def test_neighborhood_centroid(self, gazetteer_service: GazetteerService) -> None:
        centroid = gazetteer_service.get_neighborhood_centroid("dardania")
        assert centroid is not None
        assert centroid[0] == pytest.approx(42.6580, abs=0.01)
