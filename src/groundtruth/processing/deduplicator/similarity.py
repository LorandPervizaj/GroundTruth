"""Per-field similarity functions for duplicate detection."""

from decimal import Decimal

from rapidfuzz import fuzz


def numeric_similarity(
    a: float | Decimal | None,
    b: float | Decimal | None,
    tolerance: float = 0.05,
) -> float:
    """Score 0–100 for numeric field similarity."""
    if a is None or b is None:
        return 0.0
    a_f, b_f = float(a), float(b)
    if a_f == 0 and b_f == 0:
        return 100.0
    if a_f == 0 or b_f == 0:
        return 0.0
    diff = abs(a_f - b_f) / max(a_f, b_f)
    if diff <= tolerance:
        return 100.0
    if diff <= tolerance * 2:
        return 70.0
    return max(0.0, 100.0 - diff * 100)


def exact_similarity(a: int | None, b: int | None) -> float:
    """Score 0 or 100 for exact integer match."""
    if a is None or b is None:
        return 0.0
    return 100.0 if a == b else 0.0


def id_similarity(a: int | None, b: int | None) -> float:
    """Score 0 or 100 for gazetteer ID match."""
    if a is None or b is None:
        return 0.0
    return 100.0 if a == b else 0.0


def text_similarity(a: str | None, b: str | None) -> float:
    """Score 0–100 for description text similarity."""
    if not a or not b:
        return 0.0
    return float(fuzz.token_sort_ratio(a, b))
