"""Weekly spider definitions and crawl subprocess command construction."""

from __future__ import annotations

import math
import os
import sys
from pathlib import Path

from groundtruth.config import PROJECT_ROOT
from groundtruth.crawl.window import CrawlWindow

KNOWN_WEEKLY_SPIDERS = frozenset(
    {
        "merrjep",
        "gjirafa",
        "gjirafa-rent",
        "gjirafa-sale",
        "pro-rks",
        "vision",
        "topia",
        "myrealestate",
    }
)
_NUMERIC_KWARGS = frozenset({"max_pages", "max_age_days", "max_age_months", "skip_existing_days"})

# Index pages tuned for ~7 days of new listings per source.
_WEEKLY_MAX_PAGES_HTML = 40
# Per Gjirafa category index (banesa / shtepi / commercial / offices) — denser than mixed.
_WEEKLY_MAX_PAGES_GJIRAFA = 20
_WEEKLY_MAX_PAGES_API = 15
_MAX_PAGE_MULTIPLIER = 8
_GJIRAFA_WEEKLY_CATEGORIES = "banesa,shtepi-vila,objekte-afariste,zyre"

# Must match groundtruth.crawl.weekly.DEFAULT_WEEKLY_INTERVAL_DAYS.
_PAGE_SCALE_BASELINE_DAYS = 7


def scaled_max_pages(base: int, days: int) -> int:
    """Scale page budget with the lookback window (7-day baseline)."""
    weeks = max(1, math.ceil(days / _PAGE_SCALE_BASELINE_DAYS))
    return base * min(weeks, _MAX_PAGE_MULTIPLIER)


def _groundtruth_base_cmd() -> list[str]:
    candidates: list[Path] = []
    if os.name == "nt":
        candidates.append(PROJECT_ROOT / ".venv" / "Scripts" / "groundtruth.exe")
    candidates.extend(
        [
            PROJECT_ROOT / ".venv" / "bin" / "groundtruth",
            PROJECT_ROOT / ".venv" / "Scripts" / "groundtruth.exe",
        ]
    )
    for candidate in candidates:
        if not candidate.is_file():
            continue
        if os.name != "nt" and candidate.suffix.lower() == ".exe":
            continue
        return [str(candidate)]
    return [sys.executable, "-m", "groundtruth.cli"]


def _validate_spider_name(spider_name: str) -> None:
    if spider_name not in KNOWN_WEEKLY_SPIDERS:
        raise ValueError(f"Unknown spider: {spider_name}")


def _validate_crawl_kwargs(kwargs: dict[str, str]) -> None:
    for key, value in kwargs.items():
        if key in _NUMERIC_KWARGS and value and not value.isdigit():
            raise ValueError(f"Invalid numeric crawl kwarg {key}={value!r}")


def _build_crawl_command(spider_name: str, kwargs: dict[str, str]) -> list[str]:
    """Map spider kwargs to a ``groundtruth crawl`` subprocess (fresh reactor per run)."""
    _validate_spider_name(spider_name)
    _validate_crawl_kwargs(kwargs)
    cmd = [*_groundtruth_base_cmd(), "crawl"]

    if spider_name == "merrjep":
        cmd.extend(["merrjep", "--detail"])
        if index := kwargs.get("index"):
            cmd.extend(["--index", index])
    elif spider_name in ("gjirafa-rent", "gjirafa-sale", "gjirafa"):
        cmd.append(spider_name)
        if spider_name == "gjirafa" and (listing_type := kwargs.get("listing_type")):
            cmd.extend(["--listing-type", listing_type])
        if categories := kwargs.get("categories"):
            cmd.extend(["--categories", categories])
    elif spider_name == "pro-rks":
        cmd.append("pro-rks")
        if listing_type := kwargs.get("listing_type"):
            cmd.extend(["--listing-type", listing_type])
    else:
        cmd.append(spider_name)

    if (max_pages := kwargs.get("max_pages")) and max_pages != "0":
        cmd.extend(["--max-pages", max_pages])

    if spider_name in ("merrjep", "gjirafa", "gjirafa-rent", "gjirafa-sale"):
        if int(kwargs.get("max_age_days", "0")) > 0:
            cmd.extend(["--max-age-days", kwargs["max_age_days"]])
        if kwargs.get("max_age_months") == "0":
            cmd.extend(["--max-age-months", "0"])

    skip_existing = kwargs.get("skip_existing", "true").lower() in ("1", "true", "yes")
    if not skip_existing:
        cmd.append("--no-skip-existing")
    elif int(kwargs.get("skip_existing_days", "0")) > 0:
        cmd.extend(["--skip-existing-days", kwargs["skip_existing_days"]])

    if spider_name in ("vision", "topia", "myrealestate"):
        prishtina = kwargs.get("prishtina_only", "true").lower() in ("1", "true", "yes")
        if not prishtina:
            cmd.append("--no-prishtina-only")

    if crawl_window := kwargs.get("crawl_window"):
        cmd.extend(["--crawl-window", crawl_window])

    return cmd


def _weekly_spider_jobs(window: CrawlWindow) -> list[tuple[str, str, dict[str, str]]]:
    """(source_label, spider_name, kwargs) for each weekly job."""
    days = str(window.days)
    html_pages = str(scaled_max_pages(_WEEKLY_MAX_PAGES_HTML, window.days))
    gjirafa_pages = str(scaled_max_pages(_WEEKLY_MAX_PAGES_GJIRAFA, window.days))
    api_pages = str(scaled_max_pages(_WEEKLY_MAX_PAGES_API, window.days))
    common = {
        "max_age_days": days,
        "skip_existing": "true",
        "skip_existing_days": days,
    }
    return [
        (
            "merrjep-rent",
            "merrjep",
            {
                **common,
                "discovery_only": "false",
                "archive_only": "false",
                "index": "apartments_rent,houses_rent",
                "max_pages": html_pages,
                "max_age_months": "0",
            },
        ),
        (
            "merrjep-sale",
            "merrjep",
            {
                **common,
                "discovery_only": "false",
                "archive_only": "false",
                "index": "apartments_sale,houses_sale",
                "max_pages": html_pages,
                "max_age_months": "0",
            },
        ),
        (
            "gjirafa-rent",
            "gjirafa-rent",
            {
                **common,
                "categories": _GJIRAFA_WEEKLY_CATEGORIES,
                "max_pages": gjirafa_pages,
            },
        ),
        (
            "gjirafa-sale",
            "gjirafa-sale",
            {
                **common,
                "categories": _GJIRAFA_WEEKLY_CATEGORIES,
                "max_pages": gjirafa_pages,
            },
        ),
        (
            "pro-rks",
            "pro-rks",
            {
                "max_pages": api_pages,
                "listing_type": "both",
                "skip_existing": "true",
                "skip_existing_days": days,
            },
        ),
        (
            "vision",
            "vision",
            {
                **common,
                "max_pages": api_pages,
                "prishtina_only": "true",
            },
        ),
        (
            "topia",
            "topia",
            {
                **common,
                "max_pages": api_pages,
                "prishtina_only": "true",
            },
        ),
        (
            "myrealestate",
            "myrealestate",
            {
                **common,
                "max_pages": api_pages,
                "prishtina_only": "true",
            },
        ),
    ]
