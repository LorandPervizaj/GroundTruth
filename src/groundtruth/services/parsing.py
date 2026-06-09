"""Map raw listings to structured ParsedListingSchema — replayable from DB."""

from __future__ import annotations

import re
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from groundtruth.gazetteers.loader import GazetteerService
from groundtruth.models.enums import ListingType, PropertyType
from groundtruth.processing.validation import (
    MAX_SALE_PRICE,
    MIN_PRICE_PER_SQM,
    MIN_SALE_PRICE,
)
from groundtruth.models.pipeline import RawListing
from groundtruth.processing.extractors.text import TextExtractor
from groundtruth.processing.normalizers.area import AreaNormalizer
from groundtruth.processing.normalizers.price import PriceNormalizer
from groundtruth.schemas.pipeline import ParsedListingSchema

_SUSPICIOUS_PRICE = Decimal("10")

PARSER_VERSION = "1.3.0"

# Release criteria for v1.3.0: invalid <3%, neighborhood >95%, area >95%, price 100%, golden >97%

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
        self._gazetteer = GazetteerService()
        self._gazetteer.load()

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
            sale_price = self._resolve_price(price_raw, description)
        elif listing_type == ListingType.RENT:
            rent_price = self._resolve_price(price_raw, description)
        else:
            if payload.get("listing_type") == "rent" or "qira" in str(
                payload.get("listing_type_raw", "")
            ).lower():
                rent_price = self._resolve_price(price_raw, description)
                listing_type = ListingType.RENT
            else:
                sale_price = self._resolve_price(price_raw, description)

        area_sqm = self._area.normalize(payload.get("area_raw"), description)
        if area_sqm is not None and (area_sqm < 10 or area_sqm > 500):
            area_sqm = self._area.normalize(None, description)
        if listing_type == ListingType.SALE and sale_price is not None:
            sale_price = self._fixup_sale_price(sale_price, area_sqm, description)
        bedrooms = self._parse_int(payload.get("bedrooms_raw")) or extracted.bedrooms
        neighborhood_raw = self._clean_neighborhood(
            self._neighborhood_from_title(payload.get("title"))
            or self._neighborhood_from_description(description)
            or extracted.neighborhood
        )
        street_raw = self._street_from_title(payload.get("title")) or self._street_from_neighborhood_raw(
            neighborhood_raw
        )
        if not street_raw and neighborhood_raw:
            promoted_nh, promoted_street = self._maybe_promote_to_street(neighborhood_raw)
            if promoted_street:
                street_raw = promoted_street
                neighborhood_raw = promoted_nh
        if street_raw and neighborhood_raw and neighborhood_raw.lower().startswith(("rrug", "rruga")):
            neighborhood_raw = None

        complex_raw = extracted.complex_name or self._complex_from_title(payload.get("title"))
        if not complex_raw and neighborhood_raw:
            if self._gazetteer.match_complex(neighborhood_raw, neighborhood_slug=None):
                complex_raw = neighborhood_raw
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
            complex_raw=complex_raw,
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

    def _resolve_price(
        self,
        price_raw: str | None,
        description: str | None,
    ) -> Decimal | None:
        """Parse structured price first; fall back when missing or placeholder (e.g. 1 EUR)."""
        price = self._price.normalize(price_raw, None)
        desc_price = self._price.normalize(None, description) if description else None
        if price is None:
            return desc_price
        if price <= _SUSPICIOUS_PRICE and desc_price is not None and desc_price > price:
            return desc_price
        return price

    def _fixup_sale_price(
        self,
        price: Decimal,
        area_sqm: float | None,
        description: str | None,
    ) -> Decimal:
        """Correct Gjirafa sale shorthand (e.g. 1,300 EUR → 130,000) and description fallback."""
        if area_sqm is None or area_sqm <= 0:
            return price
        area = Decimal(str(area_sqm))
        if price / area >= MIN_PRICE_PER_SQM:
            return price
        desc_price = self._price.normalize(None, description) if description else None
        if desc_price is not None and desc_price > price and desc_price / area >= MIN_PRICE_PER_SQM:
            return desc_price
        if Decimal("500") <= price <= Decimal("9999"):
            scaled = price * 100
            if MIN_SALE_PRICE <= scaled <= MAX_SALE_PRICE and scaled / area >= MIN_PRICE_PER_SQM:
                return scaled
        return price

    def extract_neighborhood(self, title: str | None, description: str | None = None) -> str | None:
        """Public hook for neighborhood extraction — used by tests and golden dataset eval."""
        extracted = self._text.process(description)
        return self._clean_neighborhood(
            self._neighborhood_from_title(title)
            or self._neighborhood_from_description(description)
            or extracted.neighborhood
        )

    def _clean_neighborhood(self, value: str | None) -> str | None:
        if not value:
            return None
        text = value.strip().strip(".,;!")
        text = re.sub(r"^(?:ne\s+|në\s+|te\s+)", "", text, flags=re.IGNORECASE)
        text = re.sub(
            r"^(?:lagjia\s+e\s+|lagje\s+te\s+|lagjen\s+e\s+|lagjen\s+|lagjes\s+se\s+)",
            "",
            text,
            flags=re.IGNORECASE,
        )
        text = text.split(",")[0].strip()
        text = re.sub(r"\s*\([^)]*\)\s*$", "", text)
        text = re.sub(r"\s+afer\s+.+$", "", text, flags=re.IGNORECASE)
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
        for pattern in (
            r"lagjen\s+(Rr(?:uga|ugen)\s+[A-Za-z0-9]+)",
            r"me\s+qera\s+(Rr(?:uga|ugen)\s+[A-Za-z0-9]+)",
            r"me\s+qira\s+(Rr(?:uga|ugen)\s+[A-Za-z0-9]+)",
            r"(?:rrugën|rrugen|rrugë|rruge)\s+([A-Za-z0-9]+)",
            r"(?:te\s+|ne\s+|në\s+)(Rr(?:uga|ugen)\s+[A-Za-z0-9]+)",
        ):
            match = re.search(pattern, title, re.IGNORECASE)
            if match:
                street = match.group(1).strip()
                if not street.lower().startswith("rrug"):
                    street = f"Rruga {street}"
                return street
        return None

    def _maybe_promote_to_street(
        self, neighborhood_raw: str | None
    ) -> tuple[str | None, str | None]:
        """When NH extraction picked a street name, route it to street_raw."""
        if not neighborhood_raw:
            return None, None
        if re.match(r"^rrug", neighborhood_raw, re.IGNORECASE):
            return None, neighborhood_raw
        if self._gazetteer.match_neighborhood(neighborhood_raw, city="Prishtina"):
            return neighborhood_raw, None
        match = self._gazetteer.match_street(neighborhood_raw, neighborhood_slug=None)
        if match and match.match_type in ("exact", "alias"):
            return None, neighborhood_raw
        return neighborhood_raw, None

    def _complex_from_title(self, title: str | None) -> str | None:
        if not title:
            return None
        lower = title.lower()
        self._gazetteer._ensure_loaded()  # noqa: SLF001
        for entry in self._gazetteer._data.get("complexes", []):  # noqa: SLF001
            candidates = [entry["name"], *entry.get("aliases", [])]
            for name in candidates:
                if name.lower() in lower:
                    return entry["name"]
        return None

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
        if any(
            needle in lower
            for needle in ("me qira", " me qira ", "leshohet", "leshoj", "me qera")
        ):
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
        street_prefix = re.match(
            r"^([A-Za-zÀ-ÿ][A-Za-zÀ-ÿ0-9\s]+),\s*rrug",
            title,
            re.IGNORECASE,
        )
        if street_prefix:
            return street_prefix.group(1).strip()
        patterns = (
            r"(?:ne|në)\s+lagjen\s+e\s+(.+)",
            r"(?:ne|në)\s+lagjen\s+(.+)",
            r"(?:ne|në)\s+[Ll]agje\s+te\s+(.+)",
            r"me\s+qira\s+(?:ne|në)\s+(.+)",
            r"me\s+qira\s+te\s+(.+)",
            r"me\s+qera\s+(.+?)(?:\s*$|_)",
            r"leshohet\s+me\s+qira\s+(?:banesa\s+)?(?:ne|në|te)\s+(.+)",
            r"leshohet\s+me\s+qira\s+banesa\s+te\s+(.+)",
            r"(?:ne|në)\s+[Ss]hitje\s+(?:ne|në\s+)?(.+)",
            r"ne\s+shitje\s+te\s+(.+)",
            r"shitet\s+banese\s+te\s+(.+)",
            r"shitet\s+banesa\s+te\s+(.+)",
            r"shitet\s+banesa\s+ne\s+(?:lagjen\s+)?(.+)",
            r"(?i)shitet.*?ne\s+(.+)",
            r"(?:me\s+qira|shitje)\s+te\s+(.+)",
            r"ne\s+shitje\s+ne\s+(.+)",
            r"te\s+(Prishtina e Re|Prishtine e Re|Prishtina e re)",
            r"(?:me\s+qira|shpallje)\s+(?:ne|në)\s+(.+)",
            r"me\s+qira\s+(.+?)(?:\s*$|_)",
            r"(?:ne|në)\s+([A-Za-zÀ-ÿ][A-Za-zÀ-ÿ\s]+?)(?:\s*/|\s*$)",
        )
        for pattern in patterns:
            match = re.search(pattern, title, re.IGNORECASE)
            if match:
                value = match.group(1).strip()
                if "lagjen" in value.lower():
                    sub = re.search(r"lagjen\s+(.+)", value, re.IGNORECASE)
                    if sub:
                        value = sub.group(1).strip()
                return value
        return None

    def _neighborhood_from_description(self, description: str | None) -> str | None:
        if not description:
            return None
        patterns = (
            r"leshohet\s+me\s+qira\s+banesa\s+(?:ne|në|te)\s+([A-Za-zÀ-ÿ0-9\s]+)",
            r"me\s+qira\s+(?:banesa\s+)?(?:ne|në|te)\s+([A-Za-zÀ-ÿ0-9\s]+)",
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
