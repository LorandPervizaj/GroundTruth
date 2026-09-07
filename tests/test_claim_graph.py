"""Tests for claim dependency graph and reproducibility tuple."""

from groundtruth.claims.graph import (
    dependency_ancestors,
    dependency_descendants,
    impacted_claims,
    validate_dependencies,
)
from groundtruth.claims.registry import Claim, load_claims, register_claim


def test_dependency_chain(tmp_path) -> None:
    path = tmp_path / "registry.csv"
    register_claim(
        Claim(claim_id="GT-100", statement="parser ok", status="published"),
        path=path,
    )
    register_claim(
        Claim(
            claim_id="GT-101",
            statement="invalid rate",
            depends_on="GT-100",
            status="published",
        ),
        path=path,
    )
    register_claim(
        Claim(
            claim_id="GT-102",
            statement="downstream",
            depends_on="GT-101",
            status="draft",
        ),
        path=path,
    )

    claims = load_claims(path)
    ancestors = dependency_ancestors("GT-102", claims)
    assert [c.claim_id for c in ancestors] == ["GT-102", "GT-101", "GT-100"]

    descendants = dependency_descendants("GT-100", claims)
    assert {c.claim_id for c in descendants} == {"GT-101", "GT-102"}


def test_impact_from_parser_version(tmp_path) -> None:
    path = tmp_path / "registry.csv"
    register_claim(
        Claim(claim_id="GT-200", statement="a", parser_version="1.3.0", status="published"),
        path=path,
    )
    register_claim(
        Claim(
            claim_id="GT-201",
            statement="b",
            parser_version="1.3.0",
            depends_on="GT-200",
            status="published",
        ),
        path=path,
    )

    report = impacted_claims(parser_version="1.3.0", claims=load_claims(path))
    assert len(report.direct) == 2
    assert any(c.claim_id == "GT-201" for c in report.all_affected)


def test_validate_dependencies_ok(tmp_path) -> None:
    path = tmp_path / "registry.csv"
    register_claim(Claim(claim_id="GT-300", statement="root"), path=path)
    register_claim(
        Claim(claim_id="GT-301", statement="child", depends_on="GT-300"),
        path=path,
    )
    assert validate_dependencies(load_claims(path)) == []
