"""Tests for MerrJep published-date parsing."""

from datetime import date

from groundtruth.processing.parsers.merrjep_dates import (
    extract_published_date,
    parse_published_date_text,
)


class TestMerrJepPublishedDates:
    def test_parse_recent_albanian_month(self) -> None:
        assert parse_published_date_text("maj 16 2026") == date(2026, 5, 16)

    def test_parse_old_abbreviated_month(self) -> None:
        assert parse_published_date_text("gush 07 2015") == date(2015, 8, 7)

    def test_extract_from_html(self) -> None:
        html = '<span>Publikuar:</span><bdi class="published-date">maj 16 2026</bdi>'
        published, raw = extract_published_date(html)
        assert published == date(2026, 5, 16)
        assert raw == "maj 16 2026"

    def test_extract_from_ad_publish_info_area(self) -> None:
        html = """
        <div class="ad-publish-info-area">
            <span class="ci-text-muted">Publikuar:</span>
            <bdi class="published-date">gush 07 2015</bdi>
            <bdi class="published-time">10:42</bdi>
        </div>
        """
        published, raw = extract_published_date(html)
        assert published == date(2015, 8, 7)
        assert raw == "gush 07 2015"

    def test_invalid_text_returns_none(self) -> None:
        assert parse_published_date_text("not a date") is None

    def test_html_entity_month(self) -> None:
        html = (
            '<div class="ad-publish-info-area">'
            '<bdi class="published-date">n&#235;n 05 2022</bdi>'
            "</div>"
        )
        published, raw = extract_published_date(html)
        assert published == date(2022, 11, 5)
        assert raw == "nën 05 2022"
