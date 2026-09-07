"""Forensic dataset audit — missingness, cardinality, anomalies, distributions."""

from __future__ import annotations

import base64
import io
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sqlalchemy import func
from sqlalchemy.orm import Session

from groundtruth.models.enums import HeatingType
from groundtruth.models.pipeline import NormalizedListing, RawListing
from groundtruth.models.reference import Building, Complex, Neighborhood


@dataclass
class AuditReport:
    """Container for all Phase C audit sections."""

    generated_at: str
    total_rows: int
    unique_listings: int
    missingness: pd.DataFrame
    cardinality: dict[str, pd.DataFrame]
    impossible_values: pd.DataFrame
    anomalies: pd.DataFrame
    duplicate_groups: pd.DataFrame
    confidence_bins: pd.DataFrame
    source_bias: pd.DataFrame
    plots: dict[str, str] = field(default_factory=dict)
    meta: dict[str, Any] = field(default_factory=dict)


def _active_price(df: pd.DataFrame) -> pd.Series:
    rent = df["rent_price"].where(df["listing_type"] == "rent")
    sale = df["sale_price"].where(df["listing_type"] == "sale")
    return rent.fillna(sale)


def load_audit_dataframe(session: Session, *, dedupe: bool = True) -> tuple[pd.DataFrame, int]:
    """Load normalized listings; optionally keep latest row per source_listing_id."""
    nh_map = {n.id: n.name for n in session.query(Neighborhood).all()}
    b_map = {b.id: b.name for b in session.query(Building).all()}
    c_map = {c.id: c.name for c in session.query(Complex).all()}

    listings = session.query(NormalizedListing).all()
    total_rows = len(listings)
    rows = []
    for listing in listings:
        rows.append(
            {
                "source_listing_id": listing.source_listing_id,
                "source_website": listing.source_website,
                "original_url": listing.original_url,
                "listing_type": listing.listing_type.value if listing.listing_type else None,
                "property_type": listing.property_type.value if listing.property_type else None,
                "sale_price": float(listing.sale_price) if listing.sale_price else np.nan,
                "rent_price": float(listing.rent_price) if listing.rent_price else np.nan,
                "price_per_sqm": float(listing.price_per_sqm) if listing.price_per_sqm else np.nan,
                "area_sqm": listing.area_sqm,
                "bedrooms": listing.bedrooms,
                "bathrooms": listing.bathrooms,
                "floor": listing.floor,
                "total_floors": listing.total_floors,
                "construction_year": listing.construction_year,
                "heating_type": (
                    listing.heating_type.value
                    if listing.heating_type and listing.heating_type != HeatingType.UNKNOWN
                    else None
                ),
                "neighborhood": nh_map.get(listing.neighborhood_id, ""),
                "neighborhood_id": listing.neighborhood_id,
                "building": b_map.get(listing.building_id, ""),
                "building_id": listing.building_id,
                "complex": c_map.get(listing.complex_id, ""),
                "complex_id": listing.complex_id,
                "is_furnished": listing.is_furnished,
                "has_elevator": listing.has_elevator,
                "has_parking": listing.has_parking,
                "city": listing.city,
                "confidence_score": listing.confidence_score,
                "parser_version": listing.parser_version,
                "normalized_id": listing.id,
            }
        )
    df = pd.DataFrame(rows)
    if df.empty:
        return df, total_rows

    df["price"] = _active_price(df)

    if dedupe:
        df = df.sort_values("normalized_id").drop_duplicates("source_listing_id", keep="last")

    return df, total_rows


def missingness_matrix(df: pd.DataFrame) -> pd.DataFrame:
    fields = [
        "price",
        "area_sqm",
        "bedrooms",
        "bathrooms",
        "floor",
        "heating_type",
        "building",
        "complex",
        "is_furnished",
        "has_elevator",
        "has_parking",
        "construction_year",
        "neighborhood",
    ]
    rows = []
    n = len(df)
    for field_name in fields:
        if field_name not in df.columns:
            continue
        missing = df[field_name].isna() | (df[field_name] == "")
        rows.append(
            {
                "field": field_name,
                "missing_count": int(missing.sum()),
                "missing_percent": round(100.0 * missing.sum() / n, 1) if n else 0.0,
                "present_count": int((~missing).sum()),
            }
        )
    return pd.DataFrame(rows).sort_values("missing_percent", ascending=False)


def cardinality_report(df: pd.DataFrame) -> dict[str, pd.DataFrame]:
    reports: dict[str, pd.DataFrame] = {}
    for col, label in (
        ("neighborhood", "neighborhood"),
        ("building", "building"),
        ("complex", "complex"),
        ("heating_type", "heating_type"),
        ("property_type", "property_type"),
        ("is_furnished", "furnishing"),
    ):
        if col not in df.columns:
            continue
        series = df[col].dropna()
        series = series[series != ""]
        counts = series.value_counts().reset_index()
        counts.columns = [label, "count"]
        reports[col] = counts
    return reports


def impossible_values(df: pd.DataFrame) -> pd.DataFrame:
    checks = [
        ("price < 50", df["price"].notna() & (df["price"] < 50)),
        ("price > 2_000_000", df["price"].notna() & (df["price"] > 2_000_000)),
        ("area < 10", df["area_sqm"].notna() & (df["area_sqm"] < 10)),
        ("area > 1000", df["area_sqm"].notna() & (df["area_sqm"] > 1000)),
        ("bedrooms > 20", df["bedrooms"].notna() & (df["bedrooms"] > 20)),
        ("bathrooms > 15", df["bathrooms"].notna() & (df["bathrooms"] > 15)),
        (
            "rent_per_sqm > 100",
            (df["listing_type"] == "rent")
            & df["price_per_sqm"].notna()
            & (df["price_per_sqm"] > 100),
        ),
        (
            "sale_per_sqm < 100",
            (df["listing_type"] == "sale")
            & df["price_per_sqm"].notna()
            & (df["price_per_sqm"] < 100),
        ),
    ]
    rows = []
    for rule, mask in checks:
        flagged = df[mask]
        for _, row in flagged.head(25).iterrows():
            rows.append(
                {
                    "rule": rule,
                    "source_listing_id": row["source_listing_id"],
                    "listing_type": row["listing_type"],
                    "price": row["price"],
                    "area_sqm": row["area_sqm"],
                    "bedrooms": row["bedrooms"],
                    "neighborhood": row["neighborhood"],
                    "url": row["original_url"],
                }
            )
    summary = pd.DataFrame(
        [{"rule": rule, "count": int(mask.sum())} for rule, mask in checks]
    ).sort_values("count", ascending=False)
    if rows:
        detail = pd.DataFrame(rows)
        detail["summary_total"] = detail["rule"].map(summary.set_index("rule")["count"])
        return detail
    return summary


def zscore_anomalies(df: pd.DataFrame, column: str, z: float = 3.0) -> pd.DataFrame:
    series = df[column].dropna()
    if series.empty or series.std() == 0:
        return pd.DataFrame()
    scores = (series - series.mean()) / series.std()
    mask = scores.abs() >= z
    out = df.loc[
        series.index[mask],
        ["source_listing_id", "listing_type", column, "neighborhood", "original_url"],
    ].copy()
    out["z_score"] = scores[mask].values
    out["field"] = column
    return out


def duplicate_analysis(df: pd.DataFrame) -> pd.DataFrame:
    work = df.dropna(subset=["price", "area_sqm"]).copy()
    work["price_bucket"] = (work["price"] // 50) * 50
    work["area_bucket"] = work["area_sqm"].round(0)
    grouped = (
        work.groupby(["neighborhood_id", "area_bucket", "bedrooms", "price_bucket"], dropna=False)
        .agg(
            count=("source_listing_id", "count"),
            listings=("source_listing_id", lambda s: ", ".join(s.head(5))),
        )
        .reset_index()
    )
    return grouped[grouped["count"] >= 2].sort_values("count", ascending=False)


def confidence_calibration(df: pd.DataFrame) -> pd.DataFrame:
    scores = df["confidence_score"].dropna()
    if scores.empty:
        return pd.DataFrame()
    bins = [0.5, 0.6, 0.7, 0.8, 0.9, 1.01]
    labels = ["0.5-0.6", "0.6-0.7", "0.7-0.8", "0.8-0.9", "0.9-1.0"]
    bucket = pd.cut(scores, bins=bins, labels=labels, right=False)
    out = (
        df.loc[scores.index]
        .assign(confidence_bin=bucket.values)
        .groupby("confidence_bin", observed=True)
        .agg(
            count=("source_listing_id", "count"),
            mean_price=("price", "mean"),
            mean_area=("area_sqm", "mean"),
            pct_with_neighborhood=("neighborhood_id", lambda s: 100 * s.notna().mean()),
        )
        .reset_index()
    )
    out["sample_listings"] = out["confidence_bin"].map(
        {
            label: ", ".join(
                df.loc[scores.index][bucket == label]["source_listing_id"].head(3).tolist()
            )
            for label in labels
        }
    )
    return out


def source_bias(df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    n = len(df)
    rows.append(
        {
            "dimension": "listing_type",
            "value": "rent",
            "count": int((df["listing_type"] == "rent").sum()),
            "percent": round(100 * (df["listing_type"] == "rent").mean(), 1),
        }
    )
    rows.append(
        {
            "dimension": "listing_type",
            "value": "sale",
            "count": int((df["listing_type"] == "sale").sum()),
            "percent": round(100 * (df["listing_type"] == "sale").mean(), 1),
        }
    )
    prishtina = (
        df["city"].str.lower().isin(["prishtina", "prishtine"])
        if "city" in df.columns
        else pd.Series(False, index=df.index)
    )
    rows.append(
        {
            "dimension": "city",
            "value": "prishtina",
            "count": int(prishtina.sum()),
            "percent": round(100 * prishtina.mean(), 1),
        }
    )
    rows.append(
        {
            "dimension": "city",
            "value": "other",
            "count": int((~prishtina).sum()),
            "percent": round(100 * (~prishtina).mean(), 1),
        }
    )
    apt = df["property_type"] == "apartment"
    rows.append(
        {
            "dimension": "property_type",
            "value": "apartment",
            "count": int(apt.sum()),
            "percent": round(100 * apt.mean(), 1),
        }
    )
    rows.append(
        {
            "dimension": "property_type",
            "value": "non_apartment",
            "count": int((~apt).sum()),
            "percent": round(100 * (~apt).mean(), 1),
        }
    )
    if "price_per_sqm" in df.columns:
        rent_df = df[df["listing_type"] == "rent"]
        if not rent_df.empty and rent_df["price_per_sqm"].notna().any():
            threshold = rent_df["price_per_sqm"].quantile(0.9)
            luxury = rent_df["price_per_sqm"] >= threshold
            rows.append(
                {
                    "dimension": "rent_tier",
                    "value": f"top_decile_rent_per_sqm (>={threshold:.0f})",
                    "count": int(luxury.sum()),
                    "percent": round(100 * luxury.sum() / n, 1),
                }
            )
    return pd.DataFrame(rows)


def _plot_histogram(series: pd.Series, title: str, xlabel: str) -> str:
    fig, ax = plt.subplots(figsize=(7, 4))
    clean = series.dropna()
    if clean.empty:
        ax.text(0.5, 0.5, "No data", ha="center", va="center")
    else:
        ax.hist(clean, bins=40, color="#2563eb", edgecolor="white")
    ax.set_title(title)
    ax.set_xlabel(xlabel)
    ax.set_ylabel("Count")
    fig.tight_layout()
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=120)
    plt.close(fig)
    return base64.b64encode(buf.getvalue()).decode("ascii")


def run_audit(session: Session, *, dedupe: bool = True) -> AuditReport:
    df, total_rows = load_audit_dataframe(session, dedupe=dedupe)
    plots: dict[str, str] = {}
    if not df.empty:
        rent_df = df[df["listing_type"] == "rent"]
        plots["price"] = _plot_histogram(df["price"], "Active price distribution", "EUR")
        plots["area"] = _plot_histogram(df["area_sqm"], "Area distribution", "m²")
        plots["rent_per_sqm"] = _plot_histogram(rent_df["price_per_sqm"], "Rent per m²", "EUR/m²")
        plots["bedrooms"] = _plot_histogram(df["bedrooms"], "Bedrooms", "Count")
        plots["confidence"] = _plot_histogram(df["confidence_score"], "Confidence score", "Score")
        plots["floor"] = _plot_histogram(df["floor"], "Floor", "Floor")

    anomalies = pd.concat(
        [
            zscore_anomalies(df, "price"),
            zscore_anomalies(df, "area_sqm"),
            zscore_anomalies(rent_df, "price_per_sqm") if not df.empty else pd.DataFrame(),
        ],
        ignore_index=True,
    )

    unique_count = (
        session.query(func.count(func.distinct(RawListing.source_listing_id)))
        .filter_by(source_website="gjirafa")
        .scalar()
        or 0
    )

    return AuditReport(
        generated_at=datetime.now(UTC).isoformat(),
        total_rows=total_rows,
        unique_listings=unique_count if dedupe else total_rows,
        missingness=missingness_matrix(df),
        cardinality=cardinality_report(df),
        impossible_values=impossible_values(df),
        anomalies=anomalies,
        duplicate_groups=duplicate_analysis(df),
        confidence_bins=confidence_calibration(df),
        source_bias=source_bias(df),
        plots=plots,
        meta={"deduped_for_analysis": dedupe, "analysis_rows": len(df)},
    )


def _df_to_html(df: pd.DataFrame, max_rows: int = 50) -> str:
    if df.empty:
        return "<p><em>No rows.</em></p>"
    return df.head(max_rows).to_html(index=False, classes="dataframe", border=0)


def render_audit_html(report: AuditReport) -> str:
    sections = [
        ("Missingness matrix", _df_to_html(report.missingness)),
        ("Impossible / suspicious values", _df_to_html(report.impossible_values, 40)),
        ("Z-score anomalies (|z| ≥ 3)", _df_to_html(report.anomalies, 40)),
        ("Duplicate candidate groups", _df_to_html(report.duplicate_groups, 30)),
        ("Confidence calibration bins", _df_to_html(report.confidence_bins)),
        ("Source bias", _df_to_html(report.source_bias)),
    ]
    for name, card in report.cardinality.items():
        sections.append((f"Cardinality — {name}", _df_to_html(card, 30)))

    plot_html = "".join(
        f'<div class="plot"><h3>{name}</h3><img src="data:image/png;base64,{data}" alt="{name}"/></div>'
        for name, data in report.plots.items()
    )

    body = "\n".join(f"<h2>{title}</h2>{html}" for title, html in sections)
    return f"""<!DOCTYPE html>
<html lang="en"><head>
<meta charset="utf-8"/>
<title>GroundTruth Dataset Audit — {report.generated_at[:10]}</title>
<style>
body {{ font-family: system-ui, sans-serif; margin: 2rem; color: #111; }}
h1 {{ border-bottom: 2px solid #2563eb; padding-bottom: 0.5rem; }}
.meta {{ background: #f1f5f9; padding: 1rem; border-radius: 8px; margin-bottom: 2rem; }}
table {{ border-collapse: collapse; width: 100%; margin-bottom: 2rem; font-size: 0.9rem; }}
th, td {{ border: 1px solid #e2e8f0; padding: 0.4rem 0.6rem; text-align: left; }}
th {{ background: #f8fafc; }}
.plot {{ display: inline-block; margin: 1rem; vertical-align: top; }}
.plot img {{ max-width: 420px; border: 1px solid #e2e8f0; border-radius: 4px; }}
</style></head><body>
<h1>GroundTruth Dataset Audit</h1>
<div class="meta">
<p><strong>Generated:</strong> {report.generated_at}</p>
<p><strong>Total normalized rows:</strong> {report.total_rows:,}</p>
<p><strong>Unique source listings (Gjirafa):</strong> {report.unique_listings:,}</p>
<p><strong>Rows in this analysis:</strong> {report.meta.get("analysis_rows", 0):,} (deduped={report.meta.get("deduped_for_analysis")})</p>
<p><em>Interpret coverage as rental-focused Prishtina apartments unless source bias section says otherwise.</em></p>
</div>
<h2>Distribution plots</h2>
<div>{plot_html}</div>
{body}
</body></html>"""


def write_audit_artifacts(report: AuditReport, output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    html_path = output_dir / "audit_report.html"
    html_path.write_text(render_audit_html(report), encoding="utf-8")
    report.missingness.to_csv(output_dir / "missingness.csv", index=False)
    report.source_bias.to_csv(output_dir / "source_bias.csv", index=False)
    report.confidence_bins.to_csv(output_dir / "confidence_bins.csv", index=False)
    report.duplicate_groups.to_csv(output_dir / "duplicate_groups.csv", index=False)
    if not report.anomalies.empty:
        report.anomalies.to_csv(output_dir / "anomalies.csv", index=False)
    for name, card in report.cardinality.items():
        card.to_csv(output_dir / f"cardinality_{name}.csv", index=False)
    return html_path
