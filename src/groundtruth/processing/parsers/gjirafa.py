"""Parser for Gjirafa Patundshmëri listing pages."""

import re
from typing import Any

from selectolax.parser import HTMLParser


def _text(node) -> str | None:
    if node is None:
        return None
    text = node.text(strip=True)
    return text or None


def _field_by_label(tree: HTMLParser, label: str) -> str | None:
    for block in tree.css("fieldset.listing-info .gjcm1-4"):
        lbl = _text(block.css_first("label"))
        if lbl and label.lower() in lbl.lower():
            return _text(block.css_first("h3"))
    return None


def _detail_field(tree: HTMLParser, label: str) -> str | None:
    for lbl_node in tree.css("fieldset.listing-info .display-label"):
        lbl = _text(lbl_node)
        if lbl and label.lower() in lbl.lower():
            field = lbl_node.next
            while field is not None and "display-field" not in (field.attributes.get("class") or ""):
                field = field.next
            if field is not None:
                if label.lower().startswith("çmim") or label.lower().startswith("cmim"):
                    parts = [t.strip() for t in field.text().split() if t.strip()]
                    return "".join(parts).replace("€", " EUR").strip()
                return _text(field)
    return None


def parse_listing_html(html: str, url: str) -> dict[str, Any]:
    """Parse a Gjirafa detail page into a structured raw payload."""
    tree = HTMLParser(html)

    listing_id_match = re.search(r"/banesa-(\d+)", url)
    listing_slug = listing_id_match.group(0).lstrip("/") if listing_id_match else url.rstrip("/").split("/")[-1]

    listing_type_raw = _field_by_label(tree, "Lloji i shpalljes") or ""
    listing_type = "rent" if "qira" in listing_type_raw.lower() else "sale"

    price_raw = _detail_field(tree, "Çmimi") or _detail_field(tree, "Cmimi")
    area_raw = _field_by_label(tree, "Kuadratura")
    rooms_raw = _field_by_label(tree, "Numri i dhomave")

    description_node = tree.css_first("fieldset.listing-info .description")
    description = description_node.text(separator="\n", strip=True) if description_node else None

    images = re.findall(
        r"https://noah\.gjirafa\.com/mrj1/[a-f0-9]+\.(?:png|jpg|jpeg|webp)",
        html,
        re.IGNORECASE,
    )

    return {
        "source_listing_id": listing_slug,
        "title": _detail_field(tree, "Titulli"),
        "category": _field_by_label(tree, "Kategoria"),
        "listing_type_raw": listing_type_raw,
        "listing_type": listing_type,
        "price_raw": price_raw,
        "area_raw": area_raw,
        "bedrooms_raw": rooms_raw,
        "listing_date_raw": _detail_field(tree, "Data"),
        "city_raw": _detail_field(tree, "Rajoni"),
        "country_raw": _detail_field(tree, "Shteti"),
        "description": description,
        "image_urls": list(dict.fromkeys(images)),
        "original_url": url,
    }
