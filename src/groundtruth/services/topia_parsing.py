"""Topia API payload → ParsedListingSchema."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any

from groundtruth.models.enums import Currency, ListingType, PropertyType
from groundtruth.processing.parsers.topia import parse_topia_property
from groundtruth.schemas.pipeline import ParsedListingSchema
from groundtruth.scrapers.topia_api import DEFAULT_RESIDENTIAL_TYPES, property_page_url
from groundtruth.versions import PARSER_VERSIONS

PARSER_VERSION = PARSER_VERSIONS["topia"]
SPIDER_VERSION = "0.1.0-topia"

_PROPERTY_TYPE_MAP = {
    "apartment": PropertyType.APARTMENT,
    "house": PropertyType.HOUSE,
    "villa": PropertyType.VILLA,
    "other": PropertyType.OTHER,
}


class TopiaParsingService:
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
        prop = payload.get("property") if payload.get("property") else payload
        normalized = parse_topia_property(
            prop,
            allowed_types=DEFAULT_RESIDENTIAL_TYPES,
            prishtina_only=prishtina_only,
        )
        if normalized is None:
            return None

        listing_type = self._listing_type(normalized.get("listing_type"))
        property_type = _PROPERTY_TYPE_MAP.get(
            str(normalized.get("property_type") or "other"),
            PropertyType.OTHER,
        )

        topia_id = normalized.get("topia_id")
        slug = str(normalized.get("slug") or "")
        reference = str(normalized.get("reference") or "")
        source_id = reference or str(topia_id or slug)
        original_url = url or (property_page_url(topia_id, slug) if topia_id and slug else "")

        return ParsedListingSchema(
            parser_version=PARSER_VERSION,
            raw_listing_id=raw_listing_id,
            scrape_run_id=scrape_run_id,
            spider_version=spider_version,
            source_website="topia",
            source_listing_id=source_id,
            original_url=original_url,
            property_type=property_type,
            listing_type=listing_type,
            is_active=True,
            sale_price=self._decimal(normalized.get("sale_price")),
            rent_price=self._decimal(normalized.get("rent_price")),
            currency=Currency.EUR,
            city=str(normalized.get("city") or "Prishtina"),
            neighborhood_raw=normalized.get("neighborhood"),
            street_raw=normalized.get("street"),
            complex_raw=None,
            area_sqm=normalized.get("area_sqm"),
            bedrooms=normalized.get("bedrooms"),
            bathrooms=normalized.get("bathrooms"),
            floor=normalized.get("floor"),
            total_floors=None,
            building_year=normalized.get("year_built"),
            description_original=normalized.get("description_text"),
            image_urls=normalized.get("image_urls") or [],
            listing_date=self._parse_date(normalized.get("published_at")),
            extra_fields={
                "topia_id": topia_id,
                "reference": reference,
                "slug": slug,
                "latitude": normalized.get("latitude"),
                "longitude": normalized.get("longitude"),
                "property_type_raw": normalized.get("property_type_raw"),
                "availability": normalized.get("availability"),
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
        if isinstance(value, date) and not isinstance(value, datetime):
            return value
        try:
            return datetime.fromisoformat(str(value).replace("Z", "+00:00")).date()
        except ValueError:
            return None
