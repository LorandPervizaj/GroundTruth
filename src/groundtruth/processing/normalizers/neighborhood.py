"""Neighborhood normalization via gazetteer lookup."""

from groundtruth.gazetteers.loader import GazetteerMatch, GazetteerService
from groundtruth.processing.base import Processor


class NeighborhoodNormalizer(Processor[str | None, GazetteerMatch | None]):
    """Resolve neighborhood names to gazetteer entries."""

    def __init__(self, gazetteer: GazetteerService | None = None) -> None:
        self._gazetteer = gazetteer or GazetteerService()

    def process(
        self,
        value: str | None,
        city: str | None = None,
        **_,
    ) -> GazetteerMatch | None:
        if not value:
            return None
        return self._gazetteer.match_neighborhood(value, city=city)

    def normalize(
        self,
        value: str | None,
        city: str | None = None,
    ) -> GazetteerMatch | None:
        """Alias for process()."""
        return self.process(value, city=city)
