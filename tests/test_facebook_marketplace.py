"""Tests for Facebook informal tier (Part B)."""

import json
from pathlib import Path

from groundtruth.analytics.corpus_filters import (
    FACEBOOK_PARSER_VERSION,
    INFORMAL_SOURCE_WEBSITES,
    is_informal_source,
)
from groundtruth.analytics.facebook_signal import summarize_facebook_signals
from groundtruth.processing.parsers.facebook_marketplace import (
    listing_id_from_url,
    parse_marketplace_capture,
)
from groundtruth.services.facebook_import import import_marketplace_jsonl


class TestFacebookParser:
    def test_listing_id_from_url(self) -> None:
        assert (
            listing_id_from_url("https://www.facebook.com/marketplace/item/123456789")
            == "123456789"
        )

    def test_parse_rent_capture(self) -> None:
        record = parse_marketplace_capture(
            {
                "title": "Banesë 2+1 Ulpiana qira",
                "description": "75m2 e mobiluar 450eur",
                "price_text": "450",
                "listing_type": "rent",
                "url": "https://www.facebook.com/marketplace/item/999",
                "neighborhood_guess": "Ulpiana",
            }
        )
        assert record.listing_type == "rent"
        assert record.price_eur == 450
        assert record.area_sqm == 75
        assert record.bedrooms == 2
        assert record.confidence_tier == "informal"
        assert record.parser_version == FACEBOOK_PARSER_VERSION

    def test_informal_sources_excluded(self) -> None:
        assert is_informal_source("facebook")
        assert not is_informal_source("gjirafa")
        assert "facebook" in INFORMAL_SOURCE_WEBSITES


class TestFacebookImport:
    def test_import_dedupes_by_url(self, tmp_path: Path) -> None:
        batch = tmp_path / "batch.jsonl"
        row = {
            "title": "Test",
            "price_text": "500",
            "listing_type": "rent",
            "url": "https://www.facebook.com/marketplace/item/111",
        }
        batch.write_text(json.dumps(row) + "\n", encoding="utf-8")
        out = tmp_path / "informal.jsonl"

        first = import_marketplace_jsonl(batch, output_path=out)
        second = import_marketplace_jsonl(batch, output_path=out)
        assert first["imported"] == 1
        assert second["imported"] == 0
        assert second["skipped"] == 1


class TestFacebookSignal:
    def test_empty_summary(self) -> None:
        summary = summarize_facebook_signals(sample_days=30)
        assert summary["informal_listings"] >= 0
        assert "by_listing_type" in summary
