"""Observed public frontend read-only fallback and normal CSRF session contract."""

from __future__ import annotations

import json

from groundtruth.scrapers.harta_contract import HartaContractError

ORIGIN = "https://harta.info"
CSRF_URL = ORIGIN + "/api/security/csrf"
DATA_URL = ORIGIN + "/api/local-db"
PAGE_SIZE = 25
SUMMARY_COLUMNS = (
    "id,created_at,city,property_type,listing_type,status,price,price_total,price_unit,"
    "living_area,surface_area,sqft,bedrooms,bathrooms,address,latitude,longitude,features"
)
DETAIL_COLUMNS = SUMMARY_COLUMNS + (
    ",title,description,state,country,currency,floor,condition,surface_unit,"
    "property_sub_type,construction_status,price_per_m2"
)
FILTERS = [
    {"column": "status", "op": "eq", "value": "active"},
    {"column": "city", "op": "in", "value": ["Prishtinë", "Prishtina", "Prishtine", "Pristina"]},
    {"column": "property_type", "op": "in", "value": ["apartment", "condo", "studio"]},
    {"column": "listing_type", "op": "in", "value": ["buy", "sale", "rent"]},
]


def operation(*, offset: int = 0, source_id: str | None = None) -> dict:
    result = {
        "table": "properties",
        "kind": "select",
        "columns": DETAIL_COLUMNS if source_id else SUMMARY_COLUMNS,
        "filters": list(FILTERS),
        "orders": [
            {"column": "created_at", "ascending": False},
            {"column": "id", "ascending": True},
        ],
        "limit": 1 if source_id else PAGE_SIZE,
    }
    if source_id:
        result["filters"].append({"column": "id", "op": "eq", "value": source_id})
    else:
        result["range"] = [offset, offset + PAGE_SIZE - 1]
    return result


def validate_read_request(body: bytes) -> None:
    """Never let this adapter become a generic database proxy client."""
    try:
        value = json.loads(body)
        if not isinstance(value, dict):
            raise ValueError("Operation must be an object")
        filters = value.get("filters") or []
        allowed = set(DETAIL_COLUMNS.split(","))
        if (
            value.get("table") != "properties"
            or value.get("kind") != "select"
            or not value.get("columns")
            or not set(value["columns"].split(",")) <= allowed
            or not all(f in filters for f in FILTERS)
            or not 1 <= int(value.get("limit", 0)) <= PAGE_SIZE
        ):
            raise ValueError("Outside approved public property read contract")
        if set(value) - {"table", "kind", "columns", "filters", "orders", "limit", "range"}:
            raise ValueError("Unsupported operation fields")
    except (ValueError, TypeError, KeyError) as exc:
        raise HartaContractError("Harta operation is not a bounded scoped property read") from exc
