"""Property-type classification from Albanian listing text."""

from __future__ import annotations

import unicodedata

from groundtruth.models.enums import PropertyType

# Houses below this footprint fail validation (see ListingValidator) — not auto-retyped.
HOUSE_MIN_AREA_SQM = 150.0

_APT_MARKERS = ("banes", "banese", "banesa", "apartament", "penthouse")
_STUDIO_MARKERS = ("garsonier", "garsoniere", "studio")
_HOUSE_MARKERS = ("shtepi", "shtepia", "shpi", "shpia")
_VILLA_MARKERS = ("vila", "villa")
_KAT_SHTEPIE_MARKERS = ("kat shtepie", "kat shtepise", "kat shtepi", "kat te shtepise")
_COMMERCIAL_MARKERS = ("lokal", "zyre", "dyqan")
_LAND_MARKERS = ("truall", "toke", "parcel")
_ROOM_MARKERS = ("ndarje qeraje", " cimer", "dhom me qira", "dhoma me qira", "dhom per qira")


def _normalize(text: str) -> str:
    text = unicodedata.normalize("NFKC", text).lower()
    return text.replace("ë", "e").replace("ç", "c")


def _classify_single_text(text: str | None) -> PropertyType | None:
    if not text:
        return None
    norm = _normalize(text)
    if any(m in norm for m in _COMMERCIAL_MARKERS):
        return PropertyType.COMMERCIAL
    if any(m in norm for m in _LAND_MARKERS):
        return PropertyType.LAND
    if any(m in norm for m in _STUDIO_MARKERS):
        return PropertyType.STUDIO
    if any(m in norm for m in _ROOM_MARKERS):
        return PropertyType.ROOM
    if any(m in norm for m in _KAT_SHTEPIE_MARKERS):
        return PropertyType.APARTMENT
    if any(m in norm for m in _APT_MARKERS):
        return PropertyType.APARTMENT
    if any(m in norm for m in _VILLA_MARKERS):
        return PropertyType.VILLA
    if any(m in norm for m in _HOUSE_MARKERS):
        return PropertyType.HOUSE
    return None


def classify_property_type(
    title: str | None,
    description: str | None,
    *,
    default: PropertyType = PropertyType.APARTMENT,
) -> PropertyType:
    """Title-first property type — title beats description on conflict."""
    for text in (title, description):
        found = _classify_single_text(text)
        if found is not None:
            return found
    return default


def refine_property_type(
    property_type: PropertyType | None,
    title: str | None,
    description: str | None,
    area_sqm: float | None = None,
) -> PropertyType | None:
    """
    Fix obvious text mislabels (e.g. title says Banesa but body says shtepi).

    House minimum area is enforced by validation, not by retyping to apartment.
    Villa is not subject to house area rules.
    """
    del area_sqm  # area checks live in ListingValidator for HOUSE only
    if property_type is None:
        return None
    if property_type not in (PropertyType.HOUSE, PropertyType.VILLA):
        return property_type

    title_norm = _normalize(title or "")
    blob = _normalize(f"{title or ''} {description or ''}")

    if any(m in title_norm for m in _APT_MARKERS):
        return PropertyType.APARTMENT
    if any(m in blob for m in _KAT_SHTEPIE_MARKERS):
        return PropertyType.APARTMENT
    if any(m in blob for m in _APT_MARKERS) and not any(m in blob for m in _HOUSE_MARKERS):
        return PropertyType.APARTMENT

    return property_type
