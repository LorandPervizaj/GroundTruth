"""Parser for MerrJep listing detail pages — ld+json primary contract."""

from __future__ import annotations

import re
from typing import Any

from groundtruth.processing.parsers.merrjep_dates import extract_published_info
from groundtruth.scrapers.merrjep_archive import (
    extract_ld_json_blocks,
    find_product_ld,
    infer_transaction_type,
)
from groundtruth.scrapers.merrjep_discovery import listing_id_from_url

_EUR_IN_TEXT = re.compile(
    r"(?:€|EUR)\s*([\d\s.,]+)|([\d\s.,]+)\s*(?:€|EUR)",
    re.IGNORECASE,
)
_HTML_PRICE_RE = re.compile(
    r'class="format-money-int"[^>]*\bvalue="(\d+(?:\.\d+)?)"',
    re.IGNORECASE,
)


def extract_html_price(html: str) -> float | None:
    """Read visible listing price from MerrJep detail HTML."""
    match = _HTML_PRICE_RE.search(html)
    if not match:
        return None
    try:
        value = float(match.group(1))
    except ValueError:
        return None
    return value if value > 10 else None


def _offers_dict(product: dict) -> dict:
    offers = product.get("offers") or {}
    if isinstance(offers, list):
        return offers[0] if offers else {}
    return offers if isinstance(offers, dict) else {}


def _published_fields(html: str) -> dict[str, Any]:
    info = extract_published_info(html)
    published = info["published_date"]
    return {
        "published_date": published.isoformat() if published else None,
        "published_date_raw": info["published_date_raw"],
        "published_time_raw": info["published_time_raw"],
    }


def parse_listing_html(html: str, url: str) -> dict[str, Any]:
    """Parse MerrJep detail HTML into a structured raw payload (no normalization)."""
    listing_id = listing_id_from_url(url) or url.rstrip("/").split("/")[-1]
    published_fields = _published_fields(html)
    price_html = extract_html_price(html)
    price_fields = {"price_html": price_html} if price_html is not None else {}
    blocks = extract_ld_json_blocks(html)
    product = find_product_ld(blocks)

    if not product:
        return {
            "source_listing_id": listing_id,
            "original_url": url,
            "title": None,
            "description": None,
            "price_ldjson": None,
            "listing_type_raw": None,
            "listing_type": None,
            "has_ld_json": False,
            **published_fields,
            **price_fields,
        }

    offers = _offers_dict(product)
    name = str(product.get("name") or "")
    description = str(product.get("description") or "")
    price_ld = offers.get("price")
    try:
        price_ldjson = float(price_ld) if price_ld is not None else None
    except (TypeError, ValueError):
        price_ldjson = None

    tx = infer_transaction_type(name, description)

    return {
        "source_listing_id": listing_id,
        "original_url": url,
        "title": name or None,
        "description": description or None,
        "price_ldjson": price_ldjson,
        "listing_type_raw": name,
        "listing_type": tx if tx != "unknown" else None,
        "sku": product.get("sku") or product.get("productID"),
        "has_ld_json": True,
        **published_fields,
        **price_fields,
    }
