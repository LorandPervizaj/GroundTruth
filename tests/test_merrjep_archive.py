"""Tests for MerrJep Phase 1.5 archive and schema assessment."""

import json
from pathlib import Path

from groundtruth.scrapers.merrjep_archive import (
    archive_detail_page,
    assess_product_schema,
    build_archive_report,
    extract_ld_json_blocks,
    find_product_ld,
    infer_transaction_type,
)

SAMPLE_PRODUCT = {
    "@type": "Product",
    "name": "Banese ne shitje",
    "description": "Banesë në shitje në Ulpianë. 44m² 📍 Ulpiana, Kosovë",
    "offers": {"price": 105000.0, "priceCurrency": "EUR"},
}

SAMPLE_HTML = (
    '<html><script type="application/ld+json">' + json.dumps(SAMPLE_PRODUCT) + "</script></html>"
)


class TestMerrJepArchive:
    def test_extract_and_find_product(self) -> None:
        blocks = extract_ld_json_blocks(SAMPLE_HTML)
        product = find_product_ld(blocks)
        assert product is not None
        assert product["@type"] == "Product"

    def test_assess_product_schema(self) -> None:
        assessed = assess_product_schema(SAMPLE_PRODUCT, html=SAMPLE_HTML)
        assert assessed["has_ld_json"] is True
        assert assessed["has_price"] is True
        assert assessed["has_area"] is True
        assert assessed["has_neighborhood"] is True
        assert assessed["transaction_type"] == "sale"

    def test_infer_transaction_type(self) -> None:
        assert infer_transaction_type("Banes me qira", "") == "rent"
        assert infer_transaction_type("Banese ne shitje", "") == "sale"

    def test_archive_detail_page_writes_files(self, tmp_path: Path) -> None:
        record = archive_detail_page(
            listing_id="15838177",
            url="https://www.merrjep.com/shpallja/banese-ne-shitje/15838177",
            html=SAMPLE_HTML,
            output_dir=tmp_path,
        )
        assert (tmp_path / "15838177.html").exists()
        assert (tmp_path / "15838177.ldjson").exists()
        assert record.has_price is True

    def test_build_archive_report_passes_on_good_sample(self, tmp_path: Path) -> None:
        records = [
            archive_detail_page(
                listing_id=str(i),
                url=f"https://www.merrjep.com/shpallja/test/{i}",
                html=SAMPLE_HTML,
                output_dir=tmp_path / str(i),
            )
            for i in range(10)
        ]
        report = build_archive_report(records, archive_dir=tmp_path)
        assert report.completeness_pct["ld_json_exists"] == 100.0
        assert report.passed is True
