"""Residential complex normalization via gazetteer lookup."""

from groundtruth.gazetteers.loader import GazetteerMatch, GazetteerService
from groundtruth.processing.base import Processor


class ComplexNormalizer(Processor[str | None, GazetteerMatch | None]):
    """Resolve complex names to gazetteer entries."""

    def __init__(self, gazetteer: GazetteerService | None = None) -> None:
        self._gazetteer = gazetteer or GazetteerService()

    def process(
        self,
        value: str | None,
        neighborhood_slug: str | None = None,
        **_,
    ) -> GazetteerMatch | None:
        if not value:
            return None
        return self._gazetteer.match_complex(value, neighborhood_slug=neighborhood_slug)

    def normalize(
        self,
        value: str | None,
        neighborhood_slug: str | None = None,
    ) -> GazetteerMatch | None:
        """Alias for process()."""
        return self.process(value, neighborhood_slug=neighborhood_slug)
