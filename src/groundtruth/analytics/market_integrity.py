"""Stage 1 market-integrity baseline built from the production lookup corpus.

This module is diagnostic only.  It deliberately reuses the lookup service's
population filters and does not change any public calculation.
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd
from sqlalchemy.orm import Session

from groundtruth.analytics.corpus import _query_deduped_corpus_dataframe
from groundtruth.analytics.cross_dedup import apply_cross_dedupe
from groundtruth.analytics.market_metrics import (
    sale_psm_series,
    sane_rent_rows,
    sane_sale_rows,
)
from groundtruth.models.reference import Neighborhood
from groundtruth.services.lookup import (
    SIZE_BANDS,
    _canonical_neighborhood_ids,
    resolve_entity,
)
from groundtruth.services.lookup_cache import lookup_cache_dir

ENTITY_COLUMNS = {
    "neighborhood": "neighborhood_id",
    "district": "district_id",
    "street": "street_id",
    "complex": "complex_id",
}
APARTMENT_TYPES = frozenset({"APARTMENT", "STUDIO"})
HOUSE_TYPES = frozenset({"HOUSE", "VILLA"})


class MarketIntegrityError(RuntimeError):
    """Raised when a Stage 1 hard invariant is broken."""


@dataclass(frozen=True)
class MarketEntity:
    entity_type: str
    slug: str
    display_name: str
    column: str
    ids: tuple[int, ...]
    lookup_expectations: dict[str, int | None] = field(default_factory=dict)


def _is_present(series: pd.Series) -> pd.Series:
    if pd.api.types.is_string_dtype(series):
        return series.notna() & series.astype(str).str.strip().ne("")
    return series.notna()


def _pct_missing(series: pd.Series) -> float:
    return round(100.0 * float((~_is_present(series)).mean()), 2) if len(series) else 0.0


def _ptype(series: pd.Series) -> pd.Series:
    return series.fillna("OTHER").astype(str).str.upper()


def _stats(series: pd.Series) -> dict[str, float | int | None]:
    values = pd.to_numeric(series, errors="coerce").dropna()
    if values.empty:
        return {k: None for k in ("min", "p10", "p25", "median", "p75", "p90", "max")}
    return {
        "min": round(float(values.min()), 2),
        "p10": round(float(values.quantile(0.10)), 2),
        "p25": round(float(values.quantile(0.25)), 2),
        "median": round(float(values.median()), 2),
        "p75": round(float(values.quantile(0.75)), 2),
        "p90": round(float(values.quantile(0.90)), 2),
        "max": round(float(values.max()), 2),
    }


def _source_summary(df: pd.DataFrame) -> dict[str, Any]:
    counts = df["source_website"].fillna("(missing)").value_counts()
    total = int(counts.sum())
    shares = [round(100.0 * int(n) / total, 2) for n in counts.tolist()] if total else []
    return {
        "source_count": int(len(counts)),
        "n_per_source": {str(k): int(v) for k, v in counts.items()},
        "largest_source_share_pct": shares[0] if shares else 0.0,
        "second_largest_source_share_pct": shares[1] if len(shares) > 1 else 0.0,
    }


def _size_band(area: object) -> str | None:
    if area is None or pd.isna(area):
        return None
    value = float(area)
    matches = [band_id for band_id, _, lo, hi in SIZE_BANDS if lo <= value < hi]
    if len(matches) > 1:
        raise MarketIntegrityError(f"area {value} falls into multiple size buckets")
    return matches[0] if matches else None


def _bedroom_band(value: object) -> str | None:
    if value is None or pd.isna(value):
        return None
    bedrooms = int(value)
    return "4+" if bedrooms >= 4 else str(bedrooms) if bedrooms >= 0 else None


def _bucket_rows(df: pd.DataFrame, column: str, order: Iterable[str]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for bucket in order:
        group = df[df[column] == bucket]
        if group.empty:
            continue
        sale = group[group["listing_type"] == "sale"]
        rent = group[group["listing_type"] == "rent"]
        sale_psm = sale_psm_series(sale)
        sane_rent = sane_rent_rows(rent)
        source = _source_summary(group)
        rows.append(
            {
                "bucket": bucket,
                "sale_n": int(len(sale)),
                "rent_n": int(len(rent)),
                "union_n": int(len(group)),
                "median_sale_psm": round(float(sale_psm.median()), 2) if len(sale_psm) else None,
                "median_rent": (
                    round(float(sane_rent["rent_price"].median()), 2) if len(sane_rent) else None
                ),
                "source_count": source["source_count"],
                "largest_source_share_pct": source["largest_source_share_pct"],
            }
        )
    return rows


def _segment(df: pd.DataFrame, entity: MarketEntity) -> pd.DataFrame:
    return df[df[entity.column].isin(entity.ids)].copy()


def profile_market_entity(
    entity: MarketEntity,
    pre_cross_dedup: pd.DataFrame,
    canonical: pd.DataFrame,
) -> dict[str, Any]:
    """Profile one entity with explicit denominators and production filters."""
    pre = _segment(pre_cross_dedup, entity)
    post = _segment(canonical, entity)
    ptypes = _ptype(post["property_type"])
    apartment = post[ptypes.isin(APARTMENT_TYPES)].copy()
    sale_apt = apartment[apartment["listing_type"] == "sale"]
    rent_apt = apartment[apartment["listing_type"] == "rent"]
    sale_psm = sale_psm_series(sale_apt)
    sane_sale = sane_sale_rows(sale_apt)
    sane_rent = sane_rent_rows(rent_apt)

    apartment["bedroom_bucket"] = apartment["bedrooms"].apply(_bedroom_band)
    apartment["size_bucket"] = apartment["area_sqm"].apply(_size_band)
    duplicate_groups = 0
    if "canonical_group_id" in pre.columns:
        duplicate_groups = int(pre.loc[pre["group_size"] > 1, "canonical_group_id"].nunique())

    property_known = post["property_type"].notna()
    transaction_known = post["listing_type"].isin(("sale", "rent"))
    other = ~(ptypes.isin(APARTMENT_TYPES | HOUSE_TYPES | {"COMMERCIAL"}))
    result = {
        "entity": {
            "type": entity.entity_type,
            "slug": entity.slug,
            "display_name": entity.display_name,
        },
        "inventory": {
            "full_corpus_n": int(len(post)),
            "apartments_studios_n": int(len(apartment)),
            "houses_n": int(ptypes.isin(HOUSE_TYPES).sum()),
            "commercial_n": int((ptypes == "COMMERCIAL").sum()),
            "other_n": int(other.sum()),
            "sale_n": int((post["listing_type"] == "sale").sum()),
            "rent_n": int((post["listing_type"] == "rent").sum()),
        },
        "metric_eligibility": {
            "sale_apartment_n": int(len(sale_apt)),
            "sale_psm_eligible_n": int(len(sale_psm)),
            "rent_apartment_n": int(len(rent_apt)),
            "rent_eligible_n": int(len(sane_rent)),
            "known_bedrooms_n": int(apartment["bedrooms"].notna().sum()),
            "known_area_n": int(apartment["area_sqm"].notna().sum()),
            "size_banded_n": int(apartment["size_bucket"].notna().sum()),
        },
        "missingness_pct": {
            "bedrooms": _pct_missing(post["bedrooms"]),
            "area": _pct_missing(post["area_sqm"]),
            "price": _pct_missing(post["listing_price"]),
            "transaction_type": round(100.0 * float((~transaction_known).mean()), 2)
            if len(post)
            else 0.0,
            "location": round(100.0 * float((~post[entity.column].notna()).mean()), 2)
            if len(post)
            else 0.0,
            "property_type": round(100.0 * float((~property_known).mean()), 2)
            if len(post)
            else 0.0,
        },
        "dedup": {
            "pre_cross_dedup_n": int(len(pre)),
            "post_cross_dedup_n": int(len(post)),
            "duplicate_groups": duplicate_groups,
            "dedup_removal_pct": round(100.0 * (len(pre) - len(post)) / len(pre), 2)
            if len(pre)
            else 0.0,
        },
        "sources": _source_summary(post),
        "prices": {
            "sale_psm": _stats(sale_psm),
            "sale_total_median": round(float(sane_sale["sale_price"].median()), 2)
            if len(sane_sale)
            else None,
            "rent_median": round(float(sane_rent["rent_price"].median()), 2)
            if len(sane_rent)
            else None,
        },
        "bedroom_buckets": _bucket_rows(apartment, "bedroom_bucket", ("0", "1", "2", "3", "4+")),
        "size_buckets": _bucket_rows(apartment, "size_bucket", [b[0] for b in SIZE_BANDS]),
        "reconciliation": {
            "headline_inventory_n": int(len(post)),
            "apartment_n": int(len(apartment)),
            "sale_metric_n": int(len(sale_psm)),
            "rent_metric_n": int(len(sane_rent)),
            "bedroom_union_n": int(apartment["bedroom_bucket"].notna().sum()),
            "size_union_n": int(apartment["size_bucket"].notna().sum()),
        },
    }
    actual = result["reconciliation"]
    if entity.lookup_expectations:
        comparisons = {
            key: {
                "baseline": actual[key],
                "frozen_lookup": expected,
                "matches": expected == actual[key],
            }
            for key, expected in entity.lookup_expectations.items()
        }
        result["frozen_lookup_reconciliation"] = comparisons
    warnings: list[dict[str, Any]] = []
    if entity.lookup_expectations:
        for metric, comparison in result["frozen_lookup_reconciliation"].items():
            if not comparison["matches"]:
                warnings.append(
                    {
                        "code": "FROZEN_LOOKUP_DRIFT",
                        "metric": metric,
                        "baseline": comparison["baseline"],
                        "frozen_lookup": comparison["frozen_lookup"],
                    }
                )
        if entity.entity_type == "neighborhood" and entity.slug == "ulpiana":
            mismatches = [
                key
                for key, item in result["frozen_lookup_reconciliation"].items()
                if not item["matches"]
            ]
            if mismatches:
                details = ", ".join(
                    f"{key}={actual[key]} (lookup {entity.lookup_expectations[key]})"
                    for key in mismatches
                )
                raise MarketIntegrityError(f"Ulpiana frozen lookup does not reconcile: {details}")
    for field_name, value in result["missingness_pct"].items():
        if value >= 25:
            warnings.append({"code": "HIGH_MISSINGNESS", "field": field_name, "value_pct": value})
    if result["sources"]["largest_source_share_pct"] >= 70:
        warnings.append(
            {
                "code": "HIGH_SOURCE_CONCENTRATION",
                "value_pct": result["sources"]["largest_source_share_pct"],
            }
        )
    for metric in ("sale_metric_n", "rent_metric_n"):
        if actual[metric] < 10:
            warnings.append({"code": "LOW_SAMPLE", "metric": metric, "sample_n": actual[metric]})
    result["warnings"] = warnings
    _validate_entity(result, post, canonical)
    return result


def _validate_size_bands() -> None:
    ordered = sorted(SIZE_BANDS, key=lambda band: band[2])
    for previous, current in zip(ordered, ordered[1:], strict=False):
        if current[2] < previous[3]:
            raise MarketIntegrityError(f"overlapping size buckets: {previous[0]} and {current[0]}")


def _validate_entity(
    result: dict[str, Any], segment: pd.DataFrame, canonical: pd.DataFrame
) -> None:
    inv = result["inventory"]
    eligibility = result["metric_eligibility"]
    reconciliation = result["reconciliation"]
    counts = [*inv.values(), *eligibility.values(), *reconciliation.values()]
    if any(value < 0 for value in counts):
        raise MarketIntegrityError("negative count")
    if eligibility["sale_psm_eligible_n"] > eligibility["sale_apartment_n"]:
        raise MarketIntegrityError("sale metric N exceeds eligible parent population")
    if eligibility["rent_eligible_n"] > eligibility["rent_apartment_n"]:
        raise MarketIntegrityError("rent metric N exceeds eligible parent population")
    if eligibility["size_banded_n"] > eligibility["known_area_n"]:
        raise MarketIntegrityError("size-banded N exceeds known-area population")
    if segment["normalized_id"].duplicated().any():
        raise MarketIntegrityError("duplicate normalized IDs after canonical selection")
    if canonical["normalized_id"].duplicated().any():
        raise MarketIntegrityError("duplicate canonical primary IDs")


def _discover_entities(session: Session, cache: Path) -> list[MarketEntity]:
    manifest_path = cache / "manifest.json"
    if not manifest_path.is_file():
        raise MarketIntegrityError(f"lookup manifest not found: {manifest_path}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    entities: list[MarketEntity] = []
    seen: set[tuple[str, str]] = set()
    for entry in manifest.get("entries", []):
        entity_type, slug = entry.get("entity_type"), entry.get("slug")
        if entity_type not in ENTITY_COLUMNS or not slug or (entity_type, slug) in seen:
            continue
        payload_path = cache / str(entry["path"])
        payload = json.loads(payload_path.read_text(encoding="utf-8"))
        if payload.get("requested_slug"):
            continue
        obj = resolve_entity(session, entity_type, slug)
        if obj is None:
            raise MarketIntegrityError(
                f"public lookup entity cannot be resolved: {entity_type}/{slug}"
            )
        ids = (
            tuple(_canonical_neighborhood_ids(session, slug))
            if entity_type == "neighborhood"
            else (int(obj.id),)
        )
        pulse = payload.get("pulse") or {}
        expectations = {
            "headline_inventory_n": payload.get("total_listings"),
            "sale_metric_n": (pulse.get("sale_psm_sample") or {}).get("n"),
            "rent_metric_n": (pulse.get("median_rent_sample") or {}).get("n"),
        }
        entities.append(
            MarketEntity(
                entity_type,
                slug,
                payload["display_name"],
                ENTITY_COLUMNS[entity_type],
                ids,
                expectations,
            )
        )
        seen.add((entity_type, slug))

    for city, rows in _city_entities(session).items():
        entities.insert(
            0, MarketEntity("city", city.lower().replace(" ", "-"), city, "neighborhood_id", rows)
        )
    return entities


def _city_entities(session: Session) -> dict[str, tuple[int, ...]]:
    result: dict[str, list[int]] = {}
    for row in session.query(Neighborhood.id, Neighborhood.city).all():
        result.setdefault(str(row.city), []).append(int(row.id))
    return {name: tuple(ids) for name, ids in sorted(result.items())}


def build_market_integrity_baseline(
    session: Session,
    *,
    cache_dir: Path | None = None,
) -> dict[str, Any]:
    """Build the system-wide Stage 1 report from the production corpus boundary."""
    _validate_size_bands()
    deduped = _query_deduped_corpus_dataframe(session, active_only=True)
    tagged = apply_cross_dedupe(deduped) if not deduped.empty else deduped
    canonical = tagged[tagged["is_canonical_primary"]].copy() if not tagged.empty else tagged
    entities = _discover_entities(session, cache_dir or lookup_cache_dir())
    rows = [profile_market_entity(entity, tagged, canonical) for entity in entities]
    return {
        "schema_version": "1.0",
        "generated_at": datetime.now(UTC).isoformat(),
        "corpus": {
            "authority": "active_corpus_bundle.cross_portal_canonical",
            "pre_cross_dedup_n": int(len(tagged)),
            "post_cross_dedup_n": int(len(canonical)),
        },
        "population_notes": {
            "inventory": "12-month production analytical corpus; not confirmed-current inventory",
            "pricing": "apartment/studio rows using the existing lookup validation bands",
            "known_fields_and_buckets": "apartment/studio population for metric reconciliation",
        },
        "entity_count": len(rows),
        "warning_count": sum(len(row["warnings"]) for row in rows),
        "entities": rows,
    }


def render_market_integrity_markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# Market Integrity Baseline",
        "",
        f"Generated: {payload['generated_at']}",
        "",
        "> Diagnostic only. No formulas or public payloads are changed by this report.",
        "",
        "| Entity | Type | Inventory | Apartments | Sale metric N | Rent metric N | Pre dedup | Post dedup |",
        "|---|---|---:|---:|---:|---:|---:|---:|",
    ]
    for row in payload["entities"]:
        entity, rec, dedup = row["entity"], row["reconciliation"], row["dedup"]
        lines.append(
            f"| {entity['display_name']} | {entity['type']} | {rec['headline_inventory_n']} | "
            f"{rec['apartment_n']} | {rec['sale_metric_n']} | {rec['rent_metric_n']} | "
            f"{dedup['pre_cross_dedup_n']} | {dedup['post_cross_dedup_n']} |"
        )
    return "\n".join(lines) + "\n"


def write_market_integrity_artifacts(
    session: Session,
    output_dir: Path,
    *,
    cache_dir: Path | None = None,
) -> dict[str, Path]:
    payload = build_market_integrity_baseline(session, cache_dir=cache_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "market_integrity_baseline.json"
    csv_path = output_dir / "market_integrity_baseline.csv"
    markdown_path = output_dir / "market_integrity_baseline.md"
    json_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    markdown_path.write_text(render_market_integrity_markdown(payload), encoding="utf-8")
    flat_rows = []
    for row in payload["entities"]:
        flat_rows.append(
            {
                **row["entity"],
                **row["inventory"],
                **row["metric_eligibility"],
                **{f"missing_{k}_pct": v for k, v in row["missingness_pct"].items()},
                **row["dedup"],
                **{k: v for k, v in row["sources"].items() if k != "n_per_source"},
                **row["reconciliation"],
            }
        )
    pd.DataFrame(flat_rows).to_csv(csv_path, index=False)
    return {"json": json_path, "csv": csv_path, "markdown": markdown_path}
