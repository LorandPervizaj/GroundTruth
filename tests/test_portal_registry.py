"""Consistency tests for the formal portal metadata registry."""

from __future__ import annotations

from groundtruth.analytics.corpus_filters import SOURCE_DISPLAY_NAMES
from groundtruth.analytics.cross_dedup import SOURCE_PRIORITY
from groundtruth.portals.registry import (
    PORTALS,
    all_portal_names,
    get_portal,
    parser_versions,
    source_display_names,
    source_priority_order,
    weekly_portal_names,
)
from groundtruth.versions import PARSER_VERSIONS


def test_known_production_portals_present() -> None:
    expected = {
        "gjirafa",
        "merrjep",
        "pro-rks",
        "vision",
        "topia",
        "myrealestate",
    }
    assert all_portal_names() == expected
    assert set(parser_versions()) == expected


def test_no_duplicate_portal_identifiers() -> None:
    names = [p.name for p in PORTALS]
    spiders = [p.spider for p in PORTALS]
    priorities = [p.source_priority for p in PORTALS]
    assert len(names) == len(set(names))
    assert len(spiders) == len(set(spiders))
    assert len(priorities) == len(set(priorities))


def test_parser_versions_present_and_shared() -> None:
    versions = parser_versions()
    assert versions == PARSER_VERSIONS
    for portal in PORTALS:
        assert portal.parser_version
        assert versions[portal.name] == portal.parser_version
        assert get_portal(portal.name).parser_version == portal.parser_version


def test_display_names_consistent() -> None:
    names = source_display_names()
    assert names == SOURCE_DISPLAY_NAMES
    assert names == {
        "gjirafa": "Portal A",
        "merrjep": "Portal B",
        "pro-rks": "Portal C",
        "vision": "Portal D",
        "topia": "Portal E",
        "myrealestate": "Portal F",
    }
    # Phrase join order stays stable for empty active_sources_phrase fallback.
    assert list(names.values()) == [p.display_name for p in PORTALS]
    banned = ("gjirafa", "merrjep", "pro real", "vision real", "topia", "my real", "facebook")
    joined = " ".join(names.values()).lower()
    assert not any(token in joined for token in banned)


def test_source_priorities_consistent() -> None:
    order = source_priority_order()
    assert order == SOURCE_PRIORITY
    assert order == ("gjirafa", "merrjep", "pro-rks", "vision", "topia", "myrealestate")
    for i, name in enumerate(order):
        assert get_portal(name).source_priority == i


def test_weekly_flags_valid() -> None:
    weekly = weekly_portal_names()
    assert weekly == all_portal_names()
    for portal in PORTALS:
        assert portal.weekly is True
        assert portal.spider == portal.name
