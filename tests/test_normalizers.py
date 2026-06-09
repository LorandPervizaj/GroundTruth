"""Unit tests for field normalizers."""

from decimal import Decimal

import pytest

from groundtruth.models.enums import Currency, HeatingType
from groundtruth.processing.normalizers.area import AreaNormalizer
from groundtruth.processing.normalizers.currency import CurrencyNormalizer
from groundtruth.processing.normalizers.heating import HeatingNormalizer
from groundtruth.processing.normalizers.neighborhood import NeighborhoodNormalizer
from groundtruth.processing.normalizers.price import PriceNormalizer


class TestPriceNormalizer:
    def setup_method(self) -> None:
        self.normalizer = PriceNormalizer()

    @pytest.mark.parametrize(
        "raw,expected",
        [
            ("145.000 €", Decimal("145000.00")),
            ("145,000 EUR", Decimal("145000.00")),
            ("125,000 EUR", Decimal("125000.00")),
            ("1.300 EUR", Decimal("1300.00")),
            ("145000", Decimal("145000.00")),
            ("145k", Decimal("145000.00")),
        ],
    )
    def test_normalize_price(self, raw: str, expected: Decimal) -> None:
        assert self.normalizer.normalize(raw) == expected


class TestAreaNormalizer:
    def setup_method(self) -> None:
        self.normalizer = AreaNormalizer()

    @pytest.mark.parametrize(
        "raw,expected",
        [
            ("80 m²", 80.0),
            ("80m2", 80.0),
            ("62.04", 62.04),
        ],
    )
    def test_normalize_area(self, raw: str, expected: float) -> None:
        assert self.normalizer.normalize(raw) == expected


class TestCurrencyNormalizer:
    def test_defaults_to_eur(self) -> None:
        assert CurrencyNormalizer().normalize(None) == Currency.EUR

    def test_detects_from_description(self) -> None:
        result = CurrencyNormalizer().normalize(None, "Çmimi 300 Euro")
        assert result == Currency.EUR


class TestHeatingNormalizer:
    def test_detects_central(self) -> None:
        result = HeatingNormalizer().normalize(None, "Ngrohje qendrore")
        assert result == HeatingType.CENTRAL


class TestNeighborhoodNormalizer:
    def test_exact_match(self, gazetteer_service) -> None:
        normalizer = NeighborhoodNormalizer(gazetteer_service)
        match = normalizer.normalize("Dardania", city="Prishtina")
        assert match is not None
        assert match.slug == "dardania"
        assert match.match_type == "exact"

    def test_alias_match(self, gazetteer_service) -> None:
        normalizer = NeighborhoodNormalizer(gazetteer_service)
        match = normalizer.normalize("Kodra e Diellit", city="Prishtina")
        assert match is not None
        assert match.slug == "sunny-hill"
