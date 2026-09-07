"""Tests for Value of Information and Knowledge Capital."""

from groundtruth.analytics.knowledge_capital import claim_quality_score, knowledge_capital
from groundtruth.analytics.reviewer_agreement import field_agreement
from groundtruth.analytics.voi import value_of_information
from groundtruth.claims.registry import Claim


def test_voi_ranks_high_impact_first() -> None:
    low = value_of_information(decision_impact="low", uncertainty="unknown", cost_hours=8)
    high = value_of_information(decision_impact="very_high", uncertainty="unknown", cost_hours=8)
    furnished = value_of_information(
        decision_impact="very_high", uncertainty="unknown", cost_hours=6
    )
    assert high > low
    assert furnished > low


def test_structural_claim_scores_higher() -> None:
    desc = Claim(
        claim_id="GT-800",
        statement="median rent",
        status="published",
        claim_structure="descriptive",
        evidence_grade="C",
        maturity="M1",
        impact="medium",
    )
    struct = Claim(
        claim_id="GT-801",
        statement="neighborhood dominates",
        status="published",
        claim_structure="structural",
        evidence_grade="C",
        maturity="M1",
        impact="medium",
    )
    assert claim_quality_score(struct) > claim_quality_score(desc)


def test_cohens_kappa_perfect_agreement() -> None:
    pairs = [("yes", "yes")] * 10 + [("no", "no")] * 10
    stats = field_agreement(pairs, field="price")
    assert stats.agreement_rate == 1.0
    assert stats.cohens_kappa == 1.0


def test_knowledge_capital_sums_published() -> None:
    claims = [
        Claim(claim_id="GT-810", statement="a", status="published", impact="high", maturity="M2"),
        Claim(claim_id="GT-811", statement="b", status="draft", impact="high"),
    ]
    assert knowledge_capital(claims) > 0
    assert knowledge_capital(claims) == claim_quality_score(claims[0])
