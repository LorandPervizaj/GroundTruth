"""Inter-reviewer agreement on manual label corpus."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass


@dataclass
class FieldAgreement:
    field: str
    n_pairs: int
    agreement_rate: float
    cohens_kappa: float | None
    ambiguity_rate: float


def _cohens_kappa(labels_a: list[str], labels_b: list[str]) -> float | None:
    if len(labels_a) != len(labels_b) or not labels_a:
        return None
    categories = sorted(set(labels_a) | set(labels_b))
    if len(categories) < 2:
        return 1.0 if labels_a == labels_b else None
    n = len(labels_a)
    observed = sum(1 for a, b in zip(labels_a, labels_b, strict=True) if a == b) / n
    count_a = Counter(labels_a)
    count_b = Counter(labels_b)
    expected = sum((count_a[c] / n) * (count_b[c] / n) for c in categories)
    if expected >= 1.0:
        return 1.0 if observed == 1.0 else 0.0
    return (observed - expected) / (1.0 - expected)


def field_agreement(
    pairs: list[tuple[str, str]],
    *,
    field: str,
    ambiguity_flags: list[bool] | None = None,
) -> FieldAgreement:
    """Agreement stats for one field across reviewer pairs."""
    labels_a = [a.strip().lower() for a, b in pairs if a.strip() and b.strip()]
    labels_b = [b.strip().lower() for a, b in pairs if a.strip() and b.strip()]
    n = len(labels_a)
    if n == 0:
        return FieldAgreement(field, 0, 0.0, None, 0.0)
    agree = sum(1 for a, b in zip(labels_a, labels_b, strict=True) if a == b) / n
    kappa = _cohens_kappa(labels_a, labels_b)
    amb = 0.0
    if ambiguity_flags:
        amb = sum(ambiguity_flags) / len(ambiguity_flags)
    return FieldAgreement(
        field, n, round(agree, 4), round(kappa, 4) if kappa is not None else None, round(amb, 4)
    )
