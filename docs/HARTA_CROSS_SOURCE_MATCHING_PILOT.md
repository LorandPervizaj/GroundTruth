# Harta cross-source identity pilot and six-portal calibration

2026-10-22 · **Matching NOT ENABLED: insufficient identity evidence.**
The collector's earlier Gate 3 PASS does not authorize identity matching, field
transfer, source-weight activation or public inclusion.

## Frozen scope and review design

Snapshot: 2026-10-22 09:52:14.990338 UTC. Existing private research database,
repeatable-read/read-only. Harta remains 50 stored source identities; no crawl
expansion, ETL, merging or field updates occurred. The reference pool comprises
23,332 latest normalized apartment/studio identities across the six established
portals, including quarantined records for evidence review. Historical reference
snapshots and current Harta pages are not simultaneous observations.

The primary review contains 40 pairs with 40 distinct Harta anchors, including
37 quarantined Harta records. Counts: Gjirafa 5, Merrjep 12, Pro-rks 13, Vision 3,
Topia 4, Myrealestate 3. Each portal received at least three review cases; remaining
slots use highest-ranked unused anchors. Price/transaction/neighborhood/street
blocking and a 300-reference shortlist per anchor make this a bounded candidate
experiment, not exhaustive duplicate discovery or a probability sample.

Ranker inputs are price, defended interior area, rooms, floor, title and location.
Unclassified Harta surface_area does not count as interior agreement. Missing
fields never become positive evidence. Candidate scores are ranking points, not
identity probabilities. Shared street/building/pin alone cannot establish an
apartment. Ranking handles explicitly named letter streets such as Rruga A.
That correction replaced one pair before freezing the final frame; its original
review is retained as a nonprimary control. Total inspected pairs: 41; primary
gate denominator: 40. Cases are never pooled to manufacture precision.

All 40 primary Harta pages returned 200. References were independently read from
their existing raw snapshots; all had source description text. Full descriptions,
HTML, contacts and media are not saved by this experiment. Numeric/area/floor/unit
facts, source paths, raw IDs/timestamps, description hashes and overlap counts
provide private provenance. This is automated source-evidence extraction with
agent review of all pair-level evidence; no property-owner, independent human or
physical-location verification is claimed.

## Identity results and gate

| Result | Primary pairs |
|---|---:|
| Verified true matches | 0 |
| Verified false matches | 0 |
| Unresolved | 40 |
| Pairs receiving location ranking points | 21 |
| Shared normalized street | 1 |
| Conflicting structured claims | 13 |
| Verified field-transfer candidates | 0 |

No apartment-unit key or direct listing cross-reference linked a reviewed pair.
The longest shared description token run was seven words, which is not distinctive
unit proof. Thirteen pairs disagree on structured rooms/bathrooms/floor claims;
these are suspected mismatches, not verified false identities. Source errors,
different field definitions, time changes and stale advertisements can cause such
disagreements. One shared street and common prices/layouts do not resolve them.

**Precision and false-match rate are UNKNOWN**, not 0% or 100%. There are no
resolved identity labels from which to estimate those rates. Location raises
candidate scores but no verified identification or enrichment benefit is measured.
Neither recall nor portal-wide duplicate prevalence is estimated by this sample.

The predeclared pilot gate requires 30–50 reviewed pairs, at least 30 distinct
verified-true Harta anchors, verified-true support for at least 95% of all reviewed
proposals (unresolved never counts true), and zero verified false pairs. Unknown
labels and duplicate pairs are rejected. A passing result would authorize only
separately controlled research support; automatic merges, field transfer and
public-statistics changes remain disabled even in that state.

**Decision: NOT ENABLED.** Candidate code is an offline experiment and is not
wired into production deduplication or recurring jobs. Harta retains valuation
safeguards and candidate-only location provenance. Even a verified future identity
link would require a separate field-level check before transferring an address or
any other attribute. No unsupported interior values are imported from another ad.

The smallest useful next evidence is independently confirmed apartment-specific
unit identity or an explicit cross-portal property cross-reference for a bounded
review set, with positive and negative controls. A street/building list, higher
ranker score, more Harta scraping or repeated common layouts cannot supply that
ground truth. No administrator, publisher or property owner was contacted.

## Six established portals: calibration assessment

The six-portal evaluation ran separately with explicit source selection and policy
1.1.0. It assessed a 30-day recent intake and a 140-day historical window, keeping
pending intake separate from historical processed identities. It includes 180
stored-source checks (30 per portal), split into probability/failure-enriched
strata. These check extraction/representation, not independent publisher reliability;
failure-enriched cases are not pooled into population error rates.

Historical processed population (all property types in the evaluation):

| Portal | Unique processed | Accepted | Provisional usability score | Proposed weight |
|---|---:|---:|---:|---:|
| gjirafa | 4,594 | 4,315 | 75.517867 | 1.00 |
| merrjep | 17,572 | 14,747 | 68.392480 | 1.00 |
| myrealestate | 160 | 143 | 70.323090 | 1.00 |
| pro-rks | 4,271 | 3,214 | 69.275033 | 1.00 |
| topia | 516 | 513 | 75.622093 | 1.00 |
| vision | 113 | 98 | 68.927974 | 1.00 |

Every proposed weight remains **1.00 inactive**, with insufficient independent
measurement coverage/location verification. Publisher history and independent
location correctness remain UNKNOWN across the six. This completes a calibration
readiness assessment, not validated non-neutral weighting. Source differences in
pipeline usability must not be presented as verified publisher reputation.

The recent intake has different pending/composition rates and Vision has no
observations in that 30-day cohort; its recent score is UNKNOWN, not zero.
Historic processed scores therefore are not substituted into recent intake rates.
The offline representative-selection experiment is saved separately; any winner
changes there come from listing quality, not an activated source weight.

Harta is excluded from the six-source calibration population and evaluated
separately at the same snapshot: 50 identities, 3 accepted, 47 quarantined,
provisional 48.815, proposed weight 1.00 inactive. Existing source priorities,
validation thresholds, parser allowlists and public market statistics are unchanged.

## Reproduction, artifacts and QA

Candidate/gate replay, with no network or DB access:

```powershell
.venv/Scripts/python.exe scripts/research/harta_matching_pilot.py --snapshot .tmp/harta-matching-pilot/candidate_pool_private.json --reviews reports/generated/harta/matching_pilot/pair_reviews_private.json --calibration reports/generated/source_quality/six_portal_calibration_095214 --output reports/generated/harta/matching_pilot/pilot_assessment.json
```

Six-source assessment (use a new empty output folder and the exact ISO timestamp):

```powershell
.venv/Scripts/python.exe scripts/research/evaluate_source_quality.py --as-of "2026-10-22T09:52:14.990338+00:00" --sources gjirafa merrjep pro-rks vision topia myrealestate --output reports/generated/source_quality/six_portal_calibration_replay
```

Private evidence: `reports/generated/harta/matching_pilot/`, including final and
initial pair reviews, frozen gate, Harta quality and preservation audit.
Six-portal assessment: `reports/generated/source_quality/six_portal_calibration_095214/`.
Inputs, exact snapshot SQL and logs: `.tmp/harta-matching-pilot/`.
Executed companion: `reports/research/harta_matching_pilot.ipynb`.
No source descriptions, listing IDs, contact fields or private credentials enter Git.

Full suite: **902 passed, 45 skipped, 1 unchanged pre-existing failure**,
3 warnings, 55.43 seconds. The existing PowerShell runner test expects literal
`exit $LASTEXITCODE`; its pre-existing dirty implementation uses `exit $result`.
Focused matching tests: 8 passed; broader matching/Harta/quality regression:
161 passed. Ruff and format checks cover the four changed Python files.
Database counts/high waters are unchanged in all six pipeline tracking tables,
and all 360 pre-existing modified/untracked file hashes are preserved. No push,
deployment, source activation, record merges or field transfer occurred.
