"""Tests for hierarchical location resolution."""

from groundtruth.gazetteers.location_resolver import LocationResolver, resolve_listing_location


def test_rruga_b_resolves_matiqan_district():
    r = LocationResolver().resolve("Apartament ne Rruga B, Matiqan")
    assert r.neighborhood_slug == "matiqan"
    assert r.district_slug == "rruga-b"
    assert r.complex_slug is None


def test_royal_mall_gets_rruga_b():
    r = LocationResolver().resolve("Royal Mall, Matiqan")
    assert r.neighborhood_slug == "matiqan"
    assert r.district_slug == "rruga-b"
    assert r.complex_slug == "royal-mall"


def test_narteli_without_parent_invalid():
    r = LocationResolver().resolve("Narteli, apartament")
    assert r.invalid_location is True


def test_narteli_with_emshir_valid():
    r = LocationResolver().resolve("Narteli, Emshir")
    assert r.invalid_location is False
    assert r.neighborhood_slug == "emshir"
    assert r.complex_slug == "narteli"


def test_banesat_e_kuqe_direct_under_bregu():
    r = LocationResolver().resolve("Banesat e Kuqe, Bregu i Diellit")
    assert r.neighborhood_slug == "bregu-i-diellit"
    assert r.district_slug is None
    assert r.complex_slug == "banesat-e-kuqe"


def test_beni_dona_without_parent_invalid():
    r = LocationResolver().resolve("Banese me qira, Beni Dona")
    assert r.invalid_location is True


def test_beni_dona_lakrishte_resolves_pejton_benidona():
    r = LocationResolver().resolve("Banese me qira Lakrishte Kati i 10 Beni Dona")
    assert r.invalid_location is False
    assert r.neighborhood_slug == "pejton-lakrishte"
    assert r.complex_slug == "benidona"


def test_beni_dona_ulpiana_stays_ulpiana():
    r = LocationResolver().resolve("Banese me qira Ulpiana, Beni Dona")
    assert r.invalid_location is False
    assert r.neighborhood_slug == "ulpiana"
    assert r.complex_slug == "beni-dona"


def test_agjencionimax_lakrishte_listing():
    resolver = LocationResolver()
    r = resolve_listing_location(
        resolver,
        title="Banese me qira Lakrishte 3 + 1",
        neighborhood_raw="Pejton / Lakrishte",
        complex_raw="Beni Dona",
        description="Kati i 10 Beni Dona AC Klima 120 m2",
        city="Prishtine",
    )
    assert r.neighborhood_slug == "pejton-lakrishte"
    assert r.complex_slug == "benidona"


def test_emshir_title_beats_ontex_flooring_in_description():
    """Pro-RKS #10861: Ontex is a flooring brand in the description, not the complex."""
    resolver = LocationResolver()
    r = resolve_listing_location(
        resolver,
        title="63.8m² Apartment for #SALE in Emshir.",
        street_raw="Ali Vitija",
        description=(
            "located in Emshir, on Ali Vitija street, built by BG Construction. "
            "flooring installed by Ontex, bathrooms completed by Kerasan."
        ),
        city="Prishtina",
    )
    assert r.neighborhood_slug == "emshir"
    assert r.complex_slug is None
