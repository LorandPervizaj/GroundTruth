from __future__ import annotations

import pytest

from groundtruth.analytics.statistical_qa import evaluate_lookup_payload


def _payload() -> dict:
    return {
        "entity_type": "neighborhood",
        "slug": "ulpiana",
        "total_listings": 100,
        "corpus_revision": "R",
        "pulse": {
            "median_sale_psm_eur": 2000,
            "average_sale_psm_eur": 2000,
            "median_rent_psm_eur": 5,
            "average_rent_psm_eur": 5,
            "recent_valid_listings": 100,
            "active_listings": 100,
            "metrics": {
                "median_sale_psm": {
                    "sample_n": 50,
                    "statistic": "median",
                    "population": "recent.sale.apartment_studio",
                }
            },
        },
        "bedroom_breakdown": [
            {"bedrooms": 1, "sale_sample_n": 20, "rent_sample_n": 30, "union_sample_n": 50}
        ],
        "size_breakdown": [],
    }


def test_valid_payload_passes() -> None:
    assert evaluate_lookup_payload(_payload(), manifest_revision="R") == []


@pytest.mark.parametrize(
    "mutation,code",
    [
        (lambda p: p.update(total_listings=-1), "NEGATIVE_INVENTORY"),
        (lambda p: p.update(corpus_revision="wrong"), "CORPUS_REVISION_MISMATCH"),
        (lambda p: p["pulse"].update(average_sale_psm_eur=999), "DEPRECATED_ALIAS_DIVERGENCE"),
        (
            lambda p: p["pulse"]["metrics"]["median_sale_psm"].update(sample_n=101),
            "IMPOSSIBLE_SAMPLE_N",
        ),
        (
            lambda p: p["pulse"]["metrics"]["median_sale_psm"].update(population="recent.all"),
            "WRONG_REGISTERED_POPULATION",
        ),
        (
            lambda p: p["bedroom_breakdown"][0].update(sale_sample_n=51),
            "BUCKET_SAMPLE_EXCEEDS_UNION",
        ),
    ],
)
def test_hard_failures_are_detected(mutation, code: str) -> None:
    payload = _payload()
    mutation(payload)
    assert code in {issue.code for issue in evaluate_lookup_payload(payload, manifest_revision="R")}


def test_large_previous_release_delta_warns_with_evidence() -> None:
    current = _payload()
    previous = _payload()
    previous["pulse"]["median_sale_psm_eur"] = 1000
    issues = evaluate_lookup_payload(current, manifest_revision="R", previous=previous)
    issue = next(issue for issue in issues if issue.code == "LARGE_RELEASE_DELTA")
    assert issue.level == "WARN"
    assert issue.evidence["delta_pct"] == 100.0
