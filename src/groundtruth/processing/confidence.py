"""Compute per-listing confidence scores for analytics filtering."""

from __future__ import annotations

from dataclasses import dataclass, field

from groundtruth.schemas.pipeline import NormalizedListingSchema, ParsedListingSchema

_MATCH_WEIGHTS = {
    "exact": 1.0,
    "alias": 0.92,
    "fuzzy": 0.75,
    "street_fallback": 0.65,
    "missing": 0.0,
}


@dataclass
class ConfidenceFactors:
    """Signals collected during normalization for confidence scoring."""

    neighborhood_match_type: str = "missing"
    street_match_type: str = "missing"
    complex_match_type: str = "missing"
    building_match_type: str = "missing"


@dataclass
class ConfidenceResult:
    """Confidence score in [0, 1] with auditable breakdown."""

    score: float
    details: dict[str, float | str | bool] = field(default_factory=dict)


class ConfidenceScorer:
    """Derive a single confidence score from extraction quality and match certainty."""

    def score(
        self,
        normalized: NormalizedListingSchema,
        parsed: ParsedListingSchema,
        *,
        factors: ConfidenceFactors,
        is_valid: bool,
    ) -> ConfidenceResult:
        nh_weight = _MATCH_WEIGHTS.get(factors.neighborhood_match_type, 0.0)
        neighborhood_score = nh_weight if normalized.neighborhood_id else 0.0

        active_price = (
            normalized.rent_price
            if normalized.listing_type and normalized.listing_type.value == "rent"
            else normalized.sale_price
        )

        extraction_flags = {
            "price": active_price is not None,
            "area": normalized.area_sqm is not None,
            "neighborhood": normalized.neighborhood_id is not None,
            "description": bool(normalized.description_original),
            "listing_type": normalized.listing_type is not None,
        }
        extraction_score = sum(extraction_flags.values()) / len(extraction_flags)

        validation_score = 1.0 if is_valid else 0.0

        geocode_score = {
            "address": 1.0,
            "street": 0.85,
            "neighborhood": 0.7,
            "city": 0.5,
        }.get(normalized.geocode_precision or "", 0.4 if normalized.latitude else 0.0)

        parser_score = 1.0 if parsed.neighborhood_raw and normalized.neighborhood_id else (
            0.5 if normalized.neighborhood_id else 0.2
        )

        # Weighted blend — neighborhood certainty matters most for market reports.
        score = (
            neighborhood_score * 0.35
            + extraction_score * 0.30
            + validation_score * 0.20
            + parser_score * 0.10
            + geocode_score * 0.05
        )
        score = round(min(1.0, max(0.0, score)), 4)

        return ConfidenceResult(
            score=score,
            details={
                "neighborhood_match_type": factors.neighborhood_match_type,
                "street_match_type": factors.street_match_type,
                "neighborhood_score": round(neighborhood_score, 4),
                "extraction_score": round(extraction_score, 4),
                "extraction_flags": extraction_flags,
                "validation_passed": is_valid,
                "validation_score": validation_score,
                "parser_score": round(parser_score, 4),
                "geocode_score": round(geocode_score, 4),
            },
        )
