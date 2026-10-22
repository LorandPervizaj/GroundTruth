"""Research candidate ranking and identity gates; never merges or transfers fields."""

from __future__ import annotations

import re
import unicodedata
from difflib import SequenceMatcher


def normalized_text(value) -> str:
    value = "".join(
        c
        for c in unicodedata.normalize("NFKD", str(value or "").lower())
        if not unicodedata.combining(c)
    )
    return " ".join(re.findall(r"[a-z0-9]+", value))


def street_key(value) -> str:
    normalized = normalized_text(value)
    tokens = [
        w
        for w in normalized.split()
        if w not in {"rruga", "rr", "r", "street", "prishtina", "prishtine", "kosove", "kosova"}
    ]
    key = " ".join(tokens)
    if (
        len(key) == 1
        and key.isalpha()
        and any(w in normalized.split() for w in {"rruga", "rr", "street"})
    ):
        return key  # Prishtina has genuine streets named A, B and C.
    return key if len(key) >= 4 else ""


def _near(a, b, tolerance) -> bool:
    return (
        a is not None
        and b is not None
        and float(a) > 0
        and float(b) > 0
        and abs(float(a) - float(b)) / max(float(a), float(b)) <= tolerance
    )


def candidate_assessment(a: dict, b: dict) -> dict:
    """Rank for review only. Price, street or building cannot prove apartment identity."""
    if a["source_website"] == b["source_website"] or a.get("listing_type") != b.get("listing_type"):
        return {"eligible": False, "score": 0, "verified_identity": False}

    def price(x):
        return x.get("rent_price") if x.get("listing_type") == "rent" else x.get("sale_price")

    signals = {
        "asking_price_near": _near(price(a), price(b), 0.05),
        "interior_area_near": _near(a.get("area_sqm"), b.get("area_sqm"), 0.05),
        "bedrooms_equal": a.get("bedrooms") is not None and a.get("bedrooms") == b.get("bedrooms"),
        "bathrooms_equal": a.get("bathrooms") is not None
        and a.get("bathrooms") == b.get("bathrooms"),
        "floor_equal": a.get("floor") is not None and a.get("floor") == b.get("floor"),
        "street_equal": bool(street_key(a.get("street_raw")))
        and street_key(a.get("street_raw")) == street_key(b.get("street_raw")),
        "neighborhood_equal": a.get("neighborhood_id") is not None
        and a.get("neighborhood_id") == b.get("neighborhood_id"),
        "building_equal": a.get("building_id") is not None
        and a.get("building_id") == b.get("building_id"),
    }
    title_similarity = (
        SequenceMatcher(
            None, normalized_text(a.get("title")), normalized_text(b.get("title"))
        ).ratio()
        if a.get("title") and b.get("title")
        else 0
    )
    baseline = (
        sum(
            weight * signals[k]
            for k, weight in {
                "asking_price_near": 25,
                "interior_area_near": 15,
                "bedrooms_equal": 6,
                "bathrooms_equal": 4,
                "floor_equal": 10,
            }.items()
        )
        + 10 * title_similarity
    )
    augmented = (
        baseline
        + 20 * signals["street_equal"]
        + 5 * signals["neighborhood_equal"]
        + 5 * signals["building_equal"]
    )
    contradictions = [
        k
        for k in ["bedrooms", "bathrooms", "floor"]
        if a.get(k) is not None and b.get(k) is not None and a[k] != b[k]
    ]
    return {
        "eligible": True,
        "score": round(augmented, 3),
        "baseline_score_without_location": round(baseline, 3),
        "location_gain": round(augmented - baseline, 3),
        "signals": signals,
        "title_similarity": round(title_similarity, 4),
        "contradicting_claims": contradictions,
        "verified_identity": False,
        "area_semantics": "Only defended interior area contributes; unspecified surface is excluded.",
    }


def identity_verdict(
    *,
    shared_unit_key: bool = False,
    shared_property_cross_reference: bool = False,
    conflicting_unit_keys: bool = False,
    corroborating_unit_fields: int = 0,
) -> str:
    """A review must supply unit-specific evidence, not ranker output or proximity.

    Cross references must name the apartment, not just an agency/development.
    Description similarity, common floors/layouts and pins are supporting evidence.
    """
    if conflicting_unit_keys and (shared_unit_key or shared_property_cross_reference):
        return "unresolved"
    if conflicting_unit_keys:
        return "verified_false"
    if (shared_unit_key or shared_property_cross_reference) and corroborating_unit_fields >= 2:
        return "verified_true"
    return "unresolved"


def matching_gate(reviews: list[dict]) -> dict:
    """Predeclared conservative pilot gate; unresolved proposals do not count true."""
    allowed = {"verified_true", "verified_false", "unresolved"}
    if any(r.get("verdict") not in allowed for r in reviews):
        raise ValueError("Unknown review verdict")
    pair_keys = [(r["harta_source_id"], r["other_source"], r["other_source_id"]) for r in reviews]
    if len(pair_keys) != len(set(pair_keys)):
        raise ValueError("Duplicate review pair")
    counts = {
        k: sum(r["verdict"] == k for r in reviews)
        for k in ["verified_true", "verified_false", "unresolved"]
    }
    # This is pilot yield, not population precision or a calibrated probability.
    rate = counts["verified_true"] / len(reviews) if reviews else None
    verified_anchors = len(
        {r["harta_source_id"] for r in reviews if r["verdict"] == "verified_true"}
    )
    passed = (
        30 <= len(reviews) <= 50
        and verified_anchors >= 30
        and rate >= 0.95
        and counts["verified_false"] == 0
    )
    return {
        "status": "PASS_RESEARCH_SUPPORT_ONLY"
        if passed
        else "NOT_ENABLED_INSUFFICIENT_IDENTITY_EVIDENCE",
        "reviewed_pairs": len(reviews),
        **counts,
        "verified_true_fraction_all_reviewed": rate,
        "precision_among_resolved": counts["verified_true"]
        / (counts["verified_true"] + counts["verified_false"])
        if counts["verified_true"] + counts["verified_false"]
        else None,
        "false_match_rate_among_resolved": counts["verified_false"]
        / (counts["verified_true"] + counts["verified_false"])
        if counts["verified_true"] + counts["verified_false"]
        else None,
        "research_matching_support_enabled": passed,
        "automatic_merge_enabled": False,
        "field_transfer_enabled": False,
        "public_statistics_changed": False,
    }
