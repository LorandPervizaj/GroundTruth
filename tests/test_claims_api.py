"""Tests for structured claim API export."""

import json

from groundtruth.claims.registry import Claim


def test_reasoning_trace_structure() -> None:
    claim = Claim(
        claim_id="GT-041",
        statement="Furnished premium after controls",
        status="published",
        estimate="0.118",
        lower_ci="0.081",
        upper_ci="0.152",
        evidence_grade="A",
        causal_level="C1",
        maturity="M3",
        depends_on="GT-002;GT-015",
        half_life="2_years",
        retest_interval="quarterly",
        n="412",
    )
    trace = claim.to_reasoning_trace(policy_id="DP-003")
    assert trace["claim"] == "GT-041"
    assert trace["depends_on"] == ["GT-002", "GT-015"]
    assert trace["evidence"] == "A"
    assert trace["causal"] == "C1"
    assert trace["policy"] == "DP-003"
    assert trace["uncertainty"] == {"lower": 0.081, "upper": 0.152}


def test_export_claims_api_script(tmp_path, monkeypatch) -> None:
    from scripts import export_claims_api

    from groundtruth.claims.registry import register_claim

    reg = tmp_path / "registry.csv"
    register_claim(
        Claim(claim_id="GT-900", statement="test", status="published", estimate="1.0"),
        path=reg,
    )
    monkeypatch.setattr("groundtruth.claims.registry.REGISTRY_PATH", reg)
    out = tmp_path / "claims.json"
    export_claims_api.export(output=out, published_only=True)
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["count"] == 1
    assert data["claims"][0]["claim"] == "GT-900"
    assert "edges" in data
