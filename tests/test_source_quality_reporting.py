"""CLI, deterministic artifacts, and real pipeline-model SQL integration."""

import csv
import json
from datetime import timedelta

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session
from typer.testing import CliRunner

from groundtruth.analytics.source_quality import build_report, write_report
from groundtruth.analytics.source_quality_models import QualityReport
from groundtruth.analytics.source_quality_population import pipeline_records
from groundtruth.cli import app
from groundtruth.models import (
    InvalidListing,
    NormalizedListing,
    ParsedListing,
    RawListing,
    ScrapeRun,
)
from tests.test_source_quality import AS_OF, record, report


def test_deterministic_reports_and_machine_readable_schema(tmp_path):
    items = [
        record(identity="2"),
        record(),
        record(
            source="merrjep",
            outcome="rejected",
            listing=None,
            error_codes=["parse_error"],
            failure_stage="parse",
        ),
    ]
    first, second = tmp_path / "one", tmp_path / "two"
    write_report(report(items), first)
    write_report(report(list(reversed(items))), second)
    for name in (
        "source_quality_report.json",
        "source_quality_summary.csv",
        "source_quality_report.schema.json",
    ):
        assert (first / name).read_bytes() == (second / name).read_bytes()
    data = QualityReport.model_validate_json((first / "source_quality_report.json").read_text())
    assert data.scoring_policy_version == "1.1.0"
    text = (first / "source_quality_report.json").read_text()
    assert "example.invalid" not in text
    assert "description" not in text
    assert "NaN" not in text and "Infinity" not in text
    with (first / "source_quality_summary.csv").open(newline="") as stream:
        assert len(list(csv.DictReader(stream))) == 2
    assert "$defs" in json.loads((first / "source_quality_report.schema.json").read_text())


def test_cli_fixture_and_normal_help(tmp_path):
    fixture = tmp_path / "fixture.json"
    fixture.write_text(json.dumps([record().model_dump(mode="json")]), encoding="utf-8")
    args = [
        "analytics",
        "source-quality",
        "report",
        "--as-of",
        AS_OF.isoformat(),
        "--fixture",
        str(fixture),
        "--output",
        str(tmp_path / "out"),
        "--segment",
    ]
    result = CliRunner().invoke(app, args)
    assert result.exit_code == 0, result.output
    assert "28 source/segment summaries and 1 listing assessments" in result.output
    assert (tmp_path / "out/source_quality_report.json").exists()
    assert "source-quality" in CliRunner().invoke(app, ["analytics", "--help"]).output


@pytest.mark.parametrize(
    "contents,extra,expected",
    [
        ("[]", [], "No source data"),
        ("not json", [], "input/output failed"),
        ("[]", ["--source", "not-a-portal"], "Unknown source"),
    ],
)
def test_cli_errors_are_clear(tmp_path, contents, extra, expected):
    fixture = tmp_path / "fixture.json"
    fixture.write_text(contents)
    result = CliRunner().invoke(
        app,
        [
            "analytics",
            "source-quality",
            "report",
            "--as-of",
            AS_OF.isoformat(),
            "--fixture",
            str(fixture),
            *extra,
        ],
    )
    assert result.exit_code != 0
    assert expected in result.output


def test_cli_database_error_is_sanitized(monkeypatch):
    from sqlalchemy.exc import OperationalError

    from groundtruth.database import session as db_session

    def unavailable():
        raise OperationalError("secret-password", {}, RuntimeError("private-connection"))

    monkeypatch.setattr(db_session, "get_session_factory", unavailable)
    result = CliRunner().invoke(
        app, ["analytics", "source-quality", "report", "--as-of", "2026-10-21"]
    )
    assert result.exit_code == 1
    assert "database unavailable" in result.output
    assert "secret-password" not in result.output
    assert "private-connection" not in result.output


@pytest.fixture
def pipeline_session():
    """SQLite executes the actual ORM query; only JSONB storage spelling differs."""
    engine = create_engine("sqlite://")
    compiler = engine.dialect.type_compiler_instance
    compiler.visit_JSONB = compiler.visit_JSON
    for model in (ScrapeRun, RawListing, ParsedListing, NormalizedListing, InvalidListing):
        model.__table__.create(engine)
    with Session(engine) as session:
        session.add(ScrapeRun(id=1, spider_name="synthetic", started_at=AS_OF))
        session.flush()
        yield session
    engine.dispose()


def add_raw(session, identity, **kwargs):
    raw = RawListing(
        id=identity,
        source_website="gjirafa",
        source_listing_id=str(identity),
        original_url="https://example.invalid",
        content_hash=str(identity),
        raw_payload={},
        scrape_run_id=1,
        scraped_at=AS_OF,
        **kwargs,
    )
    session.add(raw)
    session.flush()
    return raw


def add_parsed(session, raw, identity, **kwargs):
    parsed = ParsedListing(
        id=identity,
        raw_listing_id=raw.id,
        scrape_run_id=1,
        source_website=raw.source_website,
        source_listing_id=raw.source_listing_id,
        original_url=raw.original_url,
        parsed_at=AS_OF,
        **kwargs,
    )
    session.add(parsed)
    session.flush()
    return parsed


def test_pipeline_reader_includes_raw_failures_quarantine_and_pending(pipeline_session):
    session = pipeline_session
    good = add_raw(session, 1)
    parsed = add_parsed(session, good, 1)
    values = record().listing.model_dump(
        exclude={"parsed_listing_id", "scrape_run_id", "scraped_at"}
    )
    session.add(
        NormalizedListing(
            id=1,
            parsed_listing_id=parsed.id,
            scrape_run_id=1,
            normalized_at=AS_OF,
            scraped_at=AS_OF,
            **values,
        )
    )
    broken = add_raw(session, 2)
    session.add(
        InvalidListing(
            raw_listing_id=broken.id, stage="parse", error_codes=["parse_error"], created_at=AS_OF
        )
    )
    invalid = add_raw(session, 3)
    rejected_parsed = add_parsed(
        session, invalid, 3, sale_price=-1, listing_type="sale", property_type="apartment"
    )
    # The production ETL links validation failures to parsed IDs, not normalized IDs.
    session.add(
        InvalidListing(
            parsed_listing_id=rejected_parsed.id,
            stage="validate",
            error_codes=["price_too_low"],
            created_at=AS_OF,
        )
    )
    add_raw(session, 4)
    session.flush()
    mutations = []
    statements = []

    def watch(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement)
        if not statement.lstrip().upper().startswith("SELECT"):
            mutations.append(statement)

    event.listen(session.bind, "before_cursor_execute", watch)
    rows = pipeline_records(session, sources=["gjirafa"], as_of=AS_OF, window_days=30)
    event.remove(session.bind, "before_cursor_execute", watch)
    assert not mutations
    population_sql = statements[0]
    assert "raw_payload" not in population_sql and "raw_html" not in population_sql
    assert "description_original" not in population_sql
    assert len(statements) == 2  # Population + batched quarantine lookup; no deferred-text queries.
    summary = build_report(rows, sources=["gjirafa"], as_of=AS_OF).sources[0]
    assert (
        summary.unique_source_listing_count,
        summary.accepted_count,
        summary.rejected_count,
        summary.pending_count,
    ) == (4, 1, 2, 1)
    assert summary.error_code_counts["parse_error"] == 1
    assert summary.proposed_weight == 1


def test_reader_bounds_processing_time_and_ignores_superseded_failure(pipeline_session):
    session = pipeline_session
    raw = add_raw(session, 1)
    session.add(
        InvalidListing(
            raw_listing_id=raw.id,
            stage="parse",
            error_codes=["parse_error"],
            created_at=AS_OF - timedelta(hours=1),
        )
    )
    parsed = add_parsed(session, raw, 1)
    # A later reparse must not be selected at the earlier evaluation time.
    later = add_parsed(session, raw, 2)
    later.parsed_at = AS_OF + timedelta(days=1)
    session.flush()
    rows = pipeline_records(session, sources=["gjirafa"], as_of=AS_OF, window_days=30)
    assert rows[0].outcome == "pending"
    assert rows[0].listing.parsed_listing_id is None  # raw parsed transfer has no normalized FK
    assert not rows[0].error_codes
    assert parsed.id == 1
