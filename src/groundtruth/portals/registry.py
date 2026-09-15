"""Thin authoritative registry for formal listing-portal metadata.

This is not a plugin system. Spider wiring, CLI commands, and ParsingService
dispatch remain elsewhere. Informal Facebook sources are intentionally excluded.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final


@dataclass(frozen=True, slots=True)
class PortalConfig:
    """Shared metadata for one formal source_website / portal."""

    name: str
    """Canonical ``source_website`` key used in DB rows and corpus filters."""

    spider: str
    """Primary Scrapy spider name (some portals also have rent/sale variant spiders)."""

    parser_version: str
    """Active parser version string required for corpus inclusion."""

    display_name: str
    """Public-facing placeholder label only — never a real commercial brand."""

    source_priority: int
    """Lower wins when choosing the cross-dedup primary listing (0 = highest)."""

    weekly: bool
    """Whether this portal participates in the standard weekly ingest set."""


# Ordered by source_priority ascending — insertion order feeds derived maps/tuples.
# Public display_name values are intentional placeholders (legal/product hygiene).
PORTALS: Final[tuple[PortalConfig, ...]] = (
    PortalConfig(
        name="gjirafa",
        spider="gjirafa",
        parser_version="1.3.1",
        display_name="Portal A",
        source_priority=0,
        weekly=True,
    ),
    PortalConfig(
        name="merrjep",
        spider="merrjep",
        parser_version="0.1.1-merrjep",
        display_name="Portal B",
        source_priority=1,
        weekly=True,
    ),
    PortalConfig(
        name="pro-rks",
        spider="pro-rks",
        parser_version="0.1.0-pro-rks",
        display_name="Portal C",
        source_priority=2,
        weekly=True,
    ),
    PortalConfig(
        name="vision",
        spider="vision",
        parser_version="0.1.0-vision",
        display_name="Portal D",
        source_priority=3,
        weekly=True,
    ),
    PortalConfig(
        name="topia",
        spider="topia",
        parser_version="0.1.0-topia",
        display_name="Portal E",
        source_priority=4,
        weekly=True,
    ),
    PortalConfig(
        name="myrealestate",
        spider="myrealestate",
        parser_version="0.1.0-myrealestate",
        display_name="Portal F",
        source_priority=5,
        weekly=True,
    ),
)


def get_portal(name: str) -> PortalConfig:
    for portal in PORTALS:
        if portal.name == name:
            return portal
    raise KeyError(f"Unknown portal: {name}")


def parser_versions() -> dict[str, str]:
    """Map source_website → active parser_version (insertion = priority order)."""
    return {p.name: p.parser_version for p in PORTALS}


def source_display_names() -> dict[str, str]:
    """Map source_website → public/report display name."""
    return {p.name: p.display_name for p in PORTALS}


def source_priority_order() -> tuple[str, ...]:
    """Portal names sorted by ascending source_priority (dedup primary preference)."""
    return tuple(p.name for p in sorted(PORTALS, key=lambda p: p.source_priority))


def weekly_portal_names() -> frozenset[str]:
    """Formal portals flagged for weekly ingest (spider variant names may differ)."""
    return frozenset(p.name for p in PORTALS if p.weekly)


def all_portal_names() -> frozenset[str]:
    return frozenset(p.name for p in PORTALS)


def public_parser_placeholders() -> list[str]:
    """Opaque public labels — never emit real parser version tokens (they embed brands)."""
    return [f"parser-{i}" for i in range(1, len(PORTALS) + 1)]
