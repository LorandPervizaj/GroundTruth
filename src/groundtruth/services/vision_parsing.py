"""Vision Real Estate WP REST payload → ParsedListingSchema."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any

from groundtruth.models.enums import Currency, ListingType, PropertyType
from groundtruth.processing.parsers.vision import parse_wp_property
from groundtruth.schemas.pipeline import ParsedListingSchema
from groundtruth.scrapers.vision_api import DEFAULT_RESIDENTIAL_TYPE_SLUGS
from groundtruth.versions import PARSER_VERSIONS

PARSER_VERSION = PARSER_VERSIONS["vision"]
SPIDER_VERSION = "0.1.0-vision"

_PROPERTY_TYPE_MAP = {
    "apartment": PropertyType.APARTMENT,
    "house": PropertyType.HOUSE,
    "land": PropertyType.LAND,
    "commercial": PropertyType.COMMERCIAL,
    "other": PropertyType.OTHER,
}


class VisionParsingService:
    def parse_payload(
        self,
        payload: dict[str, Any],
        *,
        url: str,
        raw_listing_id: int = 0,
        scrape_run_id: int | None = None,
        spider_version: str = SPIDER_VERSION,
        prishtina_only: bool = True,
    ) -> ParsedListingSchema | None:
        wp_prop = payload.get("property") if payload.get("property") else payload
        normalized = parse_wp_property(
            wp_prop,
            allowed_types=DEFAULT_RESIDENTIAL_TYPE_SLUGS,
            prishtina_only=prishtina_only,
        )
        if normalized is None:
            return None

        listing_type = self._listing_type(normalized.get("listing_type"))
        property_type = _PROPERTY_TYPE_MAP.get(
            str(normalized.get("property_type") or "other"),
            PropertyType.OTHER,
        )

        sale_price = self._decimal(normalized.get("sale_price"))
        rent_price = self._decimal(normalized.get("rent_price"))
        area_sqm = normalized.get("area_sqm")

        neighborhood = normalized.get("address") or normalized.get("title")

        return ParsedListingSchema(
            parser_version=PARSER_VERSION,
            raw_listing_id=raw_listing_id,
            scrape_run_id=scrape_run_id,
            spider_version=spider_version,
            source_website="vision",
            source_listing_id=str(normalized.get("slug") or normalized.get("wp_id") or ""),
            original_url=url or str(normalized.get("link") or ""),
            property_type=property_type,
            listing_type=listing_type,
            is_active=True,
            sale_price=sale_price,
            rent_price=rent_price,
            currency=Currency.EUR,
            city="Prishtina",
            neighborhood_raw=neighborhood,
            street_raw=None,
            complex_raw=None,
            area_sqm=area_sqm,
            bedrooms=normalized.get("bedrooms"),
            bathrooms=normalized.get("bathrooms"),
            floor=None,
            total_floors=None,
            building_year=normalized.get("year_built"),
            description_original=normalized.get("description_text"),
            image_urls=normalized.get("image_urls") or [],
            listing_date=self._parse_date(normalized.get("published_at")),
            extra_fields={
                "wp_id": normalized.get("wp_id"),
                "property_type_slug": normalized.get("property_type_slug"),
                "latitude": normalized.get("latitude"),
                "longitude": normalized.get("longitude"),
                "modified_at": normalized.get("modified_at"),
            },
        )

    def _listing_type(self, value: str | None) -> ListingType:
        if value == "rent":
            return ListingType.RENT
        return ListingType.SALE

    def _decimal(self, value: Any) -> Decimal | None:
        if value is None:
            return None
        try:
            return Decimal(str(value))
        except Exception:
            return None

    def _parse_date(self, value: str | None) -> date | None:
        if not value:
            return None
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00")).date()
        except ValueError:
            return None
