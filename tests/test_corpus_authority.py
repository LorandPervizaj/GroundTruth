"""Active corpus must be the public analytics source of truth."""

from __future__ import annotations

import ast
from pathlib import Path

from groundtruth.analytics.corpus_filters import ACTIVE_CORPUS_WHERE, INFORMAL_SOURCE_WEBSITES

ROOT = Path(__file__).resolve().parents[1] / "src" / "groundtruth"

PUBLIC_ANALYTICS_MODULES = [
    "analytics/annual_report.py",
    "analytics/source_skew.py",
    "analytics/valuation.py",
    "services/budget_match.py",
    "services/lookup.py",
    "services/rent_yield.py",
    "services/search.py",
]


def test_active_corpus_where_excludes_informal_and_invalid() -> None:
    sql = ACTIVE_CORPUS_WHERE
    assert "invalid_listings" in sql
    assert "parser_version" in sql
    for source in INFORMAL_SOURCE_WEBSITES:
        assert source in sql


def test_public_analytics_modules_reference_active_corpus() -> None:
    missing: list[str] = []
    for rel in PUBLIC_ANALYTICS_MODULES:
        path = ROOT / rel
        src = path.read_text(encoding="utf-8")
        ok = (
            "active_corpus_dataframe" in src
            or "ACTIVE_CORPUS_WHERE" in src
            or "active_corpus_bundle" in src
        )
        if not ok:
            missing.append(rel)
    assert not missing, f"public modules missing active corpus reference: {missing}"


def test_public_modules_parse() -> None:
    for rel in PUBLIC_ANALYTICS_MODULES:
        tree = ast.parse((ROOT / rel).read_text(encoding="utf-8"))
        assert tree is not None
