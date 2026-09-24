"""Corpus diagnostics — profile the normalized dataset before freezing v2.0."""

from __future__ import annotations

import json
import threading
import time
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd
from sqlalchemy import text
from sqlalchemy.orm import Session

from groundtruth.analytics.corpus_filters import (
    ACTIVE_CORPUS_WHERE,
    DEFAULT_MAX_AGE_MONTHS,
    EFFECTIVE_LISTING_DATE_SQL,
    GJIRAFA_PARSER_VERSION,
    MERRJEP_PARSER_VERSION,
    VALID_CORPUS_WHERE,
    active_corpus_sql_params,
)
from groundtruth.claims.hashes import dataset_fingerprint, raw_crawl_fingerprint
from groundtruth.methodology.version import METHODOLOGY_VERSION
from groundtruth.versions import ETL_PIPELINE_VERSION

COVERAGE_TIER_HIGH = 100
COVERAGE_TIER_MID = 30
_ACTIVE_CORPUS_TTL_SEC = 300


@dataclass(frozen=True)
class ActiveCorpusBundle:
    deduped: pd.DataFrame
    active: pd.DataFrame
    cross_portal_groups: int


_active_corpus_cache: tuple[datetime | None, int, bool, float, ActiveCorpusBundle] | None = None
_corpus_cache_lock = threading.Lock()


def clear_active_corpus_cache() -> None:
    """Drop in-process active corpus cache (tests, post-ETL)."""
    global _active_corpus_cache
    _active_corpus_cache = None


def _corpus_cache_revision(session: Session) -> datetime | None:
    from groundtruth.analytics.annual_export import corpus_last_updated

    return corpus_last_updated(session)


def coverage_tier(count: int) -> str:
    if count >= COVERAGE_TIER_HIGH:
        return "high"
    if count >= COVERAGE_TIER_MID:
        return "medium"
    return "low"


def coverage_tier_emoji(tier: str) -> str:
    return {"high": "🟢", "medium": "🟡", "low": "🔴"}.get(tier, "")


def bedroom_label(value: Any) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return "unknown"
    bedrooms = int(value)
    if bedrooms >= 4:
        return "4BR+"
    return f"{bedrooms}BR"


def transaction_label(value: Any) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return "unknown"
    return str(value).capitalize()


def _query_deduped_corpus_dataframe(
    session: Session,
    *,
    active_only: bool = False,
    max_age_months: int = DEFAULT_MAX_AGE_MONTHS,
    validity_only: bool = False,
) -> pd.DataFrame:
    """Load deduped corpus from SQL (uncached)."""
    active_filter = (
        VALID_CORPUS_WHERE if validity_only else ACTIVE_CORPUS_WHERE if active_only else ""
    )
    sql = text(
        f"""
        SELECT DISTINCT ON (nl.source_website, nl.source_listing_id)
            nl.id AS normalized_id,
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
            nl.bathrooms,
            nl.neighborhood_id,
            nl.street_id,
            nl.building_id,
            n.name AS neighborhood,
            nl.district_id,
            d.name AS district,
            nl.street_id,
            s.name AS street,
            nl.complex_id,
            c.name AS complex,
            nl.is_furnished,
            nl.confidence_score,
            nl.parser_version,
            {EFFECTIVE_LISTING_DATE_SQL} AS listing_date
        FROM normalized_listings nl
        LEFT JOIN neighborhoods n ON n.id = nl.neighborhood_id
        LEFT JOIN districts d ON d.id = nl.district_id
        LEFT JOIN streets s ON s.id = nl.street_id
        LEFT JOIN complexes c ON c.id = nl.complex_id
        WHERE TRUE
        {active_filter}
        ORDER BY nl.source_website, nl.source_listing_id, nl.id DESC
        """
    )
    params = (
        {"parser_versions": active_corpus_sql_params()["parser_versions"]}
        if validity_only
        else active_corpus_sql_params(max_age_months=max_age_months)
        if active_only
        else {}
    )
    df = pd.DataFrame(session.execute(sql, params).mappings().all())
    if df.empty:
        return df

    if "listing_type" in df.columns:
        df["listing_type"] = df["listing_type"].astype(str).str.lower()
    if "property_type" in df.columns:
        df["property_type"] = df["property_type"].astype(str).str.upper()

    df["listing_price"] = df.apply(
        lambda r: r["rent_price"] if r["listing_type"] == "rent" else r["sale_price"],
        axis=1,
    )
    if "price_per_sqm" not in df.columns or df["price_per_sqm"].isna().all():
        df["price_per_sqm"] = df.apply(
            lambda r: (
                r["listing_price"] / r["area_sqm"]
                if r["listing_price"] and r["area_sqm"] and r["area_sqm"] > 0
                else None
            ),
            axis=1,
        )
    return df


def deduped_corpus_dataframe(
    session: Session,
    *,
    active_only: bool = False,
    max_age_months: int = DEFAULT_MAX_AGE_MONTHS,
) -> pd.DataFrame:
    """Latest normalized row per (source_website, source_listing_id)."""
    if active_only:
        return active_corpus_bundle(session, max_age_months=max_age_months).deduped
    return _query_deduped_corpus_dataframe(
        session,
        active_only=active_only,
        max_age_months=max_age_months,
    )


def _build_active_corpus_bundle(
    session: Session,
    *,
    max_age_months: int,
    cross_dedupe: bool,
) -> ActiveCorpusBundle:
    deduped = _query_deduped_corpus_dataframe(
        session,
        active_only=True,
        max_age_months=max_age_months,
    )
    if deduped.empty or not cross_dedupe:
        return ActiveCorpusBundle(deduped=deduped, active=deduped, cross_portal_groups=0)

    from groundtruth.analytics.cross_dedup import apply_cross_dedupe

    tagged = apply_cross_dedupe(deduped)
    active = tagged[tagged["is_canonical_primary"]].copy()
    dup_groups = int(tagged[tagged["group_size"] > 1]["canonical_group_id"].nunique())
    return ActiveCorpusBundle(deduped=deduped, active=active, cross_portal_groups=dup_groups)


def active_corpus_bundle(
    session: Session,
    *,
    max_age_months: int = DEFAULT_MAX_AGE_MONTHS,
    cross_dedupe: bool = True,
) -> ActiveCorpusBundle:
    """Cached deduped + canonical active corpus for API hot paths."""
    global _active_corpus_cache
    revision = _corpus_cache_revision(session)
    now = time.monotonic()
    with _corpus_cache_lock:
        cached = _active_corpus_cache
        if (
            cached is not None
            and cached[0] == revision
            and cached[1] == max_age_months
            and cached[2] == cross_dedupe
            and now - cached[3] < _ACTIVE_CORPUS_TTL_SEC
        ):
            return cached[4]

        bundle = _build_active_corpus_bundle(
            session,
            max_age_months=max_age_months,
            cross_dedupe=cross_dedupe,
        )
        _active_corpus_cache = (revision, max_age_months, cross_dedupe, now, bundle)
        return bundle


def active_corpus_dataframe(
    session: Session,
    *,
    max_age_months: int = DEFAULT_MAX_AGE_MONTHS,
    cross_dedupe: bool = True,
) -> pd.DataFrame:
    """Product corpus: per-source dedup, optional cross-portal canonical merge."""
    if not cross_dedupe:
        return _query_deduped_corpus_dataframe(
            session,
            active_only=True,
            max_age_months=max_age_months,
        )
    return active_corpus_bundle(
        session,
        max_age_months=max_age_months,
        cross_dedupe=True,
    ).active


def _pct_present(series: pd.Series) -> float:
    if series.empty:
        return 0.0
    return round(100.0 * series.notna().sum() / len(series), 1)


def _distribution(series: pd.Series) -> dict[str, float | int | None]:
    clean = series.dropna()
    if clean.empty:
        return {"count": 0, "min": None, "p25": None, "median": None, "p75": None, "max": None}
    return {
        "count": int(len(clean)),
        "min": round(float(clean.min()), 2),
        "p25": round(float(clean.quantile(0.25)), 2),
        "median": round(float(clean.median()), 2),
        "p75": round(float(clean.quantile(0.75)), 2),
        "max": round(float(clean.max()), 2),
    }


def _count_by_threshold(
    counts: pd.Series, thresholds: tuple[int, ...] = (10, 30, 100)
) -> dict[str, int]:
    result: dict[str, int] = {}
    for threshold in thresholds:
        result[f"n_ge_{threshold}"] = int((counts >= threshold).sum())
    return result


@dataclass
class CorpusReport:
    """Data corpus profile — not a market report."""

    generated_at: str = ""
    total_listings: int = 0
    sources: list[dict[str, Any]] = field(default_factory=list)
    rent_count: int = 0
    sale_count: int = 0
    neighborhoods: dict[str, Any] = field(default_factory=dict)
    streets: dict[str, Any] = field(default_factory=dict)
    complexes: dict[str, Any] = field(default_factory=dict)
    bedrooms: dict[str, int] = field(default_factory=dict)
    area_sqm: dict[str, Any] = field(default_factory=dict)
    missingness_pct: dict[str, float] = field(default_factory=dict)
    price: dict[str, Any] = field(default_factory=dict)
    price_per_sqm: dict[str, Any] = field(default_factory=dict)
    validation: dict[str, Any] = field(default_factory=dict)
    versions: dict[str, Any] = field(default_factory=dict)
    fingerprints: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def build_corpus_report(session: Session, df: pd.DataFrame | None = None) -> CorpusReport:
    """Compute corpus diagnostics from deduped normalized listings."""
    if df is None:
        df = deduped_corpus_dataframe(session)

    report = CorpusReport(generated_at=datetime.now(UTC).isoformat())
    if df.empty:
        return report

    report.total_listings = len(df)
    report.rent_count = int((df["listing_type"] == "rent").sum())
    report.sale_count = int((df["listing_type"] == "sale").sum())

    source_rows = (
        df.groupby("source_website")
        .agg(
            listings=("source_listing_id", "count"),
            rent=("listing_type", lambda s: int((s == "rent").sum())),
            sale=("listing_type", lambda s: int((s == "sale").sum())),
            parser_version=("parser_version", "first"),
        )
        .reset_index()
    )
    report.sources = source_rows.to_dict(orient="records")

    nh_counts = df["neighborhood"].fillna("(missing)").value_counts()
    report.neighborhoods = {
        "distinct": int(df.loc[df["neighborhood_id"].notna(), "neighborhood"].nunique()),
        "with_listings": int((nh_counts.index != "(missing)").sum()),
        "top_10": nh_counts.head(10).astype(int).to_dict(),
    }

    street_counts = df.loc[df["street_id"].notna(), "street"].value_counts()
    report.streets = {
        "distinct_matched": int(df["street_id"].nunique(dropna=True)),
        "listings_with_street": int(df["street_id"].notna().sum()),
        **_count_by_threshold(street_counts),
        "top_10": street_counts.head(10).astype(int).to_dict(),
    }

    complex_counts = df.loc[df["complex_id"].notna(), "complex"].value_counts()
    report.complexes = {
        "distinct_matched": int(df["complex_id"].nunique(dropna=True)),
        "listings_with_complex": int(df["complex_id"].notna().sum()),
        **_count_by_threshold(complex_counts),
        "top_10": complex_counts.head(10).astype(int).to_dict(),
    }

    bedroom_counts = df["bedrooms"].apply(bedroom_label).value_counts()
    report.bedrooms = bedroom_counts.astype(int).to_dict()
    report.area_sqm = _distribution(df["area_sqm"])
    report.missingness_pct = {
        "price": _pct_present(df["listing_price"]),
        "area_sqm": _pct_present(df["area_sqm"]),
        "neighborhood": _pct_present(df["neighborhood_id"]),
        "street": _pct_present(df["street_id"]),
        "complex": _pct_present(df["complex_id"]),
        "bedrooms": _pct_present(df["bedrooms"]),
    }

    rent_df = df[df["listing_type"] == "rent"]
    sale_df = df[df["listing_type"] == "sale"]
    report.price = {
        "rent_eur": _distribution(rent_df["rent_price"]),
        "sale_eur": _distribution(sale_df["sale_price"]),
    }
    report.price_per_sqm = {
        "rent": _distribution(rent_df["price_per_sqm"]),
        "sale": _distribution(sale_df["price_per_sqm"]),
    }

    invalid_count = session.execute(text("SELECT COUNT(*) FROM invalid_listings")).scalar_one()
    report.validation = {
        "invalid_listings_logged": int(invalid_count),
        "normalized_listings": len(df),
        "invalid_pct_of_normalized": round(100.0 * invalid_count / len(df), 1) if len(df) else 0.0,
    }

    parser_versions = sorted(df["parser_version"].dropna().unique().tolist())
    report.versions = {
        "parser_versions": parser_versions,
        "gjirafa_parser": GJIRAFA_PARSER_VERSION,
        "merrjep_parser": MERRJEP_PARSER_VERSION,
        "etl_version": ETL_PIPELINE_VERSION,
        "methodology_version": METHODOLOGY_VERSION,
    }
    report.fingerprints = {
        "dataset_hash": dataset_fingerprint(session),
        "raw_crawl_hash": raw_crawl_fingerprint(session),
    }
    return report


def build_coverage_matrix(df: pd.DataFrame) -> pd.DataFrame:
    """
    Segment coverage: neighborhood × transaction × bedrooms.

    Tier: high (≥100), medium (30–99), low (<30).
    """
    if df.empty:
        return pd.DataFrame(
            columns=[
                "neighborhood",
                "transaction",
                "bedrooms",
                "segment",
                "observations",
                "tier",
            ]
        )

    work = df.copy()
    work["neighborhood"] = work["neighborhood"].fillna("(missing)")
    work["transaction"] = work["listing_type"].apply(transaction_label)
    work["bedrooms"] = work["bedrooms"].apply(bedroom_label)

    grouped = (
        work.groupby(["neighborhood", "transaction", "bedrooms"], dropna=False)
        .size()
        .reset_index(name="observations")
    )
    grouped["tier"] = grouped["observations"].apply(coverage_tier)
    grouped["segment"] = grouped.apply(
        lambda r: f"{r['neighborhood']} {r['transaction']} {r['bedrooms']}",
        axis=1,
    )
    return grouped.sort_values(
        ["observations", "neighborhood", "transaction", "bedrooms"],
        ascending=[False, True, True, True],
    )


def street_coverage_tiers(df: pd.DataFrame) -> dict[str, int]:
    """How many streets have n ≥ 10 / 30 / 100 listings (matched street_id only)."""
    street_df = df[df["street_id"].notna()]
    if street_df.empty:
        return {"n_ge_10": 0, "n_ge_30": 0, "n_ge_100": 0}
    counts = street_df.groupby("street_id").size()
    return _count_by_threshold(counts)


def render_corpus_markdown(report: CorpusReport, matrix: pd.DataFrame) -> str:
    """Human-readable corpus report for review before Dataset v2.0 freeze."""
    lines = [
        "# Corpus Report",
        "",
        f"Generated: {report.generated_at}",
        "",
        "> Data corpus profile — not a market report. Review before freezing Dataset v2.0.",
        "",
        "## Summary",
        "",
        "| Metric | Value |",
        "|--------|------:|",
        f"| Total listings | {report.total_listings:,} |",
        f"| Rent | {report.rent_count:,} |",
        f"| Sale | {report.sale_count:,} |",
        f"| Dataset hash | `{report.fingerprints.get('dataset_hash', '')[:16]}…` |",
        "",
        "## Sources",
        "",
        "| Source | Listings | Rent | Sale | Parser |",
        "|--------|----------|-----:|-----:|--------|",
    ]
    for row in report.sources:
        lines.append(
            f"| {row['source_website']} | {row['listings']:,} | {row['rent']:,} | "
            f"{row['sale']:,} | {row.get('parser_version', '')} |"
        )

    lines.extend(
        [
            "",
            "## Missingness (%)",
            "",
            "| Field | Present |",
            "|-------|--------:|",
        ]
    )
    for field_name, pct in report.missingness_pct.items():
        lines.append(f"| {field_name} | {pct}% |")

    lines.extend(["", "## Bedroom distribution", ""])
    for label, count in sorted(report.bedrooms.items(), key=lambda x: -x[1]):
        lines.append(f"- {label}: {count:,}")

    lines.extend(["", "## Area (m²)", ""])
    for key, val in report.area_sqm.items():
        lines.append(f"- {key}: {val}")

    lines.extend(["", "## Streets (matched)", ""])
    for key, val in report.streets.items():
        if key != "top_10":
            lines.append(f"- {key}: {val}")

    lines.extend(["", "## Complexes (matched)", ""])
    for key, val in report.complexes.items():
        if key != "top_10":
            lines.append(f"- {key}: {val}")

    if not matrix.empty:
        lines.extend(
            [
                "",
                "## Coverage matrix (top segments)",
                "",
                "Tier: 🟢 ≥100 · 🟡 30–99 · 🔴 <30",
                "",
                "| Segment | n | Tier |",
                "|---------|--:|:-----|",
            ]
        )
        for _, row in matrix.head(40).iterrows():
            emoji = coverage_tier_emoji(row["tier"])
            lines.append(f"| {row['segment']} | {row['observations']} | {emoji} {row['tier']} |")
        low = int((matrix["tier"] == "low").sum())
        mid = int((matrix["tier"] == "medium").sum())
        high = int((matrix["tier"] == "high").sum())
        lines.extend(
            [
                "",
                f"Segments: {len(matrix)} total — 🟢 {high} · 🟡 {mid} · 🔴 {low}",
            ]
        )

    return "\n".join(lines) + "\n"


def write_corpus_artifacts(
    session: Session,
    output_dir: Path,
    *,
    df: pd.DataFrame | None = None,
) -> dict[str, Path]:
    """Write corpus JSON, markdown, and coverage matrix CSV."""
    if df is None:
        df = deduped_corpus_dataframe(session)
    report = build_corpus_report(session, df)
    matrix = build_coverage_matrix(df)

    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%d")
    json_path = output_dir / f"corpus_report_{stamp}.json"
    md_path = output_dir / f"corpus_report_{stamp}.md"
    csv_path = output_dir / f"coverage_matrix_{stamp}.csv"

    payload = report.to_dict()
    payload["coverage_matrix_summary"] = {
        "segments": len(matrix),
        "high": int((matrix["tier"] == "high").sum()) if not matrix.empty else 0,
        "medium": int((matrix["tier"] == "medium").sum()) if not matrix.empty else 0,
        "low": int((matrix["tier"] == "low").sum()) if not matrix.empty else 0,
    }
    payload["street_coverage_tiers"] = street_coverage_tiers(df)

    json_path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    md_path.write_text(render_corpus_markdown(report, matrix), encoding="utf-8")
    if not matrix.empty:
        matrix.to_csv(csv_path, index=False)
    else:
        csv_path.write_text(
            "neighborhood,transaction,bedrooms,segment,observations,tier\n", encoding="utf-8"
        )

    return {"json": json_path, "markdown": md_path, "coverage_matrix": csv_path}
