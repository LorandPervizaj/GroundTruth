"""Summarize informal Facebook signals for internal review (B3)."""

from __future__ import annotations

from collections import Counter
from typing import Any

from groundtruth.analytics.display_rounding import round_rent_eur, round_sale_eur
from groundtruth.services.facebook_groups import load_group_samples
from groundtruth.services.facebook_import import load_informal_listings


def summarize_facebook_signals(*, sample_days: int = 90) -> dict[str, Any]:
    informal = load_informal_listings()
    samples = load_group_samples(days=sample_days)

    nh_counter: Counter[str] = Counter()
    type_counter: Counter[str] = Counter()
    prices_rent: list[int] = []
    prices_sale: list[int] = []

    for row in informal + samples:
        nh = row.get("neighborhood_guess")
        if nh:
            nh_counter[str(nh).strip()] += 1
        ltype = str(row.get("listing_type") or "unknown")
        type_counter[ltype] += 1
        price = row.get("price_eur")
        if price is not None:
            if ltype == "rent":
                prices_rent.append(int(price))
            elif ltype == "sale":
                prices_sale.append(int(price))

    def _median(vals: list[int], *, kind: str) -> int | None:
        if not vals:
            return None
        s = sorted(vals)
        raw = s[len(s) // 2]
        return round_rent_eur(raw) if kind == "rent" else round_sale_eur(raw)

    return {
        "informal_listings": len(informal),
        "group_samples": len(samples),
        "sample_window_days": sample_days,
        "by_listing_type": dict(type_counter),
        "top_neighborhood_guesses": nh_counter.most_common(10),
        "median_rent_eur": _median(prices_rent, kind="rent"),
        "median_sale_eur": _median(prices_sale, kind="sale"),
        "rent_price_n": len(prices_rent),
        "sale_price_n": len(prices_sale),
    }
