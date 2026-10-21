"""No-network recovery, real ORM persistence and locale/source conflict regressions."""

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import Session

from groundtruth.analytics.source_quality import build_report
from groundtruth.analytics.source_quality_population import pipeline_records
from groundtruth.models import (
    InvalidListing,
    NormalizedListing,
    ParsedListing,
    RawListing,
    ScrapeRun,
)
from groundtruth.models.etl import EtlMetrics
from groundtruth.models.lineage import DataLineage
from groundtruth.scrapers.spiders.harta import (
    FINGERPRINT_VERSION,
    HartaRawListingPipeline,
    HartaSpider,
    load_harta_state,
)
from groundtruth.services.harta_parsing import number
from tests.test_harta import KEY, html, parse, prop, response


@pytest.mark.parametrize(
    "value,expected",
    [
        ("€ 120.000", "120000"),
        ("120 000 EUR", "120000"),
        ("1.500,50", "1500.50"),
        ("1,500.50", "1500.50"),
        ("85,5", "85.5"),
        ("1.500", "1500"),
        ("1,500", "1500"),
        ("1.23.456", None),
        ("1,500,50", None),
        ("1.2.3", None),
        ("NaN", None),
        (float("inf"), None),
        (True, None),
        ("-100", None),
    ],
)
def test_locale_numbers(value, expected):
    from decimal import Decimal

    assert number(value) == (Decimal(expected) if expected else None)


@pytest.mark.parametrize(
    "changes,issue",
    [
        ({"property_type": "studio", "bedrooms": 0}, None),
        ({"description": "Paradhënie: 20000 €; kësti mujor: 300 €. Çmimi: 120.000 €"}, None),
        ({"description": "Çmimi: 1500 €/m²"}, None),
        ({"bedrooms": None, "description": "Banesë 2+1"}, None),
        ({"description": "Jepet me qira banesa"}, "harta_description_transaction_conflict"),
        ({"description": "Shitet shtëpi"}, "harta_description_property_type_conflict"),
        ({"living_area": 100, "surface_area": 80}, "harta_interior_exceeds_total_area"),
        ({"latitude": 0, "longitude": 0}, "harta_invalid_source_coordinates"),
        ({"latitude": "NaN", "longitude": 21.1}, "harta_invalid_source_coordinates"),
        ({"latitude": 42.65, "longitude": None}, "harta_invalid_source_coordinates"),
    ],
)
def test_additional_critical_cases(changes, issue):
    listing = parse(prop(**changes))
    issues = listing.extra_fields["source_validation_issues"]
    assert (issue in issues) if issue else not issues
    if changes.get("bedrooms", 2) is None:
        assert listing.bedrooms is None


def test_observed_redacted_fixture_and_jsonld_conflict():
    from groundtruth.scrapers.harta_contract import property_from_html

    fixture = json.loads(
        Path("tests/fixtures/harta/observed_redacted.json").read_text(encoding="utf8")
    )
    listing = parse(fixture["property"])
    assert listing.extra_fields["source_validation_issues"] == [
        "harta_description_price_conflict",
        "harta_missing_interior_area",
    ]
    page = html("property", prop(listing_type="rent"))
    page += '<script type="application/ld+json">{"@type":"RealEstateListing","additionalProperty":[{"name":"Rental Period","value":"daily"}]}</script>'
    assert (
        "harta_conflicting_rental_period"
        in parse(property_from_html(page)).extra_fields["source_validation_issues"]
    )


@pytest.fixture
def database():
    engine = create_engine("sqlite://")
    engine.dialect.type_compiler_instance.visit_JSONB = (
        engine.dialect.type_compiler_instance.visit_JSON
    )
    for model in (
        ScrapeRun,
        RawListing,
        ParsedListing,
        NormalizedListing,
        InvalidListing,
        EtlMetrics,
        DataLineage,
    ):
        model.__table__.create(engine)
    yield engine
    engine.dispose()


def test_committed_checkpoint_survives_no_close_duplicate_and_failed_item(database, monkeypatch):
    from groundtruth.scrapers import pipelines

    monkeypatch.setattr(pipelines, "get_session_factory", lambda: lambda: Session(database))
    spider = HartaSpider()
    pipeline = HartaRawListingPipeline()
    pipeline.open_spider(spider)
    try:
        # Real inherited RawListing/PipelineService persistence, no mock store.
        item = list(
            spider.parse_listing_page(
                response(
                    "property",
                    prop(),
                    meta={
                        "source_id": KEY,
                        "summary_fingerprint": "f1",
                    },
                )
            )
        )[0]
        pipeline.process_item(item, spider)
        with Session(database) as read:
            counts = []
            event.listen(database, "before_cursor_execute", lambda *args: counts.append(1))
            state = load_harta_state(read)
            assert len(counts) == 2
            assert state[KEY][0] == "f1"  # available BEFORE close_spider
        # Same detail, different discovery metadata, no extra raw version.
        duplicate = list(
            spider.parse_listing_page(
                response(
                    "property",
                    prop(),
                    meta={
                        "source_id": KEY,
                        "summary_fingerprint": "f2",
                    },
                )
            )
        )[0]
        assert duplicate["content_hash"] == item["content_hash"]
        pipeline.process_item(duplicate, spider)
        with Session(database) as read:
            assert len(list(read.scalars(select(RawListing)))) == 1
            assert load_harta_state(read)[KEY][0] == "f2"
        # Uncommitted pending detail callbacks must NEVER become checkpoints.
        key2 = "22222222-2222-4222-8222-222222222222"
        spider._detail_checks[key2] = {
            "checked_at": datetime.now(UTC).isoformat(),
            "summary_fingerprint": "unstored",
        }
        run_id = spider.scrape_run_id
        pipeline.close_spider(spider)
        with Session(database) as read:
            run = read.get(ScrapeRun, run_id)
            assert key2 not in run.metadata_["harta_detail_checks"]
            assert run.status.value == "failed"  # current discovery remains partial
    finally:
        pipeline._session.close()


def test_corrupt_or_unrelated_checkpoint_cannot_skip_current_raw(database):
    at = datetime.now(UTC)
    with Session(database) as session:
        session.add(
            RawListing(
                source_website="harta",
                source_listing_id=KEY,
                scrape_run_id=1,
                original_url="https://harta.info/property/" + KEY,
                content_hash="stored",
                raw_payload={"property": prop()},
                scraped_at=at - timedelta(days=8),
            )
        )
        session.add(
            ScrapeRun(
                id=1,
                spider_name="harta",
                metadata_={
                    "harta_detail_checks": {
                        KEY: {
                            "checked_at": at.isoformat(),
                            "summary_fingerprint": "false",
                            "detail_content_hash": "not-stored",
                            "fingerprint_version": FINGERPRINT_VERSION,
                        },
                    }
                },
            )
        )
        session.commit()
        assert load_harta_state(session)[KEY][0] is None
        run = session.scalar(select(ScrapeRun))
        run.metadata_ = {
            "harta_detail_checks": {
                KEY: {
                    "checked_at": "bad",
                    "summary_fingerprint": "false",
                    "detail_content_hash": "stored",
                    "fingerprint_version": FINGERPRINT_VERSION,
                }
            }
        }
        session.commit()
        assert load_harta_state(session)[KEY][0] is None


def test_real_orm_etl_validation_quality_and_parser_replay(database, monkeypatch):
    from groundtruth.models.enums import PipelineStage
    from groundtruth.scrapers.harta_contract import minimized_property
    from groundtruth.services import harta_parsing
    from groundtruth.services.etl import EtlService
    from groundtruth.services.normalization import NormalizationService
    from groundtruth.services.parsing import ParsingService

    monkeypatch.setattr("groundtruth.services.etl.log_neighborhood_failure", lambda **kw: None)
    with Session(database) as session:
        # Existing normalized repository dumps JSON scalars. PostgreSQL accepts
        # ISO dates/times on insert; SQLite requires Python objects. Emulate only
        # that driver cast without mocking persistence, ETL or validation.
        def sqlite_temporal_cast(session, *_):
            from datetime import date

            for entity in session.new:
                if isinstance(entity, NormalizedListing):
                    if isinstance(entity.listing_date, str):
                        entity.listing_date = date.fromisoformat(entity.listing_date)
                    if isinstance(entity.scraped_at, str):
                        entity.scraped_at = datetime.fromisoformat(entity.scraped_at)

        event.listen(session, "before_flush", sqlite_temporal_cast)
        run = ScrapeRun(spider_name="harta")
        session.add(run)
        session.flush()
        raw = RawListing(
            source_website="harta",
            source_listing_id=KEY,
            original_url="https://harta.info/property/" + KEY,
            scrape_run_id=run.id,
            content_hash="real-orm-test",
            raw_payload={"property": minimized_property(prop(description="Çmimi: 130000 €"))},
        )
        session.add(raw)
        session.commit()
        service = EtlService(session)
        service._normalizer = (
            NormalizationService()
        )  # deterministic local gazetteer; no reference DB
        metrics = service.run(source="harta")
        assert metrics.normalized_success == metrics.validation_failed == 1
        invalid = session.scalar(select(InvalidListing))
        assert invalid.stage == PipelineStage.VALIDATE
        assert "harta_description_price_conflict" in invalid.error_codes
        records = pipeline_records(
            session,
            sources=["harta"],
            as_of=datetime.now(UTC) + timedelta(seconds=1),
            window_days=30,
        )
        report = build_report(
            records, sources=["harta"], as_of=datetime.now(UTC) + timedelta(seconds=1)
        )
        assert report.scoring_policy_version == "1.1.0"
        assert report.sources[0].rejected_count == 1 and report.sources[0].proposed_weight == 1
        # Stored raw replay on parser upgrade needs no additional source request.
        monkeypatch.setattr(harta_parsing, "PARSER_VERSION", "future-test-harta")
        assert ParsingService().parse_raw(raw).parser_version == "future-test-harta"


def test_wall_budget_and_harta_command_parameters():
    from time import monotonic
    from types import SimpleNamespace
    from unittest.mock import MagicMock

    from scrapy import Request
    from scrapy.exceptions import IgnoreRequest

    from groundtruth.crawl.spider_commands import _build_crawl_command
    from groundtruth.scrapers.spiders.harta import HartaAccessMiddleware

    spider = HartaSpider(max_seconds="1")
    spider._started_clock = monotonic() - 2
    spider.crawler = SimpleNamespace(engine=MagicMock())
    with pytest.raises(IgnoreRequest):
        HartaAccessMiddleware().process_request(
            Request("https://harta.info/prona/banesa/prishtine"), spider
        )
    assert spider.run_status() == "budget_exhausted"
    command = _build_crawl_command(
        "harta", {"max_listings": "20", "max_seconds": "60", "crawl_window": "{}"}
    )
    assert command[command.index("--max-listings") + 1] == "20"
    assert command[command.index("--max-seconds") + 1] == "60"
    assert "--crawl-window" in command


def test_relative_date_conflict_preserves_absolute_and_address_conflict():
    from groundtruth.scrapers.harta_contract import property_from_html

    old = (datetime.now(UTC) - timedelta(days=10)).isoformat()
    page = html("property", prop(created_at=old)) + "<div>Shpallur më një datë · sot</div>"
    listing = parse(property_from_html(page))
    assert listing.listing_date.isoformat() == old[:10]
    assert "harta_relative_publication_conflict" in listing.extra_fields["source_validation_issues"]
    listing = parse(prop(address="Rruga X, Fushë Kosovë, Kosovë"))
    assert "harta_address_municipality_conflict" in listing.extra_fields["source_validation_issues"]


def test_incremental_scheduling_measurement_is_explicitly_synthetic():
    import time
    from uuid import UUID

    summaries = [prop(id=str(UUID(int=n + 1))) for n in range(50)]
    first = HartaSpider(max_listings="50")
    started = time.perf_counter()
    requests = list(first.parse_index_page(response("listings", summaries)))
    known = {
        r.meta["source_id"]: (r.meta["summary_fingerprint"], datetime.now(UTC)) for r in requests
    }
    second = HartaSpider(max_listings="50", known=known)
    repeat = list(second.parse_index_page(response("listings", summaries)))
    assert len(requests) == 50 and repeat == []
    assert second.metrics["unchanged"] == 50
    # Scheduling only; these are NOT actual HTTP counts or live pilot savings.
    artifact = {
        "population": "50 synthetic summaries; in-memory scheduling, no HTTP",
        "first_scheduled_requests": 1 + len(requests),
        "repeat_scheduled_requests": 1 + len(repeat),
        "avoided_detail_requests": 50,
        "scheduling_savings_fraction": 50 / 51,
        "elapsed_seconds": time.perf_counter() - started,
        "live_performance_claim": False,
    }
    output = Path("reports/generated/harta/fixture_incremental_comparison.json")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(artifact, indent=2), encoding="utf8")
