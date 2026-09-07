"""MY Real Estate WP payload → ParsedListingSchema."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any

from groundtruth.models.enums import Currency, ListingType, PropertyType
from groundtruth.processing.parsers.myrealestate import parse_myrealestate_property
from groundtruth.schemas.pipeline import ParsedListingSchema
from groundtruth.scrapers.myrealestate_api import DEFAULT_RESIDENTIAL_ACTION_SLUGS
from groundtruth.versions import PARSER_VERSIONS

PARSER_VERSION = PARSER_VERSIONS["myrealestate"]
SPIDER_VERSION = "0.1.0-myrealestate"

_PROPERTY_TYPE_MAP = {
    "apartment": PropertyType.APARTMENT,
    "house": PropertyType.HOUSE,
    "villa": PropertyType.VILLA,
    "other": PropertyType.OTHER,
}


class MyRealEstateParsingService:
    def parse_payload(
        self,
        payload: dict[str, Any],
        *,
        url: str,
        raw_listing_id: int = 0,
        scrape_run_id: int | None = None,
        spider_version: str = SPIDER_VERSION,
        prishtina_only: bool = True,
        raw_html: str | None = None,
    ) -> ParsedListingSchema | None:
        prop = payload.get("property") if payload.get("property") else payload
        detail_html = raw_html or payload.get("detail_html")
        normalized = parse_myrealestate_property(
            prop,
            detail_html=detail_html,
            allowed_actions=DEFAULT_RESIDENTIAL_ACTION_SLUGS,
            prishtina_only=prishtina_only,
        )
        if normalized is None:
            return None

        listing_type = self._listing_type(normalized.get("listing_type"))
        property_type = _PROPERTY_TYPE_MAP.get(
            str(normalized.get("property_type") or "other"),
            PropertyType.OTHER,
        )

        return ParsedListingSchema(
            parser_version=PARSER_VERSION,
            raw_listing_id=raw_listing_id,
            scrape_run_id=scrape_run_id,
            spider_version=spider_version,
            source_website="myrealestate",
            source_listing_id=str(normalized.get("slug") or normalized.get("wp_id") or ""),
            original_url=url or str(normalized.get("link") or ""),
            property_type=property_type,
            listing_type=listing_type,
            is_active=True,
            sale_price=self._decimal(normalized.get("sale_price")),
            rent_price=self._decimal(normalized.get("rent_price")),
            currency=Currency.EUR,
            city=str(normalized.get("city") or "Prishtina"),
            neighborhood_raw=normalized.get("neighborhood"),
            street_raw=None,
            complex_raw=None,
            area_sqm=normalized.get("area_sqm"),
            bedrooms=normalized.get("bedrooms"),
            bathrooms=normalized.get("bathrooms"),
            floor=None,
            total_floors=None,
            building_year=None,
            description_original=normalized.get("description_text"),
            image_urls=normalized.get("image_urls") or [],
            listing_date=self._parse_date(normalized.get("published_at")),
            extra_fields={
                "wp_id": normalized.get("wp_id"),
                "category_slug": normalized.get("category_slug"),
                "area_slug": normalized.get("area_slug"),
                "property_type_slug": normalized.get("property_type_slug"),
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

    def _parse_date(self, value: Any) -> date | None:
        if not value:
            return None
        try:
            return datetime.fromisoformat(str(value).replace("Z", "+00:00")).date()
        except ValueError:
            return None
