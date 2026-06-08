"""Description text cleaning."""

import re

import ftfy

from groundtruth.processing.base import Processor

_WHITESPACE = re.compile(r"\s+")


class DescriptionCleaner(Processor[str | None, str | None]):
    """Clean listing descriptions: fix encoding, normalize whitespace."""

    def process(self, value: str | None, **_) -> str | None:
        if not value:
            return None
        text = ftfy.fix_text(value)
        text = _WHITESPACE.sub(" ", text).strip()
        return text or None

    def clean(self, value: str | None) -> str | None:
        """Alias for process()."""
        return self.process(value)
