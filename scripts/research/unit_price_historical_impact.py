"""File-only historical impact analysis. Never executes ETL or database writes."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pandas as pd
from replay_unit_price_remediation import baseline_method

from groundtruth.analytics.cross_dedup import apply_cross_dedupe
from groundtruth.analytics.stats import comparable_area_weights, weighted_average
from groundtruth.analytics.unit_price_impact import (
    latest_active,
    neighborhood_medians,
    project_prices,
)
from groundtruth.analytics.valuation import (
    MIN_COMPARABLES,
    SALE_COMPARABLE_MAX_AREA_SQM,
    SALE_COMPARABLE_MAX_EUR,
    SALE_COMPARABLE_MIN_AREA_SQM,
    SALE_COMPARABLE_MIN_EUR,
    select_comparables,
)
from groundtruth.processing.validation import ListingValidator
from groundtruth.schemas.pipeline import NormalizedListingSchema
from groundtruth.services.normalization import NormalizationService
from groundtruth.services.parsing import ParsingService


def same(a, b):
    if a is None or b is None:
        return a is b
    return Decimal(str(a)) == Decimal(str(b))


def analyze_candidates(snapshot):
    parser, normalizer, validator = ParsingService(), NormalizationService(), ListingValidator()
    old_method = baseline_method("2cc30f7")
    by_raw = {}
    for row in snapshot["normalized_rows"]:
        if row["source_website"] == "gjirafa":
            by_raw.setdefault(row["raw_listing_id"], []).append(row)
    reviews, decisions = [], []
    for raw_row in snapshot["candidate_raw_versions"]:
        raw = SimpleNamespace(**raw_row, source_website="gjirafa", raw_html=None)
        before = after = normalized = None
        try:
            with patch.object(ParsingService, "_fixup_sale_price", old_method):
                before = parser.parse_raw(raw)
            after = parser.parse_raw(raw)
            normalized, factors = normalizer.normalize(after)
            validation = validator.validate(normalized)
            full_codes = [i.code for i in validation.issues]
            if factors.location_invalid:
                full_codes.append("invalid_location")
            changed = before.sale_price != after.sale_price
            review = {
                "raw_id": raw.id,
                "source_listing_id": raw.source_listing_id,
                "source_url": raw.original_url,
                "scraped_at": raw_row["scraped_at"],
                "description_sha256": raw_row["description_sha256"],
                "old_code_total": str(before.sale_price) if before.sale_price is not None else None,
                "new_code_total": str(after.sale_price) if after.sale_price is not None else None,
                "new_code_area": normalized.area_sqm,
                "code_changed_price": changed,
                "new_rule": after.extra_fields.get("provenance", {})
                .get("sale_price", {})
                .get("rule_id"),
                "full_current_dryrun_codes": sorted(set(full_codes)),
                "normalized_versions": len(by_raw.get(raw.id, [])),
            }
            reviews.append(review)
            if not changed:
                continue
            for stored in by_raw.get(raw.id, []):
                # Corpus SQL exposes uppercase display categories; schema enums
                # use lowercase values. Preserve the stored category's meaning.
                row = NormalizedListingSchema.model_validate(
                    {
                        **stored,
                        "property_type": stored["property_type"].lower()
                        if stored["property_type"]
                        else None,
                    }
                )
                before_codes = {i.code for i in validator.validate(row).issues}
                area_matches = same(row.area_sqm, normalized.area_sqm)
                extra_code_drift = before.bedrooms != after.bedrooms
                projectable = (after.sale_price is None or area_matches) and not extra_code_drift
                total = float(after.sale_price) if after.sale_price is not None else None
                psm = round(total / row.area_sqm, 2) if total and row.area_sqm else None
                projected = row.model_copy(
                    update={
                        "sale_price": after.sale_price,
                        "price_per_sqm": Decimal(str(psm)) if psm is not None else None,
                    }
                )
                after_codes = {i.code for i in validator.validate(projected).issues}
                changed_persisted = not same(row.sale_price, total) or not same(
                    row.price_per_sqm, psm
                )
                decisions.append(
                    {
                        "raw_id": raw.id,
                        "normalized_id": stored["normalized_id"],
                        "parsed_listing_id": stored["parsed_listing_id"],
                        "source_listing_id": raw.source_listing_id,
                        "old_sale_price": float(row.sale_price)
                        if row.sale_price is not None
                        else None,
                        "new_sale_price": total,
                        "old_price_per_sqm": float(row.price_per_sqm)
                        if row.price_per_sqm is not None
                        else None,
                        "new_price_per_sqm": psm,
                        "stored_area": row.area_sqm,
                        "source_parser_area": normalized.area_sqm,
                        "projectable": projectable,
                        "changed_persisted": changed_persisted,
                        "classification": "manual_area_or_nonprice_drift"
                        if not projectable
                        else "already_correct"
                        if not changed_persisted
                        else "quarantine_missing_total"
                        if total is None
                        else "supported_price_correction",
                        "before_validator_codes": sorted(before_codes),
                        "after_validator_codes": sorted(after_codes),
                        "introduced_validation_codes": sorted(after_codes - before_codes),
                        "persisted_validation_codes": stored["persisted_validation_codes"],
                        "currently_active_version": stored["currently_active"],
                        "currently_valid_version": stored["currently_valid"],
                        "current_row_fingerprint": hashlib.sha256(
                            json.dumps(stored, sort_keys=True).encode()
                        ).hexdigest(),
                    }
                )
        except Exception as exc:
            if reviews and reviews[-1]["raw_id"] == raw.id:
                reviews[-1]["error"] = type(exc).__name__
            else:
                reviews.append(
                    {
                        "raw_id": raw.id,
                        "source_listing_id": raw.source_listing_id,
                        "error": type(exc).__name__,
                        "code_changed_price": None,
                    }
                )
    return reviews, decisions


def canonical(frame, threshold):
    tagged = apply_cross_dedupe(frame, threshold=threshold)
    return tagged[tagged["is_canonical_primary"]].copy().reset_index(drop=True)


def sale_comparables(frame):
    result = frame[
        frame["listing_type"].eq("sale")
        & frame["sale_price"].between(SALE_COMPARABLE_MIN_EUR, SALE_COMPARABLE_MAX_EUR)
        & frame["area_sqm"].between(SALE_COMPARABLE_MIN_AREA_SQM, SALE_COMPARABLE_MAX_AREA_SQM)
        & frame["neighborhood_id"].notna()
    ].copy()
    result["is_commercial"] = result["property_type"].eq("COMMERCIAL")
    result["rent_price"] = result["sale_price"]
    result["rent_per_sqm"] = result["sale_price"] / result["area_sqm"]
    return result


def valuation_grid(before, after, neighborhoods):
    output = []
    for nh in sorted(neighborhoods):
        for area in [50.0, 70.0, 90.0, 110.0, 130.0, 150.0]:
            values = []
            for frame in [before, after]:
                comps, method, _, _, _, _ = select_comparables(
                    frame, neighborhood_id=nh, area_sqm=area, bedrooms=None, area_tolerance_pct=0.2
                )
                value = None
                if len(comps) >= MIN_COMPARABLES:
                    weights = comparable_area_weights(comps["area_sqm"], area, bandwidth_m2=10.0)
                    value = weighted_average(comps["rent_per_sqm"], weights) * area
                values.append({"n": len(comps), "method": method, "point_eur": value})
            b, a = values
            output.append(
                {
                    "neighborhood_id": nh,
                    "area_sqm": area,
                    "bedrooms": None,
                    "before": b,
                    "after": a,
                    "delta_eur": a["point_eur"] - b["point_eur"]
                    if a["point_eur"] is not None and b["point_eur"] is not None
                    else None,
                }
            )
    return output


def assess(snapshot, threshold):
    reviews, decisions = analyze_candidates(snapshot)
    if any("error" in review for review in reviews):
        raise ValueError("Candidate processing errors prevent a reliable impact assessment")
    rows = pd.DataFrame(snapshot["normalized_rows"])
    for col in [
        "sale_price",
        "rent_price",
        "price_per_sqm",
        "area_sqm",
        "confidence_score",
        "bedrooms",
        "bathrooms",
        "neighborhood_id",
        "street_id",
        "building_id",
    ]:
        rows[col] = pd.to_numeric(rows[col], errors="coerce")
    before = latest_active(rows)
    projected = project_prices(rows, decisions)
    after = latest_active(projected)
    print("Projected active per-source rows", len(before), "to", len(after), flush=True)
    before_canonical, after_canonical = canonical(before, threshold), canonical(after, threshold)
    print("Offline canonical rows", len(before_canonical), "to", len(after_canonical), flush=True)
    medians = neighborhood_medians(before_canonical).merge(
        neighborhood_medians(after_canonical),
        on=["neighborhood_id", "neighborhood", "listing_type", "property_type"],
        suffixes=("_before", "_after"),
        how="outer",
    )
    medians["delta_median_eur"] = (
        medians["median_asking_eur_after"] - medians["median_asking_eur_before"]
    )
    medians["delta_median_eur_m2"] = (
        medians["median_asking_eur_m2_after"] - medians["median_asking_eur_m2_before"]
    )
    comps_before, comps_after = (
        sale_comparables(before_canonical),
        sale_comparables(after_canonical),
    )
    changed_ids = {
        d["normalized_id"] for d in decisions if d["projectable"] and d["changed_persisted"]
    }
    touched = set(
        rows.loc[rows["normalized_id"].isin(changed_ids), "neighborhood_id"].dropna().astype(int)
    )
    grid = valuation_grid(comps_before, comps_after, touched)
    before_keys, after_keys = (
        set(before_canonical["normalized_id"]),
        set(after_canonical["normalized_id"]),
    )
    before_latest_ids = set(before["normalized_id"])
    summary = {
        "as_of": snapshot["as_of"],
        "historical_raw_versions_scanned": snapshot["historical_raw_versions_scanned"],
        "historical_raw_unique_ids": snapshot["historical_raw_unique_ids"],
        "candidate_raw_versions": len(reviews),
        "candidate_unique_ids": len({r["source_listing_id"] for r in reviews}),
        "code_changed_raw_versions": sum(r.get("code_changed_price") is True for r in reviews),
        "candidate_errors": sum("error" in r for r in reviews),
        "broader_syntax_unmodified": len(snapshot["broader_syntax_review"]),
        "decision_classifications": dict(Counter(d["classification"] for d in decisions)),
        "persisted_normalized_versions_affected": len(changed_ids),
        "affected_unique_source_ids": len(
            {
                d["source_listing_id"]
                for d in decisions
                if d["projectable"] and d["changed_persisted"]
            }
        ),
        "affected_current_active_source_rows": len(changed_ids & before_latest_ids),
        "active_source_rows_before": len(before),
        "active_source_rows_after": len(after),
        "canonical_rows_before": len(before_canonical),
        "canonical_rows_after": len(after_canonical),
        "canonical_removed_normalized_ids": sorted(before_keys - after_keys),
        "canonical_added_normalized_ids": sorted(after_keys - before_keys),
        "source_selection_added_ids": sorted(set(after["normalized_id"]) - before_latest_ids),
        "source_selection_removed_ids": sorted(before_latest_ids - set(after["normalized_id"])),
        "sale_comparables_before": len(comps_before),
        "sale_comparables_after": len(comps_after),
        "valuation_grid_requests": len(grid),
        "valuation_grid_changed_points": sum(
            g["delta_eur"] is not None and abs(g["delta_eur"]) > 0.005 for g in grid
        ),
        "valuation_grid_readiness_changes": sum(
            (g["before"]["point_eur"] is None) != (g["after"]["point_eur"] is None) for g in grid
        ),
        "max_absolute_grid_delta_eur": max(
            (abs(g["delta_eur"]) for g in grid if g["delta_eur"] is not None), default=0
        ),
        "dedup_threshold": threshold,
        "persistent_updates_authorized": False,
        "public_statistics_rebuilt": False,
    }
    return {
        "summary": summary,
        "raw_reviews": reviews,
        "decisions": decisions,
        "neighborhood_medians": json.loads(medians.to_json(orient="records")),
        "valuation_grid": grid,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--dedup-threshold", type=float, required=True)
    args = parser.parse_args()
    snapshot = json.loads(args.snapshot.read_text(encoding="utf-8"))
    report = assess(snapshot, args.dedup_threshold)
    report["input_sha256"] = hashlib.sha256(args.snapshot.read_bytes()).hexdigest()
    args.output.mkdir(parents=True, exist_ok=False)
    (args.output / "impact_private.json").write_text(
        json.dumps(report, indent=2, default=str), encoding="utf-8"
    )
    print(json.dumps(report["summary"]), flush=True)


if __name__ == "__main__":
    main()
