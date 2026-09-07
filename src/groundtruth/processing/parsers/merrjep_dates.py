"""Parse MerrJep published-date strings (Albanian month names)."""

from __future__ import annotations

import re
from datetime import date
from html import unescape

_PUBLISH_INFO_AREA_RE = re.compile(
    r'class="ad-publish-info-area"[^>]*>(.*?)</div>',
    re.IGNORECASE | re.DOTALL,
)
_PUBLISHED_DATE_RE = re.compile(
    r'class="published-date"[^>]*>([^<]+)<',
    re.IGNORECASE,
)
_PUBLISHED_TIME_RE = re.compile(
    r'class="published-time"[^>]*>([^<]+)<',
    re.IGNORECASE,
)

_AL_MONTHS: dict[str, int] = {
    "jan": 1,
    "janar": 1,
    "shk": 2,
    "shku": 2,
    "shkurt": 2,
    "mar": 3,
    "mars": 3,
    "pri": 4,
    "prill": 4,
    "maj": 5,
    "qer": 6,
    "qershor": 6,
    "kor": 7,
    "korr": 7,
    "korrik": 7,
    "gush": 8,
    "gusht": 8,
    "sht": 9,
    "shtator": 9,
    "tet": 10,
    "tetor": 10,
    "nen": 11,
    "nentor": 11,
    "dhj": 12,
    "dhjetor": 12,
}


def _normalize_token(token: str) -> str:
    return token.strip().lower().replace("ë", "e").replace("ç", "c")


def _resolve_month(token: str) -> int | None:
    key = _normalize_token(token)
    if key in _AL_MONTHS:
        return _AL_MONTHS[key]
    for name, month in _AL_MONTHS.items():
        if key.startswith(name) or name.startswith(key):
            return month
    return None


def parse_published_date_text(text: str) -> date | None:
    """Parse MerrJep text like ``maj 16 2026`` or ``gush 07 2015``."""
    parts = text.strip().split()
    if len(parts) < 3:
        return None
    month = _resolve_month(parts[0])
    if month is None:
        return None
    try:
        day = int(parts[1])
        year = int(parts[2])
    except ValueError:
        return None
    if year < 2000 or year > 2100 or day < 1 or day > 31:
        return None
    try:
        return date(year, month, day)
    except ValueError:
        return None


def _publish_info_block(html: str) -> str:
    """Prefer the ad-publish-info-area block; fall back to full HTML."""
    area = _PUBLISH_INFO_AREA_RE.search(html)
    return area.group(1) if area else html


def extract_published_info(html: str) -> dict[str, date | str | None]:
    """Extract published date/time from MerrJep detail HTML."""
    block = _publish_info_block(html)
    date_match = _PUBLISHED_DATE_RE.search(block)
    time_match = _PUBLISHED_TIME_RE.search(block)
    date_raw = unescape(date_match.group(1)).strip() if date_match else None
    time_raw = time_match.group(1).strip() if time_match else None
    parsed = parse_published_date_text(date_raw) if date_raw else None
    return {
        "published_date": parsed,
        "published_date_raw": date_raw,
        "published_time_raw": time_raw,
    }


def extract_published_date(html: str) -> tuple[date | None, str | None]:
    """Return parsed date and raw published-date text from detail HTML."""
    info = extract_published_info(html)
    return info["published_date"], info["published_date_raw"]  # type: ignore[return-value]
