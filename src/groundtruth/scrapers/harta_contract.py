"""Observed public HTML contract (2026-10-21); never execute hydration JavaScript."""

from __future__ import annotations

import json
import re
import unicodedata
from typing import Any
from uuid import UUID

from parsel import Selector

from groundtruth.portals.registry import get_portal

INDEX_URL = "https://harta.info/prona/banesa/prishtine"
PARSER_VERSION = get_portal("harta").parser_version


class HartaContractError(ValueError):
    """An access challenge or changed source contract must fail closed."""


def check_access(html: str) -> None:
    if re.search(r"human-gate-title|cf-turnstile|cf-chl-|Just a moment", html, re.I):
        raise HartaContractError("Harta access verification required; collection stopped")


class _Literal:
    """Small, bounded reader for the observed TanStack inline literal subset.

    Accepts only literals and inline $R[n]= assignments, never calls, references,
    computed keys, attributes or expressions. Unknown syntax raises an error.
    """

    def __init__(self, text: str) -> None:
        self.text = text
        self.pos = 0

    def _take(self, pattern: str) -> str | None:
        match = re.compile(r"\s*(?:" + pattern + ")").match(self.text, self.pos)
        if match is None:
            return None
        self.pos = match.end()
        return match.group().strip()

    def value(self, depth: int = 0) -> Any:
        if depth > 32:
            raise HartaContractError("Hydration nesting limit")
        self._take(r"\$R\[\d+\]=")
        string = self._take(r'"(?:[^"\\]|\\.)*"')
        if string is not None:
            string = re.sub(r"\\x([a-fA-F0-9]{2})", r"\\u00\1", string)
            return json.loads(string)
        if self._take(r"\{"):
            result = {}
            if self._take(r"\}"):
                return result
            while True:
                key = self._take(r"[A-Za-z_$][A-Za-z0-9_$]*")
                if key is None or not self._take(":"):
                    raise HartaContractError("Unsupported hydration object key")
                result[key] = self.value(depth + 1)
                if self._take(r"\}"):
                    return result
                if not self._take(","):
                    raise HartaContractError("Malformed hydration object")
        if self._take(r"\["):
            result = []
            if self._take(r"\]"):
                return result
            while True:
                result.append(self.value(depth + 1))
                if self._take(r"\]"):
                    return result
                if not self._take(","):
                    raise HartaContractError("Malformed hydration array")
        token = self._take(r"null\b|!0|!1|true\b|false\b|-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?")
        if token in ("!0", "true"):
            return True
        if token in ("!1", "false"):
            return False
        if token == "null":
            return None
        if token is not None:
            return json.loads(token)
        raise HartaContractError("Unsupported hydration value")


def hydration_field(html: str, field: str) -> Any:
    check_access(html)
    if len(html) > 2_000_000:
        raise HartaContractError("HTML size limit")
    scripts = Selector(text=html).css('script[id="$tsr-stream-barrier"]::text').getall()
    for script in scripts:
        match = re.search(r"\b" + re.escape(field) + r":\$R\[\d+\]=", script)
        if match:
            return _Literal(script[match.end() :]).value()
    raise HartaContractError(f"Missing public hydration field: {field}")


def property_from_html(html: str) -> dict:
    prop = hydration_field(html, "property")
    if not isinstance(prop, dict):
        raise HartaContractError("Malformed property object")
    # The observed hydration features omit rental_period while the public
    # RealEstateListing JSON-LD explicitly declares it. Retain that evidence.
    for text in Selector(text=html).css('script[type="application/ld+json"]::text').getall():
        try:
            ld = json.loads(text)
        except ValueError:
            continue
        if isinstance(ld, dict) and ld.get("@type") == "RealEstateListing":
            for fact in ld.get("additionalProperty", []):
                if fact.get("name") == "Rental Period":
                    features = dict(prop.get("features") or {})
                    features.setdefault("rental_period", fact.get("value"))
                    prop["features"] = features
    return prop


def folded(value: Any) -> str:
    return "".join(
        c
        for c in unicodedata.normalize("NFKD", str(value or "").lower())
        if not unicodedata.combining(c)
    ).strip()


def in_scope(prop: dict) -> bool:
    # Exact municipality labels only; no viewport/address-substring inference.
    return (
        folded(prop.get("city")) in {"prishtine", "prishtina", "pristina"}
        and prop.get("property_type") in {"apartment", "condo", "studio"}
        and prop.get("listing_type") in {"buy", "rent"}
    )


def listing_id(prop: dict) -> str:
    try:
        return str(UUID(str(prop["id"])))
    except (ValueError, KeyError, TypeError) as exc:
        raise HartaContractError("Missing or malformed Harta UUID") from exc


_FIELDS = frozenset(
    {
        "id",
        "title",
        "city",
        "state",
        "country",
        "address",
        "street",
        "neighborhood",
        "property_type",
        "property_sub_type",
        "listing_type",
        "status",
        "price",
        "price_unit",
        "price_total",
        "price_per_m2",
        "currency",
        "sqft",
        "living_area",
        "surface_area",
        "surface_unit",
        "bedrooms",
        "bathrooms",
        "floor",
        "created_at",
        "updated_at",
        "latitude",
        "longitude",
        "condition",
        "construction_status",
    }
)
_FEATURES = frozenset({"rental_period", "furnished", "floor_levels", "elevator", "parking"})


def minimized_property(prop: dict) -> dict:
    """Allowlist before raw persistence; descriptions reduced to consistency facts."""
    listing_id(prop)
    result = {k: v for k, v in prop.items() if k in _FIELDS}
    features = prop.get("features") or {}
    if not isinstance(features, dict):
        raise HartaContractError("Malformed features")
    result["features"] = {k: v for k, v in features.items() if k in _FEATURES}
    text = Selector(text=str(prop.get("description") or "")).xpath("string(.)").get("")
    # Only explicit labelled asking-price and area facts, never free text/contacts.
    prices = re.findall(r"[ÇçCc]mimi\s*[:=]\s*([\d., ]+)\s*(?:€|EUR)", text)
    areas = re.findall(r"(?:[Ss]ip[eë]rfaqja|[Ss]ip[eë]rfaqe)\s*[:=]\s*([\d.,]+)\s*m[²2]", text)
    result["description_facts"] = {"asking_prices": prices, "areas_sqm": areas}
    return result
