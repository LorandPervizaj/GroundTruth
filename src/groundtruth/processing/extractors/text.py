"""Extract structured fields from unstructured listing descriptions."""

import re
from dataclasses import dataclass, field

from groundtruth.processing.base import Processor
from groundtruth.processing.extractors.bedrooms import extract_bedrooms_from_text


@dataclass
class ExtractedFields:
    """Fields extracted from description text."""

    neighborhood: str | None = None
    complex_name: str | None = None
    is_furnished: bool | None = None
    has_elevator: bool | None = None
    has_parking: bool | None = None
    floor: int | None = None
    bedrooms: int | None = None
    extra: dict[str, str] = field(default_factory=dict)


class TextExtractor(Processor[str | None, ExtractedFields]):
    """Rule-based extraction from Albanian listing descriptions."""

    def process(self, value: str | None, **_) -> ExtractedFields:
        if not value:
            return ExtractedFields()

        lower = value.lower()
        result = ExtractedFields()

        floor_match = re.search(r"katin e (\d+)", lower)
        if floor_match:
            result.floor = int(floor_match.group(1))

        result.bedrooms = extract_bedrooms_from_text(value)

        if re.search(r"pa\s+mobil", lower):
            result.is_furnished = False
        elif re.search(
            r"(?:e\s+)?mobiluar|mobilimi|te\s+mobiluar|mobilimi\s+komplet",
            lower,
        ):
            result.is_furnished = True
        if "ashensor" in lower:
            result.has_elevator = True
        if "parking" in lower or "garazh" in lower:
            result.has_parking = True

        complex_match = re.search(
            r"kompleks(?:in|i)?\s+(?:e\s+)?([A-Za-z0-9\s]+)", value, re.IGNORECASE
        )
        if complex_match:
            result.complex_name = complex_match.group(1).strip()

        return result
