"""Conservative independent checks of stored source fields, not publisher truth.

The audit reads explicit source paths, never reruns the production parser and
calls the result verification. Unknown/ambiguous evidence stays unverified.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections import Counter
from contextlib import suppress
from html import unescape

from bs4 import BeautifulSoup, SoupStrainer


def number(value) -> float | None:
    if isinstance(value, list):
        value = value[0] if len(value) == 1 else None
    if isinstance(value, (float, int)):
        return float(value) if math.isfinite(value) else None
    if not isinstance(value, str):
        return None
    match = re.fullmatch(
        r"\s*(?:€|EUR)?\s*([+-]?\d[\d.,\s]*?)\s*([kK])?\s*(?:€|EUR|m²|m2)?\s*", value, re.I
    )
    if not match:
        return None
    token = match.group(1).strip()
    if re.search(r"\d\s+\d", token) and not re.fullmatch(
        r"[+-]?\d{1,3}(?:\s+\d{3})+(?:[.,]\d{1,2})?", token
    ):
        return None
    token = re.sub(r"\s+", "", token)
    # Accept unambiguous whole amounts or decimal amounts. Other formats unknown.
    if re.fullmatch(r"[+-]?\d{1,3}([.,]\d{3})+", token):
        token = token.replace(",", "").replace(".", "")
    elif re.fullmatch(r"[+-]?\d+([.,]\d{1,2})?", token):
        token = token.replace(",", ".")
    else:
        return None
    result = float(token) * (1000 if match.group(2) else 1)
    return result if math.isfinite(result) else None


def text(value) -> str:
    if isinstance(value, dict):
        value = value.get("rendered") or value.get("name") or ""
    return unescape(BeautifulSoup(str(value or ""), "html.parser").get_text(" ", strip=True))


def discrepancy_context(payload: dict, parsed: dict | None, normalized: dict | None) -> dict:
    """Safe predicates for reviewing flags; never export raw values or text."""
    raw_kind = str(payload.get("listing_type") or "").lower()
    label = str(payload.get("listing_type_raw") or "").lower()
    declared_kind = "rent" if "qira" in label else "sale" if "shit" in label else None
    p_kind = str((parsed or {}).get("listing_type") or "").lower()
    p_area = (parsed or {}).get("area_sqm")
    price = number(payload.get("price_raw"))
    p_price = number(
        (parsed or {}).get("rent_price") if p_kind == "rent" else (parsed or {}).get("sale_price")
    )
    return {
        "parsed_transaction_unknown": not p_kind,
        "source_discovery_and_display_label_conflict": bool(
            declared_kind and raw_kind and declared_kind != raw_kind
        ),
        "parsed_kind_agrees_with_display_label": bool(declared_kind and p_kind == declared_kind),
        "parsed_total_matches_displayed_price_times_area": bool(
            price is not None
            and p_price is not None
            and p_area
            and math.isclose(p_price, price * float(p_area), rel_tol=0.01)
        ),
        "price_text_explicitly_per_sqm": bool(
            re.search(r"(?:/\s*m|m[²2])", str(payload.get("price_raw") or ""), re.I)
        ),
        "raw_area_nonpositive_sentinel": number(payload.get("area_raw")) is not None
        and number(payload.get("area_raw")) <= 0,
        "normalization_changed_property_type": bool(
            parsed
            and normalized
            and str(parsed.get("property_type")) != str(normalized.get("property_type"))
        ),
        "publisher_error_proven": False,
    }


def source_facts(source: str, payload: dict, html: str | None) -> dict:
    """Field paths and checks are inspectable; no output includes source text."""
    prop = payload.get("property") or payload
    facts = {}

    def add(field, value, path):
        facts[field] = {"value": value, "path": path}

    # Independent literal source declarations, not production-parser output.
    title = text(payload.get("title") or prop.get("title"))
    nouns = {
        kind
        for pattern, kind in (
            (r"\b(?:banes\w*|apartament\w*|apartment\w*)\b", "apartment"),
            (r"\b(?:studio|garsonier\w*)\b", "studio"),
            (r"\b(?:shtepi\w*|shtëpi\w*|house)\b", "house"),
            (r"\b(?:villa|vila)\b", "villa"),
        )
        if re.search(pattern, title, re.I)
    }
    add(
        "property_type",
        next(iter(nouns)) if len(nouns) == 1 else None,
        "source title: unambiguous property noun; ambiguous titles unverified",
    )

    if source == "gjirafa":
        add("price", number(payload.get("price_raw")), "price_raw")
        add("area_sqm", number(payload.get("area_raw")), "area_raw")
        add("bedrooms", number(payload.get("bedrooms_raw")), "bedrooms_raw")
        add("listing_type", payload.get("listing_type"), "listing_type")
        add("identity", str(payload.get("source_listing_id") or ""), "source_listing_id")
    elif source == "merrjep":
        # Inspect the actual stored JSON-LD, not only the spider's numeric derivative.
        prices = []
        soup = BeautifulSoup(
            html or "",
            "html.parser",
            parse_only=SoupStrainer("script", attrs={"type": "application/ld+json"}),
        )

        def walk(item):
            if isinstance(item, list):
                for node in item:
                    walk(node)
            elif isinstance(item, dict):
                offers = item.get("offers")
                if isinstance(offers, dict) and number(offers.get("price")) is not None:
                    prices.append(number(offers["price"]))
                for name in ("@graph", "mainEntity"):
                    if name in item:
                        walk(item[name])

        for script in soup.select('script[type="application/ld+json"]'):
            with suppress(ValueError, TypeError):
                walk(json.loads(script.string or script.get_text()))
        unique = set(prices)
        add(
            "price",
            next(iter(unique)) if len(unique) == 1 else None,
            "raw_html:JSON-LD.offers.price",
        )
        add("listing_type", payload.get("listing_type"), "listing_type (discovery context)")
        add("identity", str(payload.get("source_listing_id") or ""), "source_listing_id")
    elif source == "pro-rks":
        kind = payload.get("listing_type_hint")
        if kind not in ("sale", "rent"):
            kind = (
                "sale"
                if prop.get("forSale") and not prop.get("forRent")
                else "rent"
                if prop.get("forRent") and not prop.get("forSale")
                else None
            )
        add("listing_type", kind, "listing_type_hint/forSale/forRent")
        price_key = "rentPrice" if kind == "rent" else "sellPrice"
        # A unit-price marker must be examined before alleging a parser error.
        unit = str(prop.get("rentPriceType" if kind == "rent" else "sellPriceType") or "").lower()
        add(
            "price",
            None
            if "m2" in unit or "hect" in unit or unit == "are"
            else number(prop.get(price_key)),
            f"property.{price_key} (total-price units only)",
        )
        add("area_sqm", number(prop.get("surfaceM2")), "property.surfaceM2")
        add("bedrooms", number(prop.get("numberOfBedRooms")), "property.numberOfBedRooms")
        add("identity", str(prop.get("slug") or ""), "property.slug")
        categories = prop.get("category") or []
        if not isinstance(categories, list):
            categories = [categories]
        labels = [
            str(c.get("slug") or c.get("name") or c.get("title") or "").lower()
            if isinstance(c, dict)
            else str(c).lower()
            for c in categories
        ]
        types = {
            kind
            for label in labels
            if (
                kind := {
                    "apartment": "apartment",
                    "unit": "apartment",
                    "home": "house",
                    "house": "house",
                    "villa": "villa",
                    "land": "land",
                }.get(label)
            )
        }
        if len(types) == 1:
            add("property_type", next(iter(types)), "property.category: explicit API taxonomy")
    elif source == "topia":
        add("price", number(prop.get("price")), "property.price")
        add(
            "area_sqm",
            number(prop.get("gross_area")),
            "property.gross_area (not independently proven living area)",
        )
        add("bedrooms", number(prop.get("bed_room")), "property.bed_room")
        add("listing_type", prop.get("business_type"), "property.business_type")
        add("identity", str(prop.get("reference") or prop.get("id") or ""), "property.reference/id")
        add(
            "property_type",
            {
                "apartment": "apartment",
                "penthouse": "apartment",
                "duplex": "apartment",
                "house": "house",
                "villa": "villa",
            }.get(str(prop.get("type") or "").lower()),
            "property.type",
        )
    elif source == "vision":
        meta = prop.get("property_meta") or {}
        add(
            "price",
            number(meta.get("REAL_HOMES_property_price")),
            "property.property_meta.REAL_HOMES_property_price",
        )
        add(
            "area_sqm",
            number(meta.get("REAL_HOMES_property_size")),
            "property.property_meta.REAL_HOMES_property_size",
        )
        add(
            "bedrooms",
            number(meta.get("REAL_HOMES_property_bedrooms")),
            "property.property_meta.REAL_HOMES_property_bedrooms",
        )
        add("identity", str(prop.get("slug") or ""), "property.slug")
        types = {
            kind
            for label in prop.get("class_list") or []
            if (
                kind := {
                    "property-type-banesa": "apartment",
                    "property-type-shtepi": "house",
                    "property-type-troje": "land",
                }.get(label)
            )
        }
        if len(types) == 1:
            add(
                "property_type",
                next(iter(types)),
                "property.class_list: explicit property type taxonomy",
            )
    elif source == "myrealestate":
        soup = BeautifulSoup(
            html or "",
            "html.parser",
            parse_only=SoupStrainer(attrs={"class": re.compile(r"\bprice_area\b")}),
        )
        nodes = soup.select(".price_area")
        candidates = [number(node.get_text(" ", strip=True)) for node in nodes]
        unique = {n for n in candidates if n is not None}
        add(
            "price",
            next(iter(unique)) if len(unique) == 1 else None,
            "raw_html:.price_area (unique displayed amount)",
        )
        add("identity", str(prop.get("slug") or ""), "property.slug")
        classes = prop.get("class_list") or []
        kinds = {
            "sale" if "shitje" in c else "rent" if "qira" in c else None
            for c in classes
            if str(c).startswith("property_category-")
        }
        kinds.discard(None)
        add(
            "listing_type",
            next(iter(kinds)) if len(kinds) == 1 else None,
            "property.class_list.property_category",
        )
        types = {
            kind
            for label in classes
            if (
                kind := {
                    "property_action_category-banes": "apartment",
                    "property_action_category-shtepi": "house",
                    "property_action_category-penthouse": "apartment",
                    "property_action_category-villa": "villa",
                }.get(label)
            )
        }
        if len(types) == 1:
            add(
                "property_type",
                next(iter(types)),
                "property.class_list: explicit property action taxonomy",
            )
    # Only unique explicitly labelled m² values are usable independent area evidence.
    if "area_sqm" not in facts:
        description = (
            text(payload.get("description"))
            + " "
            + text(prop.get("title"))
            + " "
            + text(prop.get("content"))
        )
        areas = {
            number(m)
            for m in re.findall(r"(?<![\d.,])(\d+(?:[.,]\d{1,2})?)\s*m\s*[²2]\b", description, re.I)
        }
        areas.discard(None)
        add(
            "area_sqm",
            next(iter(areas)) if len(areas) == 1 else None,
            "stored title/content/description: unique explicit m² token",
        )
    return facts


def compare_snapshot(*, record, stratum, payload, html, parsed, normalized) -> dict:
    facts = source_facts(record.source_name, payload, html)
    checks = {}
    for field in ("price", "area_sqm", "bedrooms", "listing_type", "property_type", "identity"):
        fact = facts.get(field, {"value": None, "path": "no independent supported evidence"})
        expected = fact["value"]

        def actual(data, field=field):
            if not data:
                return None
            if field == "price":
                return (
                    data.get("rent_price")
                    if str(data.get("listing_type") or "").lower() == "rent"
                    else data.get("sale_price")
                )
            return data.get("source_listing_id") if field == "identity" else data.get(field)

        p, n = actual(parsed), actual(normalized)

        def same(value, expected=expected):
            if value is None:
                return False
            if isinstance(expected, (int, float)):
                return math.isclose(float(value), expected, rel_tol=1e-4, abs_tol=0.01)
            return str(value).lower() == str(expected).lower()

        if expected is None or expected == "":
            status = "unverified"
        elif isinstance(expected, (int, float)) and expected <= 0 and field != "bedrooms":
            status = "source_structured_nonpositive"
        elif parsed is None:
            status = "pipeline_unprocessed" if record.outcome == "pending" else "pipeline_failed"
        elif not same(p):
            status = "parser_missing" if p is None else "parser_disagreement_requires_review"
        elif normalized is None:
            status = "parsed_agrees_normalization_unavailable"
        elif not same(n):
            status = "normalizer_disagreement_requires_review"
        else:
            status = "agrees_with_stored_source"
        checks[field] = {"status": status, "evidence_path": fact["path"]}
    gross, interior = (
        number((payload.get("property") or {}).get("gross_area")),
        number((payload.get("property") or {}).get("interior_area")),
    )
    return {
        "audit_id": hashlib.sha256(
            f"{record.source_name}:{record.observation_id}".encode()
        ).hexdigest()[:16],
        "source_name": record.source_name,
        "raw_record_id": record.observation_id,
        "stratum": stratum,
        "segment": str(record.listing.listing_type)
        if record.listing and record.listing.listing_type
        else "unknown",
        "pipeline_outcome": record.outcome,
        "checks": checks,
        "review_context": discrepancy_context(payload, parsed, normalized)
        if any(
            "disagreement" in c["status"]
            or c["status"] in {"parser_missing", "source_structured_nonpositive"}
            for c in checks.values()
        )
        else {},
        "area_semantics": {
            "gross_and_interior_both_present": gross is not None and interior is not None,
            "gross_and_interior_differ": gross is not None
            and interior is not None
            and not math.isclose(gross, interior),
            "living_area_independently_verified": False,
        },
        "property_location_accuracy": "UNVERIFIED: source claims do not establish physical location",
        "review_method": "automated explicit stored-source field comparisons; agent-reviewed rules and disagreements; no independent human label claimed",
    }


def audit_summary(checks: list[dict]) -> dict:
    summary = {}
    for source in sorted({c["source_name"] for c in checks}):
        rows = [c for c in checks if c["source_name"] == source]
        summary[source] = {
            "sample_count": len(rows),
            "strata": dict(Counter(c["stratum"] for c in rows)),
            "segments": dict(Counter(c["segment"] for c in rows)),
            "fields": {
                field: dict(Counter(c["checks"][field]["status"] for c in rows))
                for field in rows[0]["checks"]
            },
        }
    return summary
