"""Formal listing-portal metadata registry."""

from groundtruth.portals.registry import (
    PORTALS,
    PortalConfig,
    all_portal_names,
    get_portal,
    parser_versions,
    source_display_names,
    source_priority_order,
    weekly_portal_names,
)

__all__ = [
    "PORTALS",
    "PortalConfig",
    "all_portal_names",
    "get_portal",
    "parser_versions",
    "source_display_names",
    "source_priority_order",
    "weekly_portal_names",
]
