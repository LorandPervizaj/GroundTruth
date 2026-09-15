"""Frontend search must surface HTTP failures instead of empty results."""

from pathlib import Path


def test_search_js_handles_failed_http_responses() -> None:
    source = Path("web/static/search.js").read_text(encoding="utf-8")
    assert "if (!res.ok) return;" not in source
    assert 't("search_unavailable")' in source
    assert "if (!res.ok)" in source
