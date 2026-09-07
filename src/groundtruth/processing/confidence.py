"""Compute per-listing confidence scores for analytics filtering."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from groundtruth.schemas.pipeline import NormalizedListingSchema, ParsedListingSchema

_MATCH_WEIGHTS = {
    "exact": 1.0,
    "alias": 0.92,
    "fuzzy": 0.75,
    "street_fallback": 0.65,
    "complex_fallback": 0.60,
    "missing": 0.0,
}

# Decomposable component weights — must sum to 1.0
COMPONENT_WEIGHTS: dict[str, float] = {
    "price": 0.20,
    "area": 0.15,
    "neighborhood": 0.25,
    "type": 0.10,
    "parser_certainty": 0.10,
    "normalization": 0.15,
    "validation": 0.05,
}


@dataclass
class ConfidenceFactors:
    """Signals collected during normalization for confidence scoring."""

    neighborhood_match_type: str = "missing"
    neighborhood_gazetteer_slug: str | None = None
    district_match_type: str = "missing"
    district_gazetteer_slug: str | None = None
    street_match_type: str = "missing"
    complex_match_type: str = "missing"
    building_match_type: str = "missing"
    location_invalid: bool = False
    location_invalid_reason: str | None = None


@dataclass
class ConfidenceResult:
    """Confidence score in [0, 1] with auditable breakdown."""

    score: float
    details: dict[str, Any] = field(default_factory=dict)


class ConfidenceScorer:
    """Derive a decomposable confidence score from extraction quality and match certainty."""

    def score(
        self,
        normalized: NormalizedListingSchema,
        parsed: ParsedListingSchema,
        *,
        factors: ConfidenceFactors,
        is_valid: bool,
    ) -> ConfidenceResult:
        active_price = (
            normalized.rent_price
            if normalized.listing_type and normalized.listing_type.value == "rent"
            else normalized.sale_price
        )

        price_score = 1.0 if active_price is not None else 0.0
        area_score = 1.0 if normalized.area_sqm is not None else 0.0
        type_score = 1.0 if normalized.listing_type is not None else 0.0

        nh_weight = _MATCH_WEIGHTS.get(factors.neighborhood_match_type, 0.0)
        neighborhood_score = nh_weight if normalized.neighborhood_id else 0.0
        normalization_score = nh_weight

        parser_score = self._parser_certainty(parsed, normalized)

        validation_score = 1.0 if is_valid else 0.0

        components = {
            "price": round(price_score, 4),
            "area": round(area_score, 4),
            "neighborhood": round(neighborhood_score, 4),
            "type": round(type_score, 4),
            "parser_certainty": round(parser_score, 4),
            "normalization": round(normalization_score, 4),
            "validation": round(validation_score, 4),
        }

        score = round(
            sum(components[k] * COMPONENT_WEIGHTS[k] for k in COMPONENT_WEIGHTS),
            4,
        )
        score = min(1.0, max(0.0, score))

        geocode_score = {
            "address": 1.0,
            "street": 0.85,
            "neighborhood": 0.7,
            "city": 0.5,
        }.get(normalized.geocode_precision or "", 0.4 if normalized.latitude else 0.0)

        extraction_flags = {
            "price": active_price is not None,
            "area": normalized.area_sqm is not None,
            "neighborhood": normalized.neighborhood_id is not None,
            "description": bool(normalized.description_original),
            "listing_type": normalized.listing_type is not None,
        }

        provenance = (parsed.extra_fields or {}).get("provenance", {})

        return ConfidenceResult(
            score=score,
            details={
                "components": components,
                "component_weights": COMPONENT_WEIGHTS,
                "overall": score,
                "neighborhood_match_type": factors.neighborhood_match_type,
                "street_match_type": factors.street_match_type,
                "extraction_flags": extraction_flags,
                "validation_passed": is_valid,
                "geocode_score": round(geocode_score, 4),
                "provenance_fields": list(provenance.keys()) if provenance else [],
            },
        )

    def _parser_certainty(
        self,
        parsed: ParsedListingSchema,
        normalized: NormalizedListingSchema,
    ) -> float:
        """Average provenance rule certainty when available; else heuristic."""
        provenance = (parsed.extra_fields or {}).get("provenance", {})
        if provenance:
            contributions = [
                float(entry.get("confidence_contribution", 0))
                for entry in provenance.values()
                if entry.get("confidence_contribution")
            ]
            if contributions:
                return min(1.0, sum(contributions) / len(contributions))

        if parsed.neighborhood_raw and normalized.neighborhood_id:
            return 1.0
        if normalized.neighborhood_id:
            return 0.7
        return 0.3
