"""Synthetic contract and pipeline tests; these do not replace a live Gate 3 pilot."""

from copy import deepcopy
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from scrapy.exceptions import CloseSpider, IgnoreRequest
from scrapy.http import HtmlResponse, Request

from groundtruth.models.pipeline import RawListing
from groundtruth.scrapers.harta_contract import (
    HartaContractError,
    hydration_field,
    minimized_property,
    property_from_html,
)
from groundtruth.scrapers.hashing import content_hash
from groundtruth.scrapers.spiders.harta import HartaAccessMiddleware, HartaSpider
from groundtruth.services.harta_parsing import HartaParsingService
from groundtruth.services.normalization import NormalizationService
from groundtruth.services.parsing import ParsingService

KEY = "11111111-1111-4111-8111-111111111111"
NOW = datetime.now(UTC)


def prop(**changes):
    result = dict(
        id=KEY,
        city="Prishtinë",
        status="active",
        property_type="apartment",
        listing_type="buy",
        price=120000,
        price_total=120000,
        price_unit="total",
        currency="EUR",
        living_area=80,
        surface_area=90,
        surface_unit="m2",
        bedrooms=2,
        bathrooms=1,
        address="Rruga A, Prishtinë, Kosovë",
        created_at="2026-07-12 21:53:51.286+00",
        features={"rental_period": "monthly"},
    )
    result.update(changes)
    return result


def parse(p):
    return HartaParsingService().parse_payload(
        {"property": p}, url="https://harta.info/property/" + KEY
    )


def literal(value):
    import json

    if isinstance(value, dict):
        return "{" + ",".join(k + ":" + literal(v) for k, v in value.items()) + "}"
    if isinstance(value, list):
        return "[" + ",".join(literal(v) for v in value) + "]"
    return json.dumps(value)


def html(field, value):
    return (
        '<script id="$tsr-stream-barrier">x={' + field + ":$R[16]=" + literal(value) + "}</script>"
    )


def response(field, value, *, meta=None, status=200):
    return HtmlResponse(
        "https://harta.info/prona/banesa/prishtine",
        encoding="utf8",
        body=html(field, value).encode(),
        status=status,
        request=Request("https://harta.info/prona/banesa/prishtine", meta=meta or {}),
    )


@pytest.mark.parametrize(
    "changes,issue,price,area",
    [
        ({}, None, "120000", 80),
        ({"listing_type": "rent", "price": 500, "price_total": 500}, None, "500", 80),
        ({"price": None, "price_total": None}, "harta_missing_total_price", None, 80),
        (
            {"living_area": None, "surface_area": None},
            "harta_missing_interior_area",
            "120000",
            None,
        ),
        ({"living_area": 70, "surface_area": 100}, None, "120000", 70),
        (
            {"price_unit": "sqm", "price": 1500, "price_total": None},
            "harta_missing_total_price",
            None,
            80,
        ),
        ({"price_unit": "sqm", "price": 1500}, None, "120000", 80),
        ({"price": "bad", "price_total": "bad"}, "harta_missing_total_price", None, 80),
        ({"description": "Çmimi: 130000 €"}, "harta_description_price_conflict", "120000", 80),
        ({"description": "Sipërfaqja: 99 m²"}, "harta_description_area_conflict", "120000", 80),
        (
            {"listing_type": "rent", "features": {"rental_period": "daily"}},
            "harta_unconfirmed_monthly_rent",
            "120000",
            80,
        ),
        ({"bedrooms": None, "bathrooms": None}, None, "120000", 80),
        ({"created_at": None}, None, "120000", 80),
        ({"created_at": "not a date"}, None, "120000", 80),
        ({"currency": "ALL"}, "harta_unsupported_currency", "120000", 80),
        ({"surface_unit": "sqft"}, "harta_unsupported_area_unit", "120000", None),
    ],
)
def test_parser_critical_fixture_cases(changes, issue, price, area):
    parsed = parse(prop(**changes))
    assert (parsed.sale_price or parsed.rent_price) == (Decimal(price) if price else None)
    assert parsed.area_sqm == area
    if issue:
        assert issue in parsed.extra_fields["source_validation_issues"]
    else:
        assert parsed.extra_fields["source_validation_issues"] == []
    if changes.get("bedrooms", 2) is None:
        assert parsed.bedrooms is None
    if "created_at" in changes:
        assert parsed.listing_date is None


@pytest.mark.parametrize(
    "changes",
    [
        {"city": "Fushë Kosovë"},
        {"city": "Obiliq"},
        {"city": None},
        {"city": "Prishtina / Fushë Kosovë"},
        {"property_type": "house"},
        {"listing_type": "holiday"},
        {"status": "removed"},
        {"id": "bad"},
    ],
)
def test_scope_and_identity_fail_closed(changes):
    with pytest.raises(HartaContractError):
        parse(prop(**changes))


def test_privacy_and_provenance_roundtrip():
    p = prop(
        latitude=42.65,
        longitude=21.15,
        agent_email="private@example.invalid",
        agent_phone="+38312345678",
        owner_id="private",
        images=["private.jpg"],
        description="Çmimi: 120000 € Kontakt: private@example.invalid +38312345678",
    )
    minimized = minimized_property(p)
    text = str(minimized)
    assert "private" not in text and "+383" not in text and "description'" not in text
    parsed = parse(minimized)
    normalized, _ = NormalizationService().normalize(parsed)
    assert normalized.geocode_precision == "source_coords"
    assert parsed.extra_fields["coordinate_provenance"] == "source_map_pin_unverified"
    assert parsed.extra_fields["municipality_raw"] == "Prishtinë"
    assert parsed.street_raw == "Rruga A"
    assert parsed.listing_date.isoformat() == "2026-07-12"
    assert normalized.area_sqm == 80
    assert normalized.description_original is None
    assert normalized.image_urls == []


def test_literal_reader_and_rental_period_evidence():
    h = html("property", prop(listing_type="rent", features={}))
    h += '<script type="application/ld+json">{"@type":"RealEstateListing","additionalProperty":[{"name":"Rental Period","value":"monthly"}]}</script>'
    assert property_from_html(h)["features"]["rental_period"] == "monthly"
    assert hydration_field(html("listings", [prop()]), "listings")[0]["id"] == KEY
    for bad in [
        '<script id="$tsr-stream-barrier">property:$R[1]=alert(1)</script>',
        '<script id="$tsr-stream-barrier">property:$R[1]={id:window.secret}</script>',
        '<script id="$tsr-stream-barrier">property:$R[1]={bad:}</script>',
        '<div id="human-gate-title">blocked</div>',
        "<html>changed</html>",
    ]:
        with pytest.raises(HartaContractError):
            hydration_field(bad, "property")


def test_discovery_incremental_and_boundaries(tmp_path):
    first = HartaSpider(max_listings="1", report_path=str(tmp_path / "report.json"))
    requests = list(
        first.parse_index_page(response("listings", [prop(city="Obiliq"), prop(), prop()]))
    )
    assert len(requests) == 1
    assert requests[0].url == "https://harta.info/property/" + KEY
    assert first.metrics["excluded"] == 1
    fingerprint = requests[0].meta["summary_fingerprint"]
    for old_hash, age, expected in [
        (fingerprint, 0, "unchanged"),
        (fingerprint, 8, "due"),
        ("changed", 0, "changed"),
    ]:
        repeat = HartaSpider(known={KEY: (old_hash, NOW - timedelta(days=age))})
        reqs = list(repeat.parse_index_page(response("listings", [prop()])))
        assert repeat.metrics[expected] == 1
        assert len(reqs) == (0 if expected == "unchanged" else 1)
    first.closed("finished")
    assert (tmp_path / "report.json").is_file()
    with pytest.raises(CloseSpider) as stopped:
        list(HartaSpider().parse_index_page(response("listings", [])))
    assert stopped.value.reason == "harta_empty_discovery_unverified"


def test_detail_hash_identity_removal_and_no_media():
    spider = HartaSpider()
    meta = {"source_id": KEY, "summary_fingerprint": "summary"}
    r = response("property", prop(), meta=meta)
    item = list(spider.parse_listing_page(r))[0]
    assert item["raw_html"] is None
    assert item["source_listing_id"] == KEY
    assert not list(spider.parse_listing_page(response("property", {}, meta=meta, status=404)))
    assert spider.metrics["removed"] == 1
    changed = deepcopy(item["raw_payload"])
    changed["property"]["price"] = 130000
    assert content_hash(raw_payload=changed) != item["content_hash"]
    assert (
        list(
            spider.parse_listing_page(
                response("property", prop(id="22222222-2222-4222-8222-222222222222"), meta=meta)
            )
        )
        == []
    )


def test_access_budget_retry_after_and_request_allowlist():
    spider = HartaSpider(max_requests="1")
    spider.crawler = SimpleNamespace(engine=MagicMock(), stats=MagicMock(), settings=MagicMock())
    mw = HartaAccessMiddleware()
    request = Request("https://harta.info/prona/banesa/prishtine")
    mw.process_request(request, spider)
    with pytest.raises(IgnoreRequest):
        mw.process_request(request, spider)
    for url in [
        "https://harta.info/api/local-db",
        "https://evil.invalid/property/x",
        "https://harta.info/storage/image.jpg",
        "https://harta.info/profile",
    ]:
        with pytest.raises(IgnoreRequest):
            mw.process_request(Request(url), spider)
    r = HtmlResponse(request.url, body=b'<div id="human-gate-title">verify</div>', request=request)
    with pytest.raises(IgnoreRequest, match="verification"):
        mw.process_response(request, r, spider)
    assert spider._blocked
    spider._blocked = False
    r = HtmlResponse(request.url, status=429, headers={"Retry-After": "120"}, request=request)
    with pytest.raises(IgnoreRequest, match="Retry-After"):
        mw.process_response(request, r, spider)
    assert spider.metrics["http_429"] == 1


def test_dispatch_and_etl_quarantine(monkeypatch):
    from groundtruth.services.etl import EtlService

    p = prop(description="Çmimi: 130000 €")
    raw = RawListing(
        id=1,
        source_website="harta",
        source_listing_id=KEY,
        original_url="https://harta.info/property/" + KEY,
        raw_payload={"property": minimized_property(p)},
        scraped_at=NOW,
        scrape_run_id=1,
        spider_version="0.1.0-harta",
    )
    parsed = ParsingService().parse_raw(raw)
    assert parsed.parser_version == "0.1.0-harta"
    service = EtlService(MagicMock())
    service._raw_repo = MagicMock()
    service._raw_repo.list_unparsed.return_value = [raw]
    service._parsed_repo = MagicMock()
    service._parsed_repo.exists_for_raw.return_value = False
    service._pipeline = MagicMock()
    service._pipeline.store_parsed.return_value = SimpleNamespace(id=2)
    normal = NormalizationService()
    service._normalizer = normal
    normalized, _ = normal.normalize(parsed)
    normalized.parsed_listing_id = 2
    entity = SimpleNamespace(id=3, **normalized.model_dump())
    service._pipeline.normalize_and_store.return_value = entity
    service._invalid_repo = MagicMock()
    service._metrics_repo = MagicMock()
    service._metrics_repo.create_from_schema.return_value = SimpleNamespace(id=4)
    monkeypatch.setattr("groundtruth.services.etl.log_neighborhood_failure", lambda **kw: None)
    metrics = service.run(source="harta")
    assert metrics.parsed_success == metrics.normalized_success == 1
    assert metrics.validation_failed == 1
    invalid = service._invalid_repo.create_from_schema.call_args.args[0]
    assert "harta_description_price_conflict" in invalid.error_codes
    assert invalid.parsed_listing_id == 2


def test_research_registration_preserves_public_and_weekly_defaults():
    from groundtruth.crawl.spider_commands import _build_crawl_command, _weekly_spider_jobs
    from groundtruth.crawl.window import CrawlWindow
    from groundtruth.portals.registry import get_portal, source_priority_order, weekly_portal_names
    from groundtruth.versions import ACTIVE_PARSER_VERSIONS, PARSER_VERSIONS

    assert PARSER_VERSIONS["harta"] not in ACTIVE_PARSER_VERSIONS
    assert not get_portal("harta").weekly and not get_portal("harta").public
    assert "harta" not in weekly_portal_names()
    assert source_priority_order()[-1] == "harta"
    assert "harta" in _build_crawl_command("harta", {})
    assert all(job[0] != "harta" for job in _weekly_spider_jobs(CrawlWindow.last_n_days(7)))


def test_raw_pipeline_reuses_store_and_commits_bounded_items(monkeypatch):
    from groundtruth.scrapers.pipelines import RawListingPipeline
    from groundtruth.scrapers.spiders.harta import HartaRawListingPipeline

    pipeline = HartaRawListingPipeline()
    pipeline._session = MagicMock()
    pipeline._scrape_run = SimpleNamespace(metadata_={"source": "harta"})
    spider = HartaSpider()
    spider._detail_checks[KEY] = {"summary_fingerprint": "f", "checked_at": NOW.isoformat()}
    store = MagicMock(side_effect=lambda item, spider: item)
    close = MagicMock()
    monkeypatch.setattr(RawListingPipeline, "process_item", store)
    monkeypatch.setattr(RawListingPipeline, "close_spider", close)
    item = {"source_website": "harta"}
    assert pipeline.process_item(item, spider) is item
    store.assert_called_once_with(item, spider)
    pipeline._session.commit.assert_called_once()
    pipeline.close_spider(spider)
    assert pipeline._scrape_run.metadata_["harta_detail_checks"][KEY]["summary_fingerprint"] == "f"
    close.assert_called_once_with(spider)


def test_harta_dedup_compatibility_never_promotes_over_existing_sources():
    import pandas as pd

    from groundtruth.analytics.cross_dedup import canonical_corpus_dataframe

    rows = []
    for i, source in enumerate(("myrealestate", "gjirafa", "harta"), start=1):
        listing, _ = NormalizationService().normalize(parse(prop()))
        row = listing.model_dump(mode="json")
        row.update(
            source_website=source,
            normalized_id=i,
            source_listing_id=str(i),
            neighborhood_id=1,
            neighborhood="Dardania",
            listing_price=120000,
            confidence_score=1 if source == "harta" else 0.5,
        )
        rows.append(row)
    before = canonical_corpus_dataframe(pd.DataFrame(rows[:2]), threshold=85)
    after = canonical_corpus_dataframe(pd.DataFrame(rows), threshold=85)
    assert before.source_website.tolist() == after.source_website.tolist() == ["gjirafa"]
