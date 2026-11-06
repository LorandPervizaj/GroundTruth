# Part 2 — real source quality evaluation

**Evaluation date: 2026-10-21. Overall status: COMPLETE. Gate 2: PASS for an explicitly provisional assessment with neutral proposed weights.**

This is a real research-PostgreSQL evaluation, not the Part 1 fixture. No source
received independently verified publisher-location/history status, and no source
weight was activated. This report does not establish a definitive ranking of six
publishers. Original policy 1.0.0 results remain in the private generated directory
`reports/generated/source_quality/part2/evaluation/`; corrected results use `final/`.

## 1. Dataset baseline and reconciliation

Confirmed the documented local research container, existing persistent volume, and
loopback port before connecting. Docker Desktop and the existing stopped research
container were started without recreating or initializing storage. Azure was never
contacted. PostgreSQL 16.4 was queried through repeatable-read, **READ ONLY**
transactions; `transaction_read_only` was checked at entry and exit.

- As of: **2026-10-21 00:00:00 UTC**.
- Primary observation window: **2026-09-21 through 2026-10-21**, inclusive.
- Historical comparison: **2026-06-03 through 2026-10-21**, inclusive, 140 days.
- Snapshot identity: `fd07c4c07c930ebb696bb7d02f009b16d4124e8289637f1811437805e1514db9`.
- Scoring policy and report version: **1.1.0**; original policy 1.0.0 retained.

| Table | Rows | Maximum ID |
|---|---:|---:|
| raw_listings | 65,631 | 76,701 |
| parsed_listings | 63,588 | 312,381 |
| normalized_listings | 63,585 | 312,364 |
| invalid_listings | 9,445 | 30,475 |
| scrape_runs | 205 | 216 |
| etl_metrics | 219 | 283 |

Live column names/types were captured. Required tables exist. There are **zero**
unlinked quarantine records, parsed rows without raw parents, or normalized rows
without parsed parents. Quarantine contains 9,442 validation records and three
normalization failures; there are no stored parse-stage rejection rows. This does
not prove that every discovery/request/parse attempt succeeded: failures with no
stored listing cannot enter this listing-level denominator.

| Source | Historical raw versions | Unique source IDs | Latest stored raw capture |
|---|---:|---:|---|
| Gjirafa | 21,498 | 4,596 | 2026-10-18 |
| Merrjep | 32,489 | 17,754 | 2026-10-05 |
| Pro-rks | 7,724 | 4,400 | 2026-10-18 |
| Vision | 223 | 113 | 2026-08-17 |
| Topia | 1,975 | 560 | 2026-10-18 |
| MyRealEstate | 1,722 | 160 | 2026-10-18 |

The recent window contains **10,280 raw versions and 8,539 unique source IDs**;
1,741 repeated versions do not increase scoring sample sizes. The historical
intake contains **27,583 unique IDs**; the historical completed-processing cohort
contains **27,226**, including rejected records. Latest raw identity and latest
completed processing are separate populations; their scores must not be pooled.

Run counters are observations, not independent properties or necessarily new raw
inserts. ETL totals overlap reprocessing, and raw content-hash uniqueness suppresses
unchanged recrawls. Consequently run totals, raw versions, unique identities,
normalized rows, and canonical groups have separate denominators. All outcome
counts reconcile to unique identities, and sale/rent/unknown segments partition
each source's total. No fixed-priority winner selection feeds source scoring.

The primary population includes pending records, which can be intentionally
age-filtered rather than parser failures. ETL metrics contain age skips, including
157 for MyRealEstate and 393 for Topia across stored run metrics; those overlapping
run counts cannot identify or explain every pending identity. Vision has seven
recent completed crawl records despite no new raw version in the recent window.
Its old stored capture date does not establish that the crawler never ran.

## 2. Source comparison

**Recent intake; all categories/outcomes. Scores are provisional, not publisher
truth. Criterion averages use measured records only; the composite includes unknown
records with neutral imputation. Coverage is measured criterion coverage, not a
statistical confidence interval.**

| Source | Unique IDs | Accepted / rejected / pending | Quality | Validity | Completeness | Location accuracy | Coverage | Proposed weight |
|---|---:|---|---:|---:|---:|---|---:|---:|
| Gjirafa | 1,279 | 1,010 / 68 / 201 | 75.67 | 93.69 | 92.06 | UNKNOWN | 58.34% | 1.00 |
| Merrjep | 5,941 | 4,904 / 636 / 401 | 74.58 | 88.00 | 88.27 | UNKNOWN | 61.89% | 1.00 |
| Pro-rks | 726 | 112 / 6 / 608 | 54.16 | 94.92 | 84.96 | UNKNOWN | 9.75% | 1.00 |
| Vision | 0 | 0 / 0 / 0 | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | 0% | 1.00 |
| Topia | 435 | 27 / 0 / 408 | 52.05 | 100.00 | 93.75 | UNKNOWN | 4.34% | 1.00 |
| MyRealEstate | 158 | 1 / 0 / 157 | 50.21 | 100.00 | 93.75 | UNKNOWN | 0.44% | 1.00 |

Topia/MyRealEstate's 100% validity figures describe only 27/1 measured outcomes;
they do not establish the validity of hundreds of unprocessed latest records.
Recent Vision status is `no_data`, while its historical data remain assessable.

The historical completed-processing cohort gives a more useful view of the
existing parsers, with different source ages explicitly retained:

| Source | Unique processed IDs | Quality | Validity | Completeness | Consistency | Publication freshness |
|---|---:|---:|---:|---:|---:|---|
| Gjirafa | 4,594 | 75.55 | 93.93 | 91.86 | 98.31 | 43.84 |
| Merrjep | 17,572 | 68.42 | 81.72 | 85.38 | 96.35 | 37.14 |
| Pro-rks | 4,271 | 69.28 | 75.25 | 84.63 | 90.27 | UNKNOWN |
| Vision | 113 | 68.93 | 86.73 | 90.87 | 96.19 | 1.36 |
| Topia | 516 | 75.64 | 99.42 | 93.73 | 100.00 | 20.45 |
| MyRealEstate | 160 | 70.33 | 89.38 | 91.37 | 99.67 | 1.77 |

Sales/rentals/unknown have separate machine-readable summaries in all three
cohorts. These mixed-category overall tables are not a category-controlled causal
comparison. The selection simulation below uses only eligible apartments/studios
and reports apartment sales/rentals separately on identical candidate records.

## 3. Findings, attribution, and verification

**Publication provenance — confirmed pipeline issue, high confidence.** Pro-RKS's
parser derives listing dates from image `createdAt`/media paths and can fall back
to scrape time (`processing/parsers/pro_rks.py`, `services/parsing.py`). Policy 1.0.0
incorrectly treated every normalized date as publication. Policy 1.1.0 adds explicit
date origin: Pro-RKS dates remain proxy/unknown for publication freshness and do
not count as publication completeness. New undocumented adapters default to unknown.
The six dimension weights, neutral imputation 50, and eligibility thresholds are
unchanged. In the processed cohort, Pro-RKS changes from 68.07 to 69.28 because
neutral imputation replaces its low proxy-date freshness; this is not new evidence
that the publisher improved. Its proposed weight stays 1.00.

**Area semantics — confirmed extraction choice, interpretation unresolved.** Topia
copies `gross_area` into `area_sqm`. Both gross/interior fields exist in all 30
sampled records and differ in **28/30**. Agreement with the selected gross field
does not verify living area. Record and normalize area semantics before making
stronger comparisons of asking €/m². The current parser/production figures were
not changed during this assessment.

**Price/type failures — pipeline defects and source assertions must be separated.**
In the processed cohort, Merrjep has 5,222 missing areas, 397 missing transaction
types, and 1,103 unavailable active prices among 17,572 identities. All five
sampled Merrjep missing-price flags also have unknown parsed transaction type;
this is a classification dependency, not proof that the publisher omitted price.
Gjirafa has sampled price/discovery-type disagreements requiring contextual review;
these are not automatically publisher inaccuracies. A Pro-RKS type discrepancy
arises after normalization, where `refine_property_type` can deliberately override
the API category. Source-structured zero placeholders are distinguished from
verified incorrect asking prices. No heuristic flags were imported into publisher
historical reliability or independently verified location scoring.

The Pro-RKS follow-up examined **741 persisted price-conflict cases** on latest
historically processed identities. **696/741** source records mark a single market
and use zero in the inactive price field; all 741 expose both API price fields.
`ProRksParsingService` preserves zero as a price and `ListingValidator` rejects both
fields being non-null. This is a confirmed pipeline representation problem, not
evidence that those publishers supplied two contradictory asking prices. The other
45 cases and two additional conflicts found by current revalidation remain qualified.
Prioritize inactive-price normalization in a separate tested parser remediation;
do not rewrite historical results, relax validation, or assign publisher errors.

**Address precision — substantial gap, high confidence.** All six processed cohorts
have zero resolved street IDs, despite source-side address hints. Gjirafa and
Merrjep coordinates are predominantly neighborhood centroids; Pro-rks, Topia and
Vision also expose `source_coords`, which remain source assertions. Neither a
centroid nor a precise-looking coordinate establishes physical accuracy. Historical
processed neighborhood coverage is 22 for Gjirafa/Merrjep/Pro-rks, 18 for Topia/
MyRealEstate, and 15 for Vision. Separate lifecycle rows provide first/last-seen
coverage for four sources; these dates are not publication evidence.

**Coverage — useful contributions, not proven property uniqueness.** Among comparable
historical processed listings, no cross-source candidate match was found for 5,887
Merrjep, 2,770 Pro-rks, 2,188 Gjirafa, 367 Topia, 98 MyRealEstate, and 52 Vision
records. These are nonmatched candidates, not verified unique properties. Candidate
blocking misses duplicates with missing/different key fields. Within-source exact
content-hash excess is zero in these latest-identity cohorts; that does not rule
out same-property duplicates using different content or IDs.

**Verification method and limits.** Reviewed **180 stored-source snapshots, 30 per
source**, from latest historical completed processing. Samples contain reproducible
segment-stratified random cases and separately labeled failure-enriched cases;
Topia needed random top-ups because fewer enriched cases were available. All 180
sample identities agree with their stored source identifier. Direct API/JSON-LD/
HTML fields and explicit property nouns/taxonomy support field checks. Agent review
covered rules, disagreement predicates, missing-classification dependencies, date
provenance, and area semantics. No independent human labeling, physical location
verification, or current live-page/active-status verification is claimed. Unknown
fields remain unverified. A failure-enriched sample cannot estimate a source-wide
publisher error rate. Original golden data contain 901 labeled parser rows but do
not independently establish source-origin historical errors.

Per-case audit IDs, local raw-record IDs, evidence paths, strata, and safe review
predicates are retained privately in `source_quality_audit_checks.json`; no raw
descriptions, contact details, or asking values appear in that audit output.

Prioritize separate remediation for area semantics, price/type dependencies,
inactive-market zero prices, street resolution, and pipeline filtering observability. None requires relaxing
validator bounds or automatically promoting a portal's reputation.

## 4. Proposed weights and sensitivity

All six sources retain **1.00, INSUFFICIENT EVIDENCE, PROPOSED — NOT ACTIVE**.
Independent location/history measurement is unknown; observed coverage never
reaches the default 90% eligibility threshold. The recent sources with many pending
identities additionally fail processing coverage. No-data Vision cannot be weighted
from a nonexistent recent sample. No eligibility condition was bypassed.

The versioned configuration is
`evaluation/source_quality/source_weights_proposed.json`; it includes source,
segment, actual score/null, policy version, snapshot identity, weight status, and
all failed eligibility conditions. It has no runtime consumers added by this work.

Fifteen sensitivity scenarios retain baseline dimension weights or vary one by
±10% with renormalization, and test unknown imputations 40/50/60. Recent provisional
ordering is unchanged across these scenarios, but it is dominated by processing
coverage. Historical Topia/Gjirafa swap first/second, and Pro-rks/Vision swap
fourth/fifth. Do not select a definitive winner from these near ties. Merrjep's
processed score remains sixth, with attribution uncertainty. Sale/rent orders and
the minimum-30-sample subset are reported separately; volume is not a quality bonus.
Requiring at least 30 measured validity outcomes excludes recent MyRealEstate and
Topia; the retained recent score order is Gjirafa, Merrjep, Pro-rks. This sensitivity
changes inclusion, not the quality scores or eligibility policy.

## 5. Offline representative-selection impact

Used **10,816 identical eligible apartment/studio records**, producing 7,231
canonical representatives and **748 duplicate groups** with the existing matcher.
The current arm uses existing priority/confidence/normalized-ID selection. The
proposed arm uses listing quality, then the proposed source weight, completeness,
precision and deterministic source/ID ties. Eligibility and grouping are unchanged.

| Measurement | Current | Simulated |
|---|---:|---:|
| Groups changing representative | — | 339 / 748 |
| Mean quality | 78.920677 | 79.021044 |
| Mean completeness | 90.138466 | 90.099571 |
| Mean geographic precision | 46.360116 | 46.360116 |
| Median apartment sale asking €/m² | 1452.631579 | 1453.488372 |
| Median apartment rent asking €/m² | 5.392157 | 5.387960 |
| Known invalid winners | 0 | 0 |

All weights are neutral, so weight-versus-listing-quality conflicts are zero and
this is primarily a listing-quality experiment. Mean quality improves slightly,
completeness declines slightly, and asking medians move marginally. **Benefit is
inconclusive. Do not activate.** Existing candidate groups are not a complete or
independently verified duplicate truth set. No release artifacts were regenerated.

## 6. Executed commands and QA

```powershell
# Complete read-only evaluation; original policy 1.0.0 outputs were retained separately.
.venv/Scripts/python.exe scripts/research/evaluate_source_quality.py --as-of 2026-10-21T00:00:00Z --days 30 --history-days 140 --output reports/generated/source_quality/part2/final

# Actual policy 1.1 CLI pilot against the verified local research connection.
.venv/Scripts/groundtruth.exe analytics source-quality report --as-of 2026-10-21T00:00:00Z --days 30 --source pro-rks --segment --output reports/generated/source_quality/part2/pilot-policy1_1

# Offline reproduction and report validation from saved real inputs; no DB required.
.venv/Scripts/python.exe scripts/research/validate_source_quality.py --output reports/generated/source_quality/part2/final --repeat reports/generated/source_quality/part2/reproduced
```

The CLI pilot exited 0 and produced four segment summaries for 726 real identities.
An earlier Gjirafa policy 1.0 pilot successfully evaluated 377 real identities.
The output validator returned PASS: all six sources/24 summaries, correct outcome
and segment denominators, 180 unique sampled checks, bounded scores, neutral
ineligible weights, valid JSON/CSV, no NaN/Infinity, and **byte-identical JSON, CSV,
and schema** after offline regeneration from the frozen real-data inputs.

New/existing source-quality tests: **58 passed**.

```powershell
.venv/Scripts/python.exe -m pytest tests/test_source_quality_evaluation.py tests/test_source_quality.py tests/test_source_quality_reporting.py tests/test_validation.py tests/test_confidence.py tests/test_parser_kpis.py tests/test_portal_registry.py tests/test_normalizers.py tests/test_pipeline_failure_safety.py tests/test_corpus.py tests/test_corpus_authority.py tests/test_cross_dedup.py tests/test_source_skew.py tests/test_parsing.py tests/test_merrjep_parser.py tests/test_pro_rks_parser.py tests/test_vision_parser.py tests/test_topia_parser.py tests/test_myrealestate_parser.py -q --tb=short
```

Focused regression result: **143 passed**, including parser, normalization,
validation, registry, corpus, cross-dedup, and ETL failure safety tests. The isolated
SQLite pipeline-model test now enforces exactly two batched queries, preventing
hidden deferred HTML/description loads. PostgreSQL execution was tested through
the explicit read-only evaluation and CLI, never through pytest's private-DB access.

```powershell
.venv/Scripts/python.exe -m pytest -q -rs --tb=short
.venv/Scripts/python.exe -m ruff check src/groundtruth/analytics/source_quality*.py scripts/research/evaluate_source_quality.py scripts/research/validate_source_quality.py tests/test_source_quality*.py
.venv/Scripts/python.exe -m ruff format --check src/groundtruth/analytics/source_quality*.py scripts/research/evaluate_source_quality.py scripts/research/validate_source_quality.py tests/test_source_quality*.py
```

Full suite: **799 passed, 45 skipped, one pre-existing failure**, three deprecation
warnings. The unchanged failure is the weekly-runner test in
`tests/test_home_trust_snapshot.py`: its expected literal `exit $LASTEXITCODE` differs
from the existing `scripts/run_weekly.ps1` implementation using `exit $result`.
Skips comprise 27 tests requiring an unavailable dedicated test database, ten
opt-in browser tests, and eight bash/jq watchdog tests. Ruff lint passes and all
ten changed Python files are formatted. No regression was suppressed or weakened.

## 7. Files, privacy, and Git preservation

Started from `69b759027505679d20f4cd4ded27e30adc0b0b02` on
`codex/source-quality-calculator`, with 252 pre-existing status entries. Created
`codex/source-quality-evaluation` without discarding work. All 242 initially modified
tracked files retained their pre-work hashes through QA; unrelated changes remain
outside this commit. The earlier plan and README link are preserved.

Implementation inventory:

- New `analytics/source_quality_evaluation.py` and `source_quality_audit.py`.
- New `scripts/research/evaluate_source_quality.py` and `validate_source_quality.py`.
- Updated `analytics/source_quality.py`, `source_quality_models.py`, and `source_quality_population.py` for explicit date origin and narrow batched queries.
- Updated source-quality fixture/tests; new `tests/test_source_quality_evaluation.py`.
- Updated scoring documentation, this Gate 2 evidence, and the inactive aggregate weight configuration.

The generated real reports and private scoring-input snapshot remain under ignored
`reports/generated/source_quality/part2/final/`. Git contains only code, synthetic
tests/fixtures, aggregate evidence, and the inactive aggregate proposed configuration.
No real credentials or connection strings, private descriptions, contact data, or individual listing
values are staged. No frontend, Azure configuration, production services, live
dedup priorities, corpus filters, published medians, valuations, or release artifacts
were changed. No migrations, new crawl, scraper, Harta work, or push occurred.
The implementation commit is identified in this chat's completion response and
`git log -1` on this branch; only the inventory above belongs to it.

Required private artifacts: primary report/CSV/schema; baseline; diagnostic JSON;
verification Markdown and case checks; sensitivity JSON; proposed weights; impact
JSON/Markdown; policy comparison; collection review; QA results; historical intake
and processed reports; and the redacted scoring snapshot for reproduction.

## 8. Gate decision and Part 3 readiness

**PASS for Part 2's evidence-backed assessment.** Actual PostgreSQL reads succeeded,
all six sources were assessed with recent-data absence explicit, failed/pending/
rejected populations remained visible, repeated versions did not inflate listing
counts, 180 stored snapshots were reviewed with uncertainty preserved, policy
sensitivity and offline impact were assessed, required focused QA passed, and
generated report content is reproducible. No trustworthy non-neutral publisher
weights or verified location/history measurements are claimed. The unrelated
full-suite failure and interpretation gaps remain explicit.

Part 3 may begin with policy 1.1.0 and neutral initial Harta weight. It must preserve
stable source IDs, raw provenance, rejected outcomes, transaction/category identity,
living-versus-gross area semantics, explicit publication/update/observation dates,
and location precision separate from independently verified accuracy. Existing
parser/address follow-ups and human/physical verification remain separate work;
they do not justify preferential Harta scoring or activating these proposed weights.
Harta integration has not started.
