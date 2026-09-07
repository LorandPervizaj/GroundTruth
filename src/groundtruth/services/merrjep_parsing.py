"""MerrJep raw payload → parsed listing with explicit fallback chains and provenance."""

from __future__ import annotations

import re
import unicodedata
from datetime import date
from decimal import Decimal
from typing import Any

from groundtruth.gazetteers.loader import GazetteerService
from groundtruth.models.enums import ListingType, PropertyType
from groundtruth.processing.extractors.bedrooms import extract_bedrooms_from_text, sanitize_bedrooms
from groundtruth.processing.extractors.property_type import (
    classify_property_type,
    refine_property_type,
)
from groundtruth.processing.normalizers.area import AreaNormalizer
from groundtruth.processing.normalizers.price import PriceNormalizer
from groundtruth.processing.parsers.merrjep import parse_listing_html
from groundtruth.processing.parsers.merrjep_dates import parse_published_date_text
from groundtruth.provenance.extract import extract_by_rules, neighborhood_postprocess
from groundtruth.provenance.models import ProvenanceCollector
from groundtruth.provenance.rules import (
    MJ_AREA_DESC,
    MJ_AREA_TITLE,
    MJ_BED_TEXT,
    MJ_NH_COMPLEX,
    MJ_NH_GAZETTEER,
    MJ_NH_REGEX,
    MJ_NH_STREET,
    MJ_PRICE_DESC,
    MJ_PRICE_HTML,
    MJ_PRICE_LDJSON,
    MJ_PRICE_PER_SQM,
    MJ_PRICE_TITLE,
    MJ_PRICE_ZERO_OVERRIDE,
    MJ_TYPE_DESC,
    MJ_TYPE_NAME,
    NH_DESCRIPTION_RULES,
    NH_TITLE_RULES,
)
from groundtruth.schemas.pipeline import ParsedListingSchema
from groundtruth.versions import PARSER_VERSIONS

PARSER_VERSION = PARSER_VERSIONS["merrjep"]
_SUSPICIOUS_PRICE = Decimal("10")
_EUR_LEADING_RE = re.compile(r"€\s*(\d{1,3}(?:[.,]\d{3})+|\d+(?:[.,]\d{1,2})?)")
_PER_SQM_PRICE_RE = re.compile(
    r"(?:çmimi|qmimi|cmimi)\s*(?:per|për)\s*m\s*?2?\s*[:\s]*([\d\s.,]+)\s*(?:€|eur)",
    re.IGNORECASE,
)
_AREA_SNIP_RE = re.compile(r"(\d+(?:[.,]\d+)?)\s*m[²2]\b", re.IGNORECASE)

_NEIGHBORHOOD_BLOCKLIST = frozenset(
    {
        "facebook",
        "instagram",
        "whatsapp",
        "numrin",
        "kontaktoni",
        "shitje",
        "qira",
        "qera",
    }
)


class MerrJepParsingService:
    """Measurement-first MerrJep parser — provenance on every field."""

    def __init__(self) -> None:
        self._price = PriceNormalizer()
        self._area = AreaNormalizer()
        self._gazetteer = GazetteerService()
        self._gazetteer.load()

    def parse_html(self, html: str, url: str) -> tuple[ParsedListingSchema, dict[str, Any]]:
        """Parse HTML end-to-end; return schema and provenance dict."""
        payload = parse_listing_html(html, url)
        return self.parse_payload(payload, url=url)

    def parse_payload(
        self,
        payload: dict[str, Any],
        *,
        url: str | None = None,
        raw_listing_id: int = 0,
    ) -> tuple[ParsedListingSchema, dict[str, Any]]:
        title = payload.get("title")
        description = payload.get("description")
        prov = ProvenanceCollector(parser_version=PARSER_VERSION)

        listing_type = self._resolve_listing_type(payload, title, description, prov)
        area_sqm = self._resolve_area(description, title, prov)

        sale_price: Decimal | None = None
        rent_price: Decimal | None = None
        if listing_type == ListingType.SALE:
            sale_price = self._resolve_price(
                payload, title, description, prov, field="sale_price", area_sqm=area_sqm
            )
        elif listing_type == ListingType.RENT:
            rent_price = self._resolve_price(
                payload, title, description, prov, field="rent_price", area_sqm=area_sqm
            )
        neighborhood_raw = self._resolve_neighborhood(title, description, prov)
        street_raw = self._resolve_street(title, description, prov)
        complex_raw = self._resolve_complex(title, description, prov)
        bedrooms = self._resolve_bedrooms(title, description, prov, area_sqm=area_sqm)
        property_type = refine_property_type(
            self._map_property_type(title, description),
            title,
            description,
            area_sqm,
        )

        schema = ParsedListingSchema(
            parser_version=PARSER_VERSION,
            raw_listing_id=raw_listing_id,
            scrape_run_id=None,
            spider_version="0.1.0-merrjep",
            source_website="merrjep",
            source_listing_id=str(payload.get("source_listing_id", "")),
            original_url=url or payload.get("original_url", ""),
            listing_date=self._resolve_listing_date(payload),
            property_type=property_type,
            listing_type=listing_type,
            is_active=True,
            sale_price=sale_price,
            rent_price=rent_price,
            city="Prishtina",
            neighborhood_raw=neighborhood_raw,
            street_raw=street_raw,
            complex_raw=complex_raw,
            area_sqm=area_sqm,
            bedrooms=bedrooms,
            description_original=description,
            image_urls=[],
            extra_fields={
                "title": title,
                "price_ldjson": payload.get("price_ldjson"),
                "has_ld_json": payload.get("has_ld_json"),
                "provenance": prov.to_dict(),
            },
        )
        return schema, prov.to_dict()

    def _resolve_price(
        self,
        payload: dict[str, Any],
        title: str | None,
        description: str | None,
        prov: ProvenanceCollector,
        *,
        field: str,
        area_sqm: float | None = None,
    ) -> Decimal | None:
        """ld+json → description (incl. €/m²) → title → null."""
        ld_price = payload.get("price_ldjson")
        price = self._price.normalize(ld_price, None) if ld_price is not None else None

        if price is not None and price > _SUSPICIOUS_PRICE:
            prov.record(
                field,
                price,
                rule_id=MJ_PRICE_LDJSON,
                source="ld_json",
                source_text=str(ld_price),
                confidence_contribution=0.25,
            )
            return price

        html_price = payload.get("price_html")
        if html_price is not None:
            price = self._price.normalize(html_price, None)
            if price is not None and price > _SUSPICIOUS_PRICE:
                prov.record(
                    field,
                    price,
                    rule_id=MJ_PRICE_HTML,
                    source="html",
                    source_text=str(html_price),
                    confidence_contribution=0.22,
                )
                return price

        per_sqm_total = self._price_per_sqm_total(description, title, area_sqm)
        if per_sqm_total is not None and per_sqm_total > _SUSPICIOUS_PRICE:
            prov.record(
                field,
                per_sqm_total,
                rule_id=MJ_PRICE_PER_SQM,
                source="description",
                source_text=description,
                confidence_contribution=0.18,
            )
            return per_sqm_total

        desc_price = self._extract_price_text(description)
        if desc_price is not None and desc_price > _SUSPICIOUS_PRICE:
            rule = (
                MJ_PRICE_ZERO_OVERRIDE
                if price is not None and price <= _SUSPICIOUS_PRICE
                else MJ_PRICE_DESC
            )
            prov.record(
                field,
                desc_price,
                rule_id=rule,
                source="description",
                source_text=description,
                confidence_contribution=0.20,
            )
            return desc_price

        title_price = self._extract_price_text(title)
        if title_price is not None and title_price > _SUSPICIOUS_PRICE:
            prov.record(
                field,
                title_price,
                rule_id=MJ_PRICE_TITLE,
                source="title",
                source_text=title,
                confidence_contribution=0.15,
            )
            return title_price

        return None

    def _price_per_sqm_total(
        self,
        description: str | None,
        title: str | None,
        area_sqm: float | None,
    ) -> Decimal | None:
        text = f"{title or ''}\n{description or ''}"
        match = _PER_SQM_PRICE_RE.search(text)
        if not match:
            return None
        per_sqm = self._price.normalize(match.group(1), None)
        if per_sqm is None or per_sqm <= _SUSPICIOUS_PRICE:
            return None
        area = area_sqm
        if area is None:
            area_match = _AREA_SNIP_RE.search(text)
            if area_match:
                area = self._area.normalize(area_match.group(1), None)
        if area is None or area < 10:
            return None
        return (per_sqm * Decimal(str(area))).quantize(Decimal("0.01"))

    def _extract_price_text(self, text: str | None) -> Decimal | None:
        if not text:
            return None
        text = unicodedata.normalize("NFKC", text)
        price = self._price.normalize(None, text)
        if price is not None:
            return price
        match = _EUR_LEADING_RE.search(text)
        if match:
            return self._price.normalize(match.group(1), None)
        return None

    def _resolve_bedrooms(
        self,
        title: str | None,
        description: str | None,
        prov: ProvenanceCollector,
        *,
        area_sqm: float | None,
    ) -> int | None:
        bedrooms = extract_bedrooms_from_text(title, description)
        if bedrooms is not None:
            prov.record(
                "bedrooms",
                bedrooms,
                rule_id=MJ_BED_TEXT,
                source="title"
                if title and extract_bedrooms_from_text(title) is not None
                else "description",
                source_text=title or description,
                confidence_contribution=0.08,
            )
        return sanitize_bedrooms(bedrooms, area_sqm=area_sqm)

    def _resolve_area(
        self,
        description: str | None,
        title: str | None,
        prov: ProvenanceCollector,
    ) -> float | None:
        """description → title → null."""
        area = self._area.normalize(None, description) if description else None
        if area is not None and 10 <= area <= 500:
            prov.record(
                "area_sqm",
                area,
                rule_id=MJ_AREA_DESC,
                source="description",
                source_text=description,
                confidence_contribution=0.15,
            )
            return area

        area = self._area.normalize(None, title) if title else None
        if area is not None and 10 <= area <= 500:
            prov.record(
                "area_sqm",
                area,
                rule_id=MJ_AREA_TITLE,
                source="title",
                source_text=title,
                confidence_contribution=0.12,
            )
            return area

        return None

    def _resolve_neighborhood(
        self,
        title: str | None,
        description: str | None,
        prov: ProvenanceCollector,
    ) -> str | None:
        """gazetteer → complex → street → regex → null."""
        combined = f"{title or ''}\n{description or ''}"

        nh = self._match_gazetteer_in_text(combined, kind="neighborhoods", city="Prishtina")
        if nh:
            prov.record(
                "neighborhood_raw",
                nh,
                rule_id=MJ_NH_GAZETTEER,
                source="description",
                source_text=combined[:200],
                confidence_contribution=0.30,
            )
            return nh

        cx = self._match_gazetteer_in_text(combined, kind="complexes")
        if cx:
            prov.record(
                "neighborhood_raw",
                cx,
                rule_id=MJ_NH_COMPLEX,
                source="description",
                source_text=combined[:200],
                confidence_contribution=0.22,
            )
            return cx

        st = self._match_gazetteer_in_text(combined, kind="streets")
        if st:
            prov.record(
                "street_raw",
                st,
                rule_id=MJ_NH_STREET,
                source="description",
                source_text=combined[:200],
                confidence_contribution=0.18,
            )
            return None

        for source_text, rules in (
            (title, NH_TITLE_RULES),
            (description, NH_DESCRIPTION_RULES),
        ):
            value, match, rule_id = extract_by_rules(
                source_text, rules, postprocess=neighborhood_postprocess
            )
            cleaned = self._clean_neighborhood(value)
            if cleaned:
                prov.record(
                    "neighborhood_raw",
                    cleaned,
                    rule_id=MJ_NH_REGEX,
                    source="title" if source_text is title else "description",
                    source_text=source_text,
                    match=match,
                    confidence_contribution=0.12,
                )
                return cleaned

        return None

    def _resolve_street(
        self,
        title: str | None,
        description: str | None,
        prov: ProvenanceCollector,
    ) -> str | None:
        if prov.fields.get("street_raw"):
            return prov.fields["street_raw"].value
        combined = f"{title or ''} {description or ''}"
        return self._match_gazetteer_in_text(combined, kind="streets")

    def _resolve_complex(
        self,
        title: str | None,
        description: str | None,
        prov: ProvenanceCollector,
    ) -> str | None:
        if (
            prov.fields.get("neighborhood_raw")
            and prov.fields["neighborhood_raw"].rule_id == MJ_NH_COMPLEX
        ):
            return prov.fields["neighborhood_raw"].value
        combined = f"{title or ''} {description or ''}"
        return self._match_gazetteer_in_text(combined, kind="complexes")

    def _match_gazetteer_in_text(
        self,
        text: str,
        *,
        kind: str,
        city: str | None = None,
    ) -> str | None:
        if not text:
            return None
        lower = text.lower()
        entries = self._gazetteer._data.get(kind, [])  # noqa: SLF001
        candidates: list[tuple[int, str]] = []
        for entry in entries:
            if city and kind == "neighborhoods":
                entry_city = str(entry.get("city", "")).lower()
                if entry_city and city.lower() not in entry_city and entry_city not in city.lower():
                    continue
            for name in [entry["name"], *entry.get("aliases", [])]:
                if len(name) >= 3 and name.lower() in lower:
                    candidates.append((len(name), entry["name"]))
        if not candidates:
            return None
        candidates.sort(reverse=True)
        return candidates[0][1]

    def _resolve_listing_type(
        self,
        payload: dict[str, Any],
        title: str | None,
        description: str | None,
        prov: ProvenanceCollector,
    ) -> ListingType | None:
        raw = payload.get("listing_type")
        if raw == "rent":
            lt = ListingType.RENT
            prov.record(
                "listing_type", lt.value, rule_id=MJ_TYPE_NAME, source="title", source_text=title
            )
            return lt
        if raw == "sale":
            lt = ListingType.SALE
            prov.record(
                "listing_type", lt.value, rule_id=MJ_TYPE_NAME, source="title", source_text=title
            )
            return lt

        text = f"{title or ''} {description or ''}".lower()
        if any(m in text for m in ("me qira", "me qera", "per qira", " jepet ", " leshohet ")):
            lt = ListingType.RENT
            prov.record(
                "listing_type",
                lt.value,
                rule_id=MJ_TYPE_DESC,
                source="description",
                source_text=description,
            )
            return lt
        if any(m in text for m in ("ne shitje", "per shitje", "shitet", "shitje")):
            lt = ListingType.SALE
            prov.record(
                "listing_type",
                lt.value,
                rule_id=MJ_TYPE_DESC,
                source="description",
                source_text=description,
            )
            return lt
        return None

    def _map_property_type(self, title: str | None, description: str | None) -> PropertyType:
        return classify_property_type(title, description)

    def _clean_neighborhood(self, value: str | None) -> str | None:
        if not value:
            return None
        text = value.strip().strip(".,;!")
        text = re.sub(r"^(?:ne\s+|në\s+|te\s+)", "", text, flags=re.IGNORECASE)
        text = text.split(",")[0].strip()
        if text.lower() in _NEIGHBORHOOD_BLOCKLIST or len(text) < 3:
            return None
        return text

    def _resolve_listing_date(self, payload: dict[str, Any]) -> date | None:
        iso = payload.get("published_date")
        if iso:
            try:
                return date.fromisoformat(str(iso))
            except ValueError:
                pass
        raw = payload.get("published_date_raw")
        if raw:
            return parse_published_date_text(str(raw))
        return None
