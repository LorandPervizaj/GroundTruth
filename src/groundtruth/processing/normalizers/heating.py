"""Heating type normalization."""

import re

from groundtruth.models.enums import HeatingType
from groundtruth.processing.base import Processor

_HEATING_KEYWORDS: dict[HeatingType, list[str]] = {
    HeatingType.CENTRAL: ["qendror", "central", "termo", "ngrohje qendrore"],
    HeatingType.GAS: ["gaz", "gas"],
    HeatingType.ELECTRIC: ["elektrik", "electric"],
    HeatingType.WOOD: ["dru", "wood", "sobë"],
    HeatingType.NONE: ["pa ngrohje", "no heating"],
}


class HeatingNormalizer(Processor[HeatingType | str | None, HeatingType | None]):
    """Normalize heating type from structured field or description."""

    def process(
        self,
        value: HeatingType | str | None,
        description: str | None = None,
        **_,
    ) -> HeatingType | None:
        if isinstance(value, HeatingType):
            return value
        if value:
            lower = str(value).lower()
            for heating_type, keywords in _HEATING_KEYWORDS.items():
                if any(kw in lower for kw in keywords):
                    return heating_type

        if description:
            lower = description.lower()
            for heating_type, keywords in _HEATING_KEYWORDS.items():
                if any(re.search(rf"\b{re.escape(kw)}\b", lower) for kw in keywords):
                    return heating_type

        return HeatingType.UNKNOWN if value or description else None

    def normalize(
        self,
        value: HeatingType | str | None,
        description: str | None = None,
    ) -> HeatingType | None:
        """Alias for process()."""
        return self.process(value, description=description)
