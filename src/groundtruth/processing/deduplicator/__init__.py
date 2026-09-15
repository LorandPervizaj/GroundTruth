"""Duplicate detection: scoring and similarity (live path)."""

from groundtruth.processing.deduplicator.scoring import DuplicateScorer
from groundtruth.processing.deduplicator.similarity import (
    exact_similarity,
    id_similarity,
    numeric_similarity,
    text_similarity,
)

__all__ = [
    "DuplicateScorer",
    "exact_similarity",
    "id_similarity",
    "numeric_similarity",
    "text_similarity",
]