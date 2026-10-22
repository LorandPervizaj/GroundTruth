# GroundTruth — read-only historical unit-price impact

2026-10-22 · **Assessment complete. Persistent remediation NOT APPROVED.**

Reference: [unit-price code correction](UNIT_PRICE_ARITHMETIC_REMEDIATION.md).
This document is the reference for this chat's historical-impact assessment.
The four-case code fix does not update historical database rows.

## Snapshot, grain and coverage

Private loopback research database `rema`, port15432. Capture used a repeatable-read,
read-only transaction at **2026-10-22 12:59:48.667638 UTC**. No ETL job, SQL writer,
scraper, Azure operation, public cache refresh or deployment was run.

All **21,498 Gjirafa raw versions / 4,596 distinct listing IDs** were scanned,
without date, active, quarantine, property-type or corpus filters. Every historical
version remains distinct; counts of versions must not be read as counts of homes.
The frozen projection includes all **63,686 normalized versions across all sources**.

The corrected description-unit syntax appears in741 raw versions /363 listing IDs.
The old and corrected parser methods disagree on621 of those raw versions.
All candidates replayed successfully; zero processing errors. Multiple parsed
attempts explain why621 raw versions correspond to659 affected normalized rows.
The first adapter pass had an uppercase/lowercase enum mismatch and was discarded;
the assessment now stops if any candidate processing error remains.

Another217 raw versions /138 disjoint listing IDs contain broader unit syntax.
Combined screening covers958 versions /501 IDs, but those217 are not silently
included as confirmed corrections. Their source tokens include `€uro`, `per/për m²`,
emoji-separated currency/units and bare `/m²`. One loose adjacency match also
requires discrimination. The existing correction does not handle these spellings.
There may be further unrecognized representations outside these explicit screens;
the supported impact is a **lower bound**, not proof that every price error is found.
Twenty-eight of those138 alternate-syntax IDs are currently selected active source
rows; they are not included in the71 affected rows calculated from the existing fix.

Source descriptions were minimized to relevant fields and contact patterns redacted
for private replay inputs. Original content hashes and description hashes retain
provenance. No original photographs or contact details enter Git.

## Persisted values versus corrected arithmetic

**659 normalized versions /301 listing IDs** would differ from stored prices:

| Classification | Normalized versions | Distinct source IDs |
|---|---:|---:|
| Explicit source-supported arithmetic totals |403|206|
| No defensible total: price must remain missing/quarantined |256|95|

The403 arithmetic calculations include **one source-unit outlier**: raw23992,
normalized272603. Its literal claim produces €5,747,000 / €82,100 per m² and the
unchanged validator rejects it as `price_per_sqm_too_high`. It is already excluded
and is held for source review, rather than described as a verified plausible value.

The approval manifest therefore separates **402 price-only correction candidates**,
**256 missing-total quarantine candidates**, and **1 outlier on hold**. It authorizes
none of them. Four hundred of the402 currently pass persisted validity; two already
have exclusions that must remain. Of the256 missing-total cases,250 currently pass
persisted validity and6 already have exclusions. No existing rejection is removed.

There are71 affected **currently selected active source rows**:44 price corrections
and27 newly excluded missing-total rows. This differs from429 eligible historical
versions: SQL filters rows before choosing the latest eligible row per source ID.
Older eligible versions could reappear after quarantine, so all versions were
modelled. No such fallback appears for the27 removed source selections in this run.

The original four records still contain the old values in the database:

| Raw ID | Stored total | Dry-run total |
|---|---:|---:|
|26890|€130,000|€104,000|
|27285|€85,000|€51,000|
|45140|€115,000|€94,300|
|76665|€140,000|€189,000|

These are asking-price arithmetic corrections from source claims. No independent
transaction-price, ownership, physical-location or interior-area certification is
implied. Missing/ambiguous net, gross, terrace or multiunit evidence stays unresolved.

## Conditional corpus and analytics impact

This is a **price-only, in-memory projection onto existing normalized rows**.
Stored location, area, bedrooms, confidence, dates, versions, weights and exclusion
states are preserved. Current validation is applied before/after the price projection;
newly introduced issues exclude rows, while unrelated pre-existing problems are
reported without silently promoting or repairing records. A whole-ETL replay could
change additional fields and is not equivalent to this bounded scenario.

The existing corpus filters use the unchanged parser allowlist,12-month cutoff
**2025-10-22**, persisted validity exclusions and latest eligible source rows.
The existing cross-source deduplication runs offline at its unchanged threshold85.
No new matching or deduplication behavior is activated.

| Measure | Stored baseline | Counterfactual |
|---|---:|---:|
| Active source rows before cross-source dedup |15,648|15,621|
| Canonical active rows after existing dedup |11,744|11,730|
| Sale input rows before apartment-specific comparable selection |3,094|3,082|

Cross-source representatives change as prices enter different duplicate blocks:
29 baseline canonical normalized IDs leave and15 existing IDs become representatives.
Those are offline selection changes, not new records, merges or activated matches.
Other portals' prices remain untouched; their representative selection can change.
Harta remains outside the public parser allowlist and has zero active source rows.

### Neighborhood asking-price medians

The table uses the frozen canonical corpus, separately for sale apartments and
stored neighborhood assignments. It is an offline descriptive assessment, not a
rebuild of Metrik's published releases. The IDs/names are resolver assignments,
not independently verified physical locations.

| Neighborhood | Listings before → after | Median asking total | Median asking €/m² |
|---|---|---|---|
| Dardania | 148 → 149 | €121,500 → €120,000 | €1,950.00 → €1,950.00 |
| Arbëria | 181 → 177 | €145,000 → €146,000 | €1,580.94 → €1,580.94 |
| Qendra | 175 → 170 | €150,000 → €152,500 | €2,003.79 → €2,007.58 |
| Bregu i Diellit | 252 → 253 | €120,000 → €120,000 | €1,666.67 → €1,658.34 |
| Veternik | 574 → 572 | €125,000 → €125,000 | €1,248.32 → €1,247.83 |
| Emshir | 288 → 285 | €124,000 → €124,000 | €1,482.12 → €1,482.76 |
| Spitali | 126 → 123 | €130,000 → €130,000 | €1,428.57 → €1,423.06 |
| Qafa | 42 → 41 | €160,500 → €160,000 | €2,078.65 → €2,078.65 |
| Matiqan | 884 → 888 | €124,000 → €123,000 | €1,400.00 → €1,394.94 |

Nine named apartment-neighborhood groups change in count or a median. A separate
unknown-neighborhood apartment group and an `OTHER` property group of only two
records also change. The latter's €188,000 median-total shift is not a reliable
apartment-market estimate and is not included as such above.

### Valuation-input sensitivity

The assessment reuses sale-input bounds, `select_comparables`, area weights and
the weighted point calculation from the current model. A fixed grid uses16 touched
neighborhoods × six areas (50,70,90,110,130,150 m²), with bedrooms unspecified.
It is a diagnostic grid, not every possible request, and does not recompute public
confidence intervals or publish new valuation results.

**40/96 grid points change**, with no30-comparable readiness transition on this grid.
Largest observed change: **Qendra,90 m²**, €211,983.90 → €219,772.69,
**+€7,788.80 (+3.67%)**, using44 →41 comparables and the same ±10m² selection tier.
This is the largest sampled change, not a worst-case bound over all properties.
Modest overall median changes therefore do not establish negligible model impact.

## Review-ready artifacts and separate approval gate

Private outputs under `reports/generated/unit_price_historical_impact/reviewed/`:

- `impact_private.json`:741 raw reviews,659 persisted before/after decisions,
  neighborhood comparisons, valuation grid and frozen-input fingerprint.
- `remediation_review_manifest_private.json`: exact normalized/parsed/raw IDs,
  old/new values, existing/new validation codes, current source-primary flags,
  row fingerprints and the three proposed review batches. **REVIEW_ONLY_NOT_APPROVED**.
- `unresolved_review_queue_private.json`:95 source IDs with unresolved area/total,
  the held outlier, and217 alternate-syntax candidates. No values are invented.
- `CURRENT_ACTIVE_REVIEW.md`: a human-readable71-row table with source links,
  stored/proposed totals and proposed quarantine outcomes.

Manifest SHA-256:
`b6126ad97dd3c60f95798eba3af132062f0445e1b76ceae1857e17d90c06b4cf`.

Frozen source/projection inputs and preservation evidence remain in the parent
directory. The preliminary failed adapter output is explicitly invalidated and
is not an assessment. The [executed notebook](../reports/research/unit_price_historical_impact.ipynb)
provides inspectable aggregate calculations without database access.

File-only reproduction, choosing a new output directory:

```powershell
.venv/Scripts/python.exe scripts/research/unit_price_historical_impact.py --snapshot reports/generated/unit_price_historical_impact/frozen_inputs_private.json --dedup-threshold 85 --output reports/generated/unit_price_historical_impact/new_replay
```

**No persistent remediation is approved or implemented by this task.** A later
approval should identify the exact manifest hash and approved batch(es), with:

1. A restorable private backup and tested restore route, plus exact before-images
   of normalized, parsed, provenance, validation and dependent lineage state.
2. Code/input hashes and old-value/fingerprint preconditions; abort on unexpected
   state instead of overwriting newer work.
3. One audit identifier per batch, transaction boundaries, idempotent skip of
   already-applied targets and no whole-source destructive reprocessing.
4. Explicit preservation of existing exclusions, and scoped quarantine records
   for missing totals. The source-unit outlier stays on hold.
5. Post-write invariants and an exact rollback: restore backed-up values and
   remove only this batch's audit/quarantine additions. Preserve all earlier history.
6. Separate review before any public statistics rebuild or deployment.

The217 syntax candidates need a bounded source-evidence/parser-extension task;
do not bulk-apply guessed totals to them. The95 ambiguous IDs can remain quarantined
until listing-specific area-basis evidence exists. Revised golden labels from the
earlier task are not used as independent truth in this database assessment.

## QA and preservation

- Focused projection, arithmetic, cross-dedup, corpus and validator tests:
  **49 passed in3.41s**.
- Full suite: **931 passed,45 skipped,1 unchanged pre-existing failure**,
  3 warnings,58.57s. The known weekly-runner test still expects literal
  `exit $LASTEXITCODE`; the pre-existing runner uses `exit $result`.
- Ruff check/format pass for the three task Python files.
- Read-only verification: six pipeline table counts/high waters unchanged;
  all **63,686 persisted normalized/eligibility projections** match the snapshot.
  Initial full table digests are recorded, but final verification does not claim
  a second byte-level comparison of every raw HTML value.
- All **360 pre-existing modified/untracked files** retain their hashes.
- No source-quality policy1.1.0, weight, registry, parser, Harta setting, published
  Metrik artifact or Azure configuration changes. No push or deployment.

**Decision:** the historical issue is material enough to justify a separately
reviewed remediation. Preserve the approval boundary; do not rebuild public market
outputs as part of the database correction.
