"""Tests for corpus diagnostics."""

import pandas as pd

from groundtruth.analytics.corpus import (
    CorpusReport,
    bedroom_label,
    build_coverage_matrix,
    coverage_tier,
    coverage_tier_emoji,
    render_corpus_markdown,
)
from groundtruth.analytics.corpus_filters import (
    ACTIVE_PARSER_VERSIONS,
    DEFAULT_MAX_AGE_MONTHS,
    PRO_RKS_PARSER_VERSION,
    active_corpus_cutoff_date,
)
from groundtruth.services.merrjep_parsing import PARSER_VERSION as MERRJEP_PARSER_VERSION
from groundtruth.services.parsing import PARSER_VERSION as GJIRAFA_PARSER_VERSION


class TestCorpusHelpers:
    def test_active_corpus_defaults(self) -> None:
        assert DEFAULT_MAX_AGE_MONTHS == 12
        assert GJIRAFA_PARSER_VERSION in ACTIVE_PARSER_VERSIONS
        assert MERRJEP_PARSER_VERSION in ACTIVE_PARSER_VERSIONS
        assert PRO_RKS_PARSER_VERSION in ACTIVE_PARSER_VERSIONS
        cutoff = active_corpus_cutoff_date()
        assert cutoff.year >= 2024

    def test_bedroom_label(self) -> None:
        assert bedroom_label(2) == "2BR"
        assert bedroom_label(4) == "4BR+"
        assert bedroom_label(6) == "4BR+"
        assert bedroom_label(None) == "unknown"

    def test_coverage_tier(self) -> None:
        assert coverage_tier(142) == "high"
        assert coverage_tier(96) == "medium"
        assert coverage_tier(7) == "low"

    def test_coverage_tier_emoji(self) -> None:
        assert coverage_tier_emoji("high") == "🟢"
        assert coverage_tier_emoji("low") == "🔴"


class TestDedupedCorpus:
    def test_listing_type_normalized_to_lowercase(self) -> None:
        from groundtruth.analytics import corpus as corpus_mod

        class FakeResult:
            def mappings(self):
                return self

            def all(self):
                return [
                    {
                        "source_website": "merrjep",
                        "source_listing_id": "1",
                        "listing_type": "RENT",
                        "property_type": "APARTMENT",
                        "sale_price": None,
                        "rent_price": 300.0,
                        "price_per_sqm": None,
                        "area_sqm": 60.0,
                        "bedrooms": 2,
                        "neighborhood_id": 1,
                        "neighborhood": "Ulpiana",
                        "street_id": None,
                        "street": None,
                        "complex_id": None,
                        "complex": None,
                        "is_furnished": False,
                        "confidence_score": 0.9,
                        "parser_version": "0.1.1-merrjep",
                        "listing_date": None,
                    }
                ]

        class FakeSession:
            def execute(self, *_args, **_kwargs):
                return FakeResult()

        df = corpus_mod.deduped_corpus_dataframe(FakeSession())
        assert df.iloc[0]["listing_type"] == "rent"
        assert df.iloc[0]["property_type"] == "APARTMENT"


class TestCoverageMatrix:
    def test_build_coverage_matrix(self) -> None:
        df = pd.DataFrame(
            {
                "neighborhood": ["Arbëria", "Arbëria", "Ulpiana", "Veternik"],
                "listing_type": ["sale", "rent", "rent", "sale"],
                "bedrooms": [2, 2, 1, 4],
            }
        )
        matrix = build_coverage_matrix(df)
        assert len(matrix) == 4
        arb_sale = matrix[
            (matrix["neighborhood"] == "Arbëria") & (matrix["transaction"] == "Sale")
        ].iloc[0]
        assert arb_sale["observations"] == 1
        assert arb_sale["tier"] == "low"
        assert "Arbëria Sale 2BR" in arb_sale["segment"]

    def test_render_corpus_markdown_includes_matrix(self) -> None:
        report = CorpusReport(
            generated_at="2026-06-11T00:00:00+00:00",
            total_listings=4,
            rent_count=2,
            sale_count=2,
            sources=[{"source_website": "merrjep", "listings": 4, "rent": 2, "sale": 2}],
            bedrooms={"2BR": 2, "1BR": 1, "4BR+": 1},
            missingness_pct={"price": 95.0},
            fingerprints={"dataset_hash": "abc123"},
        )
        matrix = build_coverage_matrix(
            pd.DataFrame(
                {
                    "neighborhood": ["Arbëria"],
                    "listing_type": ["rent"],
                    "bedrooms": [2],
                }
            )
        )
        md = render_corpus_markdown(report, matrix)
        assert "Corpus Report" in md
        assert "Coverage matrix" in md
        assert "Arbëria Rent 2BR" in md
