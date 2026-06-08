"""Currency normalization."""

from groundtruth.models.enums import Currency
from groundtruth.processing.base import Processor


class CurrencyNormalizer(Processor[Currency | str | None, Currency]):
    """Normalize currency to enum. Defaults to EUR for Kosovo market."""

    def process(
        self,
        value: Currency | str | None,
        description: str | None = None,
        **_,
    ) -> Currency:
        if isinstance(value, Currency):
            return value
        if value:
            upper = str(value).upper().strip()
            for currency in Currency:
                if currency.value == upper:
                    return currency

        if description:
            lower = description.lower()
            if "$" in description or "usd" in lower:
                return Currency.USD
            if "chf" in lower:
                return Currency.CHF
            if "€" in description or "eur" in lower or "euro" in lower:
                return Currency.EUR

        return Currency.EUR

    def normalize(
        self,
        value: Currency | str | None,
        description: str | None = None,
    ) -> Currency:
        """Alias for process()."""
        return self.process(value, description=description)
