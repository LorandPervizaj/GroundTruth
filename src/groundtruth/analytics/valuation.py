"""Rule-based rent valuation engine v0.1 — Dataset v1.0 baseline."""

from __future__ import annotations

import json
import re
import threading
import time
from contextlib import suppress
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd
from rapidfuzz import fuzz
from sqlalchemy.orm import Session

from groundtruth.analytics.corpus_filters import DEFAULT_MAX_AGE_MONTHS
from groundtruth.analytics.dataset_confidence import compute_dataset_confidence
from groundtruth.analytics.display_rounding import (
    round_rent_eur,
    round_rent_psm,
    round_sale_eur,
    round_sale_psm,
)
from groundtruth.analytics.stats import (
    bootstrap_weighted_mean_ci,
    comparable_area_weights,
    weighted_average,
)
from groundtruth.config import PROJECT_ROOT
from groundtruth.datasets.manifest import frozen_dataset_version
from groundtruth.models.reference import Neighborhood
from groundtruth.schemas.valuation import (
    ComparableListing,
    ExcludedFactor,
    NegotiationAid,
    ValuationExplanation,
    ValuationRequest,
    ValuationResult,
)

RENT_MODEL_ID = "DM-002"
SALE_MODEL_ID = "DM-003"
MODEL_VERSION = "1.1.0"
AREA_WEIGHT_BANDWIDTH_M2 = 10.0
PRODUCT_VERSION = "1.0"
MIN_COMPARABLES = 30

# ---------------------------------------------------------------------------
# Bound layers (intentional, not accidental duplication)
# 1) Ingestion validity: processing/validation.py (broad sanity for corpus entry)
# 2) Active corpus: analytics/corpus_filters.py (parser/age/informal/invalid)
# 3) Valuation comparability: constants below (stricter bands so extremes
#    that passed ingestion do not distort comparable medians/estimates)
# ---------------------------------------------------------------------------
RENT_COMPARABLE_MIN_EUR = 80
RENT_COMPARABLE_MAX_EUR = 2500
RENT_COMPARABLE_MIN_AREA_SQM = 20
RENT_COMPARABLE_MAX_AREA_SQM = 200
SALE_COMPARABLE_MIN_EUR = 10_000
SALE_COMPARABLE_MAX_EUR = 500_000
SALE_COMPARABLE_MIN_AREA_SQM = 20
SALE_COMPARABLE_MAX_AREA_SQM = 200
INSUFFICIENT_EVIDENCE_MSG = (
    "There is currently insufficient evidence to produce a reliable estimate "
    "for this combination of neighborhood and apartment characteristics."
)
PARSER_ACCURACY = 0.92
MAX_COMPARABLES_SHOWN = 12
AREA_BUCKET_M2 = 5
DEFAULT_AREA_MATCH_TOLERANCE_M2 = 5.0
CONFIDENCE_CALIBRATED = False

_COMPARABLES_CACHE_TTL_SEC = 3600
_comparables_cache_lock = threading.Lock()
_comparables_cache: tuple[datetime | None, float, pd.DataFrame, pd.DataFrame] | None = None

RENT_COMPARABLES_FILE = "rent_comparables.json.gz"
SALE_COMPARABLES_FILE = "sale_comparables.json.gz"
COMPARABLES_META_FILE = "comparables_meta.json"


def _comparables_revision(session: Session) -> datetime | None:
    from groundtruth.analytics.annual_export import corpus_last_updated

    return corpus_last_updated(session)


def comparables_cache_ready() -> bool:
    with _comparables_cache_lock:
        return _comparables_cache is not None


def copy_cached_comparables_pair() -> tuple[pd.DataFrame, pd.DataFrame] | None:
    """Return in-memory comparables without touching the database."""
    with _comparables_cache_lock:
        cached = _comparables_cache
        if cached is None:
            return None
        return _normalize_comparables_pair(cached[2], cached[3])


def seed_comparables_cache(
    revision: datetime | None,
    rent_df: pd.DataFrame,
    sale_df: pd.DataFrame,
) -> None:
    """Seed in-process comparables cache (e.g. after weekly analytics build)."""
    global _comparables_cache
    now = time.monotonic()
    with _comparables_cache_lock:
        _comparables_cache = (revision, now, rent_df, sale_df)


def persist_comparables_disk_cache(
    base: Path,
    rent_df: pd.DataFrame,
    sale_df: pd.DataFrame,
    corpus_revision: str | None,
) -> None:
    """Write comparables to disk for instant API valuate (avoids ~2 min cold SQL)."""
    base.mkdir(parents=True, exist_ok=True)
    rent_df.to_json(
        base / RENT_COMPARABLES_FILE,
        orient="table",
        compression="gzip",
        date_format="iso",
    )
    sale_df.to_json(
        base / SALE_COMPARABLES_FILE,
        orient="table",
        compression="gzip",
        date_format="iso",
    )
    meta = {
        "corpus_revision": corpus_revision,
        "rent_rows": len(rent_df),
        "sale_rows": len(sale_df),
    }
    (base / COMPARABLES_META_FILE).write_text(json.dumps(meta), encoding="utf-8")


def hydrate_comparables_from_disk(base: Path, corpus_revision: str | None) -> bool:
    """Load safe JSON comparables into the in-process cache."""
    global _comparables_cache
    meta_path = base / COMPARABLES_META_FILE
    rent_path = base / RENT_COMPARABLES_FILE
    if not corpus_revision or not meta_path.is_file() or not rent_path.is_file():
        return False
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    if meta.get("corpus_revision") != corpus_revision:
        return False
    rent_df = pd.read_json(rent_path, orient="table", compression="gzip")
    sale_path = base / SALE_COMPARABLES_FILE
    sale_df = (
        pd.read_json(sale_path, orient="table", compression="gzip")
        if sale_path.is_file()
        else pd.DataFrame()
    )
    rev_dt: datetime | None = None
    with suppress(ValueError):
        rev_dt = datetime.fromisoformat(corpus_revision)
    now = time.monotonic()
    with _comparables_cache_lock:
        _comparables_cache = (rev_dt, now, rent_df, sale_df)
    return True


def _ensure_rent_per_sqm(df: pd.DataFrame) -> pd.DataFrame:
    """Older disk caches omitted rent_per_sqm; derive it when missing."""
    if df.empty or "rent_per_sqm" in df.columns:
        return df
    if "rent_price" not in df.columns or "area_sqm" not in df.columns:
        return df
    out = df.copy()
    out["rent_per_sqm"] = out["rent_price"] / out["area_sqm"]
    return out


def _normalize_comparables_pair(
    rent_df: pd.DataFrame,
    sale_df: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    return _ensure_rent_per_sqm(rent_df.copy()), _ensure_rent_per_sqm(sale_df.copy())


def _load_comparables_pair(session: Session) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Rent + sale comparable frames — memory, then disk, then SQL."""
    global _comparables_cache
    now = time.monotonic()
    with _comparables_cache_lock:
        cached = _comparables_cache
        if cached is not None and now - cached[1] < _COMPARABLES_CACHE_TTL_SEC:
            return _normalize_comparables_pair(cached[2], cached[3])

    revision = _comparables_revision(session)
    rev_iso = revision.isoformat() if revision else None
    from groundtruth.services.lookup_cache import lookup_cache_dir, lookup_cache_manifest

    manifest = lookup_cache_manifest()
    if (
        manifest
        and manifest.get("corpus_revision") == rev_iso
        and hydrate_comparables_from_disk(lookup_cache_dir(), rev_iso)
    ):
        with _comparables_cache_lock:
            cached = _comparables_cache
            if cached is not None:
                return _normalize_comparables_pair(cached[2], cached[3])

    rent_df = rent_comparables_dataframe(session)
    sale_df = sale_comparables_dataframe(session)
    if rev_iso:
        persist_comparables_disk_cache(lookup_cache_dir(), rent_df, sale_df, rev_iso)
    with _comparables_cache_lock:
        _comparables_cache = (revision, now, rent_df, sale_df)
    return _normalize_comparables_pair(rent_df, sale_df)


DATASET_MANIFEST_V1 = PROJECT_ROOT / "data" / "datasets" / "dataset_v1.0.json"
DATASET_MANIFEST_V2 = PROJECT_ROOT / "data" / "datasets" / "dataset_v2.0.json"

_COMMERCIAL_RE = re.compile(
    r"\b(zyre|zyrë|lokal|komercial|commercial|office|dyqan|shop)\b",
    re.IGNORECASE,
)


def _load_dataset_version() -> str:
    return frozen_dataset_version()


def is_likely_commercial(title: str | None, description: str | None) -> bool:
    text_blob = f"{title or ''} {description or ''}"
    return bool(_COMMERCIAL_RE.search(text_blob))


def resolve_neighborhood(session: Session, name_or_id: str) -> Neighborhood:
    """Resolve neighborhood by numeric id or fuzzy name match."""
    if name_or_id.strip().isdigit():
        nh = session.get(Neighborhood, int(name_or_id))
        if nh is None:
            raise ValueError(f"Neighborhood id {name_or_id} not found")
        return nh

    query = name_or_id.strip().lower()
    neighborhoods = session.query(Neighborhood).all()
    if not neighborhoods:
        raise ValueError("No neighborhoods in gazetteer")

    best: Neighborhood | None = None
    best_score = 0
    for nh in neighborhoods:
        score = fuzz.token_sort_ratio(query, nh.name.lower())
        if score > best_score:
            best_score = score
            best = nh

    if best is None or best_score < 75:
        raise ValueError(f"Neighborhood '{name_or_id}' not recognized")
    return best


def resolve_neighborhood_from_comparables(
    df: pd.DataFrame,
    name_or_id: str,
    session: Session | None,
) -> tuple[int, str]:
    """Resolve neighborhood from comparables first, falling back to DB gazetteer."""
    if not df.empty and {"neighborhood_id", "neighborhood_name"}.issubset(df.columns):
        if name_or_id.strip().isdigit():
            nh_id = int(name_or_id)
            rows = df[df["neighborhood_id"] == nh_id]
            if not rows.empty:
                return nh_id, str(rows.iloc[0]["neighborhood_name"])

        query = name_or_id.strip().lower()
        names = (
            df[["neighborhood_id", "neighborhood_name"]]
            .dropna()
            .drop_duplicates()
            .itertuples(index=False)
        )
        best: tuple[int, str] | None = None
        best_score = 0
        for neighborhood_id, neighborhood_name in names:
            score = fuzz.token_sort_ratio(query, str(neighborhood_name).lower())
            if score > best_score:
                best_score = score
                best = (int(neighborhood_id), str(neighborhood_name))
        if best is not None and best_score >= 75:
            return best

    if session is None:
        raise ValueError(f"Neighborhood '{name_or_id}' not recognized")
    nh = resolve_neighborhood(session, name_or_id)
    return nh.id, nh.name


def list_neighborhood_names(session: Session) -> list[str]:
    return sorted(n.name for n in session.query(Neighborhood).order_by(Neighborhood.name).all())


def area_bucket_sqm(area_sqm: float, *, bucket: int = AREA_BUCKET_M2) -> float:
    """Round area to nearest bucket (60 and 62 both → 60)."""
    return round(area_sqm / bucket) * bucket


def area_match_bounds(
    area_sqm: float,
    *,
    tolerance_m2: float = DEFAULT_AREA_MATCH_TOLERANCE_M2,
    bucket: int = AREA_BUCKET_M2,
) -> tuple[float, float, float]:
    """Return (bucket_center, lo, hi) for comparable area matching."""
    center = area_bucket_sqm(area_sqm, bucket=bucket)
    return center, center - tolerance_m2, center + tolerance_m2


def list_neighborhood_options(session: Session) -> list[dict[str, object]]:
    """All gazetteer neighborhoods with rent and sale listing counts for the UI."""
    from groundtruth.schemas.valuation import NeighborhoodOption

    neighborhoods = session.query(Neighborhood).order_by(Neighborhood.name).all()
    rent_counts: dict[str, int] = {}
    sale_counts: dict[str, int] = {}

    rent_df, sale_df = _load_comparables_pair(session)
    if not rent_df.empty:
        apt = rent_df["property_type"].fillna("APARTMENT").str.upper() == "APARTMENT"
        commercial = rent_df["is_commercial"] if "is_commercial" in rent_df.columns else False
        clean = rent_df[apt & ~commercial]
        for name, count in clean.groupby("neighborhood_name").size().items():
            if name:
                rent_counts[str(name)] = int(count)

    if not sale_df.empty:
        apt = sale_df["property_type"].fillna("APARTMENT").str.upper() == "APARTMENT"
        commercial = sale_df["is_commercial"] if "is_commercial" in sale_df.columns else False
        clean = sale_df[apt & ~commercial]
        for name, count in clean.groupby("neighborhood_name").size().items():
            if name:
                sale_counts[str(name)] = int(count)

    options = [
        NeighborhoodOption(
            name=neighborhood.name,
            slug=neighborhood.slug,
            rent_listings=rent_counts.get(neighborhood.name, 0),
            sale_listings=sale_counts.get(neighborhood.name, 0),
            estimate_ready=rent_counts.get(neighborhood.name, 0) >= MIN_COMPARABLES,
            sale_estimate_ready=sale_counts.get(neighborhood.name, 0) >= MIN_COMPARABLES,
        )
        for neighborhood in neighborhoods
    ]
    options.sort(key=lambda o: (-int(o.estimate_ready), -o.rent_listings, o.name))
    return [o.model_dump() for o in options]


def rent_comparables_dataframe(
    session: Session,
    *,
    max_age_months: int = DEFAULT_MAX_AGE_MONTHS,
) -> pd.DataFrame:
    """Cross-deduped rent listings with rent/m² for comparable selection."""
    from groundtruth.analytics.corpus import active_corpus_dataframe

    df = active_corpus_dataframe(session, max_age_months=max_age_months)
    if df.empty:
        return df

    rent = df[df["listing_type"] == "rent"].copy()
    rent = rent[
        rent["rent_price"].notna()
        & rent["rent_price"].between(RENT_COMPARABLE_MIN_EUR, RENT_COMPARABLE_MAX_EUR)
        & rent["area_sqm"].notna()
        & rent["area_sqm"].between(RENT_COMPARABLE_MIN_AREA_SQM, RENT_COMPARABLE_MAX_AREA_SQM)
        & rent["neighborhood_id"].notna()
    ]
    if rent.empty:
        return rent

    rent = rent.rename(columns={"neighborhood": "neighborhood_name"})
    rent["rent_per_sqm"] = rent["rent_price"] / rent["area_sqm"]
    rent["is_commercial"] = rent["property_type"].astype(str).str.upper().eq("COMMERCIAL")
    return rent[
        [
            "source_website",
            "source_listing_id",
            "rent_price",
            "area_sqm",
            "bedrooms",
            "neighborhood_id",
            "neighborhood_name",
            "property_type",
            "is_commercial",
            "rent_per_sqm",
        ]
    ].copy()


def sale_comparables_dataframe(
    session: Session,
    *,
    max_age_months: int = DEFAULT_MAX_AGE_MONTHS,
) -> pd.DataFrame:
    """Cross-deduped sale listings with €/m² for comparable selection."""
    from groundtruth.analytics.corpus import active_corpus_dataframe

    df = active_corpus_dataframe(session, max_age_months=max_age_months)
    if df.empty:
        return df

    sale = df[df["listing_type"] == "sale"].copy()
    sale = sale[
        sale["sale_price"].notna()
        & sale["sale_price"].between(SALE_COMPARABLE_MIN_EUR, SALE_COMPARABLE_MAX_EUR)
        & sale["area_sqm"].notna()
        & sale["area_sqm"].between(SALE_COMPARABLE_MIN_AREA_SQM, SALE_COMPARABLE_MAX_AREA_SQM)
        & sale["neighborhood_id"].notna()
    ]
    if sale.empty:
        return sale

    sale = sale.rename(columns={"neighborhood": "neighborhood_name"})
    sale["sale_per_sqm"] = sale["sale_price"] / sale["area_sqm"]
    sale["is_commercial"] = sale["property_type"].astype(str).str.upper().eq("COMMERCIAL")
    # Shared comparable-selection columns (sale path reuses rent column names)
    sale["rent_price"] = sale["sale_price"]
    sale["rent_per_sqm"] = sale["sale_per_sqm"]
    return sale[
        [
            "source_website",
            "source_listing_id",
            "sale_price",
            "rent_price",
            "area_sqm",
            "bedrooms",
            "neighborhood_id",
            "neighborhood_name",
            "property_type",
            "is_commercial",
            "sale_per_sqm",
            "rent_per_sqm",
        ]
    ].copy()


def _apply_bedroom_stratify(
    area_df: pd.DataFrame,
    bedrooms: int | None,
    method_base: str,
) -> tuple[pd.DataFrame, str, bool] | None:
    if bedrooms is None:
        return None
    bed_df = area_df[area_df["bedrooms"] == bedrooms]
    if len(bed_df) >= MIN_COMPARABLES:
        return bed_df, f"{method_base}+bedrooms", True
    return None


def select_comparables(
    df: pd.DataFrame,
    *,
    neighborhood_id: int,
    area_sqm: float,
    bedrooms: int | None,
    area_tolerance_pct: float,
    area_match_tolerance_m2: float = DEFAULT_AREA_MATCH_TOLERANCE_M2,
) -> tuple[pd.DataFrame, str, bool, float, float, float]:
    """Filter comparables with 5 m² area buckets; widen if sample is thin."""
    nh_df = df[df["neighborhood_id"] == neighborhood_id].copy()
    bucket_center, match_lo, match_hi = area_match_bounds(
        area_sqm, tolerance_m2=area_match_tolerance_m2
    )
    if nh_df.empty:
        return nh_df, "neighborhood", False, bucket_center, match_lo, match_hi

    apt = nh_df["property_type"].fillna("APARTMENT").str.upper() == "APARTMENT"
    commercial = nh_df["is_commercial"] if "is_commercial" in nh_df.columns else False
    nh_df = nh_df[apt & ~commercial]

    def _pick(area_df: pd.DataFrame, label: str) -> tuple[pd.DataFrame, str, bool] | None:
        if len(area_df) < MIN_COMPARABLES:
            return None
        stratified = _apply_bedroom_stratify(area_df, bedrooms, label)
        if stratified:
            return stratified
        return area_df, label, False

    # Tier 1: ±5 m² around rounded bucket (60 m² and 62 m² share the same band)
    bucket_df = nh_df[(nh_df["area_sqm"] >= match_lo) & (nh_df["area_sqm"] <= match_hi)]
    bucket_method = f"neighborhood+{int(bucket_center)}m2±{int(area_match_tolerance_m2)}m"
    picked = _pick(bucket_df, bucket_method)
    if picked:
        comps, method, bed = picked
        return comps, method, bed, bucket_center, match_lo, match_hi

    # Tier 2: ±10 m²
    wide_lo, wide_hi = bucket_center - 10, bucket_center + 10
    wide_df = nh_df[(nh_df["area_sqm"] >= wide_lo) & (nh_df["area_sqm"] <= wide_hi)]
    picked = _pick(wide_df, f"neighborhood+{int(bucket_center)}m2±10m")
    if picked:
        comps, method, bed = picked
        return comps, method, bed, bucket_center, wide_lo, wide_hi

    # Tier 3: ±20% (legacy fallback)
    pct_lo = area_sqm * (1 - area_tolerance_pct)
    pct_hi = area_sqm * (1 + area_tolerance_pct)
    pct_df = nh_df[(nh_df["area_sqm"] >= pct_lo) & (nh_df["area_sqm"] <= pct_hi)]
    picked = _pick(pct_df, "neighborhood+area±20%")
    if picked:
        comps, method, bed = picked
        return comps, method, bed, bucket_center, pct_lo, pct_hi

    # Tier 4: full neighborhood
    picked = _pick(nh_df, "neighborhood")
    if picked:
        comps, method, bed = picked
        return comps, method, bed, bucket_center, match_lo, match_hi

    fallback = bucket_df if len(bucket_df) >= len(nh_df) else nh_df
    return fallback, "neighborhood+area", False, bucket_center, match_lo, match_hi


def _confidence_label(n: int, score: float) -> str:
    if n < MIN_COMPARABLES:
        return "Low"
    if CONFIDENCE_CALIBRATED and n >= 80 and score >= 0.35:
        return "High"
    if n >= 30:
        return "Medium"
    return "Low"


def _assess(
    listing_rent: float,
    point: float,
    lo: float,
    hi: float,
    *,
    n: int,
    dataset_version: str,
) -> tuple[str, float, str]:
    vs_pct = (listing_rent - point) / point * 100
    if listing_rent > hi:
        assessment = "above_comparables"
        summary = (
            f"Observed asking price is approximately {max(vs_pct, 0):.0f}% above "
            f"the weighted comparable average of {n} listings in Dataset {dataset_version}."
        )
    elif listing_rent < lo:
        assessment = "below_comparables"
        summary = (
            f"Observed asking price is approximately {abs(min(vs_pct, 0)):.0f}% below "
            f"the weighted comparable average of {n} listings in Dataset {dataset_version}."
        )
    else:
        assessment = "within_comparables"
        summary = (
            f"Observed asking price falls within the bootstrap interval "
            f"of {n} comparable listings in Dataset {dataset_version}."
        )
    return assessment, round(vs_pct, 1), summary


def _round_valuation_eur(value: Any, kind: str) -> int | None:
    return round_rent_eur(value) if kind == "rent" else round_sale_eur(value)


def _build_comparable_listings(
    comps: pd.DataFrame,
    *,
    target_area: float,
    bandwidth_m2: float = AREA_WEIGHT_BANDWIDTH_M2,
    valuation_kind: str = "rent",
) -> list[ComparableListing]:
    weights = comparable_area_weights(comps["area_sqm"], target_area, bandwidth_m2=bandwidth_m2)
    ranked = comps.assign(_area_weight=weights).sort_values(
        ["_area_weight", "area_sqm"], ascending=[False, True]
    )
    shown = ranked.head(MAX_COMPARABLES_SHOWN)
    round_psm = round_rent_psm if valuation_kind == "rent" else round_sale_psm
    return [
        ComparableListing(
            source_listing_id=row.source_listing_id,
            area_sqm=int(round(float(row.area_sqm))),
            bedrooms=int(row.bedrooms) if pd.notna(row.bedrooms) else None,
            rent_eur=_round_valuation_eur(row.rent_price, valuation_kind),
            rent_per_sqm=round_psm(row.rent_per_sqm),
        )
        for row in shown.itertuples()
    ]


def estimate_valuation(
    session: Session | None,
    request: ValuationRequest,
    *,
    rent_comparables: pd.DataFrame | None = None,
    sale_comparables: pd.DataFrame | None = None,
    exclude_listing_keys: frozenset[tuple[str, str]] | None = None,
) -> ValuationResult:
    """Produce a fair-market rent or sale estimate from neighborhood comparables."""
    kind = request.valuation_type
    dataset_version = _load_dataset_version()
    if rent_comparables is not None or sale_comparables is not None:
        rent_df = rent_comparables.copy() if rent_comparables is not None else pd.DataFrame()
        sale_df = sale_comparables.copy() if sale_comparables is not None else pd.DataFrame()
    else:
        rent_df, sale_df = _load_comparables_pair(session)
    df = rent_df if kind == "rent" else sale_df
    if (
        exclude_listing_keys
        and not df.empty
        and {"source_website", "source_listing_id"}.issubset(df.columns)
    ):
        keys = df.apply(
            lambda row: (str(row["source_website"]), str(row["source_listing_id"])),
            axis=1,
        )
        df = df[~keys.isin(exclude_listing_keys)]
    if df.empty:
        raise ValueError(
            "No rent listings available for valuation"
            if kind == "rent"
            else "No sale listings available for valuation"
        )
    neighborhood_id, neighborhood_name = resolve_neighborhood_from_comparables(
        df,
        request.neighborhood,
        session,
    )

    comps, method, bedroom_applied, bucket_center, match_lo, match_hi = select_comparables(
        df,
        neighborhood_id=neighborhood_id,
        area_sqm=request.area_sqm,
        bedrooms=request.bedrooms,
        area_tolerance_pct=request.area_tolerance_pct,
        area_match_tolerance_m2=request.area_match_tolerance_m2,
    )

    n = len(comps)
    if n < MIN_COMPARABLES:
        raise ValueError(INSUFFICIENT_EVIDENCE_MSG)

    area = request.area_sqm
    area_weights = comparable_area_weights(
        comps["area_sqm"],
        area,
        bandwidth_m2=AREA_WEIGHT_BANDWIDTH_M2,
    )
    rps_ci = bootstrap_weighted_mean_ci(
        comps["rent_per_sqm"],
        area_weights,
        n_resamples=1000,
        seed=42,
    )
    if rps_ci is None:
        raise ValueError("Could not compute €/m² confidence interval")

    weighted_rps, rps_lo, rps_hi = rps_ci
    point = weighted_rps * area
    lo = rps_lo * area
    hi = rps_hi * area
    comparable_median = weighted_average(comps["rent_price"], area_weights)
    if comparable_median is None:
        raise ValueError("Could not compute weighted comparable price")

    missing_bed = float(comps["bedrooms"].isna().mean()) if "bedrooms" in comps else 0.0
    conf = compute_dataset_confidence(
        n=n,
        parser_accuracy=PARSER_ACCURACY,
        critical_field_missing_rate=missing_bed,
        n_sources=1,
    )
    label = _confidence_label(n, conf.score)
    notes = [
        "Comparables drawn from the active public listing corpus; cross-source validation is ongoing.",
        f"Comparable sample n={n} ({method}).",
        "Commercial/office listings excluded from comparables when detected in title.",
    ]
    if n < 50:
        notes.append("Small comparable sample — treat range as indicative.")

    excluded = [
        ExcludedFactor(
            factor="furnishing",
            reason="Market-wide furnishing premium inconclusive after controls (GT-006).",
            claim_id="GT-006",
        ),
        ExcludedFactor(factor="floor", reason="No published structural claim; data coverage low."),
        ExcludedFactor(factor="parking", reason="Not extracted reliably in Dataset v1.0."),
    ]

    assessment = vs_pct = summary = None
    negotiation: NegotiationAid | None = None
    asking_price = request.listing_rent_eur if kind == "rent" else request.listing_sale_eur
    if asking_price is not None:
        assessment, vs_pct, summary = _assess(
            asking_price,
            point,
            lo,
            hi,
            n=n,
            dataset_version=dataset_version,
        )
        negotiation = NegotiationAid(
            comparable_median_rent_eur=_round_valuation_eur(comparable_median, kind),
            negotiation_lo_eur=_round_valuation_eur(lo, kind),
            negotiation_hi_eur=_round_valuation_eur(hi, kind),
            listing_rent_eur=_round_valuation_eur(asking_price, kind),
            monthly_difference_eur=_round_valuation_eur(asking_price - comparable_median, kind),
        )

    why_checks = [
        f"{n} comparable apartments",
        "Same neighborhood",
        f"Similar size (~{int(bucket_center)} m², ±{int(request.area_match_tolerance_m2)} m²)",
        "Closer in size weighted more heavily",
    ]
    if bedroom_applied:
        why_checks.append("Similar bedrooms")
    else:
        why_checks.append("Bedrooms not matched (insufficient stratified sample)")

    top_factors = ["Area-weighted €/m²", "Neighborhood comparables"]
    if bedroom_applied:
        top_factors.append("Bedroom-matched comparables")

    explanation = ValuationExplanation(
        estimate=_round_valuation_eur(point, kind),
        confidence=label,
        sample_size=n,
        top_factors=top_factors,
        excluded=[f"{e.factor} ({e.claim_id})" if e.claim_id else e.factor for e in excluded],
        dataset_version=dataset_version,
        comparable_method=method,
    )

    method_summary = (
        "Area-weighted average €/m² × area"
        + (" with bedroom-matched comparables" if bedroom_applied else "")
        + "; furnishing effect not applied."
    )

    return ValuationResult(
        valuation_type=kind,
        model_id=RENT_MODEL_ID if kind == "rent" else SALE_MODEL_ID,
        model_version=MODEL_VERSION,
        dataset_version=dataset_version,
        product_version=PRODUCT_VERSION,
        neighborhood_id=neighborhood_id,
        neighborhood_name=neighborhood_name,
        area_sqm=area,
        area_bucket_sqm=bucket_center,
        area_match_lo_sqm=match_lo,
        area_match_hi_sqm=match_hi,
        bedrooms=request.bedrooms,
        point_estimate_eur=_round_valuation_eur(point, kind),
        lower_ci_eur=_round_valuation_eur(lo, kind),
        upper_ci_eur=_round_valuation_eur(hi, kind),
        median_rent_per_sqm=round_rent_psm(weighted_rps)
        if kind == "rent"
        else round_sale_psm(weighted_rps),
        comparable_median_rent_eur=_round_valuation_eur(comparable_median, kind),
        comparable_count=n,
        comparable_method=method,
        bedroom_adjustment_applied=bedroom_applied,
        comparables=_build_comparable_listings(comps, target_area=area, valuation_kind=kind),
        why_checks=why_checks,
        listing_rent_eur=request.listing_rent_eur if kind == "rent" else None,
        assessment=assessment,
        vs_median_pct=vs_pct,
        assessment_summary=summary,
        negotiation=negotiation,
        confidence_label=label,
        confidence_score=round(conf.score, 3),
        confidence_notes=notes,
        excluded_factors=excluded,
        method_summary=method_summary,
        explanation=explanation,
    )


def estimate_rent_valuation(session: Session, request: ValuationRequest) -> ValuationResult:
    """Backward-compatible rent-only entry point."""
    if request.valuation_type != "rent":
        request = request.model_copy(update={"valuation_type": "rent"})
    return estimate_valuation(session, request)


def compute_public_valuation(request: ValuationRequest) -> ValuationResult:
    """Prefer in-memory comparables cache; fall back to a short-lived DB session."""
    from groundtruth.database.session import get_session_factory

    if comparables_cache_ready():
        pair = copy_cached_comparables_pair()
        if pair is not None:
            rent_df, sale_df = pair
            return estimate_valuation(
                None,
                request,
                rent_comparables=rent_df,
                sale_comparables=sale_df,
            )

    session = get_session_factory()()
    try:
        return estimate_valuation(session, request)
    finally:
        session.close()
