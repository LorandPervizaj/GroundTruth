"""Regression tests for neighborhood extraction — every bug fix becomes a permanent test."""

import pytest

from groundtruth.services.parsing import ParsingService


class TestNeighborhoodExtraction:
    def setup_method(self) -> None:
        self.parser = ParsingService()

    def extract(self, title: str | None, description: str | None = None) -> str | None:
        return self.parser.extract_neighborhood(title, description)

    @pytest.mark.parametrize(
        "title,expected",
        [
            ("Banese me qira ne Emshir", "Emshir"),
            ("Banese ne lagjen e Spitalit", "Spitalit"),
            ("Banesë me qira në Lagjen e Spitalit", "Spitalit"),
            ("Mati 1, rruga B", "Mati 1"),
            ("Shitet Banesa ne Ulpian", "Ulpian"),
            ("Banese me qira ne Dardania", "Dardania"),
            ("Banes me qera Emshir", "Emshir"),
            ("Banes me qera Mati 1", "Mati 1"),
            ("Shitet banesa te Prishtina e Re", "Prishtina e Re"),
            ("Shitet banese te Qafa", "Qafa"),
            ("Banes ne Shitje Bregu i Diellit", "Bregu i Diellit"),
            ("SHITET SUPER BANESA NE BREGUN E DIELLIT !", "BREGUN E DIELLIT"),
        ],
    )
    def test_neighborhood_from_title(self, title: str, expected: str) -> None:
        assert self.extract(title) == expected

    def test_neighborhood_from_description_lagje_te(self) -> None:
        desc = "Leshohet banese me qira ne Lagje te Spitalit, 2 dhoma gjumi"
        assert self.extract("Banesë me qira", desc) == "Spitalit"

    def test_blocklist_rejects_facebook(self) -> None:
        assert self.extract("Kontaktoni ne facebook") is None
