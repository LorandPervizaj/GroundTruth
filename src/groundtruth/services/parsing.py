"""Map raw listings to structured ParsedListingSchema — replayable from DB."""

from __future__ import annotations

import re
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from groundtruth.models.enums import ListingType, PropertyType
from groundtruth.models.pipeline import RawListing
from groundtruth.processing.extractors.text import TextExtractor
from groundtruth.processing.normalizers.area import AreaNormalizer
from groundtruth.processing.normalizers.price import PriceNormalizer
from groundtruth.schemas.pipeline import ParsedListingSchema

PARSER_VERSION = "1.2.0"

# Strings that are never neighborhoods — usually parser false-positives from descriptions.
_NEIGHBORHOOD_BLOCKLIST = frozenset({
    "facebook", "instagram", "whatsapp", "numrin", "numri", "kontaktoni", "kontakto",
    "teresi", "komplet", "mobiluar", "shitje", "katin", "perdhese", "perdhes",
    "viber", "telegram", "smart", "estate", "youtube", "tiktok",
})

_CATEGORY_MAP: list[tuple[str, PropertyType]] = [
    ("banes", PropertyType.APARTMENT),
    ("shtëpi", PropertyType.HOUSE),
    ("shtepi", PropertyType.HOUSE),
    ("vila", PropertyType.VILLA),
    ("tok", PropertyType.LAND),
    ("garazh", PropertyType.GARAGE),
    ("lokal", PropertyType.COMMERCIAL),
]


class ParsingService:
    """Convert immutable raw payloads into ParsedListingSchema."""

    def __init__(self) -> None:
        self._price = PriceNormalizer()
        self._area = AreaNormalizer()
        self._text = TextExtractor()

    def parse_raw(self, raw: RawListing) -> ParsedListingSchema:
        """Parse a raw listing based on its source website."""
        if raw.source_website == "gjirafa":
            return self._parse_gjirafa(raw)
        raise ValueError(f"No parser for source: {raw.source_website}")

    def _parse_gjirafa(self, raw: RawListing) -> ParsedListingSchema:
        payload = raw.raw_payload or {}
        description = payload.get("description")
        extracted = self._text.process(description)

        listing_type = self._map_listing_type(payload.get("listing_type"))
        listing_type = self._infer_listing_type(payload.get("title"), listing_type)
        price_raw = payload.get("price_raw")
        sale_price: Decimal | None = None
        rent_price: Decimal | None = None
        if listing_type == ListingType.SALE:
            sale_price = self._price.normalize(price_raw, description)
        elif listing_type == ListingType.RENT:
            rent_price = self._price.normalize(price_raw, description)
        else:
            if payload.get("listing_type") == "rent" or "qira" in str(
                payload.get("listing_type_raw", "")
            ).lower():
                rent_price = self._price.normalize(price_raw, description)
                listing_type = ListingType.RENT
            else:
                sale_price = self._price.normalize(price_raw, description)

        area_sqm = self._area.normalize(payload.get("area_raw"), description)
        if area_sqm is not None and area_sqm < 10:
            area_sqm = self._area.normalize(None, description)
        bedrooms = self._parse_int(payload.get("bedrooms_raw")) or extracted.bedrooms
        neighborhood_raw = self._clean_neighborhood(
            self._neighborhood_from_title(payload.get("title"))
            or self._neighborhood_from_description(description)
            or extracted.neighborhood
        )
        street_raw = self._street_from_title(payload.get("title")) or self._street_from_neighborhood_raw(
            neighborhood_raw
        )
        if street_raw and neighborhood_raw and neighborhood_raw.lower().startswith(("rrug", "rruga")):
            neighborhood_raw = None

        return ParsedListingSchema(
            parser_version=PARSER_VERSION,
            raw_listing_id=raw.id,
            scrape_run_id=raw.scrape_run_id,
            spider_version=raw.spider_version,
            source_website=raw.source_website,
            source_listing_id=raw.source_listing_id,
            original_url=raw.original_url,
            listing_date=self._parse_gjirafa_date(payload.get("listing_date_raw")),
            property_type=self._map_property_type(payload.get("category")),
            listing_type=listing_type,
            is_active=True,
            sale_price=sale_price,
            rent_price=rent_price,
            city=self._normalize_city(payload.get("city_raw")),
            neighborhood_raw=neighborhood_raw,
            street_raw=street_raw,
            complex_raw=extracted.complex_name,
            area_sqm=area_sqm,
            bedrooms=bedrooms,
            floor=extracted.floor,
            is_furnished=extracted.is_furnished,
            has_elevator=extracted.has_elevator,
            has_parking=extracted.has_parking,
            description_original=description,
            image_urls=payload.get("image_urls") or [],
            extra_fields={
                "title": payload.get("title"),
                "category_raw": payload.get("category"),
                "listing_type_raw": payload.get("listing_type_raw"),
                "country_raw": payload.get("country_raw"),
            },
        )

    def _clean_neighborhood(self, value: str | None) -> str | None:
        if not value:
            return None
        text = value.strip().strip(".,;")
        text = re.sub(r"^(?:ne\s+|në\s+)", "", text, flags=re.IGNORECASE)
        text = re.sub(
            r"^(?:lagje\s+te\s+|lagjen\s+e\s+|lagjen\s+|lagjes\s+se\s+)",
            "",
            text,
            flags=re.IGNORECASE,
        )
        text = re.sub(r"\s*[_\s]+\d+\+\d+\s*$", "", text)
        text = re.sub(r"\s+\d+\+\d+\s*$", "", text)
        text = text.split("/")[0].strip()
        if text.lower() in _NEIGHBORHOOD_BLOCKLIST or len(text) < 3:
            return None
        if text.lower().startswith(("rrug", "rruga", "shitje ")):
            return None
        return text.strip().strip(".,;") or None

    def _street_from_title(self, title: str | None) -> str | None:
        if not title:
            return None
        match = re.search(
            r"(?:te\s+|ne\s+)(Rr(?:uga|ugen)\s+[A-Za-z0-9]+)",
            title,
            re.IGNORECASE,
        )
        return match.group(1).strip() if match else None

    def _street_from_neighborhood_raw(self, neighborhood_raw: str | None) -> str | None:
        if not neighborhood_raw:
            return None
        if re.match(r"^rrug", neighborhood_raw, re.IGNORECASE):
            return neighborhood_raw
        return None

    def _infer_listing_type(
        self,
        title: str | None,
        current: ListingType | None,
    ) -> ListingType | None:
        if not title:
            return current
        lower = title.lower()
        if "me qira" in lower or " me qira " in lower:
            return ListingType.RENT
        if "ne shitje" in lower or "për shitje" in lower or "per shitje" in lower:
            return ListingType.SALE
        return current

    def _map_listing_type(self, value: Any) -> ListingType | None:
        if value is None:
            return None
        text = str(value).lower()
        if text in ("rent", "qira"):
            return ListingType.RENT
        if text in ("sale", "shitje"):
            return ListingType.SALE
        return None

    def _map_property_type(self, category: str | None) -> PropertyType | None:
        if not category:
            return None
        lower = category.lower()
        for needle, prop_type in _CATEGORY_MAP:
            if needle in lower:
                return prop_type
        return PropertyType.OTHER

    def _parse_int(self, value: Any) -> int | None:
        if value is None:
            return None
        match = re.search(r"\d+", str(value))
        return int(match.group()) if match else None

    def _parse_gjirafa_date(self, raw: str | None) -> date | None:
        if not raw:
            return None
        for fmt in ("%d/%m/%Y %H:%M", "%d/%m/%Y"):
            try:
                return datetime.strptime(raw.strip(), fmt).date()
            except ValueError:
                continue
        return None

    def _normalize_city(self, city: str | None) -> str | None:
        if not city:
            return None
        mapping = {
            "prishtine": "Prishtina",
            "prishtina": "Prishtina",
            "prizren": "Prizren",
            "peje": "Peja",
            "peja": "Peja",
        }
        return mapping.get(city.strip().lower(), city.strip())

    def _neighborhood_from_title(self, title: str | None) -> str | None:
        if not title:
            return None
        patterns = (
            r"(?:ne|në)\s+lagjen\s+e\s+(.+)",
            r"(?:ne|në)\s+lagjen\s+(.+)",
            r"(?:ne|në)\s+[Ll]agje\s+te\s+(.+)",
            r"(?:me\s+qira|shitje)\s+te\s+(.+)",
            r"ne\s+shitje\s+ne\s+(.+)",
            r"(?:ne|në)\s+([A-Za-zÀ-ÿ][A-Za-zÀ-ÿ\s]+?)(?:\s*/|\s*$)",
            r"(?:me\s+qira|shpallje)\s+(?:ne|në)\s+(.+)",
        )
        for pattern in patterns:
            match = re.search(pattern, title, re.IGNORECASE)
            if match:
                return match.group(1).strip()
        return None

    def _neighborhood_from_description(self, description: str | None) -> str | None:
        if not description:
            return None
        patterns = (
            r"(?:ne|në)\s+lagjen\s+e\s+([A-Za-zÀ-ÿ0-9\s]+)",
            r"(?:ne|në)\s+lagjen\s+([A-Za-zÀ-ÿ0-9\s]+)",
            r"(?:ne|në)\s+lagje\s+te\s+([A-Za-zÀ-ÿ0-9\s]+)",
        )
        for pattern in patterns:
            match = re.search(pattern, description, re.IGNORECASE)
            if match:
                candidate = match.group(1).strip()
                if len(candidate) > 2:
                    return candidate
        return None
