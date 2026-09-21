"""Diagnostic: trace extreme €/m² and rent values in the released comparables.

Run after a release build to see which listings drive the right tail of the public
price distributions, and whether a single repeated price is distorting them.

    uv run python scripts/audit_price_outliers.py
"""

from __future__ import annotations

import gzip
import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / "reports" / "generated" / "lookup_cache"


def load(name: str) -> list[dict]:
    with gzip.open(CACHE / f"{name}.json.gz", "rt", encoding="utf-8") as fh:
        return json.load(fh)["data"]


def main() -> None:
    sale = [r for r in load("sale_comparables") if r.get("sale_per_sqm")]
    rent = [r for r in load("rent_comparables") if r.get("rent_price")]

    sale.sort(key=lambda r: -r["sale_per_sqm"])
    print("TOP 20 sale EUR/m2")
    for r in sale[:20]:
        print(
            "  psm={:>8.0f} price={:>12,.0f} area={:>7.1f} beds={} type={} comm={} src={}/{}".format(
                r["sale_per_sqm"],
                r["sale_price"],
                r["area_sqm"],
                r["bedrooms"],
                r["property_type"],
                r["is_commercial"],
                r["source_website"],
                r["source_listing_id"],
            )
        )

    rent.sort(key=lambda r: -r["rent_price"])
    print("\nTOP 20 rent monthly")
    for r in rent[:20]:
        print(
            "  rent={:>9,.0f} area={:>7.1f} rpsm={:>7.2f} beds={} type={} comm={} src={}/{}".format(
                r["rent_price"],
                r["area_sqm"],
                r.get("rent_per_sqm") or 0,
                r["bedrooms"],
                r["property_type"],
                r["is_commercial"],
                r["source_website"],
                r["source_listing_id"],
            )
        )

    print("\nRepeated exact sale prices (a spike here means a parser artifact, not a market)")
    for price, count in Counter(round(r["sale_price"]) for r in sale).most_common(5):
        sources = Counter(r["source_website"] for r in sale if round(r["sale_price"]) == price)
        print(f"  EUR {price:>9,} x{count:<5} sources={dict(sources)}")

    print("\nArea histogram for sale psm >= 6000")
    hi = [r for r in sale if r["sale_per_sqm"] >= 6000]
    print("  count", len(hi), "of", len(sale))
    print("  areas", Counter(round(r["area_sqm"]) for r in hi).most_common(12))
    print("  types", Counter(r["property_type"] for r in hi).most_common())
    print("  prices", sorted(round(r["sale_price"]) for r in hi)[:20])

    print("\nRent >= 3000")
    rhi = [r for r in rent if r["rent_price"] >= 3000]
    print("  count", len(rhi), "of", len(rent))
    print("  types", Counter(r["property_type"] for r in rhi).most_common())
    print("  areas", sorted(round(r["area_sqm"]) for r in rhi)[:20])


if __name__ == "__main__":
    main()
