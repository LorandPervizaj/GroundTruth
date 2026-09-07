"""Public rent-yield calculator backed by active corpus medians."""

from __future__ import annotations

import json
from pathlib import Path

from sqlalchemy.orm import Session

from groundtruth.analytics.corpus import active_corpus_dataframe
from groundtruth.analytics.market_table import build_neighborhood_market_table
from groundtruth.analytics.valuation import MIN_COMPARABLES
from groundtruth.config import PROJECT_ROOT, get_settings

RENT_YIELD_CACHE = PROJECT_ROOT / "data" / "api" / "rent_yield.json"


def _neighborhood_meta() -> dict[int, dict]:
    path = get_settings().gazetteer_dir / "neighborhoods.json"
    if not path.is_file():
        return {}
    entries = json.loads(path.read_text(encoding="utf-8"))
    return {int(e["id"]): e for e in entries if e.get("id") is not None}


def load_rent_yield_cache(path: Path | None = None) -> list[dict]:
    cache_path = path or RENT_YIELD_CACHE
    if not cache_path.is_file():
        return []
    try:
        payload = json.loads(cache_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    rows = payload.get("rows")
    return rows if isinstance(rows, list) else []


def write_rent_yield_cache(rows: list[dict], path: Path | None = None) -> None:
    cache_path = path or RENT_YIELD_CACHE
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"rows": rows}
    cache_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def build_rent_yield_from_lookup_cache() -> list[dict]:
    """Build rent-yield rows from precomputed neighborhood lookup cache (no DB)."""
    from groundtruth.services.lookup_cache import (
        cache_is_loaded,
        get_cached_lookup,
        get_cached_markets,
    )

    if not cache_is_loaded():
        return []

    rows: list[dict] = []
    for summary in get_cached_markets():
        rent_n = int(summary.rent_listings or 0)
        sale_n = int(summary.sale_listings or 0)
        if rent_n < MIN_COMPARABLES or sale_n < MIN_COMPARABLES:
            continue
        lookup = get_cached_lookup("neighborhood", summary.slug)
        if not lookup:
            continue
        pulse = lookup.pulse
        median_rent = summary.median_rent_eur or pulse.median_rent_eur
        median_sale = pulse.median_sale_eur
        if median_rent is None or median_sale is None or float(median_sale) <= 0:
            continue
        yield_pct = (float(median_rent) * 12 / float(median_sale)) * 100
        rows.append(
            {
                "neighborhood_name": summary.name,
                "slug": summary.slug,
                "median_rent_eur": round(float(median_rent), 0),
                "median_sale_eur": round(float(median_sale), 0),
                "median_rent_psm": summary.median_rent_psm_eur,
                "median_sale_psm": (
                    round(float(pulse.average_sale_psm_eur), 0)
                    if pulse.average_sale_psm_eur is not None
                    else None
                ),
                "gross_yield_pct": round(yield_pct, 2),
                "rent_listings": rent_n,
                "sale_listings": sale_n,
                "estimate_ready": True,
            }
        )
    rows.sort(key=lambda r: (-(r["gross_yield_pct"] or 0), r["neighborhood_name"]))
    if rows:
        write_rent_yield_cache(rows)
    return rows


def build_rent_yield_table(session: Session) -> list[dict]:
    """Neighborhood-level gross rent yield where both rent and sale samples are sufficient."""
    df = active_corpus_dataframe(session)
    if df.empty:
        return []

    table = build_neighborhood_market_table(df)
    if table.empty or "gross_yield_pct" not in table.columns:
        return []

    nh_lookup = _neighborhood_meta()
    rows: list[dict] = []
    for _, row in table.iterrows():
        nh_id = int(row["neighborhood_id"])
        rent_n = int(row.get("rent_inventory", 0) or 0)
        sale_n = int(row.get("inventory", 0) or 0)
        yield_pct = row.get("gross_yield_pct")
        if yield_pct is None or rent_n < MIN_COMPARABLES or sale_n < MIN_COMPARABLES:
            continue
        meta = nh_lookup.get(nh_id, {})
        rows.append(
            {
                "neighborhood_id": nh_id,
                "neighborhood_name": meta.get("name", ""),
                "slug": meta.get("slug"),
                "median_rent_eur": round(float(row["median_rent"]), 0)
                if row.get("median_rent") is not None
                else None,
                "median_sale_eur": round(float(row["median_sale"]), 0)
                if row.get("median_sale") is not None
                else None,
                "median_rent_psm": (
                    round(float(row["median_rent"]) / float(row["median_size_sqm"]), 1)
                    if row.get("median_rent") and row.get("median_size_sqm")
                    else None
                ),
                "median_sale_psm": round(float(row["median_price_per_sqm"]), 0)
                if row.get("median_price_per_sqm") is not None
                else None,
                "gross_yield_pct": round(float(yield_pct), 2),
                "rent_listings": rent_n,
                "sale_listings": sale_n,
                "estimate_ready": True,
            }
        )
    rows.sort(key=lambda r: (-(r["gross_yield_pct"] or 0), r["neighborhood_name"]))
    write_rent_yield_cache(rows)
    return rows
