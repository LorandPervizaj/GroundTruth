"""MerrJep Phase 1.5 — archive detail pages and assess ld+json schema completeness."""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path

_LD_JSON_RE = re.compile(
    r'<script type="application/ld\+json">(.*?)</script>',
    re.DOTALL | re.IGNORECASE,
)
_AREA_RE = re.compile(r"(\d+(?:[.,]\d+)?)\s*m[²2]\b", re.IGNORECASE)
_NEIGHBORHOOD_RE = re.compile(
    r"(?:📍\s*|(?:ne|në)\s+(?:lagjen\s+)?)([A-Za-zÀ-ÿ][A-Za-zÀ-ÿ\s\-']{2,40})",
    re.IGNORECASE,
)
_RENT_RE = re.compile(r"\b(qira|qera|me\s+qira|me\s+qera|per\s+qira)\b", re.IGNORECASE)
_SALE_RE = re.compile(r"\b(shitje|per\s+shitje|ne\s+shitje)\b", re.IGNORECASE)

# Phase 1.5 gates — schema must meet these before writing a parser.
ARCHIVE_GATE_LD_JSON_PCT = 95.0
ARCHIVE_GATE_PRICE_PCT = 95.0
ARCHIVE_GATE_AREA_PCT = 90.0
ARCHIVE_GATE_NEIGHBORHOOD_PCT = 90.0
ARCHIVE_GATE_TRANSACTION_PCT = 98.0


@dataclass
class ArchiveRecord:
    """One archived detail page with schema completeness flags."""

    listing_id: str
    url: str
    html_path: str
    ldjson_path: str | None
    has_ld_json: bool
    has_price: bool
    has_area: bool
    has_neighborhood: bool
    transaction_type: str  # rent | sale | unknown
    price_raw: float | None = None
    area_signal: str | None = None
    neighborhood_signal: str | None = None
    product_name: str | None = None
    ld_types: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class ArchiveReport:
    """Phase 1.5 completeness summary across archived pages."""

    mode: str = "archive"
    completed_at: str = ""
    archive_dir: str = ""
    pages_archived: int = 0
    completeness_pct: dict[str, float] = field(default_factory=dict)
    gates: dict[str, float] = field(default_factory=dict)
    passed: bool = False
    notes: list[str] = field(default_factory=list)
    records: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        data = asdict(self)
        # Keep manifest compact in top-level report; full records included for QA.
        return data


def extract_ld_json_blocks(html: str) -> list[dict]:
    """Parse all ``application/ld+json`` blocks from HTML."""
    blocks: list[dict] = []
    for match in _LD_JSON_RE.finditer(html):
        raw = match.group(1).strip()
        if not raw:
            continue
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict):
            blocks.append(data)
        elif isinstance(data, list):
            blocks.extend(item for item in data if isinstance(item, dict))
    return blocks


def find_product_ld(blocks: list[dict]) -> dict | None:
    """Return the first schema.org Product block."""
    for block in blocks:
        if block.get("@type") == "Product":
            return block
        graph = block.get("@graph")
        if isinstance(graph, list):
            for node in graph:
                if isinstance(node, dict) and node.get("@type") == "Product":
                    return node
    return None


def infer_transaction_type(name: str, description: str) -> str:
    """Infer rent vs sale from title and description."""
    text = f"{name} {description}".lower()
    is_rent = bool(_RENT_RE.search(text))
    is_sale = bool(_SALE_RE.search(text))
    if is_rent and not is_sale:
        return "rent"
    if is_sale and not is_rent:
        return "sale"
    return "unknown"


def assess_product_schema(product: dict | None, *, html: str) -> dict:
    """Score field presence on a Product ld+json block (no full parsing)."""
    if not product:
        return {
            "has_ld_json": False,
            "has_price": False,
            "has_area": False,
            "has_neighborhood": False,
            "transaction_type": "unknown",
            "price_raw": None,
            "area_signal": None,
            "neighborhood_signal": None,
            "product_name": None,
            "ld_types": [],
        }

    offers = product.get("offers") or {}
    if isinstance(offers, list):
        offers = offers[0] if offers else {}

    price = offers.get("price")
    try:
        price_val = float(price) if price is not None else None
    except (TypeError, ValueError):
        price_val = None

    name = str(product.get("name") or "")
    description = str(product.get("description") or "")

    area_match = _AREA_RE.search(description) or _AREA_RE.search(html[:50_000])
    nh_match = _NEIGHBORHOOD_RE.search(description) or _NEIGHBORHOOD_RE.search(name)

    tx = infer_transaction_type(name, description)

    return {
        "has_ld_json": True,
        "has_price": price_val is not None and price_val > 0,
        "has_area": area_match is not None,
        "has_neighborhood": nh_match is not None,
        "transaction_type": tx,
        "price_raw": price_val,
        "area_signal": area_match.group(0) if area_match else None,
        "neighborhood_signal": nh_match.group(1).strip() if nh_match else None,
        "product_name": name or None,
        "ld_types": ["Product"],
    }


def archive_detail_page(
    *,
    listing_id: str,
    url: str,
    html: str,
    output_dir: Path,
) -> ArchiveRecord:
    """Write raw HTML + ld+json sidecar; return completeness record."""
    output_dir.mkdir(parents=True, exist_ok=True)
    html_path = output_dir / f"{listing_id}.html"
    html_path.write_text(html, encoding="utf-8")

    blocks = extract_ld_json_blocks(html)
    product = find_product_ld(blocks)
    assessed = assess_product_schema(product, html=html)

    ldjson_path: str | None = None
    if product:
        ld_path = output_dir / f"{listing_id}.ldjson"
        ld_path.write_text(
            json.dumps(product, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        ldjson_path = str(ld_path)

    return ArchiveRecord(
        listing_id=listing_id,
        url=url,
        html_path=str(html_path),
        ldjson_path=ldjson_path,
        **assessed,
    )


def _pct(true_count: int, total: int) -> float:
    return round(100.0 * true_count / total, 1) if total else 0.0


def build_archive_report(
    records: list[ArchiveRecord],
    *,
    archive_dir: Path,
    ld_json_gate: float = ARCHIVE_GATE_LD_JSON_PCT,
    price_gate: float = ARCHIVE_GATE_PRICE_PCT,
    area_gate: float = ARCHIVE_GATE_AREA_PCT,
    neighborhood_gate: float = ARCHIVE_GATE_NEIGHBORHOOD_PCT,
    transaction_gate: float = ARCHIVE_GATE_TRANSACTION_PCT,
) -> ArchiveReport:
    """Aggregate Phase 1.5 completeness and evaluate gates."""
    total = len(records)
    completeness = {
        "ld_json_exists": _pct(sum(1 for r in records if r.has_ld_json), total),
        "price_populated": _pct(sum(1 for r in records if r.has_price), total),
        "area_populated": _pct(sum(1 for r in records if r.has_area), total),
        "neighborhood_populated": _pct(sum(1 for r in records if r.has_neighborhood), total),
        "transaction_distinguishable": _pct(
            sum(1 for r in records if r.transaction_type in ("rent", "sale")), total
        ),
    }
    gates = {
        "ld_json_exists_pct": ld_json_gate,
        "price_populated_pct": price_gate,
        "area_populated_pct": area_gate,
        "neighborhood_populated_pct": neighborhood_gate,
        "transaction_distinguishable_pct": transaction_gate,
    }
    passed = (
        completeness["ld_json_exists"] >= ld_json_gate
        and completeness["price_populated"] >= price_gate
        and completeness["area_populated"] >= area_gate
        and completeness["neighborhood_populated"] >= neighborhood_gate
        and completeness["transaction_distinguishable"] >= transaction_gate
    )

    notes: list[str] = []
    for key, gate_val in (
        ("ld_json_exists", ld_json_gate),
        ("price_populated", price_gate),
        ("area_populated", area_gate),
        ("neighborhood_populated", neighborhood_gate),
        ("transaction_distinguishable", transaction_gate),
    ):
        actual = completeness[key]
        if actual < gate_val:
            notes.append(f"{key}: {actual}% < gate {gate_val}%.")

    if passed:
        notes.append("Schema stable enough to proceed with parser implementation.")

    return ArchiveReport(
        completed_at=datetime.now(UTC).isoformat(),
        archive_dir=str(archive_dir),
        pages_archived=total,
        completeness_pct=completeness,
        gates=gates,
        passed=passed,
        notes=notes,
        records=[r.to_dict() for r in records],
    )


def write_archive_report(report: ArchiveReport, output_dir: Path) -> Path:
    """Write Phase 1.5 JSON report beside archived HTML files."""
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / "merrjep_archive_report.json"
    path.write_text(json.dumps(report.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8")
    return path
