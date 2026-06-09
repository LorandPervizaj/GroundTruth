"""Price normalization: 145.000 €, 145k → Decimal."""

import re
from decimal import Decimal, InvalidOperation

from groundtruth.processing.base import Processor

_PRICE_PATTERN = re.compile(
    r"(?P<value>[\d\s.,]+)\s*(?P<suffix>[kK])?",
    re.UNICODE,
)


class PriceNormalizer(Processor[Decimal | float | int | str | None, Decimal | None]):
    """Normalize price values from structured fields or description text."""

    def process(
        self,
        value: Decimal | float | int | str | None,
        description: str | None = None,
        **_,
    ) -> Decimal | None:
        if value is None and description:
            return self._extract_from_text(description)
        if value is None:
            return None
        if isinstance(value, Decimal):
            return value
        if isinstance(value, (int, float)):
            return Decimal(str(value))

        cleaned = str(value).strip()
        if not cleaned:
            return None

        match = _PRICE_PATTERN.search(cleaned.replace("€", "").replace("EUR", ""))
        if not match:
            return self._parse_decimal(cleaned)

        raw_value = self._parse_numeric_token(match.group("value"))
        if raw_value is None:
            return None
        try:
            amount = Decimal(raw_value)
        except InvalidOperation:
            return None

        if match.group("suffix"):
            amount *= 1000
        return amount.quantize(Decimal("0.01"))

    def normalize(
        self,
        value: Decimal | float | int | str | None,
        description: str | None = None,
    ) -> Decimal | None:
        """Alias for process()."""
        return self.process(value, description=description)

    def _parse_numeric_token(self, token: str) -> str | None:
        """Parse European and US-style grouped numbers: 125.000, 125,000, 1.300, 1,50."""
        cleaned = token.strip().replace(" ", "").replace("€", "").replace("EUR", "")
        if not cleaned:
            return None
        # Thousands grouped with dots: 125.000
        if re.fullmatch(r"\d{1,3}(?:\.\d{3})+", cleaned):
            return cleaned.replace(".", "")
        # Thousands grouped with commas: 125,000 (common on Gjirafa)
        if re.fullmatch(r"\d{1,3}(?:,\d{3})+", cleaned):
            return cleaned.replace(",", "")
        if "," in cleaned and "." in cleaned:
            if cleaned.rfind(",") > cleaned.rfind("."):
                return cleaned.replace(".", "").replace(",", ".")
            return cleaned.replace(",", "")
        # Decimal comma only when not a thousands pattern: 1,50
        if "," in cleaned:
            return cleaned.replace(",", ".")
        return cleaned

    def _parse_decimal(self, text: str) -> Decimal | None:
        parsed = self._parse_numeric_token(
            text.replace("€", "").replace("EUR", "").strip()
        )
        if parsed is None:
            return None
        try:
            return Decimal(parsed).quantize(Decimal("0.01"))
        except InvalidOperation:
            return None

    def _extract_from_text(self, text: str) -> Decimal | None:
        patterns = [
            r"çmimi[:\s]*([\d\s.,]+)\s*(?:€|eur|euro)?",
            r"cmimi[:\s]*([\d\s.,]+)\s*(?:€|eur|euro)?",
            r"price[:\s]*([\d\s.,]+)",
            r"(\d[\d\s.,]+)\s*(?:€|eur|euro)\b",
            r"(\d[\d\s.,]+)\s*mij[eë]\b",
        ]
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                amount = self.process(match.group(1))
                if amount is not None:
                    return amount
        return None
