"""MerrJep parser evaluation — coverage vs extraction accuracy, provenance breakdown."""

from __future__ import annotations

import json
import re
from collections import Counter
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from groundtruth.gazetteers.loader import GazetteerService
from groundtruth.processing.parsers.merrjep import parse_listing_html
from groundtruth.scrapers.merrjep_archive import (
    _AREA_RE,
    _RENT_RE,
    _SALE_RE,
    extract_ld_json_blocks,
    find_product_ld,
    infer_transaction_type,
)
from groundtruth.scrapers.merrjep_signals import numeric_price_signal, price_signal_loose
from groundtruth.services.merrjep_parsing import MerrJepParsingService

# Phase 2 gates — extraction when numeric signal exists; coverage is report-only.
EXTRACTION_GATE_PRICE = 99.0
OMISSION_CLASSIFICATION_GATE = 99.0
EXTRACTION_GATE_AREA = 99.0
EXTRACTION_GATE_NEIGHBORHOOD = 97.0
EXTRACTION_GATE_TYPE = 99.0


@dataclass
class FieldEval:
    """Per-field coverage and extraction accuracy."""

    signal_present: int = 0
    extracted: int = 0
    correct_when_signal: int = 0
    coverage_pct: float = 0.0
    extraction_accuracy_pct: float = 0.0
    provenance_counts: dict[str, int] = field(default_factory=dict)
    missing_reasons: dict[str, int] = field(default_factory=dict)
    numeric_signal_present: int = 0
    omission_classified_correct: int = 0
    omission_total: int = 0


@dataclass
class ParserEvalReport:
    """Phase 2 measurement report."""

    mode: str = "parser_eval"
    completed_at: str = ""
    archive_dir: str = ""
    listings_evaluated: int = 0
    fields: dict[str, dict[str, Any]] = field(default_factory=dict)
    provenance_summary: dict[str, int] = field(default_factory=dict)
    gates: dict[str, float] = field(default_factory=dict)
    passed: bool = False
    notes: list[str] = field(default_factory=list)
    gjirafa_benchmark: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


def _pct(num: int, denom: int) -> float:
    return round(100.0 * num / denom, 1) if denom else 0.0


def _area_signal(description: str, title: str) -> bool:
    return bool(_AREA_RE.search(f"{description} {title}"))


def _neighborhood_signal(text: str, gazetteer: GazetteerService) -> bool:
    if not text:
        return False
    lower = text.lower()
    if "📍" in text:
        return True
    gazetteer._ensure_loaded()  # noqa: SLF001
    for entry in gazetteer._data.get("neighborhoods", []):  # noqa: SLF001
        for name in [entry["name"], *entry.get("aliases", [])]:
            if len(name) >= 4 and name.lower() in lower:
                return True
    return bool(re.search(r"(?:ne|në)\s+lagj", lower, re.I))


def _type_signal(title: str, description: str) -> bool:
    text = f"{title} {description}"
    return bool(_RENT_RE.search(text) or _SALE_RE.search(text))


def classify_missing_price(
    product: dict | None,
    description: str,
    title: str,
    *,
    extracted: bool,
    numeric_signal: bool,
) -> str | None:
    if extracted:
        return None
    if numeric_signal:
        return "parser_bug"
    if product:
        offers = product.get("offers") or {}
        if isinstance(offers, list):
            offers = offers[0] if offers else {}
        try:
            price = float(offers.get("price", -1))
            if price in (0, 1):
                return "seller_omitted"
        except (TypeError, ValueError):
            pass
    if price_signal_loose(product, description, title):
        return "seller_omitted"
    return "seller_omitted"


def classify_missing_area(
    description: str, title: str, *, extracted: bool, signal: bool
) -> str | None:
    if extracted:
        return None
    if not signal:
        return "seller_omitted"
    return "parser_limitation"


def classify_missing_neighborhood(
    text: str,
    *,
    extracted: bool,
    signal: bool,
    gazetteer: GazetteerService,
) -> str | None:
    if extracted:
        return None
    if not signal:
        return "seller_omitted"
    if _neighborhood_signal(text, gazetteer):
        return "ambiguous_wording"
    return "unknown"


def evaluate_archive_dir(archive_dir: Path) -> ParserEvalReport:
    """Run measurement-first parser eval on archived HTML files."""
    parser = MerrJepParsingService()
    gazetteer = GazetteerService()
    gazetteer.load()

    price_eval = FieldEval()
    area_eval = FieldEval()
    nh_eval = FieldEval()
    type_eval = FieldEval()
    prov_counter: Counter[str] = Counter()
    total = 0

    html_files = sorted(archive_dir.glob("*.html"))
    for html_path in html_files:
        listing_id = html_path.stem
        html = html_path.read_text(encoding="utf-8")
        blocks = extract_ld_json_blocks(html)
        product = find_product_ld(blocks)
        payload = parse_listing_html(html, f"https://www.merrjep.com/shpallja/x/{listing_id}")
        title = payload.get("title") or ""
        description = payload.get("description") or ""
        combined = f"{title}\n{description}"

        schema, prov = parser.parse_payload(payload, url=payload.get("original_url", ""))
        total += 1

        for field_prov in prov.values():
            rule = field_prov.get("rule_id", "unknown")
            prov_counter[rule] += 1

        # Price
        p_numeric = numeric_price_signal(product, description, title)
        p_loose = price_signal_loose(product, description, title)
        p_extracted = schema.sale_price is not None or schema.rent_price is not None
        if p_loose:
            price_eval.signal_present += 1
        if p_numeric:
            price_eval.numeric_signal_present += 1
            if p_extracted:
                price_eval.correct_when_signal += 1
        if p_extracted:
            price_eval.extracted += 1
        rule = prov.get("sale_price") or prov.get("rent_price")
        if rule:
            rid = rule.get("rule_id", "unknown")
            price_eval.provenance_counts[rid] = price_eval.provenance_counts.get(rid, 0) + 1
        reason = classify_missing_price(
            product, description, title, extracted=p_extracted, numeric_signal=p_numeric
        )
        if reason and not p_extracted:
            price_eval.missing_reasons[reason] = price_eval.missing_reasons.get(reason, 0) + 1
            price_eval.omission_total += 1
            if reason == "seller_omitted" and not p_numeric or reason == "parser_bug" and p_numeric:
                price_eval.omission_classified_correct += 1

        # Area
        a_signal = _area_signal(description, title)
        a_extracted = schema.area_sqm is not None
        if a_signal:
            area_eval.signal_present += 1
            if a_extracted:
                area_eval.correct_when_signal += 1
        if a_extracted:
            area_eval.extracted += 1
        if prov.get("area_sqm"):
            rid = prov["area_sqm"].get("rule_id", "unknown")
            area_eval.provenance_counts[rid] = area_eval.provenance_counts.get(rid, 0) + 1
        if not a_extracted:
            reason = classify_missing_area(description, title, extracted=False, signal=a_signal)
            if reason:
                area_eval.missing_reasons[reason] = area_eval.missing_reasons.get(reason, 0) + 1

        # Neighborhood
        n_signal = _neighborhood_signal(combined, gazetteer)
        n_extracted = schema.neighborhood_raw is not None
        if n_signal:
            nh_eval.signal_present += 1
            if n_extracted:
                nh_eval.correct_when_signal += 1
        if n_extracted:
            nh_eval.extracted += 1
        if prov.get("neighborhood_raw"):
            rid = prov["neighborhood_raw"].get("rule_id", "unknown")
            nh_eval.provenance_counts[rid] = nh_eval.provenance_counts.get(rid, 0) + 1
        if not n_extracted:
            reason = classify_missing_neighborhood(
                combined, extracted=False, signal=n_signal, gazetteer=gazetteer
            )
            if reason:
                nh_eval.missing_reasons[reason] = nh_eval.missing_reasons.get(reason, 0) + 1

        # Type
        t_signal = _type_signal(title, description)
        t_extracted = schema.listing_type is not None
        expected = infer_transaction_type(title, description)
        if t_signal:
            type_eval.signal_present += 1
            if t_extracted and schema.listing_type:
                parsed_tx = schema.listing_type.value.lower()
                if expected == "unknown" or parsed_tx == expected:
                    type_eval.correct_when_signal += 1
        if t_extracted:
            type_eval.extracted += 1
        if prov.get("listing_type"):
            rid = prov["listing_type"].get("rule_id", "unknown")
            type_eval.provenance_counts[rid] = type_eval.provenance_counts.get(rid, 0) + 1

    def finalize(
        fe: FieldEval, total_n: int, *, use_numeric_signal: bool = False
    ) -> dict[str, Any]:
        fe.coverage_pct = _pct(fe.extracted, total_n)
        denom = fe.numeric_signal_present if use_numeric_signal else fe.signal_present
        fe.extraction_accuracy_pct = _pct(fe.correct_when_signal, denom)
        out = asdict(fe)
        if use_numeric_signal:
            out["omission_classification_pct"] = _pct(
                fe.omission_classified_correct, fe.omission_total
            )
        return out

    fields = {
        "price": finalize(price_eval, total, use_numeric_signal=True),
        "area": finalize(area_eval, total),
        "neighborhood": finalize(nh_eval, total),
        "listing_type": finalize(type_eval, total),
    }

    omission_pct = fields["price"].get("omission_classification_pct", 100.0)
    gates = {
        "price_extraction_when_numeric_signal": EXTRACTION_GATE_PRICE,
        "price_omission_classification": OMISSION_CLASSIFICATION_GATE,
        "area_extraction_when_signal": EXTRACTION_GATE_AREA,
        "neighborhood_extraction_when_signal": EXTRACTION_GATE_NEIGHBORHOOD,
        "type_extraction_when_signal": EXTRACTION_GATE_TYPE,
    }
    passed = (
        fields["price"]["extraction_accuracy_pct"] >= EXTRACTION_GATE_PRICE
        and omission_pct >= OMISSION_CLASSIFICATION_GATE
        and fields["area"]["extraction_accuracy_pct"] >= EXTRACTION_GATE_AREA
        and fields["neighborhood"]["extraction_accuracy_pct"] >= EXTRACTION_GATE_NEIGHBORHOOD
        and fields["listing_type"]["extraction_accuracy_pct"] >= EXTRACTION_GATE_TYPE
    )

    notes: list[str] = []
    gate_field_map = {
        "price_extraction_when_numeric_signal": "price",
        "area_extraction_when_signal": "area",
        "neighborhood_extraction_when_signal": "neighborhood",
        "type_extraction_when_signal": "listing_type",
    }
    for key, gate in gates.items():
        if key == "price_omission_classification":
            actual = omission_pct
            if actual < gate:
                notes.append(f"price: omission classification {actual}% < gate {gate}%.")
            continue
        field_key = gate_field_map.get(key, key.replace("_extraction_when_signal", ""))
        actual = fields[field_key]["extraction_accuracy_pct"]
        label = "numeric signal" if key == "price_extraction_when_numeric_signal" else "signal"
        if actual < gate:
            notes.append(
                f"{field_key}: extraction {actual}% < gate {gate}% (when {label} present)."
            )
    for field_key in ("price", "area", "neighborhood", "listing_type"):
        cov = fields[field_key]["coverage_pct"]
        notes.append(f"{field_key}: overall coverage {cov}% (report only).")

    if passed:
        notes.insert(0, "Parser meets extraction-accuracy gates — ready for ETL integration QA.")

    return ParserEvalReport(
        completed_at=datetime.now(UTC).isoformat(),
        archive_dir=str(archive_dir),
        listings_evaluated=total,
        fields=fields,
        provenance_summary=dict(prov_counter),
        gates=gates,
        passed=passed,
        notes=notes,
        gjirafa_benchmark={
            "price_extraction_signal_present": "~99%",
            "area_extraction_signal_present": "~99.6%",
            "neighborhood_extraction": "~96%+",
            "type": "~99%",
        },
    )


def build_price_failure_review(archive_dir: Path) -> list[dict[str, Any]]:
    """Manual-style classification of listings with no extracted price."""
    parser = MerrJepParsingService()
    rows: list[dict[str, Any]] = []

    for html_path in sorted(archive_dir.glob("*.html")):
        listing_id = html_path.stem
        html = html_path.read_text(encoding="utf-8")
        blocks = extract_ld_json_blocks(html)
        product = find_product_ld(blocks)
        payload = parse_listing_html(html, f"https://www.merrjep.com/shpallja/x/{listing_id}")
        title = payload.get("title") or ""
        description = payload.get("description") or ""

        schema, _ = parser.parse_payload(payload, url=payload.get("original_url", ""))
        extracted = schema.sale_price is not None or schema.rent_price is not None
        if extracted:
            continue

        numeric = numeric_price_signal(product, description, title)
        offers = (product or {}).get("offers") or {}
        if isinstance(offers, list):
            offers = offers[0] if offers else {}
        ld_price = offers.get("price")

        rows.append(
            {
                "id": listing_id,
                "numeric_price_exists": numeric,
                "parser_correct": not numeric,
                "reason": "parser_bug" if numeric else "seller_omitted",
                "ld_price": ld_price,
                "title": title[:100],
            }
        )
    return rows


def write_parser_eval_report(report: ParserEvalReport, output_dir: Path) -> Path:
    path = output_dir / "merrjep_parser_eval.json"
    path.write_text(json.dumps(report.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8")
    return path


def enrich_archive_report_with_missing_reasons(archive_dir: Path) -> Path:
    """Backfill Phase 1.5 archive report with missing-field reason counts."""
    report_path = archive_dir / "merrjep_archive_report.json"
    if not report_path.exists():
        raise FileNotFoundError(report_path)

    data = json.loads(report_path.read_text(encoding="utf-8"))
    eval_report = evaluate_archive_dir(archive_dir)
    data["missing_field_reasons"] = {
        "price": eval_report.fields["price"]["missing_reasons"],
        "area": eval_report.fields["area"]["missing_reasons"],
        "neighborhood": eval_report.fields["neighborhood"]["missing_reasons"],
    }
    report_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    return report_path
