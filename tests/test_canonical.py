"""Tests for canonical neighborhood name resolution."""

from groundtruth.gazetteers.canonical import (
    canonical_neighborhood_meta,
    resolve_neighborhood_slug,
    slugs_for_canonical,
)


class TestCanonicalNeighborhoods:
    def test_dragodan_redirects_to_arberia(self) -> None:
        assert resolve_neighborhood_slug("dragodan") == "arberia"

    def test_arberia_aliases_include_dragodan(self) -> None:
        meta = canonical_neighborhood_meta("arberia")
        assert meta.canonical_slug == "arberia"
        assert meta.display_name == "Arbëria"
        assert "Dragodan" in meta.also_known_as

    def test_mati_redirects_to_matiqan(self) -> None:
        assert resolve_neighborhood_slug("mati") == "matiqan"
        assert resolve_neighborhood_slug("mati-2") == "matiqan"

    def test_slugs_for_matiqan_includes_merged(self) -> None:
        slugs = slugs_for_canonical("matiqan")
        assert "matiqan" in slugs
        assert "mati" in slugs

    def test_pejton_merges_to_pejton_lakrishte(self) -> None:
        assert resolve_neighborhood_slug("lakrishte") == "pejton-lakrishte"
        meta = canonical_neighborhood_meta("pejton-lakrishte")
        assert "Lakrishte" in meta.also_known_as or "Pejton" in meta.also_known_as
