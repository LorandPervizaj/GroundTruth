"""Offline evidence summaries; no pipeline writes or source-weight activation."""

from __future__ import annotations

from collections import Counter
from math import sqrt

VERDICTS = frozenset({"VERIFIED_TRUE", "VERIFIED_FALSE", "UNRESOLVED"})
COMPARABLE = frozenset({"source_agreement", "parser_error", "normalizer_error"})
FIELD_CLASSES = COMPARABLE | frozenset(
    {
        "unknown",
        "semantic_unknown",
        "source_placeholder",
        "source_internal_conflict",
        "not_applicable",
    }
)


def wilson(successes: int, trials: int) -> list[float] | None:
    """95% binomial reference interval; callers must disclose sampling limitations."""
    if not 0 <= successes <= trials:
        raise ValueError("Invalid binomial denominator")
    if not trials:
        return None
    z = 1.959963984540054
    p = successes / trials
    scale = 1 + z * z / trials
    center = (p + z * z / (2 * trials)) / scale
    half = z * sqrt(p * (1 - p) / trials + z * z / (4 * trials * trials)) / scale
    return [round(max(0, center - half), 6), round(min(1, center + half), 6)]


def matching_metrics(reviews: list[dict]) -> dict:
    ids = [r["pair_id"] for r in reviews]
    if len(ids) != len(set(ids)) or any(r["verdict"] not in VERDICTS for r in reviews):
        raise ValueError("Duplicate pair or unsupported verdict")
    if any(r["verdict"] != "UNRESOLVED" and not r.get("decision_evidence") for r in reviews):
        raise ValueError("Verified verdict requires documented evidence")
    counts = Counter(r["verdict"] for r in reviews)
    resolved = counts["VERIFIED_TRUE"] + counts["VERIFIED_FALSE"]
    return {
        "reviewed": len(reviews),
        **{v: counts[v] for v in sorted(VERDICTS)},
        "resolved_denominator": resolved,
        "precision_resolved_only": counts["VERIFIED_TRUE"] / resolved if resolved else None,
        "false_fraction_resolved_only": counts["VERIFIED_FALSE"] / resolved if resolved else None,
        "precision_binomial_reference_95": wilson(counts["VERIFIED_TRUE"], resolved),
        "population_precision": None,
        "threshold_validated": False,
        "location_gain_pairs": sum(r["location_gain"] > 0 for r in reviews),
        "verified_true_location_gain_pairs": sum(
            r["location_gain"] > 0 and r["verdict"] == "VERIFIED_TRUE" for r in reviews
        ),
        "research_matching_support_enabled": False,
        "automatic_merge_enabled": False,
        "field_transfer_enabled": False,
    }


def field_metrics(rows: list[dict]) -> dict:
    """Keep each source/stratum/field denominator separate; never pool correlated fields."""
    if any(r["classification"] not in FIELD_CLASSES for r in rows):
        raise ValueError("Unsupported field classification")
    result = {}
    keys = sorted({(r["source"], r["stratum"], r["field"]) for r in rows})
    for source, stratum, field in keys:
        selected = [
            r for r in rows if (r["source"], r["stratum"], r["field"]) == (source, stratum, field)
        ]
        counts = Counter(r["classification"] for r in selected)
        comparable = sum(counts[c] for c in COMPARABLE)
        result.setdefault(source, {}).setdefault(stratum, {})[field] = {
            "sampled_listings": len(selected),
            "counts": dict(sorted(counts.items())),
            "comparable": comparable,
            "source_representation_accuracy": counts["source_agreement"] / comparable
            if comparable
            else None,
            "unknown_or_noncomparable": len(selected) - comparable,
            "wilson_reference_95": wilson(counts["source_agreement"], comparable)
            if stratum == "random_segment_stratum"
            else None,
        }
    return result
