"""Map raw listings to structured ParsedListingSchema — replayable from DB."""

from __future__ import annotations

import re
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from groundtruth.gazetteers.loader import GazetteerService
from groundtruth.models.enums import ListingType, PropertyType
from groundtruth.models.pipeline import RawListing
from groundtruth.processing.extractors.bedrooms import sanitize_bedrooms
from groundtruth.processing.extractors.text import TextExtractor
from groundtruth.processing.normalizers.area import AreaNormalizer
from groundtruth.processing.normalizers.price import PriceNormalizer
from groundtruth.processing.validation import (
    MAX_SALE_PRICE,
    MIN_PRICE_PER_SQM,
    MIN_SALE_PRICE,
)
from groundtruth.provenance.extract import extract_by_rules, neighborhood_postprocess
from groundtruth.provenance.models import ProvenanceCollector
from groundtruth.provenance.rules import (
    AREA_DESC_FALLBACK,
    AREA_REJECT_PLACEHOLDER,
    AREA_STRUCTURED,
    NH_DESCRIPTION_RULES,
    NH_TEXT_EXTRACT,
    NH_TITLE_RULES,
    PRICE_DESC_FALLBACK,
    PRICE_PLACEHOLDER_OVERRIDE,
    PRICE_SALE_DESC_FALLBACK,
    PRICE_SALE_SHORTHAND,
    PRICE_STRUCTURED,
    TYPE_RAW_FIELD,
    TYPE_TITLE_INFER,
)
from groundtruth.schemas.pipeline import ParsedListingSchema
from groundtruth.services.merrjep_parsing import MerrJepParsingService
from groundtruth.services.myrealestate_parsing import MyRealEstateParsingService
from groundtruth.services.pro_rks_parsing import ProRksParsingService
from groundtruth.services.topia_parsing import TopiaParsingService
from groundtruth.services.vision_parsing import VisionParsingService
from groundtruth.versions import PARSER_VERSIONS

_SUSPICIOUS_PRICE = Decimal("10")

PARSER_VERSION = PARSER_VERSIONS["gjirafa"]

# Release criteria for v1.3.0: invalid <3%, neighborhood >95%, area >95%, price 100%, golden >97%

# Strings that are never neighborhoods — usually parser false-positives from descriptions.
_NEIGHBORHOOD_BLOCKLIST = frozenset(
    {
        "facebook",
        "instagram",
        "whatsapp",
        "numrin",
        "numri",
        "kontaktoni",
        "kontakto",
        "teresi",
        "komplet",
        "mobiluar",
        "shitje",
        "katin",
        "perdhese",
        "perdhes",
        "viber",
        "telegram",
        "smart",
        "estate",
        "youtube",
        "tiktok",
    }
)

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
        self._merrjep = MerrJepParsingService()
        self._pro_rks = ProRksParsingService()
        self._vision = VisionParsingService()
        self._topia = TopiaParsingService()
        self._myrealestate = MyRealEstateParsingService()

    def parse_raw(self, raw: RawListing) -> ParsedListingSchema:
        """Parse a raw listing based on its source website."""
        if raw.source_website == "gjirafa":
            return self._parse_gjirafa(raw)
        if raw.source_website == "merrjep":
            return self._parse_merrjep(raw)
        if raw.source_website == "pro-rks":
            return self._parse_pro_rks(raw)
        if raw.source_website == "vision":
            return self._parse_vision(raw)
        if raw.source_website == "topia":
            return self._parse_topia(raw)
        if raw.source_website == "myrealestate":
            return self._parse_myrealestate(raw)
        raise ValueError(f"No parser for source: {raw.source_website}")

    def _parse_topia(self, raw: RawListing) -> ParsedListingSchema:
        payload = dict(raw.raw_payload or {})
        prishtina_only = bool(payload.get("prishtina_only", True))
        schema = self._topia.parse_payload(
            payload,
            url=raw.original_url,
            raw_listing_id=raw.id,
            scrape_run_id=raw.scrape_run_id,
            spider_version=raw.spider_version,
            prishtina_only=prishtina_only,
        )
        if schema is None:
            raise ValueError("Topia listing filtered (non-residential or outside Prishtina)")
        return schema

    def _parse_myrealestate(self, raw: RawListing) -> ParsedListingSchema:
        payload = dict(raw.raw_payload or {})
        prishtina_only = bool(payload.get("prishtina_only", True))
        schema = self._myrealestate.parse_payload(
            payload,
            url=raw.original_url,
            raw_listing_id=raw.id,
            scrape_run_id=raw.scrape_run_id,
            spider_version=raw.spider_version,
            prishtina_only=prishtina_only,
            raw_html=raw.raw_html,
        )
        if schema is None:
            raise ValueError(
                "MY Real Estate listing filtered (non-residential or outside Prishtina)"
            )
        return schema

    def _parse_vision(self, raw: RawListing) -> ParsedListingSchema:
        payload = dict(raw.raw_payload or {})
        prishtina_only = bool(payload.get("prishtina_only", True))
        schema = self._vision.parse_payload(
            payload,
            url=raw.original_url,
            raw_listing_id=raw.id,
            scrape_run_id=raw.scrape_run_id,
            spider_version=raw.spider_version,
            prishtina_only=prishtina_only,
        )
        if schema is None:
            raise ValueError(
                "Vision listing filtered (non-residential or outside Prishtina district)"
            )
        return schema

    def _parse_pro_rks(self, raw: RawListing) -> ParsedListingSchema:
        schema = self._pro_rks.parse_payload(
            dict(raw.raw_payload or {}),
            url=raw.original_url,
            raw_listing_id=raw.id,
            scrape_run_id=raw.scrape_run_id,
            spider_version=raw.spider_version,
        )
        if schema.listing_date is None and raw.scraped_at is not None:
            schema = schema.model_copy(update={"listing_date": raw.scraped_at.date()})
        return schema

    def _parse_merrjep(self, raw: RawListing) -> ParsedListingSchema:
        payload = dict(raw.raw_payload or {})
        raw_html = getattr(raw, "raw_html", None)
        if raw_html:
            if not payload.get("published_date"):
                from groundtruth.processing.parsers.merrjep_dates import extract_published_info

                info = extract_published_info(raw_html)
                published = info.get("published_date")
                if published is not None:
                    payload["published_date"] = published.isoformat()
                    payload["published_date_raw"] = info.get("published_date_raw")
                    payload["published_time_raw"] = info.get("published_time_raw")
            if not payload.get("price_html"):
                from groundtruth.processing.parsers.merrjep import extract_html_price

                price_html = extract_html_price(raw_html)
                if price_html is not None:
                    payload["price_html"] = price_html
        schema, _ = self._merrjep.parse_payload(
            payload,
            url=raw.original_url,
            raw_listing_id=raw.id,
        )
        schema.scrape_run_id = raw.scrape_run_id
        schema.spider_version = raw.spider_version
        return schema

    def _parse_gjirafa(self, raw: RawListing) -> ParsedListingSchema:
        payload = raw.raw_payload or {}
        description = payload.get("description")
        title = payload.get("title")
        extracted = self._text.process(description)
        prov = ProvenanceCollector(parser_version=PARSER_VERSION)

        listing_type, _ = self._resolve_listing_type(payload, title, prov)
        price_raw = payload.get("price_raw")
        sale_price: Decimal | None = None
        rent_price: Decimal | None = None
        if listing_type == ListingType.SALE:
            sale_price, _ = self._resolve_price(price_raw, description, prov, field="sale_price")
        elif listing_type == ListingType.RENT:
            rent_price, _ = self._resolve_price(price_raw, description, prov, field="rent_price")
        else:
            if (
                payload.get("listing_type") == "rent"
                or "qira" in str(payload.get("listing_type_raw", "")).lower()
            ):
                rent_price, _ = self._resolve_price(
                    price_raw, description, prov, field="rent_price"
                )
                listing_type = ListingType.RENT
                prov.record(
                    "listing_type",
                    listing_type.value,
                    rule_id=TYPE_RAW_FIELD,
                    source="listing_type_raw",
                    source_text=str(payload.get("listing_type_raw", "")),
                    confidence_contribution=0.10,
                )
            else:
                sale_price, _ = self._resolve_price(
                    price_raw, description, prov, field="sale_price"
                )

        area_sqm, _ = self._resolve_area(payload.get("area_raw"), description, prov)
        if listing_type == ListingType.SALE and sale_price is not None:
            sale_price, _ = self._fixup_sale_price(sale_price, area_sqm, description, prov)
        bedrooms = sanitize_bedrooms(
            self._parse_int(payload.get("bedrooms_raw")) or extracted.bedrooms,
            area_sqm=area_sqm,
            price=float(rent_price or sale_price) if (rent_price or sale_price) else None,
        )
        neighborhood_raw = self._clean_neighborhood(
            self._neighborhood_from_title(title, prov)
            or self._neighborhood_from_description(description, prov)
            or self._neighborhood_from_text(extracted.neighborhood, description, prov)
        )
        street_raw = self._street_from_title(
            payload.get("title")
        ) or self._street_from_neighborhood_raw(neighborhood_raw)
        if not street_raw and neighborhood_raw:
            promoted_nh, promoted_street = self._maybe_promote_to_street(neighborhood_raw)
            if promoted_street:
                street_raw = promoted_street
                neighborhood_raw = promoted_nh
        if (
            street_raw
            and neighborhood_raw
            and neighborhood_raw.lower().startswith(("rrug", "rruga"))
        ):
            neighborhood_raw = None

        complex_raw = extracted.complex_name or self._complex_from_title(payload.get("title"))
        if (
            not complex_raw
            and neighborhood_raw
            and self._gazetteer.match_complex(
                neighborhood_raw,
                neighborhood_slug=None,
            )
        ):
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
                "title": title,
                "category_raw": payload.get("category"),
                "listing_type_raw": payload.get("listing_type_raw"),
                "country_raw": payload.get("country_raw"),
                "provenance": prov.to_dict(),
            },
        )

    def _resolve_listing_type(
        self,
        payload: dict[str, Any],
        title: str | None,
        prov: ProvenanceCollector,
    ) -> tuple[ListingType | None, str | None]:
        listing_type = self._map_listing_type(payload.get("listing_type"))
        rule_id: str | None = TYPE_RAW_FIELD if listing_type else None
        inferred = self._infer_listing_type(title, listing_type)
        if inferred != listing_type and inferred is not None:
            listing_type = inferred
            rule_id = TYPE_TITLE_INFER
        if listing_type is not None and rule_id:
            prov.record(
                "listing_type",
                listing_type.value,
                rule_id=rule_id,
                source="title" if rule_id == TYPE_TITLE_INFER else "listing_type",
                source_text=title
                if rule_id == TYPE_TITLE_INFER
                else str(payload.get("listing_type", "")),
                confidence_contribution=0.10,
            )
        return listing_type, rule_id

    def _resolve_price(
        self,
        price_raw: str | None,
        description: str | None,
        prov: ProvenanceCollector | None = None,
        *,
        field: str = "rent_price",
    ) -> tuple[Decimal | None, str | None]:
        """Parse structured price first; fall back when missing or placeholder (e.g. 1 EUR)."""
        price = self._price.normalize(price_raw, None)
        desc_price = self._price.normalize(None, description) if description else None
        rule_id: str | None = None
        result: Decimal | None
        if price is None:
            result = desc_price
            rule_id = PRICE_DESC_FALLBACK if desc_price else None
            source = "description"
            source_text = description
        elif price <= _SUSPICIOUS_PRICE and desc_price is not None and desc_price > price:
            result = desc_price
            rule_id = PRICE_PLACEHOLDER_OVERRIDE
            source = "description"
            source_text = description
        else:
            result = price
            rule_id = PRICE_STRUCTURED
            source = "price_raw"
            source_text = price_raw
        if prov and result is not None and rule_id:
            prov.record(
                field,
                result,
                rule_id=rule_id,
                source=source,
                source_text=source_text,
                confidence_contribution=0.20,
            )
        return result, rule_id

    def _resolve_area(
        self,
        area_raw: str | None,
        description: str | None,
        prov: ProvenanceCollector,
    ) -> tuple[float | None, str | None]:
        area_sqm = self._area.normalize(area_raw, description)
        rule_id = AREA_STRUCTURED if area_raw and area_sqm is not None else None
        source = "area_raw"
        source_text = area_raw
        if area_sqm is not None and (area_sqm < 10 or area_sqm > 500):
            area_sqm = self._area.normalize(None, description)
            rule_id = AREA_REJECT_PLACEHOLDER if area_raw else AREA_DESC_FALLBACK
            source = "description"
            source_text = description
        elif area_sqm is not None and not area_raw:
            rule_id = AREA_DESC_FALLBACK
            source = "description"
            source_text = description
        if area_sqm is not None and rule_id:
            prov.record(
                "area_sqm",
                area_sqm,
                rule_id=rule_id,
                source=source,
                source_text=source_text,
                confidence_contribution=0.15,
            )
        return area_sqm, rule_id

    def _fixup_sale_price(
        self,
        price: Decimal,
        area_sqm: float | None,
        description: str | None,
        prov: ProvenanceCollector | None = None,
    ) -> tuple[Decimal, str | None]:
        """Correct Gjirafa sale shorthand (e.g. 1,300 EUR → 130,000) and description fallback."""
        if area_sqm is None or area_sqm <= 0:
            return price, None
        area = Decimal(str(area_sqm))
        if price / area >= MIN_PRICE_PER_SQM:
            return price, None
        desc_price = self._price.normalize(None, description) if description else None
        if desc_price is not None and desc_price > price and desc_price / area >= MIN_PRICE_PER_SQM:
            if prov:
                prov.record(
                    "sale_price",
                    desc_price,
                    rule_id=PRICE_SALE_DESC_FALLBACK,
                    source="description",
                    source_text=description,
                    confidence_contribution=0.20,
                )
            return desc_price, PRICE_SALE_DESC_FALLBACK
        if Decimal("500") <= price <= Decimal("9999"):
            scaled = price * 100
            if MIN_SALE_PRICE <= scaled <= MAX_SALE_PRICE and scaled / area >= MIN_PRICE_PER_SQM:
                if prov:
                    prov.record(
                        "sale_price",
                        scaled,
                        rule_id=PRICE_SALE_SHORTHAND,
                        source="price_raw",
                        source_text=str(price),
                        confidence_contribution=0.20,
                    )
                return scaled, PRICE_SALE_SHORTHAND
        return price, None

    def extract_neighborhood(self, title: str | None, description: str | None = None) -> str | None:
        """Public hook for neighborhood extraction — used by tests and golden dataset eval."""
        extracted = self._text.process(description)
        return self._clean_neighborhood(
            self._neighborhood_from_title(title)
            or self._neighborhood_from_description(description)
            or extracted.neighborhood
        )

    def _neighborhood_from_text(
        self,
        value: str | None,
        description: str | None,
        prov: ProvenanceCollector | None = None,
    ) -> str | None:
        if not value:
            return None
        if prov:
            prov.record(
                "neighborhood_raw",
                value,
                rule_id=NH_TEXT_EXTRACT,
                source="description",
                source_text=description,
                confidence_contribution=0.15,
            )
        return value

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
            needle in lower for needle in ("me qira", " me qira ", "leshohet", "leshoj", "me qera")
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

    def _neighborhood_from_title(
        self,
        title: str | None,
        prov: ProvenanceCollector | None = None,
    ) -> str | None:
        value, match, rule_id = extract_by_rules(
            title,
            NH_TITLE_RULES,
            postprocess=neighborhood_postprocess,
        )
        if value and prov and rule_id and match:
            prov.record(
                "neighborhood_raw",
                value,
                rule_id=rule_id,
                source="title",
                source_text=title,
                match=match,
                confidence_contribution=0.25,
            )
        return value

    def _neighborhood_from_description(
        self,
        description: str | None,
        prov: ProvenanceCollector | None = None,
    ) -> str | None:
        value, match, rule_id = extract_by_rules(
            description,
            NH_DESCRIPTION_RULES,
            postprocess=neighborhood_postprocess,
        )
        if value and prov and rule_id and match:
            prov.record(
                "neighborhood_raw",
                value,
                rule_id=rule_id,
                source="description",
                source_text=description,
                match=match,
                confidence_contribution=0.25,
            )
        return value
