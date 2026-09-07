"""Match neighborhoods to a renter or buyer budget and apartment requirements."""

from __future__ import annotations

import logging
from typing import Any, Literal

import pandas as pd
from sqlalchemy.orm import Session

from groundtruth.analytics.corpus import active_corpus_dataframe
from groundtruth.analytics.display_rounding import (
    round_rent_eur,
    round_rent_psm,
    round_sale_eur,
    round_sale_psm,
)
from groundtruth.analytics.sample_confidence import confidence_level
from groundtruth.models.reference import Neighborhood
from groundtruth.schemas.budget_match import (
    BudgetMatchNeighborhood,
    BudgetMatchRequest,
    BudgetMatchResponse,
    FitTier,
)

logger = logging.getLogger(__name__)

MIN_MATCH_LISTINGS = 3
BUDGET_TOLERANCE = 1.01

# Typical apartment sizes by bedroom count — used when user picks beds but not area.
BEDROOM_TYPICAL_SQM: dict[int, float] = {0: 32.0, 1: 45.0, 2: 62.0, 3: 82.0, 4: 100.0, 5: 115.0}

_CONFIDENCE_SCORE = {"high": 100.0, "medium": 78.0, "low": 48.0, "insufficient": 12.0}


def _apply_filters(
    df: pd.DataFrame,
    *,
    listing_type: Literal["rent", "sale"],
    bedrooms: int | None,
) -> tuple[pd.DataFrame, str]:
    work = df[df["listing_type"] == listing_type].copy()
    if "property_type" in work.columns:
        work = work[work["property_type"].fillna("APARTMENT").str.upper() == "APARTMENT"]
    work = work.dropna(subset=["neighborhood"])
    if bedrooms is not None and "bedrooms" in work.columns:
        work = work[work["bedrooms"] == bedrooms]
    price_col = "rent_price" if listing_type == "rent" else "sale_price"
    work = work.dropna(subset=[price_col, "area_sqm"])
    work = work[work[price_col] > 0]
    return work, price_col


def _listings_in_area_band(
    df: pd.DataFrame,
    *,
    min_area_sqm: float | None,
    max_area_sqm: float | None,
) -> pd.DataFrame:
    work = df
    if min_area_sqm is not None:
        work = work[work["area_sqm"].notna() & (work["area_sqm"] >= min_area_sqm)]
    if max_area_sqm is not None:
        work = work[work["area_sqm"].notna() & (work["area_sqm"] <= max_area_sqm)]
    return work


def resolve_target_sqm(
    request: BudgetMatchRequest,
    *,
    typical_area: float | None = None,
) -> float:
    """Size we price against — respects bedroom norms and the user's area band."""
    bed_floor = BEDROOM_TYPICAL_SQM.get(request.bedrooms) if request.bedrooms is not None else None

    if request.min_area_sqm is not None and request.max_area_sqm is not None:
        target = (request.min_area_sqm + request.max_area_sqm) / 2.0
    elif request.min_area_sqm is not None:
        target = request.min_area_sqm + 12.0
    elif request.max_area_sqm is not None:
        target = request.max_area_sqm - 12.0
    elif bed_floor is not None:
        target = bed_floor
    elif typical_area is not None:
        target = float(typical_area)
    else:
        target = 70.0

    if bed_floor is not None:
        target = max(target, bed_floor)
    if request.min_area_sqm is not None:
        target = max(target, request.min_area_sqm)
    if request.max_area_sqm is not None:
        target = min(target, request.max_area_sqm)

    return round(target, 0)


def _uses_segment_pricing(request: BudgetMatchRequest) -> bool:
    return (
        request.bedrooms is not None
        or request.min_area_sqm is not None
        or request.max_area_sqm is not None
    )


def _price_psm(
    *,
    median_price: float,
    median_area: float,
    median_psm: float | None,
) -> float | None:
    if median_psm is not None and median_psm > 0:
        return float(median_psm)
    if median_area > 0:
        return median_price / median_area
    return None


def estimate_apartment_price(
    *,
    median_price: float,
    median_area: float,
    median_psm: float | None,
    target_sqm: float,
) -> tuple[float, float | None]:
    psm = _price_psm(median_price=median_price, median_area=median_area, median_psm=median_psm)
    if psm is None:
        return median_price, None
    return psm * target_sqm, psm


def _area_fit_pct(
    median_area: float,
    *,
    target_sqm: float,
    min_area_sqm: float | None,
    max_area_sqm: float | None,
) -> float | None:
    if not _uses_segment_pricing(
        BudgetMatchRequest(
            min_area_sqm=min_area_sqm,
            max_area_sqm=max_area_sqm,
            bedrooms=None,
            max_budget_eur=1,
        )
    ):
        return None
    tolerance = max(12.0, target_sqm * 0.18)
    delta = abs(median_area - target_sqm)
    return round(max(0.0, 100.0 - (delta / tolerance) * 100.0), 1)


def _headroom_pct(budget: float, price: float) -> tuple[float, float]:
    headroom_eur = max(0.0, budget - price)
    headroom_pct = round((headroom_eur / budget) * 100.0, 1) if budget else 0.0
    return headroom_eur, headroom_pct


def _headroom_score(headroom_pct: float) -> float:
    if headroom_pct >= 25.0:
        return 88.0
    if headroom_pct >= 12.0:
        return 100.0
    if headroom_pct >= 5.0:
        return 92.0
    if headroom_pct >= 0.0:
        return max(35.0, 70.0 + headroom_pct * 4.0)
    return 20.0


def _fit_tier(
    *,
    afford_pct: float,
    match_count: int,
    confidence: str,
    headroom_pct: float,
    compare_price: float,
    budget: float,
) -> FitTier:
    stretched = compare_price > budget * 0.94 or headroom_pct < 3.0
    if stretched:
        return "stretch"
    strong = (
        afford_pct >= 40.0
        and match_count >= 8
        and confidence in ("high", "medium")
        and headroom_pct >= 8.0
    )
    if strong:
        return "best"
    if afford_pct >= 20.0 and match_count >= MIN_MATCH_LISTINGS and headroom_pct >= 3.0:
        return "good"
    return "stretch"


def _composite_fit_score(
    *,
    afford_pct: float,
    match_count: int,
    confidence: str,
    headroom_pct: float,
    area_fit_pct: float | None,
    gross_yield_pct: float | None,
    listing_type: Literal["rent", "sale"],
) -> float:
    inventory_score = min(100.0, (match_count / 25.0) * 100.0)
    confidence_score = _CONFIDENCE_SCORE.get(confidence, 12.0)
    headroom_score = _headroom_score(headroom_pct)
    area_score = area_fit_pct if area_fit_pct is not None else 72.0
    yield_score = (
        min(100.0, ((gross_yield_pct or 0.0) / 6.5) * 100.0) if listing_type == "sale" else 0.0
    )

    if listing_type == "rent":
        return round(
            afford_pct * 0.34
            + inventory_score * 0.20
            + confidence_score * 0.18
            + headroom_score * 0.18
            + area_score * 0.10,
            1,
        )
    return round(
        afford_pct * 0.26
        + inventory_score * 0.16
        + confidence_score * 0.16
        + headroom_score * 0.16
        + area_score * 0.10
        + yield_score * 0.16,
        1,
    )


def _yield_for_neighborhood(
    nh_df: pd.DataFrame,
    *,
    listing_type: Literal["rent", "sale"],
) -> float | None:
    if listing_type != "sale":
        return None
    rent = nh_df[nh_df["listing_type"] == "rent"]["rent_price"].dropna()
    sale = nh_df[nh_df["listing_type"] == "sale"]["sale_price"].dropna()
    if len(rent) < MIN_MATCH_LISTINGS or len(sale) < MIN_MATCH_LISTINGS:
        return None
    med_rent = float(rent.median())
    med_sale = float(sale.median())
    if med_sale <= 0:
        return None
    return round((med_rent * 12.0 / med_sale) * 100.0, 2)


def _summary_key(
    *,
    fit_tier: FitTier,
    listing_type: Literal["rent", "sale"],
    gross_yield_pct: float | None,
    match_count: int,
    cached: bool,
    segment_pricing: bool,
) -> str:
    if match_count < MIN_MATCH_LISTINGS:
        return "budget_match_summary_sparse"
    if fit_tier == "stretch":
        return "budget_match_summary_stretch"
    if fit_tier == "best":
        return (
            "budget_match_summary_strong_rent"
            if listing_type == "rent"
            else "budget_match_summary_strong_sale"
        )
    if gross_yield_pct is not None and gross_yield_pct >= 4.5:
        return "budget_match_summary_yield"
    if cached and segment_pricing:
        return "budget_match_summary_estimated"
    if cached:
        return "budget_match_summary_cached"
    return "budget_match_summary_default"


def _row_to_neighborhood(
    row: dict[str, Any],
    request: BudgetMatchRequest,
) -> BudgetMatchNeighborhood:
    med_price = row["median_price_eur"]
    med_psm = row["median_price_psm"]
    est_price = row.get("estimated_price_eur", med_price)
    return BudgetMatchNeighborhood(
        slug=row["slug"],
        name=row["name"],
        match_count=row["match_count"],
        sample_count=row["sample_count"],
        afford_pct=row["afford_pct"],
        median_price_eur=round_rent_eur(med_price)
        if request.listing_type == "rent"
        else round_sale_eur(med_price),
        median_area_sqm=round(float(row["median_area_sqm"]), 0)
        if row["median_area_sqm"] is not None
        else None,
        median_price_psm=round_rent_psm(med_psm)
        if request.listing_type == "rent" and med_psm is not None
        else round_sale_psm(med_psm)
        if med_psm is not None
        else None,
        gross_yield_pct=row["gross_yield_pct"],
        confidence=row["confidence"],  # type: ignore[arg-type]
        fit_score=row["fit_score"],
        fit_tier=row.get("fit_tier") or "good",
        budget_headroom_eur=round(float(row.get("budget_headroom_eur") or 0), 0),
        budget_headroom_pct=row.get("budget_headroom_pct"),
        area_fit_pct=row.get("area_fit_pct"),
        estimated_target_sqm=row.get("estimated_target_sqm"),
        estimated_price_eur=round_rent_eur(est_price)
        if request.listing_type == "rent"
        else round_sale_eur(est_price),
        rank=int(row.get("rank") or 0),
        summary_key=row["summary_key"],
    )


def _score_neighborhood_row(
    *,
    request: BudgetMatchRequest,
    slug: str,
    name: str,
    match_count: int,
    sample_count: int,
    median_price: float,
    median_area: float,
    median_psm: float | None,
    gross_yield_pct: float | None,
    confidence: str,
    cached: bool,
) -> dict[str, Any] | None:
    target_sqm = resolve_target_sqm(request, typical_area=median_area)
    estimated_price, psm = estimate_apartment_price(
        median_price=median_price,
        median_area=median_area,
        median_psm=median_psm,
        target_sqm=target_sqm,
    )
    segment_pricing = _uses_segment_pricing(request)
    compare_price = estimated_price if segment_pricing else median_price

    if compare_price > request.max_budget_eur * BUDGET_TOLERANCE:
        return None

    display_psm = psm or _price_psm(
        median_price=median_price, median_area=median_area, median_psm=median_psm
    )
    if display_psm is not None:
        if request.max_price_psm_eur is not None and display_psm > request.max_price_psm_eur:
            return None
        if request.min_price_psm_eur is not None and display_psm < request.min_price_psm_eur:
            return None

    afford_pct = round(100.0 * match_count / sample_count, 1) if sample_count else 0.0
    headroom_eur, headroom_pct = _headroom_pct(request.max_budget_eur, compare_price)
    area_fit = _area_fit_pct(
        median_area,
        target_sqm=target_sqm,
        min_area_sqm=request.min_area_sqm,
        max_area_sqm=request.max_area_sqm,
    )
    fit_tier = _fit_tier(
        afford_pct=afford_pct,
        match_count=match_count,
        confidence=confidence,
        headroom_pct=headroom_pct,
        compare_price=compare_price,
        budget=request.max_budget_eur,
    )
    fit_score = _composite_fit_score(
        afford_pct=afford_pct,
        match_count=match_count,
        confidence=confidence,
        headroom_pct=headroom_pct,
        area_fit_pct=area_fit,
        gross_yield_pct=gross_yield_pct,
        listing_type=request.listing_type,
    )
    return {
        "slug": slug,
        "name": name,
        "match_count": match_count,
        "sample_count": sample_count,
        "afford_pct": afford_pct,
        "median_price_eur": median_price,
        "median_area_sqm": median_area,
        "median_price_psm": psm if psm is not None else median_psm,
        "gross_yield_pct": gross_yield_pct,
        "confidence": confidence,
        "fit_score": fit_score,
        "fit_tier": fit_tier,
        "budget_headroom_eur": headroom_eur,
        "budget_headroom_pct": headroom_pct,
        "area_fit_pct": area_fit,
        "estimated_target_sqm": target_sqm if segment_pricing else None,
        "estimated_price_eur": compare_price if segment_pricing else None,
        "summary_key": _summary_key(
            fit_tier=fit_tier,
            listing_type=request.listing_type,
            gross_yield_pct=gross_yield_pct,
            match_count=match_count,
            cached=cached,
            segment_pricing=segment_pricing,
        ),
    }


def match_neighborhoods_from_dataframe(
    df: pd.DataFrame,
    request: BudgetMatchRequest,
    *,
    slug_by_name: dict[str, str] | None = None,
) -> list[BudgetMatchNeighborhood]:
    if df.empty:
        return []

    filtered, price_col = _apply_filters(
        df,
        listing_type=request.listing_type,
        bedrooms=request.bedrooms,
    )
    if filtered.empty:
        return []

    slug_map = slug_by_name or {}
    psm_col = "price_per_sqm" if request.listing_type == "sale" else None
    rows: list[dict[str, Any]] = []

    for nh_name, _nh_filtered in filtered.groupby("neighborhood", sort=False):
        slug = slug_map.get(str(nh_name))
        if not slug:
            continue
        nh_beds = filtered[filtered["neighborhood"] == nh_name]
        nh_segment = _listings_in_area_band(
            nh_beds,
            min_area_sqm=request.min_area_sqm,
            max_area_sqm=request.max_area_sqm,
        )
        pricing_pool = nh_segment if len(nh_segment) >= MIN_MATCH_LISTINGS else nh_beds
        sample_n = len(pricing_pool)
        if sample_n < MIN_MATCH_LISTINGS:
            continue
        in_budget = pricing_pool[pricing_pool[price_col] <= request.max_budget_eur]
        match_n = len(in_budget)
        if match_n < MIN_MATCH_LISTINGS and _uses_segment_pricing(request):
            in_budget = nh_beds[nh_beds[price_col] <= request.max_budget_eur]
            match_n = len(in_budget)
        if match_n < MIN_MATCH_LISTINGS:
            continue

        median_price = float(in_budget[price_col].median())
        median_area = float(pricing_pool["area_sqm"].median())
        median_psm = None
        if request.listing_type == "sale" and psm_col:
            psm_series = (pricing_pool[price_col] / pricing_pool["area_sqm"]).dropna()
            if not psm_series.empty:
                median_psm = float(psm_series.median())
        elif request.listing_type == "rent":
            rent_psm = (pricing_pool["rent_price"] / pricing_pool["area_sqm"]).dropna()
            if not rent_psm.empty:
                median_psm = float(rent_psm.median())

        nh_full = df[df["neighborhood"] == nh_name]
        gross_yield = _yield_for_neighborhood(nh_full, listing_type=request.listing_type)
        row = _score_neighborhood_row(
            request=request,
            slug=slug,
            name=str(nh_name),
            match_count=match_n,
            sample_count=sample_n,
            median_price=median_price,
            median_area=median_area,
            median_psm=median_psm,
            gross_yield_pct=gross_yield,
            confidence=confidence_level(match_n),
            cached=False,
        )
        if row:
            rows.append(row)

    rows.sort(
        key=lambda r: (-r["fit_score"], -r["budget_headroom_pct"], -r["match_count"], r["name"])
    )
    out: list[BudgetMatchNeighborhood] = []
    for rank, row in enumerate(rows[: request.top_n], start=1):
        row["rank"] = rank
        out.append(_row_to_neighborhood(row, request))
    return out


def _passes_cached_profile(
    *,
    typical_area: float | None,
    typical_beds: int | None,
    bedrooms: int | None,
) -> bool:
    return not (bedrooms is not None and typical_beds is not None and typical_beds < bedrooms)


def _match_from_lookup_cache(request: BudgetMatchRequest) -> list[BudgetMatchNeighborhood]:
    from groundtruth.services.lookup_cache import (
        cache_is_loaded,
        get_cached_lookup,
        get_cached_markets,
    )

    if not cache_is_loaded():
        return []

    rows: list[dict[str, Any]] = []
    for summary in get_cached_markets():
        lookup = get_cached_lookup("neighborhood", summary.slug)
        if not lookup:
            continue
        pulse = lookup.pulse
        if not _passes_cached_profile(
            typical_area=pulse.typical_area_sqm,
            typical_beds=pulse.typical_bedrooms,
            bedrooms=request.bedrooms,
        ):
            continue

        if request.listing_type == "rent":
            med = summary.median_rent_eur or pulse.median_rent_eur
            n = summary.rent_listings
            med_psm = summary.median_rent_psm_eur or pulse.average_rent_psm_eur
        else:
            med = pulse.median_sale_eur
            n = summary.sale_listings
            med_psm = pulse.average_sale_psm_eur

        if med is None or n < MIN_MATCH_LISTINGS:
            continue

        med_f = float(med)
        typical_area = float(pulse.typical_area_sqm or resolve_target_sqm(request))
        row = _score_neighborhood_row(
            request=request,
            slug=summary.slug,
            name=summary.name,
            match_count=n,
            sample_count=n,
            median_price=med_f,
            median_area=typical_area,
            median_psm=float(med_psm) if med_psm is not None else None,
            gross_yield_pct=None,
            confidence=summary.confidence,
            cached=True,
        )
        if row:
            rows.append(row)

    rows.sort(
        key=lambda r: (-r["fit_score"], -r["budget_headroom_pct"], -r["match_count"], r["name"])
    )
    out: list[BudgetMatchNeighborhood] = []
    for rank, row in enumerate(rows[: request.top_n], start=1):
        row["rank"] = rank
        out.append(_row_to_neighborhood(row, request))
    return out


def budget_match(session: Session, request: BudgetMatchRequest) -> BudgetMatchResponse:
    neighborhoods: list[BudgetMatchNeighborhood] = []
    cached = False
    degraded = False
    try:
        df = active_corpus_dataframe(session)
        slug_by_name = {n.name: n.slug for n in session.query(Neighborhood).all() if n.slug}
        neighborhoods = match_neighborhoods_from_dataframe(df, request, slug_by_name=slug_by_name)
    except Exception:
        logger.exception("budget_match_database_error")
        degraded = True
        neighborhoods = []

    if not neighborhoods:
        neighborhoods = _match_from_lookup_cache(request)
        cached = bool(neighborhoods)

    total_matches = sum(n.match_count for n in neighborhoods)
    return BudgetMatchResponse(
        listing_type=request.listing_type,
        max_budget_eur=request.max_budget_eur,
        min_area_sqm=request.min_area_sqm,
        max_area_sqm=request.max_area_sqm,
        min_price_psm_eur=request.min_price_psm_eur,
        max_price_psm_eur=request.max_price_psm_eur,
        bedrooms=request.bedrooms,
        neighborhoods=neighborhoods,
        total_matches=total_matches,
        cached=cached,
        degraded=degraded,
        degradation_reason="database_unavailable" if degraded else None,
    )
