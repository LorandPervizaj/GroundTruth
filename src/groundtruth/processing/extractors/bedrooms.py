"""Bedroom extraction from Albanian listing titles and descriptions."""

from __future__ import annotations

import re
import unicodedata

MAX_BEDROOMS = 10

_DHOMA = r"dhom\w*"
_DHOME_NOT_LIVING = rf"{_DHOMA}\b(?!\s+e\s+(?:ndej|nde\w*|dit\w*|gjum|fjetj))"

_WORD_TO_NUM: dict[str, int] = {
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "nje": 1,
    "një": 1,
    "dy": 2,
    "tri": 3,
    "kater": 4,
    "katër": 4,
    "pesë": 5,
    "pese": 5,
    "gjashtë": 6,
    "gjashte": 6,
    "shtatë": 7,
    "shtate": 7,
    "tetë": 8,
    "tete": 8,
    "nëntë": 9,
    "nente": 9,
    "dhjetë": 10,
    "dhjete": 10,
}

_COUNT_TOKEN = (
    r"\d{1,2}|nje|një|dy|tri|kater|katër|pesë|pese|gjashtë|gjashte|"
    r"shtatë|shtate|tetë|tete|nëntë|nente|dhjetë|dhjete"
)

# N+M layout: 2+1, Pejton_2+1, (3+1), 2 + 1
_PLUS_ONE_RE = re.compile(r"(?:^|[^\d])(\d{1,2})\s*\+\s*(\d{1,2})(?:\b|[^\d])")

# MerrJep structured field: "Dhoma: 2", "Dhoma: 1", "Dhoma: 2.5"
_DHOMA_FIELD_RE = re.compile(
    rf"\b{_DHOMA}\s*:\s*(\d+(?:[.,]\d+)?)",
    re.IGNORECASE,
)

# "2 dhoma gjumi", "DyDhoma gjumi", "3dhoma gjumi", "dy dhoma glumi" (typo)
_BEDROOM_GJUMI_RE = re.compile(
    rf"\b({_COUNT_TOKEN})\s*{_DHOMA}(?:\s+(?:t[ëe]?|te|e))?\s*g\w*um",
    re.IGNORECASE,
)

# "Dhoma gjumi - 3", "Dhoma gjumi 2"
_GJUMI_TRAIL_COUNT_RE = re.compile(
    rf"\b{_DHOMA}\s*g\w*um\w*\s*[-:–]?\s*(\d{{1,2}})",
    re.IGNORECASE,
)

# "dy dhoma te fjetjes", "1 dhom? e fjetjes", "dy dhoma fjetje"
_FJETJE_RE = re.compile(
    rf"\b({_COUNT_TOKEN})\s*dh\w*m\w*[^a-zA-Z0-9]{{0,3}}(?:\s+(?:te\s+)?)?(?:e\s+)?fjetj",
    re.IGNORECASE,
)

# "dydhomshe", "dy dhomeshe", "tridhomshe", "1 dhomshe", "obligative1 dhomshe"
_DHOMSHE_COUNT_RE = re.compile(
    rf"(?:\b({_COUNT_TOKEN})|(?<=[^\d])(\d{{1,2}}))\s*{_DHOMA}she\b",
    re.IGNORECASE,
)
_DHOMSHE_WORD_RE = re.compile(
    rf"\b(dy|tri|nje|një)\s*{_DHOMA}she\b",
    re.IGNORECASE,
)

# "dy dhoma", "|Dy dhoma |" (not day/living room)
_WORD_DHOMA_RE = re.compile(
    rf"\b({_COUNT_TOKEN})\s+{_DHOMA}\b(?!\s+e\s+(?:dit|nde|gjum|fjetj))",
    re.IGNORECASE,
)

# "Dhom gjumi", "Dhom? gjumi" (abbreviated / mojibake)
_LOOSE_GJUMI_RE = re.compile(
    rf"\b{_DHOMA}[^a-zA-Z0-9]{{0,3}}\s*g\w*um",
    re.IGNORECASE,
)

# "Dholam e gjumit" (dhoma typo)
_DHOMA_TYPO_GJUMI_RE = re.compile(
    r"\bdh\w+l\w*\s+(?:e\s+)?g\w*um",
    re.IGNORECASE,
)

# "Kuzhinë … Dhome" or "Dhome … Kuzhinë" list → 1 BR
_KUZHIN_DHOME_RE = re.compile(
    rf"(?:kuzhin\w*.{{0,60}}{_DHOME_NOT_LIVING}|{_DHOME_NOT_LIVING}.{{0,60}}kuzhin\w*)",
    re.IGNORECASE | re.DOTALL,
)

# "Renditjet: - Dhome - Kuzhine -"
_LIST_DHOME_RE = re.compile(
    rf"(?:renditj|posedon|struktur).{{0,100}}-?\s*{_DHOMA}\b\s*-",
    re.IGNORECASE | re.DOTALL,
)

# "2 dhoma", "1 dhomshe" — not living-room phrasing
_DIGIT_DHOMA_RE = re.compile(
    rf"\b(\d{{1,2}})\s+{_DHOMA}(?!\s+e\s+(?:ndej|dit|gjum))",
    re.IGNORECASE,
)

# Singular bedroom: "dhoma gjumi", "dhoma e gjumit", "një dhomë gjumi"
_SINGULAR_BEDROOM_RE = re.compile(
    rf"\b(?:një|nje|1\s+)?{_DHOMA}(?:\s+(?:t[ëe]?|te|e))?\s*g\w*um",
    re.IGNORECASE,
)

# Sallon+kuzhinë list with a single "dhome" (not living-room phrasing) → 1 BR
_STRUCTURE_ONE_BED_RE = re.compile(
    rf"(?:sallon|kuzhin).{{0,120}}\b{_DHOMA}\b(?!\s+e\s+(?:ndej|dit|gjum))",
    re.IGNORECASE | re.DOTALL,
)

_ENGLISH_BED_RE = re.compile(
    r"\b(one|two|three|four|1|2|3|4)\s*(?:bed(?:room)?s?|br)\b",
    re.IGNORECASE,
)

# garsoniere + common MerrJep typos (gasoniere, gasonjerk, Garsonjere, …)
_GARSONIERE_RE = re.compile(
    r"\b(?:gars|gas)on\w*(?:ier|jer|jerk)\w*",
    re.IGNORECASE,
)
_STUDIO_RE = re.compile(r"\bstudio\b", re.IGNORECASE)

# Open-plan / living-room only: "dhomen e ndenjes", "dhoma e dites"
_LIVING_ROOM_ONLY_RE = re.compile(
    rf"\b{_DHOMA}\s+(?:e\s+)?(?:nde\w*|dit\w*)",
    re.IGNORECASE,
)

# Sallon + kuzhinë with no bedroom mention → typical 1+1 layout (1 bedroom)
_SALON_KITCHEN_RE = re.compile(
    r"sallon.{0,60}kuzhin|kuzhin.{0,60}sallon",
    re.IGNORECASE | re.DOTALL,
)


def _normalize(text: str) -> str:
    return unicodedata.normalize("NFKC", text)


def _parse_count(token: str) -> int | None:
    token = token.lower()
    value = int(token) if token.isdigit() else _WORD_TO_NUM.get(token)
    if value is None or value < 0 or value > MAX_BEDROOMS:
        return None
    return value


def _parse_decimal_count(raw: str) -> int | None:
    try:
        value = round(float(raw.replace(",", ".")))
    except ValueError:
        return None
    if value < 0 or value > MAX_BEDROOMS:
        return None
    return value


def _has_bedroom_hint(text: str) -> bool:
    lower = text.lower()
    return bool(
        re.search(rf"{_DHOMA}\s+(?:e\s+)?g\w*um", lower)
        or re.search(rf"\b({_COUNT_TOKEN})\s+{_DHOMA}", lower)
        or _PLUS_ONE_RE.search(lower)
        or _DHOMA_FIELD_RE.search(lower)
    )


def _extract_from_text(text: str) -> int | None:
    plus = _PLUS_ONE_RE.search(text)
    if plus:
        bedrooms = int(plus.group(1))
        if 0 <= bedrooms <= MAX_BEDROOMS:
            return bedrooms

    field = _DHOMA_FIELD_RE.search(text)
    if field:
        bedrooms = _parse_decimal_count(field.group(1))
        if bedrooms is not None:
            return bedrooms

    gjumi = _BEDROOM_GJUMI_RE.search(text)
    if gjumi:
        bedrooms = _parse_count(gjumi.group(1))
        if bedrooms is not None:
            return bedrooms

    trail = _GJUMI_TRAIL_COUNT_RE.search(text)
    if trail:
        bedrooms = int(trail.group(1))
        if 0 <= bedrooms <= MAX_BEDROOMS:
            return bedrooms

    fjetje = _FJETJE_RE.search(text)
    if fjetje:
        bedrooms = _parse_count(fjetje.group(1))
        if bedrooms is not None:
            return bedrooms

    dhomshe = _DHOMSHE_COUNT_RE.search(text) or _DHOMSHE_WORD_RE.search(text)
    if dhomshe:
        token = dhomshe.group(1) or (dhomshe.lastindex and dhomshe.group(dhomshe.lastindex))
        bedrooms = _parse_count(token) if token else 1
        if bedrooms is not None:
            return bedrooms

    word_dhom = _WORD_DHOMA_RE.search(text)
    if word_dhom:
        bedrooms = _parse_count(word_dhom.group(1))
        if bedrooms is not None:
            return bedrooms

    dhom = _DIGIT_DHOMA_RE.search(text)
    if dhom:
        bedrooms = int(dhom.group(1))
        if 0 <= bedrooms <= MAX_BEDROOMS:
            return bedrooms

    if (
        _SINGULAR_BEDROOM_RE.search(text)
        or _LOOSE_GJUMI_RE.search(text)
        or _DHOMA_TYPO_GJUMI_RE.search(text)
    ):
        return 1

    english = _ENGLISH_BED_RE.search(text)
    if english:
        bedrooms = _parse_count(english.group(1))
        if bedrooms is not None:
            return bedrooms

    if _GARSONIERE_RE.search(text) or _STUDIO_RE.search(text):
        return 0

    if not _has_bedroom_hint(text) and _LIVING_ROOM_ONLY_RE.search(text):
        return 0

    if (
        _STRUCTURE_ONE_BED_RE.search(text)
        or _KUZHIN_DHOME_RE.search(text)
        or _LIST_DHOME_RE.search(text)
    ):
        return 1

    if (
        not _has_bedroom_hint(text)
        and _SALON_KITCHEN_RE.search(text)
        and not _LIVING_ROOM_ONLY_RE.search(text)
    ):
        return 1

    return None


def extract_bedrooms_from_text(*texts: str | None) -> int | None:
    """
    Extract bedroom count from title/description.

    Priority per text (title before description): N+M layout → Dhoma: N field
    → explicit dhoma gjumi → digit + dhoma → singular dhoma gjumi → studio/garsoniere.
    """
    for text in texts:
        if not text:
            continue
        result = _extract_from_text(_normalize(text))
        if result is not None:
            return result
    return None


def sanitize_bedrooms(
    bedrooms: int | None,
    *,
    area_sqm: float | None = None,
    price: float | None = None,
) -> int | None:
    """Drop implausible bedroom values (common when price/area leak into the field)."""
    if bedrooms is None:
        return None
    if bedrooms > MAX_BEDROOMS:
        return None
    if area_sqm is not None and bedrooms == int(area_sqm) and area_sqm <= MAX_BEDROOMS:
        return None
    if price is not None and bedrooms == int(price) and price <= MAX_BEDROOMS:
        return None
    return bedrooms
