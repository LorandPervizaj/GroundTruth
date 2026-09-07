"""Tests for MerrJep Phase 1 discovery helpers."""

from groundtruth.scrapers.merrjep_discovery import (
    MERRJEP_INDEX_URLS,
    analyze_id_stability,
    build_discovery_stats,
    build_page_url,
    category_base_url,
    classify_listing_category,
    extract_listing_urls,
    extract_max_page_number,
    listing_id_from_url,
    marginal_yield_buckets,
    register_listing_urls,
    resolve_start_urls,
)

SAMPLE_INDEX_HTML = """
<html><body>
  <a href="/shpallja/banese-ne-shitje/15837729">sale</a>
  <a href="/shpallja/banes-me-qera/15833318">rent</a>
  <a href="/shpallja/banese-ne-shitje/15837729">dup</a>
  <a href="https://www.merrjep.com/shpallje/patundshmeri/banesa/prishtine?Page=2">p2</a>
  <a href="https://www.merrjep.com/shpallje/patundshmeri/banesa/prishtine?Page=2596">last</a>
</body></html>
"""


class TestMerrJepDiscovery:
    def test_extract_listing_urls_dedupes_hrefs(self) -> None:
        base = "https://www.merrjep.com/shpallje/patundshmeri/banesa/prishtine"
        urls = extract_listing_urls(SAMPLE_INDEX_HTML, base)
        assert len(urls) == 2
        assert all("/shpallja/" in u for u in urls)

    def test_listing_id_from_url(self) -> None:
        assert (
            listing_id_from_url("https://www.merrjep.com/shpallja/banese-ne-shitje/15837729")
            == "15837729"
        )

    def test_build_page_url(self) -> None:
        base = "https://www.merrjep.com/shpallje/patundshmeri/banesa/prishtine"
        assert build_page_url(base, 2).endswith("Page=2")
        assert build_page_url(build_page_url(base, 2), 3).endswith("Page=3")

    def test_category_base_url_strips_page(self) -> None:
        url = "https://www.merrjep.com/shpallje/patundshmeri/banesa/prishtine?Page=5"
        assert "Page" not in category_base_url(url)

    def test_extract_max_page_number(self) -> None:
        assert extract_max_page_number(SAMPLE_INDEX_HTML) == 2596

    def test_classify_listing_category(self) -> None:
        assert (
            classify_listing_category("https://www.merrjep.com/shpallja/banes-me-qera/1")
            == "apartment_rent"
        )
        assert (
            classify_listing_category("https://www.merrjep.com/shpallja/banese-ne-shitje/2")
            == "apartment_sale"
        )

    def test_register_listing_urls_tracks_duplicates(self) -> None:
        seen: set[str] = set()
        cats: dict[str, int] = {}
        urls = [
            "https://www.merrjep.com/shpallja/banes-me-qera/1",
            "https://www.merrjep.com/shpallja/banese-ne-shitje/2",
            "https://www.merrjep.com/shpallja/banes-me-qera-dup/1",
        ]
        added, dup_hits, new_ids = register_listing_urls(
            urls, seen_ids=seen, duplicate_hits=0, category_counts=cats
        )
        assert added == 2
        assert dup_hits == 1
        assert new_ids == ["1", "2"]
        assert seen == {"1", "2"}
        assert cats["apartment_rent"] == 1

    def test_marginal_yield_buckets(self) -> None:
        yields = [(i, 50) for i in range(1, 11)] + [(i, 10) for i in range(11, 21)]
        buckets = marginal_yield_buckets(yields)
        assert buckets[0] == {"pages": "1-10", "new_ids": 500}
        assert buckets[1] == {"pages": "11-20", "new_ids": 100}

    def test_analyze_id_stability(self) -> None:
        ids = {"100", "200", "300"}
        id_to_url = {i: f"https://www.merrjep.com/shpallja/test/{i}" for i in ids}
        report = analyze_id_stability(ids, id_to_url, [(1, 3)])
        assert report["all_numeric"] is True
        assert report["suitable_as_primary_key"] is True

    def test_resolve_start_urls_rent_filter(self) -> None:
        urls = resolve_start_urls("rent")
        assert urls == [MERRJEP_INDEX_URLS["rent"]]
        assert "me-qera" in urls[0]

    def test_resolve_start_urls_apartments_sale(self) -> None:
        urls = resolve_start_urls("apartments_sale")
        assert urls == [MERRJEP_INDEX_URLS["apartments_sale"]]
        assert "banesa" in urls[0]
        assert "ne-shitje" in urls[0]

    def test_resolve_start_urls_houses(self) -> None:
        rent = resolve_start_urls("houses_rent")
        sale = resolve_start_urls("houses_sale")
        assert rent == [MERRJEP_INDEX_URLS["houses_rent"]]
        assert sale == [MERRJEP_INDEX_URLS["houses_sale"]]
        assert "shtepi/me-qera" in rent[0]
        assert "shtepi/ne-shitje" in sale[0]

    def test_resolve_start_urls_comma_separated(self) -> None:
        urls = resolve_start_urls("apartments_rent,houses_rent")
        assert urls == [
            MERRJEP_INDEX_URLS["apartments_rent"],
            MERRJEP_INDEX_URLS["houses_rent"],
        ]

    def test_build_discovery_stats_pass_fail(self) -> None:
        stats = build_discovery_stats(
            start_urls=["https://example.com"],
            index_pages_crawled=50,
            seen_ids=set(str(i) for i in range(2503)),
            duplicate_hits=245,
            urls_seen=2748,
            last_page_number=50,
            max_page_link_seen=2596,
            listing_urls_target=2400,
            max_duplicate_rate_pct=12.0,
        )
        assert stats.passed is True

        fail = build_discovery_stats(
            start_urls=["https://example.com"],
            index_pages_crawled=10,
            seen_ids={"1", "2"},
            duplicate_hits=0,
            urls_seen=2,
            last_page_number=10,
            max_page_link_seen=100,
            listing_urls_target=2400,
        )
        assert fail.passed is False
        assert fail.notes
