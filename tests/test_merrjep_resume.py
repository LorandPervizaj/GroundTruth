"""Tests for crawl skip/resume helpers."""

from groundtruth.scrapers import merrjep_resume


def test_load_existing_listing_ids_uses_zero_day_window(monkeypatch) -> None:
    captured: dict = {}

    def stub(session=None, *, source_website="merrjep", within_days=0):
        captured["source_website"] = source_website
        captured["within_days"] = within_days
        return {"x"}

    monkeypatch.setattr(merrjep_resume, "load_skip_listing_ids", stub)
    result = merrjep_resume.load_existing_listing_ids(source_website="gjirafa")
    assert result == {"x"}
    assert captured == {"source_website": "gjirafa", "within_days": 0}
