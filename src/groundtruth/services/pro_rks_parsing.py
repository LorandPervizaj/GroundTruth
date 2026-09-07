"""Pro Real Estate API payload → ParsedListingSchema."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from groundtruth.models.enums import (
    BuildingAgeCategory,
    Currency,
    HeatingType,
    ListingType,
    PropertyType,
)
from groundtruth.processing.parsers.pro_rks import (
    extract_listing_date,
    nested_name,
    parse_detail_payload,
    strip_html,
)
from groundtruth.processing.redaction import redact_agent
from groundtruth.schemas.pipeline import ParsedListingSchema
from groundtruth.versions import PARSER_VERSIONS

PARSER_VERSION = PARSER_VERSIONS["pro-rks"]
SPIDER_VERSION = "0.1.0-pro-rks"

_CATEGORY_MAP: dict[str, PropertyType] = {
    "apartment": PropertyType.APARTMENT,
    "home": PropertyType.HOUSE,
    "house": PropertyType.HOUSE,
    "unit": PropertyType.APARTMENT,
    "villa": PropertyType.VILLA,
    "land": PropertyType.LAND,
    "office": PropertyType.COMMERCIAL,
    "store": PropertyType.COMMERCIAL,
    "warehouse": PropertyType.COMMERCIAL,
    "object": PropertyType.OTHER,
    "garage": PropertyType.GARAGE,
}

_HEATING_MAP: dict[str, HeatingType] = {
    "keds": HeatingType.CENTRAL,
    "central": HeatingType.CENTRAL,
    "gas": HeatingType.GAS,
    "electric": HeatingType.ELECTRIC,
    "wood": HeatingType.WOOD,
}


class ProRksParsingService:
    def parse_payload(
        self,
        payload: dict[str, Any],
        *,
        url: str,
        raw_listing_id: int = 0,
        scrape_run_id: int | None = None,
        spider_version: str = SPIDER_VERSION,
    ) -> ParsedListingSchema:
        normalized = parse_detail_payload(
            payload, listing_type_hint=payload.get("listing_type_hint")
        )
        prop = payload.get("property") or payload

        listing_type = self._resolve_listing_type(normalized, payload.get("listing_type_hint"))
        property_type = self._map_property_type(normalized.get("categories") or [])

        sale_price = self._decimal(normalized.get("sell_price"))
        rent_price = self._decimal(normalized.get("rent_price"))

        area = normalized.get("surface_m2")
        area_sqm = float(area) if area is not None else None

        bedrooms = self._int(normalized.get("bedrooms"))
        bathrooms = self._int(normalized.get("bathrooms"))
        floor = self._int(normalized.get("floor"))
        total_floors = self._int(normalized.get("total_floors"))
        building_year = self._int(normalized.get("building_year"))

        description = (
            normalized.get("description_en")
            or normalized.get("description_text")
            or strip_html(prop.get("description"))
        )

        street = normalized.get("street_name")
        complex_name = normalized.get("complex_name")
        title = normalized.get("title_en") or normalized.get("title")
        address = normalized.get("address") or nested_name(prop.get("address"))
        location_hints = " ".join(filter(None, [address, title, street, complex_name]))
        neighborhood = location_hints or None

        return ParsedListingSchema(
            parser_version=PARSER_VERSION,
            raw_listing_id=raw_listing_id,
            scrape_run_id=scrape_run_id,
            spider_version=spider_version,
            source_website="pro-rks",
            source_listing_id=str(normalized.get("slug") or prop.get("slug") or ""),
            original_url=url,
            property_type=property_type,
            listing_type=listing_type,
            is_active=True,
            sale_price=sale_price,
            rent_price=rent_price,
            currency=Currency.EUR,
            city="Prishtina",
            neighborhood_raw=neighborhood,
            street_raw=street,
            complex_raw=complex_name,
            building_raw=normalized.get("builder_name"),
            area_sqm=area_sqm,
            bedrooms=bedrooms,
            bathrooms=bathrooms,
            floor=floor,
            total_floors=total_floors,
            construction_year=building_year,
            building_age_category=self._building_age(prop),
            is_furnished=self._is_furnished(normalized.get("furnishing") or []),
            heating_type=self._map_heating(normalized.get("heating_system") or []),
            has_parking=bool(prop.get("garage")),
            description_original=description,
            image_urls=normalized.get("image_urls") or [],
            listing_date=normalized.get("listing_date") or extract_listing_date(prop),
            extra_fields={
                "pro_uuid": prop.get("id"),
                "categories": normalized.get("categories"),
                "title": normalized.get("title"),
                "title_en": normalized.get("title_en"),
                "agent": redact_agent(payload.get("agent")),
                "latitude": normalized.get("latitude"),
                "longitude": normalized.get("longitude"),
                "furnishing": normalized.get("furnishing"),
                "heating_system": normalized.get("heating_system"),
                "orientation": prop.get("orientation"),
                "infrastructure": prop.get("infrastructure"),
                "others": prop.get("others"),
                "exclusive": prop.get("exclusive"),
                "documents": prop.get("documents"),
                "possession_sheet": prop.get("possessionSheet"),
                "parcel_number": prop.get("parcelNumber"),
                "tour_360_url": prop.get("tour360Url"),
                "address": prop.get("address"),
                "sell_price_m2": prop.get("sellPriceM2"),
                "rent_price_m2": prop.get("rentPriceM2"),
                "surface_are": prop.get("surfaceAre"),
                "surface_hectare": prop.get("surfaceHectare"),
                "old_building": prop.get("oldBuilding"),
                "number_of_rooms": prop.get("numberOfRooms"),
                "number_of_balconies": prop.get("numberOfBalconies"),
                "builder": prop.get("builder"),
                "complex": prop.get("complex"),
                "street": prop.get("street"),
                "city": prop.get("city"),
                "related_properties": payload.get("related_properties"),
            },
        )

    def _resolve_listing_type(
        self,
        normalized: dict[str, Any],
        hint: str | None,
    ) -> ListingType | None:
        if hint == "sale" or normalized.get("for_sale"):
            return ListingType.SALE
        if hint == "rent" or normalized.get("for_rent"):
            return ListingType.RENT
        return None

    def _map_property_type(self, categories: list[str]) -> PropertyType:
        for category in categories:
            mapped = _CATEGORY_MAP.get(category.lower())
            if mapped:
                return mapped
        return PropertyType.OTHER

    def _map_heating(self, systems: list[str]) -> HeatingType | None:
        for system in systems:
            mapped = _HEATING_MAP.get(str(system).lower())
            if mapped:
                return mapped
        return HeatingType.UNKNOWN if systems else None

    def _building_age(self, prop: dict[str, Any]) -> BuildingAgeCategory | None:
        if prop.get("oldBuilding"):
            return BuildingAgeCategory.OLD
        year = prop.get("buildingYear")
        if isinstance(year, int) and year >= 2015:
            return BuildingAgeCategory.NEW
        if isinstance(year, int):
            return BuildingAgeCategory.MODERN
        return None

    def _is_furnished(self, furnishing: list[str]) -> bool | None:
        if not furnishing:
            return None
        return True

    def _decimal(self, value: Any) -> Decimal | None:
        if value is None:
            return None
        try:
            return Decimal(str(value))
        except Exception:
            return None

    def _int(self, value: Any) -> int | None:
        if value is None:
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None
