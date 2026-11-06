"""Unknowns and enriched samples must not manufacture accuracy or confidence."""

import pytest

from groundtruth.analytics.evidence_verification import field_metrics, matching_metrics, wilson


def test_unresolved_matching_has_no_error_rate():
    value = matching_metrics([{"pair_id": "x", "verdict": "UNRESOLVED", "location_gain": 20}])
    assert value["precision_resolved_only"] is None
    assert value["false_fraction_resolved_only"] is None
    assert not value["threshold_validated"]


def test_verification_requires_evidence_and_unique_pairs():
    row = {"pair_id": "x", "verdict": "VERIFIED_TRUE", "location_gain": 0}
    with pytest.raises(ValueError, match="evidence"):
        matching_metrics([row])
    row["decision_evidence"] = ["independently inspected multiroom correspondence"]
    with pytest.raises(ValueError, match="Duplicate"):
        matching_metrics([row, row])
    assert matching_metrics([row])["population_precision"] is None


def test_field_unknowns_and_failure_enrichment_have_separate_denominators():
    rows = [
        {"source": "s", "field": "price", "stratum": stratum, "classification": label}
        for stratum, label in [
            ("random_segment_stratum", "source_agreement"),
            ("random_segment_stratum", "unknown"),
            ("failure_enriched", "parser_error"),
        ]
    ]
    result = field_metrics(rows)["s"]
    random = result["random_segment_stratum"]["price"]
    assert random["comparable"] == 1
    assert random["unknown_or_noncomparable"] == 1
    assert random["source_representation_accuracy"] == 1
    assert result["failure_enriched"]["price"]["wilson_reference_95"] is None


def test_empty_and_small_sample_uncertainty():
    assert wilson(0, 0) is None
    assert wilson(1, 3) == [0.061492, 0.79234]
    with pytest.raises(ValueError):
        wilson(2, 1)


def test_unknown_classification_cannot_silently_change_denominators():
    with pytest.raises(ValueError, match="classification"):
        field_metrics([{"classification": "probably_correct"}])
