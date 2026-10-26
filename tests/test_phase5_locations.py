"""Owner-confirmed market semantics and context-aware location regressions."""

import json
import unicodedata
from pathlib import Path

import pytest

from groundtruth.gazetteers.loader import GazetteerService
from groundtruth.gazetteers.location_resolver import LocationResolver, resolve_listing_location
from groundtruth.gazetteers.market_graph import (
    distinct_rollup_memberships,
    load_market_graph,
    market_children,
    market_identity_for_reference,
)
from groundtruth.gazetteers.version import compute_gazetteer_version
from groundtruth.services.normalization import NormalizationService
from groundtruth.services.pro_rks_parsing import ProRksParsingService
from tests.test_pro_rks_parser import SAMPLE_PROPERTY


@pytest.mark.parametrize(
    "text,slug",
    [
        ("Dragodan", "arberia"),
        ("Arbëria", "arberia"),
        ("Dragodani", "arberia"),
        ("Kalabria", "emshir"),
        ("Kalabri", "emshir"),
        ("Emshir", "emshir"),
        ("Emshiri", "emshir"),
        ("Në Kalabri", "emshir"),
        ("Në Emshir", "emshir"),
        ("Pejton", "pejton-lakrishte"),
        ("Lakrishta", "pejton-lakrishte"),
        ("Lakrishte", "pejton-lakrishte"),
        ("Dodona", "llullat-dodona"),
        ("4 Llullat", "llullat-dodona"),
        ("Llullat", "llullat-dodona"),
        ("Sofalia", "sofalia"),
        ("Gërmia", "sofalia"),
        ("shtepi në Gërmi", "sofalia"),
        ("Sunny Hill", "bregu-i-diellit"),
        ("Bregu i Diellit", "bregu-i-diellit"),
        ("Vranjevc", "vranjevc-kodra-trimave"),
        ("Kodra e Trimave", "vranjevc-kodra-trimave"),
        ("Qafa", "qafa"),
        ("Marigona Hill", "marigona-hill"),
        ("Marigona Residence", "marigona-residence"),
    ],
)
def test_confirmed_aliases(text, slug):
    assert LocationResolver().resolve(text).neighborhood_slug == slug


@pytest.mark.parametrize(
    "term,parent",
    [
        ("Prishtina e Re", "veternik"),
        ("Parku i Qytetit", "aktash-muhaxhere"),
        ("Mati 1", "matiqan"),
        ("Mati 2", "matiqan"),
        ("Mati 3", "matiqan"),
        ("Rruga A", "matiqan"),
        ("Rr. A", "matiqan"),
        ("Rruga B", "matiqan"),
        ("Rr. B", "matiqan"),
        ("Rruga C", "matiqan"),
        ("Rr. C", "matiqan"),
        ("Në Rrugën B", "matiqan"),
    ],
)
def test_explicit_subarea_has_confirmed_parent(term, parent):
    result = LocationResolver().resolve("Banesë në " + term)
    assert result.market_subarea_slug
    assert parent in result.parent_relationships


def test_multi_parent_is_one_entity_and_nonadditive():
    result = LocationResolver().resolve("Banesë në lagjen Sllovenia Sport")
    assert result.market_entity_id == "market_subarea:sllovenia-sport"
    assert set(result.parent_relationships) == {"aktash-muhaxhere", "qendra"}
    sets = distinct_rollup_memberships(
        [("unit1", "sllovenia-sport"), ("unit1", "sllovenia-sport"), ("unit2", "sllovenia-sport")]
    )
    assert len(sets["aktash-muhaxhere"]) == len(sets["qendra"]) == 2
    assert len(set.union(*sets.values())) == 2
    left = next(c for c in market_children("aktash-muhaxhere") if c["slug"] == "sllovenia-sport")
    right = next(c for c in market_children("qendra") if c["slug"] == "sllovenia-sport")
    assert left["entity_id"] == right["entity_id"] == result.market_entity_id
    assert market_identity_for_reference("market_neighborhood", "mati") == "market_subarea:mati-1"
    assert (
        market_identity_for_reference("market_neighborhood", "sllovenia-sport")
        == result.market_entity_id
    )


@pytest.mark.parametrize(
    "text",
    [
        "Banesë afër Sllovenia Sport",
        "Shtëpi afër Parkut të Gërmisë",
        "Shtëpi me pamje nga Gërmia",
        "Banesë afër Rrugës B",
        "Objekti C",
        "Ahmet Krasniqi",
        "Rr. Ahmet Krasniqi",
    ],
)
def test_proximity_and_letter_false_positives(text):
    result = LocationResolver().resolve(text)
    assert result.market_subarea_slug is None
    assert result.neighborhood_slug is None


def test_landmark_does_not_override_explicit_neighborhood():
    result = resolve_listing_location(
        LocationResolver(), title="Banesë në Dardani afër Royal Mall", description="Pranë rrugës B"
    )
    assert result.neighborhood_slug == "dardania"
    assert result.district_slug is None and result.complex_slug is None


def test_broad_dardania_has_no_school_specificity():
    assert LocationResolver().resolve("Dardania").district_slug is None
    assert (
        LocationResolver().resolve("Në zonën Shkolla Dardania").district_slug == "shkolla-dardania"
    )
    assert LocationResolver().resolve("Afër Shkollës Dardania").district_slug is None
    assert (
        resolve_listing_location(
            LocationResolver(), title="Banesë Dardania", description="Në zonën Shkolla Dardania"
        ).district_slug
        == "shkolla-dardania"
    )
    assert LocationResolver().resolve("Afër Shkolla Dardania").proximity_mentions
    assert (
        LocationResolver().resolve("Në zonën e Shkollës Dardania").district_slug
        == "shkolla-dardania"
    )
    assert LocationResolver().resolve("Afër Sh.F.M.U. Dardania").neighborhood_slug is None


def test_precise_street_is_distinct_from_market_corridor():
    result = LocationResolver().resolve("Adresa Rruga C, Matiqan")
    assert result.physical_street_slug == "rruga-c"
    assert result.market_entity_id == "market_subarea:rruga-c"
    graph = load_market_graph()
    assert "physical_street:rruga-c" in graph["entities"]
    assert "market_subarea:rruga-c" in graph["entities"]


def test_developer_and_nearby_mall_do_not_become_complex_membership():
    for text in [
        "Në Dardani afër Royal Mall",
        "Ndërtuar nga Tregtia, në Dardani",
        "Banesë përballë Maxi 24",
    ]:
        assert LocationResolver().resolve(text).complex_slug is None
    assert (
        LocationResolver().resolve("Banesë në kompleksin Royal City").complex_slug == "royal-city"
    )
    assert (
        LocationResolver().resolve("Banesë në kompleksin Royal Mall").complex_slug == "royal-mall"
    )
    assert LocationResolver().resolve("Narteli").invalid_location


def test_json_yaml_alias_identity_agrees():
    gaz = GazetteerService()
    resolver = LocationResolver()
    for slug, terms in load_market_graph()["alias_groups"].items():
        for term in terms:
            if term.startswith("Në "):
                continue
            assert gaz.match_neighborhood(term, city="Prishtina").slug == slug
            assert resolver.resolve(term).neighborhood_slug == slug


def test_city_provenance_and_explicit_compatibility_boundary():
    parsed = ProRksParsingService().parse_payload(
        {"property": {**SAMPLE_PROPERTY, "city": {"name": "Fushë Kosovë"}}},
        url="https://example.com/property",
    )
    assert parsed.city == "Fushë Kosovë"
    normalized, factors = NormalizationService().normalize(parsed)
    assert normalized.city == "Prishtina"
    assert factors.location_semantics["source_city_raw"] == "Fushë Kosovë"
    assert (
        factors.location_semantics["city_scope_policy"]
        == "legacy_pricing_scope_retained_pending_owner_review"
    )
    assert not factors.location_invalid


def test_missing_city_is_not_relabelled_as_explicit_source_city():
    parsed = ProRksParsingService().parse_payload(
        {"property": {**SAMPLE_PROPERTY, "city": None}}, url="https://example.com/property"
    )
    assert parsed.city is None
    assert not parsed.extra_fields["source_city_present"]


def test_fingerprint_tracks_yaml_and_graph(tmp_path):
    for rel in [
        "neighborhoods.json",
        "districts.json",
        "streets.json",
        "complexes.json",
        "building_aliases.json",
        "draft/prishtina_location_tree.yaml",
        "market_relationships.json",
    ]:
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("{}")
    baseline = compute_gazetteer_version(tmp_path)
    (tmp_path / "draft/prishtina_location_tree.yaml").write_text("changed")
    assert compute_gazetteer_version(tmp_path) != baseline
    baseline = compute_gazetteer_version(tmp_path)
    (tmp_path / "market_relationships.json").write_text("changed")
    assert compute_gazetteer_version(tmp_path) != baseline


@pytest.mark.parametrize(
    "case",
    json.loads(
        (Path(__file__).parent / "fixtures/phase5/location_examples.json").read_text(
            encoding="utf8"
        )
    ),
)
def test_redacted_original_phase4_cases(case):
    if case["case"] == "original_pro_rks_city":
        parsed = ProRksParsingService().parse_payload(
            {"property": {**SAMPLE_PROPERTY, "city": {"name": case["source_city"]}}},
            url="https://example.com/property",
        )
        assert parsed.city == case["source_city"]
        assert parsed.extra_fields["source_city_present"]
    else:
        result = resolve_listing_location(
            LocationResolver(),
            title=case.get("title"),
            description=case.get("description"),
            neighborhood_raw=case.get("neighborhood_raw"),
            street_raw=case.get("street_raw"),
        )
        assert result.district_slug != case["expect_not_district"]


@pytest.mark.parametrize(
    "text,slug",
    [
        ("Spitalit", "spitali"),
        ("Muhaxherëve", "aktash-muhaxhere"),
        ("Bregun e Diellit", "bregu-i-diellit"),
    ],
)
def test_existing_json_declensions_retain_resolver_recall(text, slug):
    assert LocationResolver().resolve(text).neighborhood_slug == slug


def test_explicit_structured_neighborhood_survives_glued_description_tokens():
    result = resolve_listing_location(
        LocationResolver(), neighborhood_raw="Qafa", description="Lokal ne QafaZyre me qera"
    )
    assert result.neighborhood_slug == "qafa"


@pytest.mark.parametrize(
    "text,slug", [("Qendër", "qendra"), ("Në Emshir", "emshir"), ("Arbëria", "arberia")]
)
def test_decomposed_albanian_unicode_keeps_tokens(text, slug):
    assert LocationResolver().resolve(unicodedata.normalize("NFD", text)).neighborhood_slug == slug


def test_road_towards_park_and_distance_do_not_assert_membership():
    assert LocationResolver().resolve("Rrugës për Gërmi").neighborhood_slug is None
    assert LocationResolver().resolve("5min nga Qendra").neighborhood_slug is None
    assert LocationResolver().resolve("Gërmia Park").neighborhood_slug is None
    assert LocationResolver().resolve("Sofalia, afër Gërmia Park").neighborhood_slug == "sofalia"


def test_school_bare_neighborhood_context_and_letter_boundaries_in_real_parser():
    from groundtruth.services.merrjep_parsing import MerrJepParsingService

    parsed, _ = MerrJepParsingService().parse_payload(
        {
            "title": "Banesë në Arbëria",
            "description": "Banesë në rrugën Ahmet Krasniqi",
            "price_ldjson": 500,
        },
        url="https://example.com/listing",
    )
    assert parsed.street_raw != "Rruga A"
    assert LocationResolver().resolve("Arberia_2+1").neighborhood_slug == "arberia"


def test_end_to_end_normalization_keeps_sllovenia_legacy_id_and_both_parents():
    from types import SimpleNamespace
    from unittest.mock import MagicMock

    from groundtruth.processing.confidence import ConfidenceScorer
    from groundtruth.schemas.pipeline import ParsedListingSchema

    data = json.loads(Path("data/gazetteers/neighborhoods.json").read_text(encoding="utf8"))
    ids = {row["slug"]: row["id"] for row in data}

    class Query:
        def filter_by(self, **kwargs):
            self.slug = kwargs["slug"]
            return self

        def first(self):
            return SimpleNamespace(id=ids[self.slug]) if self.slug in ids else None

    session = MagicMock()
    session.query.side_effect = lambda model: Query()
    parsed = ParsedListingSchema(
        source_website="pro-rks",
        source_listing_id="redacted-unit",
        original_url="https://example.com/unit",
        city="Prishtina",
        neighborhood_raw="Sllovenia Sport",
        listing_type="sale",
        property_type="apartment",
        sale_price=100000,
        area_sqm=80,
    )
    normalized, factors = NormalizationService(session).normalize(parsed)
    assert normalized.neighborhood_id == 47
    assert factors.location_semantics["market_entity_id"] == "market_subarea:sllovenia-sport"
    assert set(factors.location_semantics["parent_relationships"]) == {"aktash-muhaxhere", "qendra"}
    scored = ConfidenceScorer().score(normalized, parsed, factors=factors, is_valid=True)
    assert scored.details["location_semantics"] == factors.location_semantics


def test_cycle_is_rejected_without_schema_migration(tmp_path, monkeypatch):
    from types import SimpleNamespace

    from groundtruth.gazetteers import market_graph

    (tmp_path / "market_relationships.json").write_text(
        json.dumps({"parents": {"a": ["b"], "b": ["a"]}})
    )
    market_graph.load_market_graph.cache_clear()
    monkeypatch.setattr(
        market_graph, "get_settings", lambda: SimpleNamespace(gazetteer_dir=tmp_path)
    )
    try:
        with pytest.raises(ValueError, match="cycle"):
            market_graph.load_market_graph()
    finally:
        market_graph.load_market_graph.cache_clear()


def test_actual_market_projection_consolidates_aliases_without_mutating_units():
    import pandas as pd

    from groundtruth.analytics.market_hierarchy import canonical_market_frame

    refs = json.loads(Path("data/gazetteers/neighborhoods.json").read_text(encoding="utf8"))
    frame = pd.DataFrame(
        [
            {"unit": "a", "neighborhood_id": 14, "neighborhood": "Dragodan"},
            {"unit": "b", "neighborhood_id": 4, "neighborhood": "Arbëria"},
            {"unit": "c", "neighborhood_id": 47, "neighborhood": "Sllovenia Sport"},
        ]
    )
    before = frame.copy(deep=True)
    result = canonical_market_frame(frame, refs)
    assert list(result.neighborhood_id) == [4, 4, 47]
    assert list(result.unit) == ["a", "b", "c"]
    assert result.source_neighborhood_id.tolist() == [14, 4, 47]
    pd.testing.assert_frame_equal(frame, before)


def test_null_market_labels_are_not_counted_as_movements():
    import pandas as pd

    from groundtruth.analytics.market_hierarchy import count_market_label_changes

    before = pd.DataFrame({"neighborhood_id": [None, 4], "neighborhood": [None, "Arbëria"]})
    assert count_market_label_changes(before, before.copy()) == 0
    changed = before.copy()
    changed.loc[1, "neighborhood_id"] = 11
    changed.loc[1, "neighborhood"] = "Emshir"
    assert count_market_label_changes(before, changed) == 1
