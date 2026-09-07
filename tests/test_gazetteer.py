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

    def test_dragodan_resolves_to_arberia(self, gazetteer_service: GazetteerService) -> None:
        match = gazetteer_service.match_neighborhood("Dragodan")
        assert match is not None
        assert match.slug == "arberia"

    def test_kalabria_prishtina_resolves_to_emshir(
        self, gazetteer_service: GazetteerService
    ) -> None:
        match = gazetteer_service.match_neighborhood("Kalabria", city="Prishtina")
        assert match is not None
        assert match.slug == "emshir"

    def test_single_rruga_b_street(self, gazetteer_service: GazetteerService) -> None:
        match = gazetteer_service.match_street("te Rruga B")
        assert match is not None
        assert match.slug == "rruga-b"

    def test_royal_mall_complex(self, gazetteer_service: GazetteerService) -> None:
        match = gazetteer_service.match_complex("mbrapa Royal Mall")
        assert match is not None
        assert match.slug == "royal-mall"

    def test_rruga_a_street(self, gazetteer_service: GazetteerService) -> None:
        match = gazetteer_service.match_street("dalje te rruga A")
        assert match is not None
        assert match.slug == "rruga-a"
