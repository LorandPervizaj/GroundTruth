"""Annual market report payload — active corpus, deduped, listing_date window."""

from __future__ import annotations

from datetime import date
from typing import Any

import pandas as pd
from sqlalchemy.orm import Session

from groundtruth.analytics.annual_conclusions import (
    MIN_SALE_LISTINGS_PER_NH,
    AnnualConclusionContext,
    build_dashboard_copy,
    build_rankings_commentary,
)
from groundtruth.analytics.annual_formulas import build_annual_formulas
from groundtruth.analytics.corpus import _pct_present, active_corpus_dataframe
from groundtruth.analytics.corpus_filters import (
    DEFAULT_MAX_AGE_MONTHS,
    active_corpus_cutoff_date,
)
from groundtruth.analytics.display_rounding import round_rent_eur, round_sale_eur, round_sale_psm
from groundtruth.analytics.market_metrics import (
    median_sale_psm as round_median_sale_psm,
)
from groundtruth.analytics.market_metrics import (
    sale_psm_series,
    sane_rent_rows,
    sane_sale_rows,
)
from groundtruth.analytics.metrics.price import price_percentiles as compute_price_percentiles
from groundtruth.analytics.price_histogram import (
    sale_psm_for_distribution,
    segment_price_distribution,
)
from groundtruth.analytics.price_quality import monthly_medians_from_frame
from groundtruth.analytics.sample_confidence import confidence_level, sample_meta
from groundtruth.portals.registry import public_parser_placeholders


def _month_key(series: pd.Series) -> pd.Series:
    return pd.to_datetime(series).dt.strftime("%Y-%m")


def _neighborhood_table_rows(
    work: pd.DataFrame,
    *,
    neighborhood_slug_by_name: dict[str, str] | None,
    limit: int = 10,
) -> list[dict[str, Any]]:
    nh_counts = (
        work.dropna(subset=["neighborhood"])
        .groupby("neighborhood")
        .size()
        .sort_values(ascending=False)
        .head(limit)
    )
    rows: list[dict[str, Any]] = []
    for nh_name, count in nh_counts.items():
        nh_df = work[work["neighborhood"] == nh_name]
        nh_sale = nh_df[nh_df["listing_type"] == "sale"]
        nh_rent = nh_df[nh_df["listing_type"] == "rent"]
        slug = (neighborhood_slug_by_name or {}).get(str(nh_name))
        sale_n = len(nh_sale)
        rent_n = len(nh_rent)
        rows.append(
            {
                "neighborhood": str(nh_name),
                "slug": slug,
                "inventory": int(count),
                "sale_n": sale_n,
                "rent_n": rent_n,
                "sale_confidence": confidence_level(sale_n),
                "rent_confidence": confidence_level(rent_n),
                "median_price_per_sqm": round_median_sale_psm(sale_psm_series(nh_sale)),
                "median_rent": round_rent_eur(
                    sane_rent_rows(nh_rent)["rent_price"].median() if not nh_rent.empty else None
                ),
            }
        )
    return rows


def _neighborhood_price_rankings(
    work: pd.DataFrame,
    *,
    neighborhood_slug_by_name: dict[str, str] | None,
    limit: int = 5,
) -> dict[str, Any]:
    sale = work[work["listing_type"] == "sale"].dropna(subset=["neighborhood", "price_per_sqm"])
    if sale.empty:
        empty: dict[str, Any] = {
            "expensive": [],
            "affordable": [],
            "min_sale_listings": MIN_SALE_LISTINGS_PER_NH,
        }
        return empty

    grouped = (
        sale.groupby("neighborhood")
        .agg(
            n=("price_per_sqm", "count"),
            median_price_per_sqm=("price_per_sqm", "median"),
            median_sale_eur=("sale_price", "median"),
        )
        .reset_index()
    )
    qualified = grouped[grouped["n"] >= MIN_SALE_LISTINGS_PER_NH].copy()
    if qualified.empty:
        return {
            "expensive": [],
            "affordable": [],
            "min_sale_listings": MIN_SALE_LISTINGS_PER_NH,
        }

    slug_map = neighborhood_slug_by_name or {}

    def _row(record: pd.Series) -> dict[str, Any]:
        name = str(record["neighborhood"])
        n = int(record["n"])
        return {
            "neighborhood": name,
            "slug": slug_map.get(name),
            "n": n,
            "confidence": confidence_level(n),
            "median_price_per_sqm": round_sale_psm(record["median_price_per_sqm"]),
            "median_sale_eur": round_sale_eur(record["median_sale_eur"]),
        }

    expensive = [
        _row(r)
        for _, r in qualified.sort_values("median_price_per_sqm", ascending=False)
        .head(limit)
        .iterrows()
    ]
    affordable = [
        _row(r)
        for _, r in qualified.sort_values("median_price_per_sqm", ascending=True)
        .head(limit)
        .iterrows()
    ]
    return {
        "expensive": expensive,
        "affordable": affordable,
        "min_sale_listings": MIN_SALE_LISTINGS_PER_NH,
    }


def _size_band(area: float | None) -> str | None:
    if area is None or pd.isna(area):
        return None
    a = float(area)
    if a < 50:
        return "<50m²"
    if a < 80:
        return "50-79m²"
    if a < 110:
        return "80-109m²"
    return "110m²+"


_BEDROOM_SEGMENT_ORDER = ("0 BR", "1 BR", "2 BR", "3 BR", "4+ BR")
_SIZE_BAND_ORDER = ("<50m²", "50-79m²", "80-109m²", "110m²+")


def _bedroom_segment_label(value: object) -> str | None:
    """Map bedroom counts to display buckets; drop negatives and cap at 4+."""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    try:
        beds = int(value)
    except (TypeError, ValueError):
        return None
    if beds < 0:
        return None
    if beds >= 4:
        return "4+ BR"
    return f"{beds} BR"


def _segment_sort_key(segment: str, order: tuple[str, ...]) -> tuple[int, str]:
    rank = {label: i for i, label in enumerate(order)}
    return (rank.get(segment, len(order)), segment)


def _segment_rows(
    frame: pd.DataFrame,
    group_col: str,
    *,
    order: tuple[str, ...] | None = None,
) -> list[dict[str, Any]]:
    """Per-segment medians using sale-only €/m² (never mix rent price_per_sqm)."""
    if frame.empty or group_col not in frame.columns:
        return []
    rows: list[dict[str, Any]] = []
    for key, group in frame.dropna(subset=[group_col]).groupby(group_col, sort=False):
        sale = group[group["listing_type"] == "sale"] if "listing_type" in group.columns else group
        rent = group[group["listing_type"] == "rent"] if "listing_type" in group.columns else group
        sane_sale = sane_sale_rows(sale)
        sane_rent = sane_rent_rows(rent)
        n = len(group)
        rows.append(
            {
                "segment": str(key),
                "listings": n,
                "confidence": confidence_level(n),
                "median_sale_price": round_sale_eur(
                    sane_sale["sale_price"].median() if not sane_sale.empty else None
                ),
                "median_sale_psm": round_median_sale_psm(sale_psm_series(sale)),
                "median_rent": round_rent_eur(
                    sane_rent["rent_price"].median() if not sane_rent.empty else None
                ),
                "median_area_sqm": _round_or_none(group["area_sqm"].median(), digits=1),
            }
        )
    if order is not None:
        rows.sort(key=lambda r: _segment_sort_key(str(r["segment"]), order))
    else:
        rows.sort(key=lambda r: (-int(r["listings"]), str(r["segment"])))
    return rows


def _most_common_segment(rows: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not rows:
        return None
    return max(rows, key=lambda r: (int(r.get("listings") or 0), str(r.get("segment") or "")))


def _segment_recommendations(
    bedroom_rows: list[dict[str, Any]],
    size_rows: list[dict[str, Any]],
) -> dict[str, dict[str, str | None]]:
    def _best(
        rows: list[dict[str, Any]], key: str, *, reverse: bool = False
    ) -> dict[str, Any] | None:
        candidates = [
            r for r in rows if r.get(key) not in (None, 0) and (r.get("listings") or 0) >= 8
        ]
        if not candidates:
            return None
        return sorted(candidates, key=lambda r: float(r[key]), reverse=reverse)[0]

    # Best buy value: lowest sale €/m² among decently sampled segments.
    buy_val = _best(bedroom_rows, "median_sale_psm") or _best(size_rows, "median_sale_psm")
    # Best rent value: lowest monthly rent.
    rent_val = _best(bedroom_rows, "median_rent") or _best(size_rows, "median_rent")

    # Best buy-to-rent: highest simple gross yield proxy (rent*12 / sale_price).
    yield_candidates: list[dict[str, Any]] = []
    for row in bedroom_rows + size_rows:
        sale = row.get("median_sale_price")
        rent = row.get("median_rent")
        n = int(row.get("listings") or 0)
        if sale and rent and sale > 0 and n >= 8:
            y = (float(rent) * 12.0) / float(sale) * 100.0
            yield_candidates.append(
                {"segment": row["segment"], "yield_pct": round(y, 1), "listings": n}
            )
    buy_to_rent = (
        sorted(yield_candidates, key=lambda r: r["yield_pct"], reverse=True)[0]
        if yield_candidates
        else None
    )

    return {
        "best_buy_value": {
            "segment": buy_val["segment"] if buy_val else None,
            "reason": "lowest_sale_psm",
        },
        "best_buy_to_rent": {
            "segment": buy_to_rent["segment"] if buy_to_rent else None,
            "reason": "highest_gross_yield_proxy",
            "yield_pct": buy_to_rent["yield_pct"] if buy_to_rent else None,
        },
        "best_rent_value": {
            "segment": rent_val["segment"] if rent_val else None,
            "reason": "lowest_median_rent",
        },
    }


def _property_type_composition(work: pd.DataFrame) -> dict[str, Any]:
    if work.empty or "property_type" not in work.columns:
        return {"types": [], "top_type": None, "top_pct": None, "total": 0}
    series = work["property_type"].fillna("APARTMENT").astype(str).str.upper()
    counts = series.value_counts()
    total = int(counts.sum())
    types = [
        {"type": str(name), "count": int(count), "pct": round(100.0 * count / total, 1)}
        for name, count in counts.items()
    ]
    top = types[0] if types else None
    return {
        "types": types,
        "top_type": top["type"] if top else None,
        "top_pct": top["pct"] if top else None,
        "total": total,
    }


def _property_type_by_neighborhood(
    work: pd.DataFrame,
    *,
    neighborhood_slug_by_name: dict[str, str] | None,
    min_listings: int = 10,
    limit: int = 15,
) -> list[dict[str, Any]]:
    if work.empty or "property_type" not in work.columns:
        return []
    slug_map = neighborhood_slug_by_name or {}
    rows: list[dict[str, Any]] = []
    grouped = work.dropna(subset=["neighborhood"]).groupby("neighborhood", sort=False)
    for nh_name, nh_df in grouped:
        n = len(nh_df)
        if n < min_listings:
            continue
        pt_counts = (
            nh_df["property_type"].fillna("APARTMENT").astype(str).str.upper().value_counts()
        )
        if pt_counts.empty:
            continue
        top_type = str(pt_counts.index[0])
        top_n = int(pt_counts.iloc[0])
        rows.append(
            {
                "neighborhood": str(nh_name),
                "slug": slug_map.get(str(nh_name)),
                "top_property_type": top_type,
                "top_property_type_pct": round(100.0 * top_n / n, 1),
                "listings": n,
            }
        )
    rows.sort(key=lambda r: (-r["listings"], r["neighborhood"]))
    return rows[:limit]


def _top_segment_row(
    rows: list[dict[str, Any]],
    key: str,
    *,
    reverse: bool = True,
    min_listings: int = 8,
) -> dict[str, Any] | None:
    candidates = [
        r
        for r in rows
        if r.get(key) not in (None, 0) and int(r.get("listings") or 0) >= min_listings
    ]
    if not candidates:
        return None
    return sorted(candidates, key=lambda r: float(r[key]), reverse=reverse)[0]


def _neighborhood_segment_profiles(
    work: pd.DataFrame,
    *,
    neighborhood_slug_by_name: dict[str, str] | None,
    min_listings: int = 10,
    limit: int = 15,
) -> list[dict[str, Any]]:
    if work.empty:
        return []
    slug_map = neighborhood_slug_by_name or {}
    apt = work.copy()
    apt["size_band"] = apt["area_sqm"].apply(_size_band)
    apt["bedroom_segment"] = apt["bedrooms"].apply(_bedroom_segment_label)
    rows: list[dict[str, Any]] = []
    for nh_name, nh_df in apt.dropna(subset=["neighborhood"]).groupby("neighborhood", sort=False):
        n = len(nh_df)
        if n < min_listings:
            continue
        top_bed = None
        bed_df = nh_df.dropna(subset=["bedroom_segment"])
        if not bed_df.empty:
            top_bed = str(bed_df["bedroom_segment"].value_counts().index[0])
        top_size = None
        size_df = nh_df.dropna(subset=["size_band"])
        if not size_df.empty:
            top_size = str(size_df["size_band"].value_counts().index[0])
        rows.append(
            {
                "neighborhood": str(nh_name),
                "slug": slug_map.get(str(nh_name)),
                "listings": n,
                "top_bedroom_segment": top_bed,
                "top_size_band": top_size,
            }
        )
    rows.sort(key=lambda r: (-r["listings"], r["neighborhood"]))
    return rows[:limit]


def _neighborhood_yield_rankings(
    work: pd.DataFrame,
    *,
    neighborhood_slug_by_name: dict[str, str] | None,
    min_rent: int = 10,
    min_sale: int = 10,
    limit: int = 5,
) -> list[dict[str, Any]]:
    sale = work[work["listing_type"] == "sale"].dropna(subset=["neighborhood", "sale_price"])
    rent = work[work["listing_type"] == "rent"].dropna(subset=["neighborhood", "rent_price"])
    if sale.empty or rent.empty:
        return []
    sale_g = sale.groupby("neighborhood").agg(
        sale_n=("sale_price", "count"),
        median_sale_eur=("sale_price", "median"),
    )
    rent_g = rent.groupby("neighborhood").agg(
        rent_n=("rent_price", "count"),
        median_rent_eur=("rent_price", "median"),
    )
    merged = sale_g.join(rent_g, how="inner")
    merged = merged[(merged["sale_n"] >= min_sale) & (merged["rent_n"] >= min_rent)].copy()
    if merged.empty:
        return []
    merged["gross_yield_pct"] = (
        merged["median_rent_eur"] * 12.0 / merged["median_sale_eur"]
    ) * 100.0
    slug_map = neighborhood_slug_by_name or {}
    rows: list[dict[str, Any]] = []
    for nh_name, r in merged.sort_values("gross_yield_pct", ascending=False).head(limit).iterrows():
        sale_n = int(r["sale_n"])
        rent_n = int(r["rent_n"])
        rows.append(
            {
                "neighborhood": str(nh_name),
                "slug": slug_map.get(str(nh_name)),
                "gross_yield_pct": round(float(r["gross_yield_pct"]), 2),
                "median_rent_eur": round_rent_eur(r["median_rent_eur"]),
                "median_sale_eur": round_sale_eur(r["median_sale_eur"]),
                "sale_n": sale_n,
                "rent_n": rent_n,
                "confidence": confidence_level(min(sale_n, rent_n)),
            }
        )
    return rows


def _build_market_insights(
    work: pd.DataFrame,
    *,
    neighborhood_slug_by_name: dict[str, str] | None,
    bedroom_segments: list[dict[str, Any]],
    size_segments: list[dict[str, Any]],
    segment_recommendations: dict[str, dict[str, str | None]],
    neighborhood_rankings: dict[str, Any],
) -> dict[str, Any]:
    property_types = _property_type_composition(work)
    common_bedroom = _most_common_segment(bedroom_segments)
    common_size = _most_common_segment(size_segments)
    expensive_bedroom = _top_segment_row(bedroom_segments, "median_sale_psm")
    expensive_size = _top_segment_row(size_segments, "median_sale_psm")
    return {
        "property_types": {
            "city": property_types,
            "by_neighborhood": _property_type_by_neighborhood(
                work, neighborhood_slug_by_name=neighborhood_slug_by_name
            ),
        },
        "common_segments": {
            "most_common_bedroom": common_bedroom,
            "most_common_size_band": common_size,
            "most_expensive_bedroom": expensive_bedroom,
            "most_expensive_size_band": expensive_size,
        },
        "neighborhood_profiles": _neighborhood_segment_profiles(
            work, neighborhood_slug_by_name=neighborhood_slug_by_name
        ),
        "best_rent_yield": _neighborhood_yield_rankings(
            work, neighborhood_slug_by_name=neighborhood_slug_by_name
        ),
        "best_to_live": neighborhood_rankings.get("affordable") or [],
        "most_expensive_psm": neighborhood_rankings.get("expensive") or [],
        "segment_recommendations": segment_recommendations,
    }


def build_annual_report_from_dataframe(
    df: pd.DataFrame,
    *,
    cutoff_date: date | None = None,
    max_age_months: int = DEFAULT_MAX_AGE_MONTHS,
    neighborhood_slug_by_name: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Build annual report JSON from an active-corpus-shaped dataframe."""
    cutoff_date = cutoff_date or active_corpus_cutoff_date(max_age_months=max_age_months)

    if df.empty:
        return _empty_payload(cutoff_date=cutoff_date, max_age_months=max_age_months)

    work = df.copy()
    work["listing_month"] = _month_key(work["listing_date"])

    months = sorted(work["listing_month"].dropna().unique().tolist())

    rent_df = work[work["listing_type"] == "rent"]
    sale_df = work[work["listing_type"] == "sale"]

    rent_by_month = rent_df.groupby("listing_month").size()
    sale_by_month = sale_df.groupby("listing_month").size()

    volume = {
        "labels": months,
        "rent": [int(rent_by_month.get(m, 0)) for m in months],
        "sale": [int(sale_by_month.get(m, 0)) for m in months],
    }

    sale_clean, _sale_n, sale_exclusions, sale_raw = monthly_medians_from_frame(
        sale_df,
        month_col="listing_month",
        value_col="price_per_sqm",
    )
    prices = {
        "labels": months,
        "values": [round_sale_psm(sale_clean[m]) if m in sale_clean else None for m in months],
        "raw_values": [round_sale_psm(sale_raw[m]) if m in sale_raw else None for m in months],
        "counts": [int(sale_by_month.get(m, 0)) for m in months],
        "excluded_months": sale_exclusions,
        "metric": "median",
    }

    rent_clean, _rent_n, rent_exclusions, rent_raw = monthly_medians_from_frame(
        rent_df,
        month_col="listing_month",
        value_col="rent_price",
    )
    rent_prices = {
        "labels": months,
        "values": [round_rent_eur(rent_clean[m]) if m in rent_clean else None for m in months],
        "raw_values": [round_rent_eur(rent_raw[m]) if m in rent_raw else None for m in months],
        "counts": [int(rent_by_month.get(m, 0)) for m in months],
        "excluded_months": rent_exclusions,
        "metric": "median",
    }

    nh_counts = (
        work.dropna(subset=["neighborhood"])
        .groupby("neighborhood")
        .size()
        .sort_values(ascending=False)
        .head(5)
    )
    top_neighborhoods = [
        {"name": str(name), "count": int(count)} for name, count in nh_counts.items()
    ]

    total = len(work)
    rent_count = int((work["listing_type"] == "rent").sum())
    sale_count = int((work["listing_type"] == "sale").sum())
    rent_pct = round(100.0 * rent_count / total) if total else 0.0

    median_sale_psm = sale_psm_series(sale_df).median() if not sale_df.empty else None
    median_rent = sane_rent_rows(rent_df)["rent_price"].median() if not rent_df.empty else None

    apt_for_dist = work[
        work["property_type"].astype(str).str.contains("apartment|studio", case=False, na=False)
    ].copy()
    if apt_for_dist.empty:
        apt_for_dist = work.copy()
    # Stats distribution summaries share the same analytical ceiling as the
    # histogram (< €4,000/m²). Unrelated KPIs above still use the full band.
    sale_psm_raw = sale_psm_series(apt_for_dist[apt_for_dist["listing_type"] == "sale"])
    sale_psm_for_dist, _excluded_sale_dist = sale_psm_for_distribution(sale_psm_raw)
    pct_map = compute_price_percentiles(sale_psm_for_dist)
    price_percentiles_payload: dict[str, Any] | None = None
    if pct_map.get("p50") is not None and len(sale_psm_for_dist) > 0:
        price_percentiles_payload = {
            "p10_sale_psm": pct_map.get("p10"),
            "p50_sale_psm": pct_map.get("p50"),
            "p90_sale_psm": pct_map.get("p90"),
            "n": int(len(sale_psm_for_dist)),
            "max_psm_exclusive": 4000,
            "excluded_n": int(_excluded_sale_dist),
        }
    sale_price_distribution = segment_price_distribution(apt_for_dist, "sale")

    sources: list[dict[str, Any]] = []

    coverage = {
        "price_pct": float(_pct_present(work["listing_price"])),
        "area_pct": float(_pct_present(work["area_sqm"])),
        "neighborhood_pct": float(_pct_present(work["neighborhood_id"])),
        "bedrooms_pct": float(_pct_present(work["bedrooms"]))
        if "bedrooms" in work.columns
        else 0.0,
    }

    neighborhood_table = _neighborhood_table_rows(
        work,
        neighborhood_slug_by_name=neighborhood_slug_by_name,
        limit=10,
    )
    neighborhood_highlights = neighborhood_table[:5]
    neighborhood_rankings = _neighborhood_price_rankings(
        work,
        neighborhood_slug_by_name=neighborhood_slug_by_name,
    )

    apt = work[
        work["property_type"].astype(str).str.contains("apartment", case=False, na=False)
    ].copy()
    if apt.empty:
        apt = work.copy()
    apt["size_band"] = apt["area_sqm"].apply(_size_band)
    apt["bedroom_segment"] = apt["bedrooms"].apply(_bedroom_segment_label)
    bedroom_segments = _segment_rows(apt, "bedroom_segment", order=_BEDROOM_SEGMENT_ORDER)
    size_segments = _segment_rows(apt, "size_band", order=_SIZE_BAND_ORDER)
    segment_recommendations = _segment_recommendations(bedroom_segments, size_segments)
    market_insights = _build_market_insights(
        work,
        neighborhood_slug_by_name=neighborhood_slug_by_name,
        bedroom_segments=bedroom_segments,
        size_segments=size_segments,
        segment_recommendations=segment_recommendations,
        neighborhood_rankings=neighborhood_rankings,
    )

    valid_price_points = [
        (m, v) for m, v in zip(prices["labels"], prices["values"], strict=True) if v is not None
    ]
    peak_price_month = (
        max(valid_price_points, key=lambda x: x[1])[0] if valid_price_points else None
    )
    median_sale_psm_val = round_sale_psm(median_sale_psm)
    median_rent_val = round_rent_eur(median_rent)

    top_nh_name = top_neighborhoods[0]["name"] if top_neighborhoods else None
    top_nh_count = top_neighborhoods[0]["count"] if top_neighborhoods else 0

    volume_by_month = {
        m: {"rent": volume["rent"][i], "sale": volume["sale"][i]} for i, m in enumerate(months)
    }
    sale_psm_by_month = {
        m: float(v)
        for m, v in zip(prices["labels"], prices["values"], strict=True)
        if v is not None
    }

    ctx = AnnualConclusionContext(
        total=total,
        rent_count=rent_count,
        sale_count=sale_count,
        rent_pct=rent_pct,
        median_sale_psm=median_sale_psm_val,
        median_rent=median_rent_val,
        cutoff_date=cutoff_date,
        coverage=coverage,
        sources=sources,
        top_neighborhood=top_nh_name,
        top_neighborhood_count=top_nh_count,
        volume_by_month=volume_by_month,
        sale_psm_by_month=sale_psm_by_month,
        work=work,
    )
    methodology_meta = {
        "window_months": max_age_months,
        "cutoff_date": cutoff_date.isoformat(),
        "parser_versions": public_parser_placeholders(),
    }
    dashboard = build_dashboard_copy(
        ctx,
        peak_price_month=peak_price_month,
        methodology_meta=methodology_meta,
    )

    return {
        "volume": volume,
        "prices": prices,
        "rent_prices": rent_prices,
        "top_neighborhoods": top_neighborhoods,
        "neighborhood_highlights": neighborhood_highlights,
        "neighborhood_table": neighborhood_table,
        "neighborhood_rankings": neighborhood_rankings,
        "total_listings": total,
        "kpis": {
            "total_listings": total,
            "total_sample": sample_meta(total),
            "rent_count": rent_count,
            "rent_sample": sample_meta(rent_count),
            "sale_count": sale_count,
            "sale_sample": sample_meta(sale_count),
            "rent_pct": rent_pct,
            "median_sale_price_per_sqm": median_sale_psm_val,
            "median_sale_sample": sample_meta(sale_count),
            "median_rent": median_rent_val,
            "median_rent_sample": sample_meta(rent_count),
        },
        "sources": sources,
        "coverage": coverage,
        "methodology": {
            "window_months": max_age_months,
            "cutoff_date": cutoff_date.isoformat(),
            "date_field": "listing_date",
            "deduped": True,
            "sources": public_parser_placeholders(),
            "sale_price_metric": "median_price_per_sqm",
            "rent_price_metric": "median_rent",
            "note": "Asking prices from portal listings; not closed transactions.",
        },
        "executive_summary": dashboard["executive_summary"],
        "insights": dashboard["insights"],
        "coverage_narrative": dashboard["coverage_narrative"],
        "methodology_plain": dashboard["methodology_plain"],
        "limitations": dashboard["limitations"],
        "rankings_commentary": build_rankings_commentary(neighborhood_rankings),
        "conclusions": dashboard["conclusions"],
        "narratives": dashboard["narratives"],
        "narratives_i18n": dashboard["narratives_i18n"],
        "apartment_segments": {
            "by_bedrooms": bedroom_segments,
            "by_size_band": size_segments,
            "recommendations": segment_recommendations,
        },
        "market_insights": market_insights,
        "price_percentiles": price_percentiles_payload,
        "sale_price_distribution": sale_price_distribution,
        "formulas": build_annual_formulas(min_sale_listings=MIN_SALE_LISTINGS_PER_NH),
    }


def build_annual_report_payload(
    session: Session,
    *,
    max_age_months: int = DEFAULT_MAX_AGE_MONTHS,
) -> dict[str, Any]:
    """Load active corpus and build the annual report API payload."""
    from groundtruth.models.reference import Neighborhood

    cutoff = active_corpus_cutoff_date(max_age_months=max_age_months)
    df = active_corpus_dataframe(session, max_age_months=max_age_months)
    slug_by_name = {n.name: n.slug for n in session.query(Neighborhood).all()}
    return build_annual_report_from_dataframe(
        df,
        cutoff_date=cutoff,
        max_age_months=max_age_months,
        neighborhood_slug_by_name=slug_by_name,
    )


def _round_or_none(value: Any, digits: int = 0) -> float | None:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    return round(float(value), digits)


def _empty_payload(*, cutoff_date: date, max_age_months: int) -> dict[str, Any]:
    return {
        "volume": {"labels": [], "rent": [], "sale": []},
        "prices": {"labels": [], "values": [], "metric": "median"},
        "rent_prices": {"labels": [], "values": [], "metric": "median"},
        "top_neighborhoods": [],
        "neighborhood_highlights": [],
        "neighborhood_table": [],
        "neighborhood_rankings": {
            "expensive": [],
            "affordable": [],
            "min_sale_listings": MIN_SALE_LISTINGS_PER_NH,
        },
        "total_listings": 0,
        "kpis": {
            "total_listings": 0,
            "rent_count": 0,
            "sale_count": 0,
            "rent_pct": 0.0,
            "median_sale_price_per_sqm": None,
            "median_rent": None,
        },
        "sources": [],
        "coverage": {
            "price_pct": 0.0,
            "area_pct": 0.0,
            "neighborhood_pct": 0.0,
            "bedrooms_pct": 0.0,
        },
        "methodology": {
            "window_months": max_age_months,
            "cutoff_date": cutoff_date.isoformat(),
            "date_field": "listing_date",
            "deduped": True,
            "sources": public_parser_placeholders(),
            "sale_price_metric": "median_price_per_sqm",
            "rent_price_metric": "median_rent",
            "note": "Asking prices from portal listings; not closed transactions.",
        },
        "conclusions": {
            "sq": ["Nuk ka të dhëna në korpusin aktiv për këtë periudhë."],
            "en": ["No listings in the active corpus for this period."],
        },
        "narratives": {
            "volume_insight": "Nuk ka të dhëna në korpusin aktiv për këtë periudhë.",
            "price_insight": "Nuk ka të dhëna të mjaftueshme për trendin e çmimeve.",
            "rent_insight": "Nuk ka të dhëna për qiratë.",
            "nh_insight": "Nuk ka të dhëna lagjesh.",
            "confidence": "—",
            "confidence_text": "Korpusi aktiv është bosh.",
        },
        "narratives_i18n": {
            "sq": {
                "volume_insight": "Nuk ka të dhëna në korpusin aktiv për këtë periudhë.",
                "price_insight": "Nuk ka të dhëna të mjaftueshme për trendin e çmimeve.",
                "rent_insight": "Nuk ka të dhëna për qiratë.",
                "nh_insight": "Nuk ka të dhëna lagjesh.",
                "confidence": "—",
                "confidence_text": "Korpusi aktiv është bosh.",
            },
            "en": {
                "volume_insight": "No data in the active corpus for this period.",
                "price_insight": "Not enough data for price trends.",
                "rent_insight": "No rent data available.",
                "nh_insight": "No neighborhood data.",
                "confidence": "—",
                "confidence_text": "The active corpus is empty.",
            },
        },
        "apartment_segments": {
            "by_bedrooms": [],
            "by_size_band": [],
            "recommendations": {
                "best_buy_value": {"segment": None, "reason": "lowest_sale_psm"},
                "best_buy_to_rent": {
                    "segment": None,
                    "reason": "highest_gross_yield_proxy",
                    "yield_pct": None,
                },
                "best_rent_value": {"segment": None, "reason": "lowest_median_rent"},
            },
        },
        "market_insights": {
            "property_types": {
                "city": {"types": [], "top_type": None, "top_pct": None, "total": 0},
                "by_neighborhood": [],
            },
            "common_segments": {
                "most_common_bedroom": None,
                "most_common_size_band": None,
                "most_expensive_bedroom": None,
                "most_expensive_size_band": None,
            },
            "neighborhood_profiles": [],
            "best_rent_yield": [],
            "best_to_live": [],
            "most_expensive_psm": [],
            "segment_recommendations": {
                "best_buy_value": {"segment": None, "reason": "lowest_sale_psm"},
                "best_buy_to_rent": {
                    "segment": None,
                    "reason": "highest_gross_yield_proxy",
                    "yield_pct": None,
                },
                "best_rent_value": {"segment": None, "reason": "lowest_median_rent"},
            },
        },
        "price_percentiles": None,
        "sale_price_distribution": {
            "listing_type": "sale",
            "bins": [],
            "n": 0,
            "confidence": "insufficient",
        },
    }
