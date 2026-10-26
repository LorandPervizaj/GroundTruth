"""Production reads must preserve the hashed market release bundle."""
from types import SimpleNamespace

import pytest
from fastapi import HTTPException, Response

from groundtruth.api import routes_markets
from groundtruth.services.rent_yield import load_rent_yield_cache


def test_production_yield_serves_published_rows_without_rebuilding(monkeypatch):
    published = load_rent_yield_cache()
    assert published
    monkeypatch.setattr(routes_markets, "get_settings", lambda: SimpleNamespace(is_development=False, api_require_lookup_cache=True))
    monkeypatch.setattr(routes_markets, "load_rent_yield_cache", lambda: published)
    monkeypatch.setattr(routes_markets, "build_rent_yield_from_lookup_cache", lambda: pytest.fail("Public GET rebuilt a release artifact"))
    result = routes_markets.rent_yield(Response())
    assert result.cached
    assert [row.model_dump() for row in result.rows] == [row.model_dump() for row in type(result)(rows=published).rows]


def test_production_yield_missing_published_file_fails_closed(monkeypatch):
    monkeypatch.setattr(routes_markets, "get_settings", lambda: SimpleNamespace(is_development=False, api_require_lookup_cache=True))
    monkeypatch.setattr(routes_markets, "load_rent_yield_cache", lambda: [])
    monkeypatch.setattr(routes_markets, "build_rent_yield_from_lookup_cache", lambda: pytest.fail("Missing release artifact triggered regeneration"))
    with pytest.raises(HTTPException) as error:
        routes_markets.rent_yield(Response())
    assert error.value.status_code == 503
