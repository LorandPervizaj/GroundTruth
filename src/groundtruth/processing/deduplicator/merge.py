"""Explicit merge operations for confirmed duplicates. Never auto-merges."""

from groundtruth.config import get_settings
from groundtruth.logging import get_logger
from groundtruth.schemas.canonical import CanonicalPropertySchema, ListingSourceSchema
from groundtruth.schemas.deduplication import DuplicateMatchResult

logger = get_logger(__name__)


class DuplicateMerger:
    """
    Merge confirmed duplicate listings into canonical properties.

    Merging is always explicit — triggered only when confidence exceeds
    threshold AND dedup_auto_merge is enabled, or via manual review.
    """

    def __init__(self) -> None:
        self._settings = get_settings()

    def should_merge(self, match: DuplicateMatchResult) -> bool:
        """Return True only if auto-merge is enabled and confidence is high enough."""
        if not self._settings.dedup_auto_merge:
            return False
        return match.is_likely_duplicate

    def build_canonical_from_match(
        self,
        match: DuplicateMatchResult,
        primary: CanonicalPropertySchema,
        secondary_source: ListingSourceSchema,
    ) -> tuple[CanonicalPropertySchema, ListingSourceSchema]:
        """
        Prepare canonical property and source link from a confirmed match.

        Actual persistence is handled by CanonicalPropertyRepository.
        """
        source = ListingSourceSchema(
            normalized_listing_id=secondary_source.normalized_listing_id,
            parsed_listing_id=secondary_source.parsed_listing_id,
            source_website=secondary_source.source_website,
            source_listing_id=secondary_source.source_listing_id,
            original_url=secondary_source.original_url,
            is_primary_source=False,
            duplicate_confidence=match.confidence,
            duplicate_match_fields=match.matched_fields,
        )
        logger.info(
            "duplicate_merge_prepared",
            confidence=match.confidence,
            candidate_id=match.candidate_listing_id,
            reference_id=match.reference_listing_id,
        )
        return primary, source
