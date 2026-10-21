"""Harta public property payload → versioned parsed schema, with provenance."""

from __future__ import annotations

from contextlib import suppress
from datetime import datetime
from decimal import Decimal, InvalidOperation

from groundtruth.models.enums import Currency, ListingType, PropertyType
from groundtruth.schemas.pipeline import ParsedListingSchema
from groundtruth.scrapers.harta_contract import (
    PARSER_VERSION,
    HartaContractError,
    in_scope,
    listing_id,
    minimized_property,
)


def number(value) -> Decimal | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        result = Decimal(str(value).strip())
        return result if result.is_finite() and result > 0 else None
    except (InvalidOperation, ValueError):
        return None


def integer(value) -> int | None:
    try:
        result = Decimal(str(value))
        return int(result) if result.is_finite() and result >= 0 and result == int(result) else None
    except (InvalidOperation, ValueError, TypeError):
        return None


class HartaParsingService:
    def parse_payload(
        self,
        payload: dict,
        *,
        url: str,
        raw_listing_id: int = 0,
        scrape_run_id: int | None = None,
        spider_version: str = PARSER_VERSION,
    ) -> ParsedListingSchema:
        p = payload.get("property")
        if not isinstance(p, dict) or not in_scope(p):
            raise HartaContractError("Harta outside Prishtina apartment sale/rent scope")
        source_id = listing_id(p)
        if p.get("status") != "active":
            raise HartaContractError("Harta property unavailable or inactive")
        features = p.get("features") or {}
        rent = p["listing_type"] == "rent"
        issues = []
        if rent and features.get("rental_period") != "monthly":
            issues.append("harta_unconfirmed_monthly_rent")
        if p.get("currency") != "EUR":
            issues.append("harta_unsupported_currency")
        # price_total is explicit total even when the displayed price is per m².
        price = number(p.get("price_total"))
        if price is None and p.get("price_unit") == "total":
            price = number(p.get("price"))
        if price is None:
            issues.append("harta_missing_total_price")
        if p.get("price_unit") == "total" and price and number(p.get("price")) not in (None, price):
            issues.append("harta_conflicting_structured_price")
        interior, total = number(p.get("living_area")), number(p.get("surface_area"))
        # sqft is a legacy field labelled m² by this site, NOT square feet. Do not
        # use it to guess an interior area when only total/gross is supplied.
        area = interior
        if area is None:
            issues.append("harta_missing_interior_area")
        if p.get("surface_unit") not in (None, "m2"):
            issues.append("harta_unsupported_area_unit")
            area = None
        facts = p.get("description_facts")
        if facts is None:
            facts = minimized_property(p)["description_facts"]
        for value in facts.get("asking_prices", []):
            # Ambiguous locale punctuation remains unknown instead of guessing.
            v = number(str(value).replace(" ", ""))
            if v is None:
                issues.append("harta_ambiguous_description_price")
            elif price and v != price:
                issues.append("harta_description_price_conflict")
        for value in facts.get("areas_sqm", []):
            v = number(value)
            if v is None or (area and abs(v - area) > Decimal("0.5")):
                issues.append("harta_description_area_conflict")
        published = None
        if p.get("created_at"):
            with suppress(ValueError, TypeError):
                published = datetime.fromisoformat(p["created_at"].replace("Z", "+00:00")).date()
        floor = integer(p.get("floor"))
        levels = features.get("floor_levels") or []
        if floor is None and len(levels) == 1:
            floor = integer(levels[0])
        address = p.get("address")
        street = p.get("street")
        if not street and address and "," in address:
            street = address.split(",", 1)[0].strip()
        return ParsedListingSchema(
            raw_listing_id=raw_listing_id,
            scrape_run_id=scrape_run_id,
            source_website="harta",
            source_listing_id=source_id,
            original_url=url,
            parser_version=PARSER_VERSION,
            spider_version=spider_version,
            listing_type=ListingType.RENT if rent else ListingType.SALE,
            property_type=PropertyType.APARTMENT,
            is_active=True,
            sale_price=None if rent else price,
            rent_price=price if rent else None,
            currency=Currency.EUR,
            area_sqm=float(area) if area else None,
            city="Prishtina",
            neighborhood_raw=p.get("neighborhood"),
            street_raw=street,
            bedrooms=integer(p.get("bedrooms")),
            bathrooms=integer(p.get("bathrooms")),
            floor=floor,
            is_furnished=features.get("furnished"),
            listing_date=published,
            extra_fields={
                "source_validation_issues": sorted(set(issues)),
                "address_raw": address,
                "municipality_raw": p.get("city"),
                "area_basis": "living_area" if area else "unknown",
                "living_area_raw": str(interior) if interior else None,
                "total_area_raw": str(total) if total else None,
                "area_concepts_differ": bool(interior and total and interior != total),
                "price_unit": p.get("price_unit"),
                "price_per_m2_raw": p.get("price_per_m2"),
                "publication_date_basis": "source_declared" if published else "unknown",
                "published_at_raw": p.get("created_at"),
                "source_updated_at": p.get("updated_at"),
                "latitude": p.get("latitude"),
                "longitude": p.get("longitude"),
                "coordinate_provenance": "source_map_pin_unverified",
                "description_facts": facts,
            },
        )
