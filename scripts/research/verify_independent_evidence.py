"""Reproduce evidence reports from frozen reviewed inputs; no network or DB access.

Source observations and analyst decisions live in the private frozen evidence
file. This command validates denominators, replays unchanged policy 1.1.0, and
publishes proposed-only diagnostics. It cannot activate matching or weights.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from datetime import datetime
from pathlib import Path

from pydantic import TypeAdapter

from groundtruth.analytics.evidence_verification import field_metrics, matching_metrics
from groundtruth.analytics.source_quality import build_report
from groundtruth.analytics.source_quality_models import QualityPolicy, QualityRecord


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def save(path, value):
    Path(path).write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def generate(evidence: dict, previous: dict, recomputed: dict) -> dict:
    reviews, fields, snapshots = (
        evidence["matching_reviews"],
        evidence["field_reviews"],
        evidence["snapshot_reviews"],
    )
    if len(reviews) != 20 or len(snapshots) != 180 or len(fields) != 1080:
        raise ValueError("Expected frozen 20 pairs, 180 snapshots and six checks per snapshot")
    if len({s["audit_id"] for s in snapshots}) != 180:
        raise ValueError("Duplicate source snapshot")
    if len({(f["audit_id"], f["field"]) for f in fields}) != 1080:
        raise ValueError("Duplicate field review")
    old = {s["source_name"]: s for s in previous["sources"] if s["segment"] == "all"}
    new = {s["source_name"]: s for s in recomputed["sources"] if s["segment"] == "all"}
    summaries = []
    for source in sorted(old):
        selected = [f for f in fields if f["source"] == source]
        source_snapshots = [s for s in snapshots if s["source"] == source]
        if len(source_snapshots) != 30:
            raise ValueError("Each portal must retain thirty snapshots")
        counts = Counter(f["classification"] for f in selected)
        record = new[source]
        if record["source_quality_score"] != old[source]["source_quality_score"]:
            raise ValueError("Frozen unchanged policy replay differs from historical score")
        if record["proposed_weight"] != 1 or record["criterion_sample_counts"]["location"]:
            raise ValueError("Unjustified source-weight or independent location evidence")
        summaries.append(
            {
                "source": source,
                "reviewed_snapshots": len(source_snapshots),
                "strata": dict(Counter(s["stratum"] for s in source_snapshots)),
                "segments": dict(Counter(s["segment"] for s in source_snapshots)),
                "field_counts": dict(counts),
                "publisher_real_world_verified": 0,
                "publisher_error_rate": None,
                "publisher_truth_unknown_fraction": 1,
                "parser_error_snapshots": len(
                    {f["audit_id"] for f in selected if f["classification"] == "parser_error"}
                ),
                "normalizer_error_snapshots": len(
                    {f["audit_id"] for f in selected if f["classification"] == "normalizer_error"}
                ),
                "source_conflict_snapshots": len(
                    {
                        f["audit_id"]
                        for f in selected
                        if f["classification"] == "source_internal_conflict"
                    }
                ),
                "inactive_zero_price_parser_issue_snapshots": sum(
                    s["pro_rks_inactive_zero_price_retained"] for s in source_snapshots
                ),
                "unknown_or_noncomparable_field_fraction": sum(
                    counts[c]
                    for c in [
                        "unknown",
                        "semantic_unknown",
                        "source_placeholder",
                        "source_internal_conflict",
                        "not_applicable",
                    ]
                )
                / len(selected),
                "previous_quality": old[source]["source_quality_score"],
                "recomputed_quality": record["source_quality_score"],
                "quality_delta": 0,
                "criterion_sample_counts": record["criterion_sample_counts"],
                "observed_criterion_coverage": record["observed_criterion_coverage"],
                "proposed_weight": record["proposed_weight"],
                "active": False,
                "eligibility_reasons": record["eligibility_reason"],
                "confidence": "Insufficient independent publisher/location evidence",
            }
        )
    return {
        "assessment_version": "independent-evidence-1.0.0",
        "scoring_policy_version": "1.1.0",
        "calibration_method": "policy-1.1.0-independent-evidence-gate-v1",
        "matching": matching_metrics(reviews),
        "sources": summaries,
        "field_metrics_by_stratum": field_metrics(fields),
        "sampling_caveat": (
            "Diagnostic and segment-stratified audit, not population accuracy. Wilson intervals "
            "are field-specific binomial reference intervals for random_segment_stratum only. "
            "No pooling across correlated fields or enriched cases; segment allocation and "
            "unknown-selection effects prevent design-based population confidence claims."
        ),
        "harta": {"quality": 48.815, "weight": 1, "active": False},
        "controls": evidence["controls"],
        "publisher_reliability": "UNKNOWN; archived agreement is extraction evidence only",
        "runtime_changes": False,
    }


def reports(evidence: dict, assessment: dict, output: Path):
    reviews = evidence["matching_reviews"]
    m = assessment["matching"]
    text = (
        "# Matching evidence verification — twenty cases\n\n"
        "Diagnostic selection: highest ranking scores subject to at least two per portal. "
        "Frozen historical references are compared with twenty current public Harta pages. "
        "All twenty returned HTTP200. Images were read through their published URLs, with "
        "no access-control evasion. Media requests and checksums are in each case. "
        "First two available images per side were examined, extended to eight per side "
        "for HCM-007 and HCM-002. A logo supplies no property evidence.\n\n"
        f"VERIFIED_TRUE {m['VERIFIED_TRUE']}/20; VERIFIED_FALSE {m['VERIFIED_FALSE']}/20; "
        f"UNRESOLVED {m['UNRESOLVED']}/20. Resolved-only precision is1/3 and false "
        "fraction2/3; the precision Wilson95% reference interval is6.15–79.23%. "
        "These three selectively resolved cases do not estimate portal-wide precision, "
        "false-match rate, recall or an operating threshold. No held-out independently "
        "confirmed controls were available.\n\n"
        f"Location raises {m['location_gain_pairs']}/20 scores; the verified true case "
        f"has location gain in {m['verified_true_location_gain_pairs']} case(s). "
        "Neither a causal location benefit nor threshold validity is established. "
        "No ranking, merge, field-transfer or activation code changes.\n\n"
    )
    queue = "# Owner/manual evidence queue\n\nOnly unresolved cases. Do not send personal documents; a redacted unit plan, dated photo linkage or explicit publisher cross-reference is sufficient where indicated. No outreach was sent.\n\n"
    for r in reviews:
        text += (
            f"## {r['pair_id']} — {r['other_source']} — {r['verdict']}\n\n"
            f"Rank score {r['candidate_score']}; location gain {r['location_gain']}.\n\n"
            f"Harta: [{r['harta_source_id']}]({r['harta_url']}); raw{r['harta_raw_id']}; "
            f"checked {r['harta_checked_at']}.\n\n"
            f"Reference: [{r['other_source_id']}]({r['other_url']}); raw{r['other_raw_id']}; "
            f"captured {r['reference_captured_at']}.\n\n"
            f"{r['case_findings']}\n\nDecision/limit: "
            f"{' '.join(r['decision_evidence']) or r['uncertainty']}\n\n"
            f"Additional evidence: {r['additional_evidence']}\n\n"
            "<details><summary>Field, date, area, price-history and media provenance</summary>\n\n"
            "```json\n"
            + json.dumps(
                {
                    k: r[k]
                    for k in [
                        "harta_snapshot_fields",
                        "other_snapshot_fields",
                        "harta_current",
                        "harta_area_claims",
                        "other_area_claims",
                        "price_history",
                        "media",
                    ]
                },
                indent=2,
                ensure_ascii=False,
            )
            + "\n```\n\n</details>\n\n"
        )
        if r["verdict"] == "UNRESOLVED":
            queue += f"- **{r['pair_id']}** ([Harta]({r['harta_url']}), [{r['other_source']}]({r['other_url']})): {r['additional_evidence']}\n\n"
    (output / "matching_verification.md").write_text(text, encoding="utf-8")
    (output / "manual_review_queue.md").write_text(queue, encoding="utf-8")
    reliability = (
        "# Six-source reliability evidence\n\n"
        "All180 archived snapshots and1080 original six-field checks revisited. "
        "Detailed field_reviews.json records each old status, adjudication, source path, "
        "source/parsed/normalized value and reason. snapshot_reviews.json adds area "
        "claims, dates, missing source slots, location unknowns and inactive-price checks.\n\n"
        "Publisher real-world truth, physical location and historical claim correctness "
        "remain UNKNOWN for all180. Confirmed errors below concern representation of "
        "published information; internal source conflicts and placeholders are separate "
        "from real-world false claims. Missing extraction evidence never proves information "
        "was absent from the original listing. Explicit null/zero API slots are documented "
        "as slot missingness only, with narrative fallback and unverified alternatives retained.\n\n"
        "| Source | Reviewed | Parser-error cases | Normalizer-error cases | Source internal conflicts | Other pipeline issue | Unknown/noncomparable fields | Previous → replay quality | Weight |\n"
        "|---|---:|---:|---:|---:|---:|---:|---|---:|\n"
    )
    for s in assessment["sources"]:
        reliability += f"| {s['source']} | 30 | {s['parser_error_snapshots']} | {s['normalizer_error_snapshots']} | {s['source_conflict_snapshots']} | {s['inactive_zero_price_parser_issue_snapshots']} | {s['unknown_or_noncomparable_field_fraction']:.1%} | {s['previous_quality']:.6f} → {s['recomputed_quality']:.6f} | 1.00 inactive |\n"
    reliability += (
        "\nRows are diagnostic case counts/30, not population error rates; issue columns "
        "can overlap. Other pipeline issue is Pro-rks retaining an inactive zero-valued "
        "price alongside the active transaction price. Source-slot sentinels are in "
        "field counts, not in verified publisher error rates.\n\n"
        "Gjirafa: four descriptions explicitly quote unit prices; parsed totals use "
        "a100x heuristic rather than advertised area. Five sale-label/rent-narrative "
        "conflicts support the parser's rent choice, not a parser classification error. "
        "A1 m² placeholder is correctly rejected. A0 slot with85 m² in description "
        "is a supported fallback. One multiple-unit price remains unknown.\n\n"
        "Merrjep: automotive offers misclassified as apartments, a land offer and "
        "explicit sale/rental narratives with missing classifications show parser "
        "issues. Apartment/office dual-use ads are ambiguous, not proven parser errors. "
        "Zero JSON-LD values can coexist with positive display prices.\n\n"
        "MyRealEstate: an explicitly described350 m² house was parsed as apartment, "
        "and one explicit one-bedroom claim was omitted. "
        "Pro-rks: one explicit per-m² price was retained as total; one home taxonomy "
        "was changed to apartment by normalization. Its narrative markets multiple "
        "villas/apartments, so physical unit type stays unknown. Media-derived dates "
        "remain proxies, excluded from publication reliability.\n\n"
        "Topia: all30 apparent area agreements copy gross_area. None validates interior "
        "area; three contain different positive interior_area values. This is an area "
        "basis risk, not30 confirmed false source measurements. Vision: one explicit "
        "three-bedroom claim was omitted; unverified fields and a zero price placeholder "
        "do not establish publisher errors.\n\n"
        "Publication checks:141 dates agree with the source declaration,30 Pro-rks "
        "dates are media proxies and9 source dates remain unknown. No comparable date "
        "disagreement was found; source agreement still cannot establish actual first "
        "publication or active status. Street/neighborhood claims and all duplicate "
        "identities in the180-snapshot audit lack independent physical verification.\n\n"
        + assessment["sampling_caveat"]
        + "\n\nEach source has15 random_segment_stratum cases; enriched cases remain separate. "
        "Topia has5 failure-enriched and10 random-top-up cases; others have15 enriched. "
        "Sales/rental/unknown segment counts and every per-field numerator/denominator "
        "are in assessment.json. Binomial intervals are omitted for enriched/top-up "
        "strata and for publisher truth (zero independent trials).\n\n"
        "Policy1.1.0 replay uses the exact frozen140-day historical processed population "
        "and unchanged records. No new independently verified location/history inputs "
        "were gained; all six scores reproduce exactly. Usability scores include "
        "pipeline limitations and neutral imputation; they are not reputation rankings. "
        "Recent pending intake is not substituted for the historical processed population. "
        "All proposed weights remain1.00 because independent-location/coverage gates fail. "
        "No confidence interval for the provisional composite is invented.\n"
    )
    (output / "source_reliability.md").write_text(reliability, encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--calibration", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    evidence = load(args.evidence)
    for path, expected in evidence["source_inputs"].items():
        if hashlib.sha256(Path(path).read_bytes()).hexdigest() != expected:
            raise ValueError(f"Frozen source input changed: {path}")
    previous = load(args.calibration / "historical_processed/source_quality_report.json")
    records = TypeAdapter(list[QualityRecord]).validate_python(
        load(args.calibration / "pipeline_snapshot.json")
    )
    sources = sorted({s["source_name"] for s in previous["sources"]})
    replay = build_report(
        [r for r in records if r.outcome != "pending"],
        sources=sources,
        as_of=datetime.fromisoformat(evidence["as_of"]),
        window_days=140,
        segment=True,
        policy=QualityPolicy(),
    ).model_dump(mode="json")
    assessment = generate(evidence, previous, replay)
    args.output.mkdir(parents=True, exist_ok=False)
    save(args.output / "assessment.json", assessment)
    save(args.output / "field_reviews.json", evidence["field_reviews"])
    save(args.output / "snapshot_reviews.json", evidence["snapshot_reviews"])
    save(args.output / "policy_replay.json", replay)
    save(
        args.output / "source_weights_proposed_v1.json",
        {
            "version": assessment["calibration_method"],
            "policy": "1.1.0",
            "active": False,
            "sources": assessment["sources"],
            "harta": assessment["harta"],
        },
    )
    save(
        args.output / "input_receipt.json",
        {
            "evidence_sha256": hashlib.sha256(args.evidence.read_bytes()).hexdigest(),
            "source_inputs": evidence["source_inputs"],
        },
    )
    reports(evidence, assessment, args.output)
    print(json.dumps({"matching": assessment["matching"], "source_count": len(sources)}))


if __name__ == "__main__":
    main()
