"""Replay frozen matching candidates/reviews and six-source calibration evidence.

File-only: no source requests, database writes, merging or field transfer.
Private snapshots and reviews must already exist. Candidate rank is not identity.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

from groundtruth.analytics.harta_matching import candidate_assessment, matching_gate, street_key

SIX = ("gjirafa", "merrjep", "pro-rks", "vision", "topia", "myrealestate")


def select_pairs(pool: list[dict], count: int = 40) -> list[dict]:
    if not 30 <= count <= 50:
        raise ValueError("Pilot requires 30–50 reviewed pairs")
    harta = [r for r in pool if r["source_website"] == "harta"]
    other = [r for r in pool if r["source_website"] in SIX]
    ranked_by_anchor = {}
    keys = {id(r): street_key(r.get("street_raw")) for r in pool}
    for a in harta:
        options = []
        ap = float((a["rent_price"] if a["listing_type"] == "rent" else a["sale_price"]) or 0)
        for b in other:
            if a["listing_type"] != b["listing_type"]:
                continue
            bp = float((b["rent_price"] if b["listing_type"] == "rent" else b["sale_price"]) or 0)
            same_street = bool(keys[id(a)]) and keys[id(a)] == keys[id(b)]
            same_nh = (
                a["neighborhood_id"] is not None and a["neighborhood_id"] == b["neighborhood_id"]
            )
            if not (
                (ap > 0 and bp > 0 and abs(ap - bp) / max(ap, bp) <= 0.15) or same_nh or same_street
            ):
                continue
            rough = (
                (25 if ap and bp and abs(ap - bp) / max(ap, bp) <= 0.05 else 0)
                + (6 if a["bedrooms"] is not None and a["bedrooms"] == b["bedrooms"] else 0)
                + 5 * same_nh
                + 20 * same_street
            )
            options.append((rough, b))
        options = sorted(
            options, key=lambda t: (-t[0], t[1]["source_website"], t[1]["source_listing_id"])
        )[:300]
        ranked = [
            {"harta": a, "other": b, "assessment": candidate_assessment(a, b)} for _, b in options
        ]
        ranked.sort(
            key=lambda p: (
                -p["assessment"]["score"],
                p["other"]["source_website"],
                p["other"]["source_listing_id"],
            )
        )
        ranked_by_anchor[a["source_listing_id"]] = ranked
    selected = []
    used = set()
    for source in SIX:
        options = [
            next((p for p in ps if p["other"]["source_website"] == source), None)
            for ps in ranked_by_anchor.values()
        ]
        for p in sorted(
            [p for p in options if p],
            key=lambda p: (-p["assessment"]["score"], p["harta"]["source_listing_id"]),
        ):
            if p["harta"]["source_listing_id"] in used:
                continue
            p["selection_stratum"] = "source_coverage"
            selected.append(p)
            used.add(p["harta"]["source_listing_id"])
            if sum(x["other"]["source_website"] == source for x in selected) >= 3:
                break
    for p in sorted(
        [ps[0] for key, ps in ranked_by_anchor.items() if ps and key not in used],
        key=lambda p: (-p["assessment"]["score"], p["harta"]["source_listing_id"]),
    ):
        if len(selected) >= count:
            break
        p["selection_stratum"] = "highest_remaining_anchor_candidate"
        selected.append(p)
        used.add(p["harta"]["source_listing_id"])
    if len(selected) != count:
        raise ValueError("Insufficient distinct Harta anchors for the requested review")
    for i, p in enumerate(selected, 1):
        p["pair_id"] = f"HCM-{i:03d}"
    return selected


def report(snapshot: list[dict], reviews: list[dict], calibration: Path) -> dict:
    selected = select_pairs(snapshot, len(reviews))
    expected = {
        (
            p["harta"]["source_listing_id"],
            p["other"]["source_website"],
            p["other"]["source_listing_id"],
        )
        for p in selected
    }
    actual = {(r["harta_source_id"], r["other_source"], r["other_source_id"]) for r in reviews}
    if expected != actual:
        raise ValueError("Reviews do not correspond to the frozen deterministic candidate set")
    gate = matching_gate(reviews)
    summaries = {}
    for name, folder in [
        ("recent", calibration),
        ("historical_processed", calibration / "historical_processed"),
    ]:
        quality = json.loads((folder / "source_quality_report.json").read_text())
        rows = [s for s in quality["sources"] if s["segment"] == "all"]
        if {s["source_name"] for s in rows} != set(SIX):
            raise ValueError("Calibration must include exactly the established six portals")
        summaries[name] = rows
    return {
        "matching_gate": gate,
        "source_pair_counts": dict(Counter(r["other_source"] for r in reviews)),
        "unique_harta_anchors": len({r["harta_source_id"] for r in reviews}),
        "live_harta_http_counts": dict(Counter(str(r["harta_http_status"]) for r in reviews)),
        "location_score_gain_pairs": sum(
            r["candidate_assessment"]["location_gain"] > 0 for r in reviews
        ),
        "claim_conflict_pairs": sum(
            bool(r["candidate_assessment"]["contradicting_claims"]) for r in reviews
        ),
        "maximum_description_token_overlap": max(
            (r["longest_shared_token_run"] for r in reviews), default=0
        ),
        "description_overlap_is_not_identity_proof": True,
        "six_source_calibration": summaries,
        "harta_weight": 1.0,
        "harta_weight_active": False,
        "field_enrichment_permitted": False,
        "public_statistics_changed": False,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", type=Path, required=True)
    parser.add_argument("--reviews", type=Path, required=True)
    parser.add_argument("--calibration", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    value = report(
        json.loads(args.snapshot.read_text()),
        json.loads(args.reviews.read_text()),
        args.calibration,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(value, indent=2), encoding="utf8")
    print(
        "MATCHING_GATE",
        value["matching_gate"]["status"],
        "pairs",
        value["matching_gate"]["reviewed_pairs"],
    )


if __name__ == "__main__":
    main()
