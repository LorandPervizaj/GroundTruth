"""Duplicate detection: candidate generation, similarity, scoring, merge."""

from groundtruth.processing.deduplicator.candidate_generation import (
    generate_pairs_by_neighborhood,
    generate_pairs_by_price_band,
)
from groundtruth.processing.deduplicator.merge import DuplicateMerger
from groundtruth.processing.deduplicator.scoring import DuplicateScorer

__all__ = [
    "DuplicateMerger",
    "DuplicateScorer",
    "generate_pairs_by_neighborhood",
    "generate_pairs_by_price_band",
]
