"""Harta public property payload → versioned parsed schema, with provenance."""

from __future__ import annotations

import re
from contextlib import suppress
from datetime import datetime
from decimal import Decimal, InvalidOperation

from groundtruth.models.enums import Currency, ListingType, PropertyType
from groundtruth.schemas.pipeline import ParsedListingSchema
from groundtruth.scrapers.harta_contract import (
    PARSER_VERSION,
    HartaContractError,
    folded,
    in_scope,
    listing_id,
    minimized_property,
)


def number(value) -> Decimal | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        if isinstance(value, str):
            value = re.sub(r"(?:EUR|€)", "", value, flags=re.I).strip()
            value = re.sub(r"[\s\u00a0\u202f]", "", value)
            if not re.fullmatch(r"\d+(?:[.,]\d+)*", value):
                return None
            if "," in value and "." in value:
                decimal = "," if value.rfind(",") > value.rfind(".") else "."
                grouping = "." if decimal == "," else ","
                whole, fraction = value.rsplit(decimal, 1)
                if len(fraction) not in (1, 2) or not re.fullmatch(
                    r"\d{1,3}(?:" + re.escape(grouping) + r"\d{3})+", whole
                ):
                    return None
                value = whole.replace(grouping, "") + "." + fraction
            elif "," in value or "." in value:
                separator = "," if "," in value else "."
                if re.fullmatch(r"\d{1,3}(?:" + re.escape(separator) + r"\d{3})+", value):
                    value = value.replace(separator, "")
                elif value.count(separator) == 1 and len(value.split(separator)[1]) in (1, 2):
                    value = value.replace(separator, ".")
                else:
                    return None
        result = Decimal(str(value))
        return result if result.is_finite() and 0 < result <= Decimal("1e12") else None
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
        if not isinstance(features, dict):
            raise HartaContractError("Malformed Harta features")
        rent = p["listing_type"] == "rent"
        issues = []
        if rent and features.get("rental_period") != "monthly":
            issues.append("harta_unconfirmed_monthly_rent")
        if p.get("currency") != "EUR":
            issues.append("harta_unsupported_currency")
        if p.get("contract_issues"):
            issues.extend(p["contract_issues"])
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
            v = number(str(value).replace(" ", ""))
            if v is None:
                issues.append("harta_ambiguous_description_price")
            elif price and v != price:
                issues.append("harta_description_price_conflict")
        for value in facts.get("areas_sqm", []):
            v = number(value)
            if v is None or (area and abs(v - area) > Decimal("0.5")):
                issues.append("harta_description_area_conflict")
        declared_types = facts.get("transaction_types", [])
        if (rent and "sale" in declared_types) or (not rent and "rent" in declared_types):
            issues.append("harta_description_transaction_conflict")
        if facts.get("non_apartment_type"):
            issues.append("harta_description_property_type_conflict")
        if interior and total and interior > total:
            issues.append("harta_interior_exceeds_total_area")
        if re.search(r"\b(?:fushe kosov[ae]|obiliq)\b", folded(p.get("address"))):
            issues.append("harta_address_municipality_conflict")
        latitude, longitude = None, None
        if p.get("latitude") is not None or p.get("longitude") is not None:
            try:
                latitude, longitude = float(p["latitude"]), float(p["longitude"])
                # Broad Kosovo sanity bounds, NOT municipality verification.
                if not (41.8 <= latitude <= 43.3 and 20.0 <= longitude <= 21.9):
                    raise ValueError("Outside Kosovo bounds")
            except (ValueError, TypeError, KeyError, OverflowError):
                latitude, longitude = None, None
                issues.append("harta_invalid_source_coordinates")
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
        street_number = re.search(r"\b(\d+[A-Za-z]?)$", str(street or ""))
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
            is_under_construction=True
            if p.get("construction_status") == "under_construction"
            else None,
            is_finished=True if p.get("construction_status") == "ready" else None,
            listing_date=published,
            extra_fields={
                "source_validation_issues": sorted(set(issues)),
                "address_raw": address,
                "street_number_raw": street_number.group(1) if street_number else None,
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
                "latitude": latitude,
                "longitude": longitude,
                "coordinates_raw": [p.get("latitude"), p.get("longitude")],
                "coordinate_precision": "source_supplied_unverified"
                if latitude is not None
                else "unknown",
                "construction_status_raw": p.get("construction_status"),
                "coordinate_provenance": "source_map_pin_unverified",
                "description_facts": facts,
            },
        )
