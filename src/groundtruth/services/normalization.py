"""Orchestrates all normalizers for a parsed listing."""

from decimal import Decimal

from sqlalchemy.orm import Session

from groundtruth.models.reference import Building, Complex, Neighborhood, Street
from groundtruth.processing.cleaners.description import DescriptionCleaner
from groundtruth.processing.geocoder.service import GeocodingService
from groundtruth.processing.normalizers.area import AreaNormalizer
from groundtruth.processing.normalizers.building import BuildingNormalizer
from groundtruth.processing.normalizers.complex import ComplexNormalizer
from groundtruth.processing.normalizers.currency import CurrencyNormalizer
from groundtruth.processing.normalizers.heating import HeatingNormalizer
from groundtruth.processing.normalizers.neighborhood import NeighborhoodNormalizer
from groundtruth.processing.normalizers.price import PriceNormalizer
from groundtruth.processing.normalizers.street import StreetNormalizer
from groundtruth.gazetteers.loader import GazetteerService
from groundtruth.processing.confidence import ConfidenceFactors
from groundtruth.gazetteers.version import compute_gazetteer_version
from groundtruth.schemas.pipeline import NormalizedListingSchema, ParsedListingSchema

NORMALIZATION_VERSION = "1.0.0"
GAZETTEER_VERSION = compute_gazetteer_version()


def _match_type(match, fallback: str = "missing") -> str:
    return match.match_type if match else fallback


class NormalizationService:
    """Apply all normalizers to produce a NormalizedListingSchema."""

    def __init__(self, session: Session | None = None) -> None:
        self._session = session
        gazetteer = GazetteerService()
        gazetteer.load()
        self._price = PriceNormalizer()
        self._area = AreaNormalizer()
        self._currency = CurrencyNormalizer()
        self._neighborhood = NeighborhoodNormalizer(gazetteer)
        self._street = StreetNormalizer(gazetteer)
        self._complex = ComplexNormalizer()
        self._building = BuildingNormalizer()
        self._heating = HeatingNormalizer()
        self._description = DescriptionCleaner()
        self._geocoder = GeocodingService()

    def normalize(
        self, parsed: ParsedListingSchema
    ) -> tuple[NormalizedListingSchema, ConfidenceFactors]:
        """Transform a parsed listing into a normalized listing."""
        currency = self._currency.normalize(parsed.currency, parsed.description_original)
        # Never re-extract price from description here — avoids populating the wrong field.
        sale_price = self._price.normalize(parsed.sale_price, None)
        rent_price = self._price.normalize(parsed.rent_price, None)
        area_sqm = self._area.normalize(parsed.area_sqm, parsed.description_original)

        neighborhood_match = self._neighborhood.normalize(
            parsed.neighborhood_raw,
            city=parsed.city,
        )
        complex_match = self._complex.normalize(
            parsed.complex_raw,
            neighborhood_slug=neighborhood_match.slug if neighborhood_match else None,
        )
        street_match = self._street.normalize(
            parsed.street_raw,
            neighborhood_slug=neighborhood_match.slug if neighborhood_match else None,
        )
        building_match = self._building.normalize(
            parsed.building_raw,
            complex_slug=complex_match.slug if complex_match else None,
        )
        heating = self._heating.normalize(parsed.heating_type, parsed.description_original)
        description_cleaned = self._description.clean(parsed.description_original)

        price_per_sqm = None
        active_price = sale_price if parsed.listing_type and parsed.listing_type.value == "sale" else rent_price
        if active_price and area_sqm and area_sqm > 0:
            price_per_sqm = Decimal(str(round(float(active_price) / area_sqm, 2)))

        geocode = self._geocoder.geocode(
            neighborhood_slug=neighborhood_match.slug if neighborhood_match else None,
            street_name=street_match.name if street_match else parsed.street_raw,
            city=parsed.city,
        )

        neighborhood_id = self._db_id(Neighborhood, neighborhood_match.slug if neighborhood_match else None)
        street_id = self._db_id(Street, street_match.slug if street_match else None)
        neighborhood_match_type = _match_type(neighborhood_match)
        if neighborhood_id is None and street_id is not None and self._session:
            street_row = self._session.query(Street).filter_by(id=street_id).first()
            if street_row:
                neighborhood_id = street_row.neighborhood_id
                neighborhood_match_type = "street_fallback"
        if neighborhood_id is None and complex_match and self._session:
            complex_row = self._session.query(Complex).filter_by(slug=complex_match.slug).first()
            if complex_row and complex_row.neighborhood_id:
                neighborhood_id = complex_row.neighborhood_id
                neighborhood_match_type = "complex_fallback"

        factors = ConfidenceFactors(
            neighborhood_match_type=neighborhood_match_type,
            neighborhood_gazetteer_slug=neighborhood_match.slug if neighborhood_match else None,
            street_match_type=_match_type(street_match),
            complex_match_type=_match_type(complex_match),
            building_match_type=_match_type(building_match),
        )

        schema = NormalizedListingSchema(
            source_website=parsed.source_website,
            source_listing_id=parsed.source_listing_id,
            original_url=parsed.original_url,
            spider_version=parsed.spider_version,
            parser_version=parsed.parser_version,
            listing_date=parsed.listing_date,
            property_type=parsed.property_type,
            listing_type=parsed.listing_type,
            is_active=parsed.is_active,
            sale_price=sale_price,
            rent_price=rent_price,
            currency=currency,
            price_per_sqm=price_per_sqm,
            city=parsed.city,
            neighborhood_id=neighborhood_id or parsed.neighborhood_id,
            street_id=street_id or parsed.street_id,
            complex_id=self._db_id(Complex, complex_match.slug if complex_match else None) or parsed.complex_id,
            building_id=self._db_id(Building, building_match.slug if building_match else None)
            or parsed.building_id,
            area_sqm=area_sqm,
            bedrooms=parsed.bedrooms,
            bathrooms=parsed.bathrooms,
            floor=parsed.floor,
            total_floors=parsed.total_floors,
            construction_year=parsed.construction_year,
            building_age_category=parsed.building_age_category,
            is_new_construction=parsed.is_new_construction,
            is_under_construction=parsed.is_under_construction,
            is_finished=parsed.is_finished,
            is_furnished=parsed.is_furnished,
            heating_type=heating,
            has_elevator=parsed.has_elevator,
            has_parking=parsed.has_parking,
            description_original=parsed.description_original,
            description_cleaned=description_cleaned,
            image_urls=parsed.image_urls,
            latitude=geocode.latitude,
            longitude=geocode.longitude,
            geocode_precision=geocode.precision,
            normalization_version=NORMALIZATION_VERSION,
            gazetteer_version=GAZETTEER_VERSION,
        )
        return schema, factors

    def _db_id(self, model: type, slug: str | None) -> int | None:
        if not slug or not self._session:
            return None
        row = self._session.query(model).filter_by(slug=slug).first()
        return row.id if row else None
