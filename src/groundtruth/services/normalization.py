"""Orchestrates all normalizers for a parsed listing."""

from decimal import Decimal

from sqlalchemy.orm import Session

from groundtruth.gazetteers.loader import GazetteerService
from groundtruth.gazetteers.location_resolver import LocationResolver, resolve_listing_location
from groundtruth.gazetteers.version import compute_gazetteer_version
from groundtruth.models.reference import Building, Complex, District, Neighborhood
from groundtruth.processing.cleaners.description import DescriptionCleaner
from groundtruth.processing.confidence import ConfidenceFactors
from groundtruth.processing.extractors.property_type import refine_property_type
from groundtruth.processing.geocoder.service import GeocodingService
from groundtruth.processing.normalizers.area import AreaNormalizer
from groundtruth.processing.normalizers.building import BuildingNormalizer
from groundtruth.processing.normalizers.currency import CurrencyNormalizer
from groundtruth.processing.normalizers.heating import HeatingNormalizer
from groundtruth.processing.normalizers.price import PriceNormalizer
from groundtruth.schemas.pipeline import NormalizedListingSchema, ParsedListingSchema

NORMALIZATION_VERSION = "2.0.0"
GAZETTEER_VERSION = compute_gazetteer_version()


class NormalizationService:
    """Apply all normalizers to produce a NormalizedListingSchema."""

    def __init__(self, session: Session | None = None) -> None:
        self._session = session
        self._gazetteer = GazetteerService()
        self._gazetteer.load()
        self._resolver = LocationResolver()
        self._price = PriceNormalizer()
        self._area = AreaNormalizer()
        self._currency = CurrencyNormalizer()
        self._building = BuildingNormalizer()
        self._heating = HeatingNormalizer()
        self._description = DescriptionCleaner()
        self._geocoder = GeocodingService()

    def normalize(
        self, parsed: ParsedListingSchema
    ) -> tuple[NormalizedListingSchema, ConfidenceFactors]:
        currency = self._currency.normalize(parsed.currency, parsed.description_original)
        sale_price = self._price.normalize(parsed.sale_price, None)
        rent_price = self._price.normalize(parsed.rent_price, None)
        area_sqm = self._area.normalize(parsed.area_sqm, parsed.description_original)

        extra = parsed.extra_fields or {}
        title = extra.get("title_en") or extra.get("title")
        resolution = resolve_listing_location(
            self._resolver,
            title=title,
            neighborhood_raw=parsed.neighborhood_raw,
            street_raw=parsed.street_raw,
            complex_raw=parsed.complex_raw,
            description=parsed.description_original,
            city=parsed.city,
        )

        neighborhood_id = self._db_id(Neighborhood, resolution.neighborhood_slug)
        district_id = self._db_id(District, resolution.district_slug)
        complex_id = (
            None if resolution.invalid_location else self._db_id(Complex, resolution.complex_slug)
        )

        building_match = self._building.normalize(
            parsed.building_raw,
            complex_slug=resolution.complex_slug if complex_id else None,
        )
        heating = self._heating.normalize(parsed.heating_type, parsed.description_original)
        description_cleaned = self._description.clean(parsed.description_original)

        price_per_sqm = None
        active_price = (
            sale_price
            if parsed.listing_type and parsed.listing_type.value == "sale"
            else rent_price
        )
        if active_price and area_sqm and area_sqm > 0:
            price_per_sqm = Decimal(str(round(float(active_price) / area_sqm, 2)))

        source_lat = parsed.extra_fields.get("latitude") if parsed.extra_fields else None
        source_lng = parsed.extra_fields.get("longitude") if parsed.extra_fields else None
        if source_lat is not None and source_lng is not None:
            from groundtruth.processing.geocoder.service import GeocodeResult

            geocode = GeocodeResult(
                latitude=float(source_lat),
                longitude=float(source_lng),
                precision="source_coords",
            )
        else:
            geocode = self._geocoder.geocode(
                neighborhood_slug=resolution.neighborhood_slug,
                street_name=parsed.street_raw,
                city=parsed.city,
            )

        nh_match_type = resolution.match_type if resolution.neighborhood_slug else "missing"
        if resolution.vague_nh_only:
            nh_match_type = "neighborhood_vague"

        factors = ConfidenceFactors(
            neighborhood_match_type=nh_match_type,
            neighborhood_gazetteer_slug=resolution.neighborhood_slug,
            district_match_type=resolution.match_type if resolution.district_slug else "missing",
            district_gazetteer_slug=resolution.district_slug,
            complex_match_type="invalid"
            if resolution.invalid_location
            else (resolution.match_type if resolution.complex_slug else "missing"),
            building_match_type=building_match.match_type if building_match else "missing",
            location_invalid=resolution.invalid_location,
            location_invalid_reason=resolution.invalid_reason,
        )

        property_type = refine_property_type(
            parsed.property_type,
            title,
            parsed.description_original,
            area_sqm,
        )

        schema = NormalizedListingSchema(
            source_website=parsed.source_website,
            source_listing_id=parsed.source_listing_id,
            original_url=parsed.original_url,
            spider_version=parsed.spider_version,
            parser_version=parsed.parser_version,
            listing_date=parsed.listing_date,
            property_type=property_type,
            listing_type=parsed.listing_type,
            is_active=parsed.is_active,
            sale_price=sale_price,
            rent_price=rent_price,
            currency=currency,
            price_per_sqm=price_per_sqm,
            city=parsed.city,
            neighborhood_id=neighborhood_id or parsed.neighborhood_id,
            district_id=district_id,
            street_id=parsed.street_id,
            complex_id=complex_id or parsed.complex_id,
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
