"""Shared product corpus filters — kept import-light to avoid cycles."""

from __future__ import annotations

from datetime import date
from typing import Any

from dateutil.relativedelta import relativedelta

from groundtruth.portals.registry import source_display_names
from groundtruth.versions import (
    ACTIVE_PARSER_VERSIONS,
    FACEBOOK_PARSER_VERSION,  # noqa: F401 - re-exported for informal-tier tests
    PARSER_VERSIONS,
)

DEFAULT_MAX_AGE_MONTHS = 12
DEFAULT_WEEKLY_WINDOW_DAYS = 7
GJIRAFA_PARSER_VERSION = PARSER_VERSIONS["gjirafa"]
MERRJEP_PARSER_VERSION = PARSER_VERSIONS["merrjep"]
PRO_RKS_PARSER_VERSION = PARSER_VERSIONS["pro-rks"]
VISION_PARSER_VERSION = PARSER_VERSIONS["vision"]
TOPIA_PARSER_VERSION = PARSER_VERSIONS["topia"]
MYREALESTATE_PARSER_VERSION = PARSER_VERSIONS["myrealestate"]

# Compatibility re-export — authoritative definition is portals.registry.
SOURCE_DISPLAY_NAMES: dict[str, str] = source_display_names()

# Part B2 — informal Facebook tier; never blended into public medians.
INFORMAL_SOURCE_WEBSITES: frozenset[str] = frozenset({"facebook", "facebook-groups"})

# FACEBOOK_PARSER_VERSION re-exported from groundtruth.versions for informal-tier tests.


def is_informal_source(source_website: str) -> bool:
    return source_website in INFORMAL_SOURCE_WEBSITES


def source_display_name(source_website: str) -> str:
    """Public placeholder label for a source key (never a commercial brand)."""
    return SOURCE_DISPLAY_NAMES.get(source_website, "Portal")


def active_sources_phrase(sources: list[dict[str, object]] | None = None) -> str:
    """Generic public phrase — do not enumerate commercial portal brands."""
    if sources:
        keys = {
            str(row.get("source_website", "")).strip()
            for row in sources
            if str(row.get("source_website", "")).strip()
            and not is_informal_source(str(row.get("source_website", "")))
        }
        n = len(keys) if keys else len(SOURCE_DISPLAY_NAMES)
    else:
        n = len(SOURCE_DISPLAY_NAMES)
    if n <= 0:
        return "public listing portals"
    if n == 1:
        return "1 public listing portal"
    return f"{n} public listing portals"


# Pro-RKS API omits publish date — fall back to scrape date for corpus windowing.
EFFECTIVE_LISTING_DATE_SQL = """
COALESCE(
    nl.listing_date,
    CASE WHEN nl.source_website = 'pro-rks' THEN nl.scraped_at::date END
)
"""

_INFORMAL_SOURCE_SQL = ", ".join(f"'{s}'" for s in sorted(INFORMAL_SOURCE_WEBSITES))

VALID_CORPUS_WHERE = f"""
          AND nl.parser_version = ANY(:parser_versions)
          AND nl.source_website NOT IN ({_INFORMAL_SOURCE_SQL})
          AND NOT EXISTS (
              SELECT 1 FROM invalid_listings il
              WHERE il.parsed_listing_id = nl.parsed_listing_id
                AND il.stage IN ('validate', 'VALIDATE')
          )
"""

ACTIVE_CORPUS_WHERE = f"""
{VALID_CORPUS_WHERE}
          AND {EFFECTIVE_LISTING_DATE_SQL} IS NOT NULL
          AND {EFFECTIVE_LISTING_DATE_SQL} >= :cutoff_date
"""


def active_corpus_cutoff_date(
    *,
    max_age_months: int = DEFAULT_MAX_AGE_MONTHS,
    max_age_days: int | None = None,
) -> date:
    if max_age_days is not None and max_age_days > 0:
        return date.today() - relativedelta(days=max_age_days - 1)
    return date.today() - relativedelta(months=max_age_months)


def active_corpus_sql_params(
    *,
    max_age_months: int = DEFAULT_MAX_AGE_MONTHS,
    max_age_days: int | None = None,
) -> dict[str, Any]:
    return {
        "parser_versions": list(ACTIVE_PARSER_VERSIONS),
        "cutoff_date": active_corpus_cutoff_date(
            max_age_months=max_age_months,
            max_age_days=max_age_days,
        ),
    }
