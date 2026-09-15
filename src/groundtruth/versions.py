"""Pipeline and parser version constants.

Formal portal parser versions are owned by ``groundtruth.portals.registry``.
This module re-exports them for existing imports.
"""

from __future__ import annotations

from typing import Final

from groundtruth.portals.registry import parser_versions

ETL_PIPELINE_VERSION: Final = "1.0.0"

PARSER_VERSIONS: Final[dict[str, str]] = parser_versions()
ACTIVE_PARSER_VERSIONS: Final[tuple[str, ...]] = tuple(PARSER_VERSIONS.values())
FACEBOOK_PARSER_VERSION: Final = "0.1.0-facebook-informal"
