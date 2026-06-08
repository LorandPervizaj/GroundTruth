"""Area normalization: 80 m², 80m2, 80 sqm → float."""

import re

from groundtruth.processing.base import Processor

_AREA_PATTERN = re.compile(
    r"(?P<value>\d+(?:[.,]\d+)?)\s*(?:m²|m2|sqm|metra|meter)?",
    re.IGNORECASE,
)


class AreaNormalizer(Processor[float | int | str | None, float | None]):
    """Normalize area values to square meters."""

    def process(
        self,
        value: float | int | str | None,
        description: str | None = None,
        **_,
    ) -> float | None:
        if value is None and description:
            return self._extract_from_text(description)
        if value is None:
            return None
        if isinstance(value, (int, float)):
            return float(value)

        text = str(value).strip()
        match = _AREA_PATTERN.search(text)
        if match:
            return float(match.group("value").replace(",", "."))
        return None

    def normalize(
        self,
        value: float | int | str | None,
        description: str | None = None,
    ) -> float | None:
        """Alias for process()."""
        return self.process(value, description=description)

    def _extract_from_text(self, text: str) -> float | None:
        patterns = [
            r"siperfaqe[:\s]*(\d+(?:[.,]\d+)?)\s*m",
            r"sipërfaqe[:\s]*(\d+(?:[.,]\d+)?)\s*m",
            r"(\d+(?:[.,]\d+)?)\s*m²",
        ]
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return float(match.group(1).replace(",", "."))
        return None
