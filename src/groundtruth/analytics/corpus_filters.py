"""Shared product corpus filters — kept import-light to avoid cycles."""

from __future__ import annotations

from datetime import date
from typing import Any

from dateutil.relativedelta import relativedelta

from groundtruth.versions import (
    ACTIVE_PARSER_VERSIONS,
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

SOURCE_DISPLAY_NAMES: dict[str, str] = {
    "gjirafa": "Gjirafa",
    "merrjep": "MerrJep",
    "pro-rks": "Pro Real Estate",
    "vision": "Vision Real Estate",
    "topia": "Topia",
    "myrealestate": "MY Real Estate",
}

# Part B2 — informal Facebook tier; never blended into public medians.
INFORMAL_SOURCE_WEBSITES: frozenset[str] = frozenset({"facebook", "facebook-groups"})


def is_informal_source(source_website: str) -> bool:
    return source_website in INFORMAL_SOURCE_WEBSITES


def source_display_name(source_website: str) -> str:
    return SOURCE_DISPLAY_NAMES.get(source_website, source_website)


def active_sources_phrase(sources: list[dict[str, object]] | None = None) -> str:
    """Human-readable source list for narratives (e.g. 'Gjirafa + MerrJep + Pro Real Estate')."""
    if not sources:
        return " + ".join(SOURCE_DISPLAY_NAMES.values())
    names: list[str] = []
    for row in sources:
        key = str(row.get("source_website", ""))
        label = source_display_name(key)
        if label not in names:
            names.append(label)
    return " + ".join(names) if names else " + ".join(SOURCE_DISPLAY_NAMES.values())


# Pro-RKS API omits publish date — fall back to scrape date for corpus windowing.
EFFECTIVE_LISTING_DATE_SQL = """
COALESCE(
    nl.listing_date,
    CASE WHEN nl.source_website = 'pro-rks' THEN nl.scraped_at::date END
)
"""

_INFORMAL_SOURCE_SQL = ", ".join(f"'{s}'" for s in sorted(INFORMAL_SOURCE_WEBSITES))

ACTIVE_CORPUS_WHERE = f"""
          AND nl.parser_version = ANY(:parser_versions)
          AND nl.source_website NOT IN ({_INFORMAL_SOURCE_SQL})
          AND {EFFECTIVE_LISTING_DATE_SQL} IS NOT NULL
          AND {EFFECTIVE_LISTING_DATE_SQL} >= :cutoff_date
          AND NOT EXISTS (
              SELECT 1 FROM invalid_listings il
              WHERE il.parsed_listing_id = nl.parsed_listing_id
                AND il.stage IN ('validate', 'VALIDATE')
          )
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
