"""Tests for furnished / unfurnished extraction."""

from groundtruth.processing.extractors.text import TextExtractor


def test_unfurnished_pa_mobiluar() -> None:
    ext = TextExtractor()
    result = ext.process("Banesa me qira pa mobiluar ne Ulpiana")
    assert result.is_furnished is False


def test_furnished_mobiluar() -> None:
    ext = TextExtractor()
    result = ext.process("Banesa e mobiluar komplet me qira")
    assert result.is_furnished is True


def test_pa_mobiluar_not_furnished() -> None:
    ext = TextExtractor()
    result = ext.process("Leshohet pa mobilim, vetem kuzhine")
    assert result.is_furnished is False
