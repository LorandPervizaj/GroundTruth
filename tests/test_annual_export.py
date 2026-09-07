"""Tests for annual report cache export."""

from datetime import date

import pandas as pd

from groundtruth.analytics.annual_export import (
    corpus_data_revision,
    export_annual_report,
    finalize_annual_report_payload,
    load_annual_report_cache,
)
from groundtruth.analytics.annual_report import build_annual_report_from_dataframe


def test_finalize_adds_generated_at_and_versions() -> None:
    base = build_annual_report_from_dataframe(pd.DataFrame(), cutoff_date=date(2025, 6, 1))
    payload = finalize_annual_report_payload(base, data_revision="test-rev")
    assert payload["generated_at"]
    assert payload["data_revision"] == "test-rev"
    assert payload["methodology"]["gazetteer_version"]
    assert payload["methodology"]["parser_versions"]


def test_export_and_load_roundtrip(tmp_path, require_postgres) -> None:
    from groundtruth.database.session import get_session_factory

    out = tmp_path / "annual_report.json"
    session = get_session_factory()()
    try:
        path = export_annual_report(session, output=out)
    finally:
        session.close()
    assert path == out
    loaded = load_annual_report_cache(out)
    assert loaded is not None
    assert loaded["generated_at"]
    assert "kpis" in loaded
    assert loaded.get("data_revision")


def test_corpus_data_revision_returns_string(require_postgres) -> None:
    from groundtruth.database.session import get_session_factory

    session = get_session_factory()()
    try:
        rev = corpus_data_revision(session)
    finally:
        session.close()
    assert isinstance(rev, str)
