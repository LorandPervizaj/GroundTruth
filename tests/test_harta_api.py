"""Normal public session/read interface, no stealth or challenge verification."""

import json

import pytest
from scrapy import Request
from scrapy.exceptions import CloseSpider
from scrapy.http import HtmlResponse

from groundtruth.scrapers.harta_api import DATA_URL, PAGE_SIZE, operation, validate_read_request
from groundtruth.scrapers.harta_contract import HartaContractError
from groundtruth.scrapers.spiders.harta import HartaSpider
from tests.test_harta import KEY, prop


def response(body, **meta):
    return HtmlResponse(
        DATA_URL,
        encoding="utf8",
        body=json.dumps(body).encode(),
        request=Request(DATA_URL, meta=meta),
    )


def spider():
    result = HartaSpider(max_pages="4")
    result._csrf = "synthetic-csrf"
    result._api_mode = True
    return result


def test_public_session_and_read_only_contract():
    s = spider()
    req = list(s.parse_public_session(response({"token": "synthetic-csrf"})))[0]
    assert req.method == "POST" and req.url == DATA_URL
    assert req.headers["x-harta-csrf-token"] == b"synthetic-csrf"
    validate_read_request(req.body)
    for change in [
        {"kind": "update"},
        {"table": "profiles"},
        {"columns": "*"},
        {"filters": []},
        {"limit": 100000},
        {"orFilters": []},
    ]:
        with pytest.raises(HartaContractError):
            validate_read_request(json.dumps({**operation(), **change}).encode())


def test_public_api_pagination_end_and_count_not_inventory_total():
    from uuid import UUID

    s = spider()
    data = [prop(id=str(UUID(int=n + 1))) for n in range(PAGE_SIZE)]
    first = list(s.parse_api_index(response({"data": data, "count": PAGE_SIZE}, offset=0)))
    assert len(first) == PAGE_SIZE + 1
    assert json.loads(first[-1].body)["range"] == [PAGE_SIZE, 2 * PAGE_SIZE - 1]
    assert s.discovery_complete is False
    assert list(s.parse_api_index(response({"data": [], "count": 0}, offset=PAGE_SIZE))) == []
    assert s.discovery_complete and s.run_status() == "complete"


def test_api_empty_first_page_and_bad_contract_fail_closed():
    for body in [{"data": [], "count": 0}, {"data": None}, {"error": "broken", "data": []}]:
        with pytest.raises(CloseSpider):
            list(spider().parse_api_index(response(body, offset=0)))


def test_api_details_minimized_and_repeat_avoids_request():
    s = spider()
    requests = list(s.parse_api_index(response({"data": [prop()], "count": 1}, offset=0)))
    detail = requests[0]
    item = list(
        s.parse_api_detail(
            response(
                {
                    "data": [
                        prop(description="Çmimi: 120000 €", agent_email="private@example.invalid")
                    ]
                },
                **detail.meta,
            )
        )
    )[0]
    assert "private" not in str(item["raw_payload"])
    assert "summary_fingerprint" not in item["raw_payload"]
    from datetime import UTC, datetime

    repeat = spider()
    repeat.known = {KEY: (detail.meta["summary_fingerprint"], datetime.now(UTC))}
    assert list(repeat.parse_api_index(response({"data": [prop()], "count": 1}, offset=0))) == []
    assert repeat.metrics["unchanged"] == 1 and repeat.run_status() == "complete"


def test_daily_rent_excluded_before_detail_and_duplicate_page_stops():
    s = spider()
    assert (
        list(
            s.parse_api_index(
                response(
                    {"data": [prop(listing_type="rent", features={"rental_period": "daily"})]},
                    offset=0,
                )
            )
        )
        == []
    )
    assert s.metrics["excluded"] == 1
    s = spider()
    from uuid import UUID

    data = [prop(id=str(UUID(int=n + 1))) for n in range(PAGE_SIZE)]
    list(s.parse_api_index(response({"data": data}, offset=0)))
    with pytest.raises(CloseSpider):
        list(s.parse_api_index(response({"data": data}, offset=PAGE_SIZE)))


def test_full_excluded_page_still_advances_and_bounded_details_are_not_complete():
    from uuid import UUID

    s = spider()
    data = [
        prop(id=str(UUID(int=n + 1)), listing_type="rent", features={"rental_period": "daily"})
        for n in range(PAGE_SIZE)
    ]
    requests = list(s.parse_api_index(response({"data": data}, offset=0)))
    assert len(requests) == 1 and json.loads(requests[0].body)["range"][0] == PAGE_SIZE
    assert list(s.parse_api_index(response({"data": []}, offset=PAGE_SIZE))) == []
    assert s.discovery_complete and s.metrics["excluded"] == PAGE_SIZE
    s = spider()
    s.limit = 1
    list(
        s.parse_api_index(
            response({"data": [prop(id=str(UUID(int=n + 1))) for n in range(2)]}, offset=0)
        )
    )
    assert s.run_status() == "bounded_complete" and not s.discovery_complete
    for malformed in [[], None, "not-an-object"]:
        with pytest.raises(HartaContractError):
            validate_read_request(json.dumps(malformed).encode())
