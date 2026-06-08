"""Weighted duplicate confidence scoring."""

from groundtruth.config import get_settings
from groundtruth.processing.deduplicator.similarity import (
    exact_similarity,
    id_similarity,
    numeric_similarity,
    text_similarity,
)
from groundtruth.schemas.deduplication import DuplicateMatchResult, DuplicateScoreBreakdown
from groundtruth.schemas.pipeline import NormalizedListingSchema

FIELD_WEIGHTS: dict[str, float] = {
    "price": 0.20,
    "area": 0.20,
    "bedrooms": 0.10,
    "bathrooms": 0.05,
    "building": 0.10,
    "street": 0.10,
    "neighborhood": 0.10,
    "description": 0.15,
}


class DuplicateScorer:
    """Compare two normalized listings and return a duplicate confidence score."""

    def __init__(self, threshold: float | None = None) -> None:
        settings = get_settings()
        self._threshold = threshold or settings.dedup_fuzzy_threshold

    def score(
        self,
        candidate: NormalizedListingSchema,
        reference: NormalizedListingSchema,
        *,
        candidate_id: int = 0,
        reference_id: int = 0,
    ) -> DuplicateMatchResult:
        """Compute weighted duplicate confidence between two listings."""
        breakdown = DuplicateScoreBreakdown(
            price_score=self._price_score(candidate, reference),
            area_score=numeric_similarity(candidate.area_sqm, reference.area_sqm, tolerance=0.05),
            bedrooms_score=exact_similarity(candidate.bedrooms, reference.bedrooms),
            bathrooms_score=exact_similarity(candidate.bathrooms, reference.bathrooms),
            building_score=id_similarity(candidate.building_id, reference.building_id),
            street_score=id_similarity(candidate.street_id, reference.street_id),
            neighborhood_score=id_similarity(
                candidate.neighborhood_id, reference.neighborhood_id
            ),
            description_score=text_similarity(
                candidate.description_cleaned,
                reference.description_cleaned,
            ),
        )

        confidence = self._weighted_confidence(breakdown, candidate, reference)
        matched_fields = self._matched_fields(breakdown)

        return DuplicateMatchResult(
            candidate_listing_id=candidate_id,
            reference_listing_id=reference_id,
            confidence=round(confidence, 2),
            breakdown=breakdown,
            matched_fields=matched_fields,
            is_likely_duplicate=confidence >= self._threshold,
        )

    def _weighted_confidence(
        self,
        breakdown: DuplicateScoreBreakdown,
        candidate: NormalizedListingSchema,
        reference: NormalizedListingSchema,
    ) -> float:
        scores = {
            "price": breakdown.price_score,
            "area": breakdown.area_score,
            "bedrooms": breakdown.bedrooms_score,
            "bathrooms": breakdown.bathrooms_score,
            "building": breakdown.building_score,
            "street": breakdown.street_score,
            "neighborhood": breakdown.neighborhood_score,
            "description": breakdown.description_score,
        }
        active_weights = {
            field: weight
            for field, weight in FIELD_WEIGHTS.items()
            if self._field_available(field, candidate, reference)
        }
        if not active_weights:
            return 0.0
        weight_sum = sum(active_weights.values())
        return sum(
            scores[field] * (weight / weight_sum) for field, weight in active_weights.items()
        )

    def _field_available(
        self,
        field: str,
        candidate: NormalizedListingSchema,
        reference: NormalizedListingSchema,
    ) -> bool:
        checks: dict[str, bool] = {
            "price": (candidate.sale_price or candidate.rent_price) is not None
            and (reference.sale_price or reference.rent_price) is not None,
            "area": candidate.area_sqm is not None and reference.area_sqm is not None,
            "bedrooms": candidate.bedrooms is not None and reference.bedrooms is not None,
            "bathrooms": candidate.bathrooms is not None and reference.bathrooms is not None,
            "building": candidate.building_id is not None and reference.building_id is not None,
            "street": candidate.street_id is not None and reference.street_id is not None,
            "neighborhood": candidate.neighborhood_id is not None
            and reference.neighborhood_id is not None,
            "description": bool(candidate.description_cleaned and reference.description_cleaned),
        }
        return checks.get(field, False)

    def _matched_fields(self, breakdown: DuplicateScoreBreakdown) -> list[str]:
        threshold = 80.0
        mapping = {
            "price": breakdown.price_score,
            "area": breakdown.area_score,
            "bedrooms": breakdown.bedrooms_score,
            "bathrooms": breakdown.bathrooms_score,
            "building": breakdown.building_score,
            "street": breakdown.street_score,
            "neighborhood": breakdown.neighborhood_score,
            "description": breakdown.description_score,
        }
        return [field for field, score in mapping.items() if score >= threshold]

    def _price_score(
        self,
        a: NormalizedListingSchema,
        b: NormalizedListingSchema,
    ) -> float:
        price_a = a.sale_price or a.rent_price
        price_b = b.sale_price or b.rent_price
        if price_a is None or price_b is None:
            return 0.0
        return numeric_similarity(float(price_a), float(price_b), tolerance=0.03)
