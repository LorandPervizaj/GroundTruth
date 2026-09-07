"""MerrJep field-signal detection for parser evaluation (coverage vs extraction)."""

from __future__ import annotations

import re

_PRICE_SIGNAL_RE = re.compile(
    r"(?:€|EUR)\s*([\d\s.,]+)|([\d\s.,]+)\s*(?:€|EUR)",
    re.IGNORECASE,
)

CONTACT_PHRASES = (
    "marrëveshje",
    "marreveshje",
    "marrveshje",
    "sipas marr",
    "kontaktoni",
    "kontakto",
    "i volitshum",
    "cmimi: -",
    "çmimi: -",
)


def _parse_amount(raw: str) -> float | None:
    cleaned = raw.replace(" ", "").replace(",", "")
    try:
        return float(cleaned)
    except ValueError:
        return None


def numeric_price_signal(product: dict | None, description: str, title: str) -> bool:
    """True when a recoverable numeric price exists (not placeholder / contact-only)."""
    text = f"{title}\n{description}".lower()
    if product:
        offers = product.get("offers") or {}
        if isinstance(offers, list):
            offers = offers[0] if offers else {}
        try:
            ld_price = float(offers.get("price", -1))
            if ld_price > 10:
                return True
        except (TypeError, ValueError):
            pass

    for m in _PRICE_SIGNAL_RE.finditer(f"{description} {title}"):
        for g in m.groups():
            if not g:
                continue
            amount = _parse_amount(g)
            if amount is not None and amount > 10:
                return True

    return bool(
        re.search(
            r"(?:€|eur)\s*/\s*m|per\s+m2|për\s+m2|qmimi\s+per\s+m2",
            text,
            re.I,
        )
        and re.search(r"\d[\d\s.,]{2,}\s*(?:€|eur)", text, re.I)
    )


def price_signal_loose(product: dict | None, description: str, title: str) -> bool:
    """Legacy loose signal (includes ld+json price=1 placeholders)."""
    if product:
        offers = product.get("offers") or {}
        if isinstance(offers, list):
            offers = offers[0] if offers else {}
        price = offers.get("price")
        try:
            if price is not None and float(price) > 0:
                return True
        except (TypeError, ValueError):
            pass
    return bool(_PRICE_SIGNAL_RE.search(f"{description} {title}"))
