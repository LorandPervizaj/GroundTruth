"""Market lookup assembly — neighborhood, district, street, complex."""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from urllib.parse import urlsplit

import pandas as pd
from sqlalchemy import text
from sqlalchemy.orm import Session, joinedload

from groundtruth.analytics.annual_export import corpus_last_updated
from groundtruth.analytics.corpus import (
    active_corpus_bundle,
    active_corpus_dataframe,
    bedroom_label,
)
from groundtruth.analytics.corpus_filters import (
    ACTIVE_CORPUS_WHERE,
    EFFECTIVE_LISTING_DATE_SQL,
    active_corpus_sql_params,
    source_display_name,
)
from groundtruth.analytics.display_rounding import (
    round_area,
    round_rent_eur,
    round_rent_psm,
    round_sale_eur,
    round_sale_psm,
)
from groundtruth.analytics.geocode_boundary import (
    corpus_geocode_stats,
    neighborhood_geocode_summary,
)
from groundtruth.analytics.listing_health import listing_health_signals, segment_health_summary
from groundtruth.analytics.listing_lifecycle import (
    lifecycle_lookup_map,
    median_days_on_market,
    segment_days_on_market,
)
from groundtruth.analytics.market_history import (
    DEFAULT_HISTORY_MONTHS,
    biweekly_points_from_observations,
    load_entity_observations,
)
from groundtruth.analytics.market_metrics import (
    median_rent_psm,
    median_sale_psm,
    rent_psm_series,
    sale_psm_series,
    sane_rent_rows,
    sane_sale_rows,
)
from groundtruth.analytics.metrics.price import price_percentiles as _compute_percentiles
from groundtruth.analytics.price_histogram import segment_price_distribution
from groundtruth.analytics.sample_confidence import (
    MetricEvidence,
    confidence_level,
    metric_confidence,
    metric_evidence_payload,
    sample_meta,
)
from groundtruth.analytics.valuation import MIN_COMPARABLES
from groundtruth.datasets.manifest import (
    frozen_at,
    frozen_dataset_fingerprint,
    frozen_dataset_version,
    manifest_quality,
)
from groundtruth.gazetteers.canonical import (
    canonical_neighborhood_meta,
    resolve_neighborhood_slug,
    slugs_for_canonical,
)
from groundtruth.models.reference import Complex, District, Neighborhood, Street
from groundtruth.schemas.lookup import (
    BedroomBreakdown,
    ChildEntity,
    CityComparison,
    CompareNeighborhood,
    CompareResponse,
    CorpusMeta,
    GeoSummary,
    HistoryPoint,
    ListingHealthSummary,
    MarketHistory,
    MarketLookup,
    MarketPulse,
    MetricSample,
    MetricValue,
    NeighborhoodMarketSummary,
    ParentEntity,
    PriceDistribution,
    PricePercentiles,
    PropertyTypeMarket,
    RecentListing,
    RelatedEntity,
    SizeBreakdown,
)

EntityTypeLit = Literal["neighborhood", "district", "street", "complex"]

_APARTMENT_PROPERTY_TYPES = frozenset({"APARTMENT", "STUDIO"})

_SALE_PROPERTY_GROUPS: list[tuple[str, str, frozenset[str]]] = [
    ("apartment", "Apartments", frozenset({"APARTMENT", "STUDIO"})),
    ("house", "Houses", frozenset({"HOUSE", "VILLA"})),
    ("land", "Land", frozenset({"LAND"})),
    ("commercial", "Commercial", frozenset({"COMMERCIAL"})),
]

SIZE_BANDS: list[tuple[str, str, float, float]] = [
    ("0-50", "0–50 m²", 0, 50),
    ("50-70", "50–70 m²", 50, 70),
    ("70-90", "70–90 m²", 70, 90),
    ("90-120", "90–120 m²", 90, 120),
    ("120+", "120+ m²", 120, 10_000),
]

_ENTITY_CONFIG: dict[EntityTypeLit, tuple[str, str]] = {
    "neighborhood": ("neighborhood_id", "neighborhood"),
    "district": ("district_id", "district"),
    "street": ("street_id", "street"),
    "complex": ("complex_id", "complex"),
}

_MIN_CHILD_LISTINGS = 5


def _source_diversity_multiplier() -> float:
    """Load cached source-skew penalty from last weekly analytics run."""
    from groundtruth.analytics.source_skew import source_diversity_penalty
    from groundtruth.config import get_settings

    skew_path = get_settings().reports_generated_dir / "source_skew.json"
    if not skew_path.is_file():
        return 1.0
    try:
        import json

        data = json.loads(skew_path.read_text(encoding="utf-8"))
        return source_diversity_penalty(data.get("shares") or {})
    except Exception:
        return 1.0


def _metric_sample(n: int) -> MetricSample:
    meta = sample_meta(n, source_diversity=_source_diversity_multiplier())
    return MetricSample(n=meta["n"], confidence=meta["confidence"])  # type: ignore[arg-type]


def _entity_centroid(entity_type: EntityTypeLit, entity) -> tuple[float | None, float | None]:
    if entity_type == "neighborhood":
        return entity.centroid_lat, entity.centroid_lng
    nh = getattr(entity, "neighborhood", None)
    if nh:
        return nh.centroid_lat, nh.centroid_lng
    return None, None


def _segment_geo_summary(
    session: Session,
    neighborhood_ids: list[int],
    *,
    centroid_lat: float | None,
    centroid_lng: float | None,
) -> GeoSummary | None:
    if not neighborhood_ids:
        return None
    raw = neighborhood_geocode_summary(
        session,
        neighborhood_ids,
        centroid_lat=centroid_lat,
        centroid_lng=centroid_lng,
    )
    if raw["listings_with_coords"] == 0 and centroid_lat is None:
        return None
    return GeoSummary.model_validate(raw)


def _segment_listing_health(
    segment: pd.DataFrame,
    lifecycle_map: dict,
) -> ListingHealthSummary | None:
    if segment.empty or not lifecycle_map:
        return None
    entries: list[dict] = []
    for row in segment.itertuples(index=False):
        key = (str(row.source_website), str(row.source_listing_id))
        life = lifecycle_map.get(key)
        if life:
            entries.append(life)
    if not entries:
        return None
    return ListingHealthSummary.model_validate(segment_health_summary(entries))


def _assign_size_band(area: float | None) -> str | None:
    if area is None or (isinstance(area, float) and pd.isna(area)):
        return None
    for band_id, _, lo, hi in SIZE_BANDS:
        if lo <= area < hi:
            return band_id
    return None


def _segment_df(df: pd.DataFrame, entity_type: EntityTypeLit, entity_id: int) -> pd.DataFrame:
    col, _ = _ENTITY_CONFIG[entity_type]
    return df[df[col] == entity_id].copy()


def _canonical_neighborhood_ids(session: Session, canonical_slug: str) -> list[int]:
    slugs = set(slugs_for_canonical(canonical_slug))
    rows = (
        session.query(Neighborhood.id, Neighborhood.slug).filter(Neighborhood.slug.in_(slugs)).all()
    )
    return [int(row.id) for row in rows]


def _segment_df_neighborhood(
    df: pd.DataFrame, session: Session, canonical_slug: str
) -> pd.DataFrame:
    ids = _canonical_neighborhood_ids(session, canonical_slug)
    if not ids:
        return pd.DataFrame()
    return df[df["neighborhood_id"].isin(ids)].copy()


def _apartment_market_df(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    ptype = df["property_type"].fillna("APARTMENT").astype(str).str.upper()
    return df[ptype.isin(_APARTMENT_PROPERTY_TYPES)].copy()


def _sale_by_property_type_breakdown(segment: pd.DataFrame) -> list[PropertyTypeMarket]:
    if segment.empty:
        return []
    sale = segment[segment["listing_type"] == "sale"]
    if sale.empty:
        return []
    ptype = sale["property_type"].fillna("APARTMENT").astype(str).str.upper()
    rows: list[PropertyTypeMarket] = []
    covered: set[str] = set()
    for key, label, types in _SALE_PROPERTY_GROUPS:
        group = sale[ptype.isin(types)]
        covered.update(types)
        if group.empty:
            continue
        psm = sale_psm_series(group)
        areas = group["area_sqm"].dropna()
        n = len(group)
        rows.append(
            PropertyTypeMarket(
                property_type=key,  # type: ignore[arg-type]
                label=label,
                average_sale_psm_eur=median_sale_psm(psm),
                median_sale_psm_eur=median_sale_psm(psm),
                median_sale_eur=round_sale_eur(group["sale_price"].median()),
                median_area_sqm=round_area(areas.median() if not areas.empty else None),
                listings=n,
                confidence=confidence_level(n),  # type: ignore[arg-type]
            )
        )
    other = sale[~ptype.isin(covered)]
    if not other.empty:
        psm = sale_psm_series(other)
        areas = other["area_sqm"].dropna()
        n = len(other)
        rows.append(
            PropertyTypeMarket(
                property_type="other",
                label="Other",
                average_sale_psm_eur=median_sale_psm(psm),
                median_sale_psm_eur=median_sale_psm(psm),
                median_sale_eur=round_sale_eur(other["sale_price"].median()),
                median_area_sqm=round_area(areas.median() if not areas.empty else None),
                listings=n,
                confidence=confidence_level(n),  # type: ignore[arg-type]
            )
        )
    return rows


def _observation_count(session: Session, entity_type: EntityTypeLit, entity_id: int) -> int:
    col = _ENTITY_CONFIG[entity_type][0]
    sql = text(
        f"""
        SELECT COUNT(*)
        FROM listing_observations lo
        JOIN normalized_listings nl ON nl.id = lo.normalized_listing_id
        WHERE nl.{col} = :entity_id
        """
    )
    return int(session.execute(sql, {"entity_id": entity_id}).scalar() or 0)


def _observation_count_neighborhood(session: Session, canonical_slug: str) -> int:
    ids = _canonical_neighborhood_ids(session, canonical_slug)
    if not ids:
        return 0
    sql = text(
        """
        SELECT COUNT(*)
        FROM listing_observations lo
        JOIN normalized_listings nl ON nl.id = lo.normalized_listing_id
        WHERE nl.neighborhood_id = ANY(:entity_ids)
        """
    )
    return int(session.execute(sql, {"entity_ids": ids}).scalar() or 0)


def _build_pulse(
    segment: pd.DataFrame,
    observations: int,
    *,
    inventory_count: int | None = None,
    last_updated: datetime | None = None,
    lifecycle_map: dict | None = None,
) -> MarketPulse:
    sale = segment[segment["listing_type"] == "sale"]
    rent = segment[segment["listing_type"] == "rent"]
    metric_n = len(segment)
    n_inventory = inventory_count if inventory_count is not None else metric_n
    confidence_n = len(rent) if not rent.empty else metric_n
    areas = segment["area_sqm"].dropna()
    beds = segment["bedrooms"].dropna()
    sale_psm = sale_psm_series(sale) if not sale.empty else pd.Series(dtype=float)
    rent_psm = rent_psm_series(rent) if not rent.empty else pd.Series(dtype=float)
    sane_rent = sane_rent_rows(rent) if not rent.empty else rent
    sane_sale = sane_sale_rows(sale) if not sale.empty else sale
    sale_with_price = (
        sane_sale[sane_sale["sale_price"].notna()] if not sane_sale.empty else sane_sale
    )
    rent_with_price = (
        sane_rent[sane_rent["rent_price"].notna()] if not sane_rent.empty else sane_rent
    )
    dom_median, dom_n, dom_conf = segment_days_on_market(segment, lifecycle_map or {})
    sale_psm_value = median_sale_psm(sale_psm)
    rent_psm_value = median_rent_psm(rent_psm)
    median_sale_value = round_sale_eur(
        sane_sale["sale_price"].median() if not sane_sale.empty else None
    )
    median_rent_value = round_rent_eur(
        sane_rent["rent_price"].median() if not sane_rent.empty else None
    )
    metric_specs = {
        "median_sale_psm": (sale_psm_value, "EUR_PER_M2", len(sale_psm), "recent.sale.apartment_studio", sale),
        "median_rent_psm": (rent_psm_value, "EUR_PER_M2_MONTH", len(rent_psm), "recent.rent.apartment_studio", rent),
        "median_sale_eur": (median_sale_value, "EUR", len(sale_with_price), "recent.sale.apartment_studio", sale_with_price),
        "median_rent_eur": (median_rent_value, "EUR_MONTH", len(rent_with_price), "recent.rent.apartment_studio", rent_with_price),
    }
    metrics = {}
    for metric_id, (value, unit, sample_n, population, evidence_df) in metric_specs.items():
        source_counts = evidence_df["source_website"].value_counts() if not evidence_df.empty else pd.Series(dtype=int)
        evidence = MetricEvidence(
            sample_n=sample_n,
            source_count=int(len(source_counts)),
            freshness_days=0,
            largest_source_share_pct=(
                round(100.0 * float(source_counts.iloc[0]) / sample_n, 2)
                if sample_n and len(source_counts)
                else None
            ),
        )
        metrics[metric_id] = MetricValue(
            value=value,
            statistic="median",
            unit=unit,
            sample_n=sample_n,
            population=population,
            confidence=metric_confidence(evidence),
            window={"days": 365},
            as_of=last_updated,
            evidence=metric_evidence_payload(evidence),
        )
    return MarketPulse(
        average_sale_psm_eur=sale_psm_value,
        average_rent_psm_eur=rent_psm_value,
        median_sale_psm_eur=sale_psm_value,
        median_rent_psm_eur=rent_psm_value,
        median_sale_eur=median_sale_value,
        median_rent_eur=median_rent_value,
        typical_area_sqm=round_area(areas.median() if not areas.empty else None),
        typical_bedrooms=int(beds.median()) if not beds.empty else None,
        active_listings=n_inventory,
        recent_valid_listings=n_inventory,
        observations=observations or n_inventory,
        data_sources=[],
        confidence=confidence_level(confidence_n),  # type: ignore[arg-type]
        sale_psm_sample=_metric_sample(len(sale_psm)),
        rent_psm_sample=_metric_sample(len(rent_psm)),
        median_sale_sample=_metric_sample(len(sale_with_price)),
        median_rent_sample=_metric_sample(len(rent_with_price)),
        median_days_on_market=dom_median,
        days_on_market_sample=MetricSample(n=dom_n, confidence=dom_conf),  # type: ignore[arg-type]
        last_updated=last_updated,
        metrics=metrics,
    )


_PRICE_TIER_LABELS = ("$", "$$", "$$$", "$$$$")


def _build_price_percentiles(apartment_segment: pd.DataFrame) -> PricePercentiles | None:
    """10th / 50th / 90th percentile of sale €/m²."""
    sale = (
        apartment_segment[apartment_segment["listing_type"] == "sale"]
        if not apartment_segment.empty
        else apartment_segment
    )
    psm = sale_psm_series(sale) if not sale.empty else pd.Series(dtype=float)
    if psm.empty:
        return None
    pcts = _compute_percentiles(psm)
    return PricePercentiles(
        p10_sale_psm=pcts.get("p10"),
        p50_sale_psm=pcts.get("p50"),
        p90_sale_psm=pcts.get("p90"),
        n=len(psm),
    )


def _build_city_comparison(
    apartment_segment: pd.DataFrame,
    full_df: pd.DataFrame,
) -> CityComparison | None:
    """Neighborhood sale €/m² and rent vs city-wide medians, with tier."""
    if full_df.empty or apartment_segment.empty:
        return None

    # City-wide medians (all apartments)
    city_apt = full_df.copy()
    ptype = city_apt["property_type"].fillna("APARTMENT").astype(str).str.upper()
    city_apt = city_apt[ptype.isin(_APARTMENT_PROPERTY_TYPES)]
    if city_apt.empty:
        return None

    city_sale = city_apt[city_apt["listing_type"] == "sale"]
    city_rent = city_apt[city_apt["listing_type"] == "rent"]
    city_sale_psm = sale_psm_series(city_sale) if not city_sale.empty else pd.Series(dtype=float)
    city_rent_prices = (
        sane_rent_rows(city_rent)["rent_price"] if not city_rent.empty else pd.Series(dtype=float)
    )

    city_median_sale = median_sale_psm(city_sale_psm)
    city_median_rent = (
        round_rent_eur(city_rent_prices.median()) if not city_rent_prices.empty else None
    )

    # Neighborhood medians
    nh_sale = apartment_segment[apartment_segment["listing_type"] == "sale"]
    nh_rent = apartment_segment[apartment_segment["listing_type"] == "rent"]
    nh_sale_psm = sale_psm_series(nh_sale) if not nh_sale.empty else pd.Series(dtype=float)
    nh_rent_sane = sane_rent_rows(nh_rent) if not nh_rent.empty else nh_rent

    nh_median_sale = median_sale_psm(nh_sale_psm)
    nh_median_rent = (
        round_rent_eur(nh_rent_sane["rent_price"].median()) if not nh_rent_sane.empty else None
    )

    # Premium %
    premium_pct = None
    if city_median_sale and nh_median_sale and city_median_sale > 0:
        premium_pct = round(((nh_median_sale - city_median_sale) / city_median_sale) * 100, 1)

    # Price tier via city-wide quartiles
    tier = "$$"
    if not city_sale_psm.empty and nh_median_sale is not None:
        q25 = city_sale_psm.quantile(0.25)
        q50 = city_sale_psm.quantile(0.50)
        q75 = city_sale_psm.quantile(0.75)
        if nh_median_sale < q25:
            tier = "$"
        elif nh_median_sale < q50:
            tier = "$$"
        elif nh_median_sale < q75:
            tier = "$$$"
        else:
            tier = "$$$$"

    return CityComparison(
        city_median_sale_psm=city_median_sale,
        city_median_rent=city_median_rent,
        neighborhood_sale_psm=nh_median_sale,
        neighborhood_rent=nh_median_rent,
        premium_pct=premium_pct,
        price_tier=tier,  # type: ignore[arg-type]
    )


def get_corpus_meta(session: Session) -> CorpusMeta:
    bundle = active_corpus_bundle(session)
    raw_df = bundle.deduped
    df = bundle.active
    quality = manifest_quality()
    frozen = frozen_at()
    if raw_df.empty:
        return CorpusMeta(
            corpus_updated_at=corpus_last_updated(session),
            active_listings=0,
            active_listings_confidence="insufficient",
            raw_listings=0,
            cross_portal_duplicates_removed=0,
            cross_portal_duplicate_groups=0,
            median_days_on_market=median_days_on_market(session),
            data_sources=[],
            source_count=0,
            geocode_coverage_pct=None,
            geocode_mismatch_pct=None,
            dataset_version=frozen_dataset_version(),
            dataset_frozen_at=frozen,
            dataset_fingerprint=frozen_dataset_fingerprint(),
            invalid_pct=quality.get("invalid_pct"),
            golden_accuracy_pct=quality.get("golden_accuracy_pct"),
            public_product_scope=str(quality.get("public_product_scope") or "rent_and_sale"),
        )

    raw_count = len(raw_df)
    active_count = len(df)
    geo = corpus_geocode_stats(session)
    return CorpusMeta(
        corpus_updated_at=corpus_last_updated(session),
        active_listings=active_count,
        active_listings_confidence=confidence_level(active_count),  # type: ignore[arg-type]
        raw_listings=raw_count,
        cross_portal_duplicates_removed=raw_count - active_count,
        cross_portal_duplicate_groups=bundle.cross_portal_groups,
        median_days_on_market=median_days_on_market(session),
        data_sources=[],
        source_count=0,
        geocode_coverage_pct=geo.get("coverage_pct"),  # type: ignore[arg-type]
        geocode_mismatch_pct=geo.get("mismatch_pct"),  # type: ignore[arg-type]
        dataset_version=frozen_dataset_version(),
        dataset_frozen_at=frozen,
        dataset_fingerprint=frozen_dataset_fingerprint(),
        invalid_pct=quality.get("invalid_pct"),
        golden_accuracy_pct=quality.get("golden_accuracy_pct"),
        public_product_scope=str(quality.get("public_product_scope") or "rent_and_sale"),
    )


def _bedroom_bucket(bedrooms: object) -> int | None:
    if bedrooms is None or (isinstance(bedrooms, float) and pd.isna(bedrooms)):
        return None
    beds = int(bedrooms)
    if beds < 0:
        return None
    return min(beds, 4)


def _bedroom_breakdown(segment: pd.DataFrame) -> list[BedroomBreakdown]:
    rows: list[BedroomBreakdown] = []
    work = segment.copy()
    work["bedroom_bucket"] = work["bedrooms"].apply(_bedroom_bucket)
    work = work[work["bedroom_bucket"].notna()]
    for beds, group in work.groupby("bedroom_bucket", sort=True):
        bucket = int(beds)
        sale = group[group["listing_type"] == "sale"]
        rent = group[group["listing_type"] == "rent"]
        sane_rent = sane_rent_rows(rent)
        sane_sale = sane_sale_rows(sale)
        n = len(group)
        rows.append(
            BedroomBreakdown(
                bedrooms=bucket,
                label=bedroom_label(bucket),
                average_sale_psm_eur=median_sale_psm(sale_psm_series(sale)),
                average_rent_psm_eur=median_rent_psm(rent_psm_series(rent)),
                median_sale_psm_eur=median_sale_psm(sale_psm_series(sale)),
                median_rent_psm_eur=median_rent_psm(rent_psm_series(rent)),
                median_sale_eur=round_sale_eur(
                    sane_sale["sale_price"].median() if not sane_sale.empty else None
                ),
                median_rent_eur=round_rent_eur(
                    sane_rent["rent_price"].median() if not sane_rent.empty else None
                ),
                listings=n,
                sale_sample_n=len(sale_psm_series(sale)),
                rent_sample_n=len(sane_rent),
                union_sample_n=n,
                confidence=confidence_level(n),  # type: ignore[arg-type]
                sale_confidence=confidence_level(len(sale_psm_series(sale))),  # type: ignore[arg-type]
                rent_confidence=confidence_level(len(sane_rent)),  # type: ignore[arg-type]
            )
        )
    return sorted(rows, key=lambda r: r.bedrooms)


def _size_breakdown(segment: pd.DataFrame) -> list[SizeBreakdown]:
    rows: list[SizeBreakdown] = []
    work = segment.copy()
    work["size_band"] = work["area_sqm"].apply(_assign_size_band)
    for band_id, label, _, _ in SIZE_BANDS:
        group = work[work["size_band"] == band_id]
        if group.empty:
            continue
        sale = group[group["listing_type"] == "sale"]
        rent = group[group["listing_type"] == "rent"]
        sane_rent = sane_rent_rows(rent)
        sane_sale = sane_sale_rows(sale)
        n = len(group)
        rows.append(
            SizeBreakdown(
                size_band=band_id,
                label=label,
                average_sale_psm_eur=median_sale_psm(sale_psm_series(sale)),
                average_rent_psm_eur=median_rent_psm(rent_psm_series(rent)),
                median_sale_psm_eur=median_sale_psm(sale_psm_series(sale)),
                median_rent_psm_eur=median_rent_psm(rent_psm_series(rent)),
                median_sale_eur=round_sale_eur(
                    sane_sale["sale_price"].median() if not sane_sale.empty else None
                ),
                median_rent_eur=round_rent_eur(
                    sane_rent["rent_price"].median() if not sane_rent.empty else None
                ),
                listings=n,
                sale_sample_n=len(sale_psm_series(sale)),
                rent_sample_n=len(sane_rent),
                union_sample_n=n,
                confidence=confidence_level(n),  # type: ignore[arg-type]
                sale_confidence=confidence_level(len(sale_psm_series(sale))),  # type: ignore[arg-type]
                rent_confidence=confidence_level(len(sane_rent)),  # type: ignore[arg-type]
            )
        )
    return rows


_RECENT_SOURCE_ORDER = ("gjirafa", "merrjep", "pro-rks", "vision", "topia", "myrealestate")
_RECENT_PER_SOURCE_POOL = 40


def _within_source_diversity_key(listing: RecentListing) -> str:
    band = _assign_size_band(listing.area_sqm) if listing.area_sqm is not None else "unknown"
    ptype = listing.property_type or "other"
    return f"{listing.listing_type}|{ptype}|{band}"


def _pick_from_source_pool(
    pool: list[RecentListing],
    count: int,
    seen: set[tuple[str, str]],
) -> list[RecentListing]:
    if count <= 0 or not pool:
        return []

    buckets: dict[str, list[RecentListing]] = {}
    for item in pool:
        buckets.setdefault(_within_source_diversity_key(item), []).append(item)

    picked: list[RecentListing] = []
    while buckets and len(picked) < count:
        progressed = False
        for key in sorted(buckets):
            stack = buckets.get(key) or []
            while stack:
                item = stack.pop(0)
                uid = (item.source, item.source_listing_id)
                if uid in seen:
                    continue
                seen.add(uid)
                picked.append(item)
                progressed = True
                if len(picked) >= count:
                    break
            if not stack:
                buckets.pop(key, None)
            if len(picked) >= count:
                break
        if not progressed:
            break

    if len(picked) < count:
        for item in pool:
            uid = (item.source, item.source_listing_id)
            if uid in seen:
                continue
            seen.add(uid)
            picked.append(item)
            if len(picked) >= count:
                break
    return picked


def _source_quotas(sources: list[str], limit: int) -> dict[str, int]:
    if not sources:
        return {}
    base = limit // len(sources)
    remainder = limit % len(sources)
    quotas = {source: base for source in sources}
    for source in sources[:remainder]:
        quotas[source] += 1
    return quotas


def _interleave_by_source(
    by_source: dict[str, list[RecentListing]],
    sources: list[str],
    limit: int,
) -> list[RecentListing]:
    stacks = {source: list(by_source.get(source) or []) for source in sources}
    interleaved: list[RecentListing] = []
    while len(interleaved) < limit:
        progressed = False
        for source in sources:
            stack = stacks.get(source) or []
            if not stack:
                continue
            interleaved.append(stack.pop(0))
            progressed = True
            if len(interleaved) >= limit:
                break
        if not progressed:
            break
    return interleaved


def _pick_diverse_recent(candidates: list[RecentListing], limit: int = 10) -> list[RecentListing]:
    """~Equal slots per portal, then mix rent/sale and segments within each source."""
    if not candidates:
        return []

    by_source: dict[str, list[RecentListing]] = {}
    for item in candidates:
        by_source.setdefault(item.source, []).append(item)

    sources = [s for s in _RECENT_SOURCE_ORDER if s in by_source]
    sources.extend(sorted(s for s in by_source if s not in sources))

    quotas = _source_quotas(sources, limit)
    seen: set[tuple[str, str]] = set()
    picked_by_source: dict[str, list[RecentListing]] = {}

    for source in sources:
        picked_by_source[source] = _pick_from_source_pool(
            by_source[source],
            quotas[source],
            seen,
        )

    shortfall = limit - sum(len(rows) for rows in picked_by_source.values())
    if shortfall > 0:
        for source in sources:
            if shortfall <= 0:
                break
            extra = _pick_from_source_pool(by_source[source], shortfall, seen)
            if extra:
                picked_by_source.setdefault(source, []).extend(extra)
                shortfall -= len(extra)

    return _interleave_by_source(picked_by_source, sources, limit)


def _safe_public_listing_url(value: object) -> str | None:
    """Allow only browser-safe HTTP(S) listing links in public responses."""
    candidate = str(value or "").strip()
    try:
        parsed = urlsplit(candidate)
    except ValueError:
        return None
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.netloc:
        return None
    if parsed.username or parsed.password:
        return None
    return candidate


def _recent_listings(
    session: Session,
    entity_type: EntityTypeLit,
    entity_id: int,
    *,
    neighborhood_ids: list[int] | None = None,
    lifecycle_map: dict | None = None,
) -> list[RecentListing]:
    col = _ENTITY_CONFIG[entity_type][0]
    if entity_type == "neighborhood" and neighborhood_ids:
        entity_filter = "nl.neighborhood_id = ANY(:entity_ids)"
        entity_param_key = "entity_ids"
        entity_param_val: object = neighborhood_ids
    else:
        entity_filter = f"nl.{col} = :entity_id"
        entity_param_key = "entity_id"
        entity_param_val = entity_id
    sql = text(
        f"""
        WITH deduped AS (
            SELECT DISTINCT ON (nl.source_website, nl.source_listing_id)
                nl.source_website,
                nl.source_listing_id,
                nl.original_url,
                nl.listing_type::text AS listing_type,
                nl.property_type::text AS property_type,
                nl.sale_price::float AS sale_price,
                nl.rent_price::float AS rent_price,
                nl.price_per_sqm::float AS price_per_sqm,
                nl.area_sqm,
                nl.bedrooms,
                {EFFECTIVE_LISTING_DATE_SQL} AS listing_date,
                nl.scraped_at,
                nl.id
            FROM normalized_listings nl
            WHERE {entity_filter}
            {ACTIVE_CORPUS_WHERE}
            ORDER BY nl.source_website, nl.source_listing_id, nl.id DESC
        ),
        ranked AS (
            SELECT
                deduped.*,
                ROW_NUMBER() OVER (
                    PARTITION BY deduped.source_website
                    ORDER BY deduped.listing_date DESC NULLS LAST, deduped.id DESC
                ) AS source_rank
            FROM deduped
        )
        SELECT *
        FROM ranked
        WHERE source_rank <= :per_source_limit
        ORDER BY listing_date DESC NULLS LAST, id DESC
        """
    )
    params = {
        entity_param_key: entity_param_val,
        "per_source_limit": _RECENT_PER_SOURCE_POOL,
        **active_corpus_sql_params(),
    }
    parsed: list[RecentListing] = []
    for row in session.execute(sql, params).mappings().all():
        is_rent = str(row["listing_type"]).lower() == "rent"
        price = row["rent_price"] if is_rent else row["sale_price"]
        if price is None:
            continue
        public_url = _safe_public_listing_url(row["original_url"])
        if public_url is None:
            continue
        # Do not expose third-party brand domains in the public UI/API.
        public_url = ""

        key = (str(row["source_website"]), str(row["source_listing_id"]))
        life = (lifecycle_map or {}).get(key, {})
        last_seen = life.get("last_seen") or (
            row["listing_date"].isoformat()
            if row.get("listing_date")
            else (row["scraped_at"].date().isoformat() if row["scraped_at"] else None)
        )
        dom = life.get("days_on_market")
        price_changed = life.get("price_changed")
        obs_count = life.get("observation_count")
        parsed.append(
            RecentListing(
                source=source_display_name(str(row["source_website"])),
                source_listing_id=row["source_listing_id"],
                url=public_url,
                listing_type=str(row["listing_type"]).lower(),
                property_type=str(row["property_type"]).lower()
                if row.get("property_type")
                else None,
                price_eur=round_rent_eur(price) if is_rent else round_sale_eur(price),
                price_per_sqm_eur=round_sale_psm(row["price_per_sqm"]),
                area_sqm=round_area(row["area_sqm"]),
                bedrooms=int(row["bedrooms"]) if row["bedrooms"] is not None else None,
                first_seen=life.get("first_seen"),
                last_seen=last_seen,
                days_on_market=dom,
                observation_count=obs_count,
                price_changed=price_changed,
                health_signals=listing_health_signals(
                    days_on_market=dom,
                    price_changed=price_changed,
                    observation_count=obs_count,
                ),
            )
        )

    return _pick_diverse_recent(parsed, limit=10)


def _child_entities(
    session: Session,
    df: pd.DataFrame,
    entity_type: EntityTypeLit,
    entity_id: int,
    *,
    neighborhood_ids: list[int] | None = None,
) -> list[ChildEntity]:
    children: list[ChildEntity] = []
    if entity_type == "neighborhood":
        ids = neighborhood_ids or [entity_id]
        seg = df[df["neighborhood_id"].isin(ids)]
        for col, etype, model in [
            ("district_id", "district", District),
            ("complex_id", "complex", Complex),
        ]:
            counts = seg[seg[col].notna()].groupby(col).size().sort_values(ascending=False)
            for eid, count in counts.items():
                if int(count) < _MIN_CHILD_LISTINGS:
                    continue
                ent = session.get(model, int(eid))
                if ent:
                    children.append(
                        ChildEntity(
                            entity_type=etype,  # type: ignore[arg-type]
                            slug=ent.slug,
                            display_name=ent.name,
                            listings=int(count),
                        )
                    )
    elif entity_type == "district":
        seg = df[df["district_id"] == entity_id]
        counts = (
            seg[seg["complex_id"].notna()].groupby("complex_id").size().sort_values(ascending=False)
        )
        for eid, count in counts.items():
            if int(count) < _MIN_CHILD_LISTINGS:
                continue
            ent = session.get(Complex, int(eid))
            if ent:
                children.append(
                    ChildEntity(
                        entity_type="complex",
                        slug=ent.slug,
                        display_name=ent.name,
                        listings=int(count),
                    )
                )
    return children[:12]


def _related_entities(
    session: Session,
    df: pd.DataFrame,
    entity_type: EntityTypeLit,
    entity_id: int,
    neighborhood_id: int | None,
) -> list[RelatedEntity]:
    related: list[RelatedEntity] = []
    if entity_type == "neighborhood":
        return related
    if neighborhood_id:
        nh = session.get(Neighborhood, neighborhood_id)
        if nh:
            meta = canonical_neighborhood_meta(nh.slug)
            nh_ids = _canonical_neighborhood_ids(session, meta.canonical_slug)
            related.append(
                RelatedEntity(
                    entity_type="neighborhood",
                    slug=meta.canonical_slug,
                    display_name=meta.display_name,
                    listings=int(len(df[df["neighborhood_id"].isin(nh_ids)])) if nh_ids else 0,
                )
            )
    return related


def resolve_neighborhood_lookup(
    session: Session, slug: str
) -> tuple[Neighborhood | None, str | None]:
    """Resolve to canonical neighborhood; return (entity, requested_slug_if_redirected)."""
    if not session.query(Neighborhood).filter(Neighborhood.slug == slug).first():
        return None, None
    canonical_slug = resolve_neighborhood_slug(slug)
    requested = slug if canonical_slug != slug else None
    entity = session.query(Neighborhood).filter(Neighborhood.slug == canonical_slug).first()
    return entity, requested


def resolve_entity(session: Session, entity_type: EntityTypeLit, slug: str):
    if entity_type == "neighborhood":
        entity, _ = resolve_neighborhood_lookup(session, slug)
        return entity
    if entity_type == "district":
        return (
            session.query(District)
            .options(joinedload(District.neighborhood))
            .filter(District.slug == slug)
            .first()
        )
    if entity_type == "street":
        return (
            session.query(Street)
            .options(joinedload(Street.neighborhood))
            .filter(Street.slug == slug)
            .first()
        )
    return (
        session.query(Complex)
        .options(joinedload(Complex.neighborhood), joinedload(Complex.district))
        .filter(Complex.slug == slug)
        .first()
    )


def _breadcrumb_chain(entity_type: EntityTypeLit, entity) -> list[ParentEntity]:
    crumbs: list[ParentEntity] = []
    if entity_type == "complex":
        if entity.district:
            crumbs.append(
                ParentEntity(
                    entity_type="district",
                    slug=entity.district.slug,
                    display_name=entity.district.name,
                )
            )
        if entity.neighborhood:
            crumbs.insert(
                0,
                ParentEntity(
                    entity_type="neighborhood",
                    slug=entity.neighborhood.slug,
                    display_name=entity.neighborhood.name,
                ),
            )
    elif entity_type == "district":
        if entity.neighborhood:
            crumbs.append(
                ParentEntity(
                    entity_type="neighborhood",
                    slug=entity.neighborhood.slug,
                    display_name=entity.neighborhood.name,
                )
            )
    elif entity_type == "street" and entity.neighborhood:
        crumbs.append(
            ParentEntity(
                entity_type="neighborhood",
                slug=entity.neighborhood.slug,
                display_name=entity.neighborhood.name,
            )
        )
    return crumbs


def get_market_lookup(
    session: Session,
    entity_type: EntityTypeLit,
    slug: str,
    *,
    corpus_df: pd.DataFrame | None = None,
) -> MarketLookup | None:
    requested_slug: str | None = None
    also_known_as: list[str] = []

    if entity_type == "neighborhood":
        entity, requested_slug = resolve_neighborhood_lookup(session, slug)
        if entity is None:
            return None
        meta = canonical_neighborhood_meta(entity.slug)
        also_known_as = list(meta.also_known_as)
    else:
        entity = resolve_entity(session, entity_type, slug)
        if entity is None:
            return None

    df = corpus_df if corpus_df is not None else active_corpus_dataframe(session)
    if df.empty:
        df = pd.DataFrame()

    nh_ids: list[int] | None = None
    if entity_type == "neighborhood":
        nh_ids = _canonical_neighborhood_ids(session, entity.slug)
        full_segment = (
            _segment_df_neighborhood(df, session, entity.slug) if not df.empty else pd.DataFrame()
        )
        observations = _observation_count_neighborhood(session, entity.slug)
    else:
        full_segment = _segment_df(df, entity_type, entity.id) if not df.empty else pd.DataFrame()
        observations = _observation_count(session, entity_type, entity.id)

    apartment_segment = _apartment_market_df(full_segment)

    neighborhood_id: int | None = None
    city = "Prishtina"
    breadcrumb = _breadcrumb_chain(entity_type, entity)
    parent: ParentEntity | None = breadcrumb[-1] if breadcrumb else None

    if entity_type == "neighborhood":
        neighborhood_id = entity.id
        city = entity.city or city
    elif entity_type == "district" or entity_type == "street" or entity_type == "complex":
        neighborhood_id = entity.neighborhood_id
        if entity.neighborhood:
            city = entity.neighborhood.city or city

    corpus_updated = corpus_last_updated(session)
    lifecycle_keys: list[tuple[str, str]] = []
    if not apartment_segment.empty:
        lifecycle_keys = list(
            zip(
                apartment_segment["source_website"].astype(str),
                apartment_segment["source_listing_id"].astype(str),
                strict=True,
            )
        )
    lifecycle_map = lifecycle_lookup_map(session, listing_keys=lifecycle_keys)
    display_name = (
        canonical_neighborhood_meta(entity.slug).display_name
        if entity_type == "neighborhood"
        else entity.name
    )
    centroid_lat, centroid_lng = _entity_centroid(entity_type, entity)
    geo_nh_ids = nh_ids if nh_ids else ([neighborhood_id] if neighborhood_id else [])
    geo = _segment_geo_summary(
        session,
        geo_nh_ids,
        centroid_lat=centroid_lat,
        centroid_lng=centroid_lng,
    )
    sale_dist_raw = segment_price_distribution(apartment_segment, "sale")
    rent_dist_raw = segment_price_distribution(apartment_segment, "rent")
    sale_dist = (
        PriceDistribution.model_validate(sale_dist_raw) if sale_dist_raw.get("bins") else None
    )
    rent_dist = (
        PriceDistribution.model_validate(rent_dist_raw) if rent_dist_raw.get("bins") else None
    )
    listing_health = _segment_listing_health(apartment_segment, lifecycle_map)
    percentiles = _build_price_percentiles(apartment_segment)
    city_cmp = _build_city_comparison(apartment_segment, df)
    return MarketLookup(
        entity_type=entity_type,
        slug=entity.slug,
        display_name=display_name,
        also_known_as=also_known_as,
        requested_slug=requested_slug,
        city=city,
        corpus_updated_at=corpus_updated,
        pulse=_build_pulse(
            apartment_segment,
            observations,
            inventory_count=len(full_segment),
            last_updated=corpus_updated,
            lifecycle_map=lifecycle_map,
        ),
        price_percentiles=percentiles,
        city_comparison=city_cmp,
        sale_by_property_type=_sale_by_property_type_breakdown(full_segment),
        bedroom_breakdown=_bedroom_breakdown(apartment_segment),
        size_breakdown=_size_breakdown(apartment_segment),
        recent_listings=_recent_listings(
            session,
            entity_type,
            entity.id,
            neighborhood_ids=nh_ids,
            lifecycle_map=lifecycle_map,
        ),
        parent=parent,
        breadcrumb=breadcrumb,
        children=_child_entities(session, df, entity_type, entity.id, neighborhood_ids=nh_ids),
        related=_related_entities(session, df, entity_type, entity.id, neighborhood_id),
        geo=geo,
        sale_price_distribution=sale_dist,
        rent_price_distribution=rent_dist,
        listing_health=listing_health,
        dataset_version=frozen_dataset_version(),
        corpus_revision=corpus_updated.isoformat() if corpus_updated else None,
        generated_at=datetime.now().astimezone(),
        pricing_window_days=365,
        inventory_as_of=None,
        total_listings=len(full_segment),
    )


def compare_neighborhoods(session: Session, slugs: list[str]) -> CompareResponse:
    """Side-by-side pulse metrics for 2–3 neighborhoods."""
    from groundtruth.services.lookup_cache import cache_is_loaded, resolve_market_lookup

    unique: list[str] = []
    for slug in slugs:
        key = resolve_neighborhood_slug(slug.strip().lower())
        if key and key not in unique:
            unique.append(key)
    if len(unique) < 2 or len(unique) > 3:
        raise ValueError("Provide 2–3 unique neighborhood slugs")

    items: list[CompareNeighborhood] = []
    corpus_updated: datetime | None = None
    corpus_df: pd.DataFrame | None = None

    for slug in unique:
        if cache_is_loaded():
            lookup = resolve_market_lookup(session, "neighborhood", slug)
        else:
            if corpus_df is None:
                corpus_df = active_corpus_dataframe(session)
            lookup = get_market_lookup(session, "neighborhood", slug, corpus_df=corpus_df)
        if lookup is None:
            raise ValueError(f"Unknown neighborhood: {slug}")
        if corpus_updated is None:
            corpus_updated = lookup.corpus_updated_at
        items.append(
            CompareNeighborhood(
                slug=lookup.slug,
                display_name=lookup.display_name,
                pulse=lookup.pulse,
            )
        )
    return CompareResponse(neighborhoods=items, corpus_updated_at=corpus_updated)


def get_market_history(
    session: Session,
    entity_type: EntityTypeLit,
    slug: str,
    *,
    months: int = DEFAULT_HISTORY_MONTHS,
) -> MarketHistory | None:
    entity = resolve_entity(session, entity_type, slug)
    if entity is None:
        return None

    obs = load_entity_observations(session, entity_type, entity.id, months=months)
    raw_points = biweekly_points_from_observations(obs)
    points = [HistoryPoint.model_validate(p) for p in raw_points]

    return MarketHistory(
        entity_type=entity_type,
        slug=entity.slug,
        display_name=entity.name,
        months=months,
        points=points,
    )


def list_neighborhood_market_summaries(session: Session) -> list[NeighborhoodMarketSummary]:
    df = active_corpus_dataframe(session)
    if df.empty:
        return []
    neighborhoods = session.query(Neighborhood).order_by(Neighborhood.name).all()
    slug_by_id = {n.id: n.slug for n in neighborhoods}
    name_by_id = {n.id: n.name for n in neighborhoods}
    summaries: list[NeighborhoodMarketSummary] = []
    for nh_id, group in df.groupby("neighborhood_id", dropna=True):
        nh_id_int = int(nh_id)
        slug = slug_by_id.get(nh_id_int)
        name = name_by_id.get(nh_id_int)
        if not slug or not name:
            continue
        rent_group = group[group["listing_type"] == "rent"]
        sale_group = group[group["listing_type"] == "sale"]
        rent_n = len(rent_group)
        sale_n = len(sale_group)
        rent_psm = (rent_group["rent_price"] / rent_group["area_sqm"]).dropna()
        summaries.append(
            NeighborhoodMarketSummary(
                slug=slug,
                name=name,
                rent_listings=rent_n,
                sale_listings=sale_n,
                median_rent_eur=round_rent_eur(rent_group["rent_price"].median())
                if rent_n
                else None,
                median_rent_psm_eur=round_rent_psm(
                    rent_psm.median() if not rent_psm.empty else None
                ),
                confidence=confidence_level(rent_n or sale_n),  # type: ignore[arg-type]
                estimate_ready=rent_n >= MIN_COMPARABLES,
            )
        )
    summaries.sort(key=lambda s: (-(s.rent_listings + s.sale_listings), s.name))
    return summaries
