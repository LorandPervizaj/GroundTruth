"""A recreated disposable SQL sidecar has no reference rows yet."""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pandas as pd

from groundtruth.analytics import coverage


def test_empty_reference_catalog_keeps_coverage_schema(monkeypatch):
    session = MagicMock()
    session.query.return_value.order_by.return_value.all.return_value = []
    monkeypatch.setattr(coverage, "rent_comparables_dataframe", lambda _: pd.DataFrame())
    monkeypatch.setattr(coverage, "sale_comparables_dataframe", lambda _: pd.DataFrame())
    frame = coverage.build_neighborhood_coverage_table(session)
    assert frame.empty
    assert {
        "neighborhood_id",
        "rent_comps",
        "sale_comps",
        "rent_estimate_ready",
        "sale_estimate_ready",
    }.issubset(frame.columns)


def test_empty_sql_sidecar_coverage_snapshot_is_valid(monkeypatch):
    from groundtruth.analytics import annual_export
    from groundtruth.services import coverage_metrics

    session = MagicMock()
    session.query.return_value.all.return_value = []
    columns = [
        "neighborhood_id",
        "rent_comps",
        "sale_comps",
        "rent_estimate_ready",
        "sale_estimate_ready",
    ]
    monkeypatch.setattr(
        coverage_metrics,
        "build_neighborhood_coverage_table",
        lambda _: pd.DataFrame(columns=columns),
    )
    monkeypatch.setattr(
        coverage_metrics,
        "active_corpus_bundle",
        lambda _: SimpleNamespace(active=pd.DataFrame(), deduped=pd.DataFrame()),
    )
    monkeypatch.setattr(annual_export, "corpus_last_updated", lambda _: None)
    snapshot = coverage_metrics.build_coverage_snapshot(session)
    assert snapshot.raw_listings == snapshot.canonical_listings == snapshot.neighborhoods_total == 0
