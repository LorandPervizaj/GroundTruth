"""Geocoding with neighborhood centroid fallback."""

from dataclasses import dataclass

from groundtruth.config import get_settings
from groundtruth.gazetteers.loader import GazetteerService
from groundtruth.logging import get_logger

logger = get_logger(__name__)


@dataclass
class GeocodeResult:
    """Geocoding result with precision indicator."""

    latitude: float | None = None
    longitude: float | None = None
    precision: str = "none"  # none | neighborhood | street | address


class GeocodingService:
    """Geocode listings. Neighborhood centroid first; address-level optional."""

    def __init__(self, gazetteer: GazetteerService | None = None) -> None:
        self._gazetteer = gazetteer or GazetteerService()
        self._settings = get_settings()

    def geocode(
        self,
        *,
        neighborhood_slug: str | None = None,
        street_name: str | None = None,
        city: str | None = None,
        full_address: str | None = None,
    ) -> GeocodeResult:
        """Return coordinates using the best available method."""
        if neighborhood_slug:
            centroid = self._gazetteer.get_neighborhood_centroid(neighborhood_slug)
            if centroid:
                return GeocodeResult(
                    latitude=centroid[0],
                    longitude=centroid[1],
                    precision="neighborhood",
                )

        if self._settings.geocoding_enabled and full_address:
            return self._geocode_address(full_address, city)

        return GeocodeResult()

    def _geocode_address(self, address: str, city: str | None) -> GeocodeResult:
        """Optional address-level geocoding via Nominatim."""
        try:
            from geopy.geocoders import Nominatim

            query = f"{address}, {city or 'Prishtina'}, Kosovo"
            geolocator = Nominatim(user_agent=self._settings.nominatim_user_agent)
            location = geolocator.geocode(query, timeout=10)
            if location:
                return GeocodeResult(
                    latitude=location.latitude,
                    longitude=location.longitude,
                    precision="address",
                )
        except Exception as exc:
            logger.warning("geocoding_failed", address=address, error=str(exc))
        return GeocodeResult()
