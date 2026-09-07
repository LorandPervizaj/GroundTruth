"""Single source of truth for active pipeline and parser versions."""

from __future__ import annotations

from typing import Final

ETL_PIPELINE_VERSION: Final = "1.0.0"

PARSER_VERSIONS: Final[dict[str, str]] = {
    "gjirafa": "1.3.1",
    "merrjep": "0.1.1-merrjep",
    "pro-rks": "0.1.0-pro-rks",
    "vision": "0.1.0-vision",
    "topia": "0.1.0-topia",
    "myrealestate": "0.1.0-myrealestate",
}

ACTIVE_PARSER_VERSIONS: Final[tuple[str, ...]] = tuple(PARSER_VERSIONS.values())
FACEBOOK_PARSER_VERSION: Final = "0.1.0-facebook-informal"
