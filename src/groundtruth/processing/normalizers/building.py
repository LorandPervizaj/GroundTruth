"""Building name normalization via gazetteer lookup."""

from groundtruth.gazetteers.loader import GazetteerMatch, GazetteerService
from groundtruth.processing.base import Processor


class BuildingNormalizer(Processor[str | None, GazetteerMatch | None]):
    """Resolve building names to gazetteer entries."""

    def __init__(self, gazetteer: GazetteerService | None = None) -> None:
        self._gazetteer = gazetteer or GazetteerService()

    def process(
        self,
        value: str | None,
        complex_slug: str | None = None,
        **_,
    ) -> GazetteerMatch | None:
        if not value:
            return None
        return self._gazetteer.match_building(value, complex_slug=complex_slug)

    def normalize(
        self,
        value: str | None,
        complex_slug: str | None = None,
    ) -> GazetteerMatch | None:
        """Alias for process()."""
        return self.process(value, complex_slug=complex_slug)
