# GroundTruth — unit-price arithmetic remediation

2026-10-22 · **Completion gate: PASS**

This implements the four-case follow-up from
[independent evidence verification](INDEPENDENT_EVIDENCE_VERIFICATION.md).
No persisted listing records were reprocessed or updated.

## Source-to-pipeline trace and actual results

All four archived records are Gjirafa sales. The literal `price_raw` amounts are
euro rates; their descriptions explicitly quote those same amounts per m² and
give one matching advertised area. `PriceNormalizer` correctly extracted the
numbers. `ParsingService._fixup_sale_price` then ignored their units and applied
the legacy 100× shorthand. `NormalizationService` preserved that erroneous total
and divided it by area. All old totals passed the existing sanity bands, so
validation alone could not detect this arithmetic error.

| Case / archived raw ID | Source rate | Advertised area | Parsed and normalized total before | Parsed and normalized total after | Normalized €/m² before → after | Validation before → after |
|---|---:|---:|---:|---:|---:|---|
| UP-01 / 26890 | €1,300/m² | 80 m² | €130,000 | **€104,000** | 1,625 → 1,300 | Valid → valid |
| UP-02 / 27285 | €850/m² | 60 m² | €85,000 | **€51,000** | 1,416.67 → 850 | Valid → valid |
| UP-03 / 45140 | €1,150/m² | 82 m² | €115,000 | **€94,300** | 1,402.44 → 1,150 | Valid → valid |
| UP-04 / 76665 | €1,400/m² | 135 m² | €140,000 | **€189,000** | 1,037.04 → 1,400 | Valid → valid |

These are source-supported asking-price calculations, not verified transaction
values. The areas remain source-advertised areas with their original semantics;
the correction does not certify them as net/interior or gross. No conversion
between area bases occurs. UP-02's separately priced optional €6,000 garage is
not added to the apartment total. Currency extraction/conversion was not the
cause, and all four remain EUR.

Minimized literal regression evidence, raw IDs and expected totals are in
`tests/fixtures/unit_price_arithmetic.json`. Full source references and field
adjudications remain in the earlier private verification artifacts.

## Narrow correction and quarantine

The Gjirafa sale fallback recognizes explicit euro-per-m² claims before applying
the old shorthand. The extracted scalar price must match the quoted rate, and
there must be one unique positive narrative area matching the parsed area.
Multiplication uses Decimal arithmetic and cent rounding. No other portal's
price parser or shared price/currency/area normalizer changes.

Missing area, distinct net/gross or terrace components, multiple unit areas,
conflicting structured/narrative areas, multiple rates or approximate areas
cannot establish a single total. The rule leaves `sale_price` unset; the existing
validator emits `missing_price` and the normal ETL path quarantines it. Each of
the four fixtures has a missing-area counterfactual proving this behavior.

Existing total prices and unrelated material rates are not reinterpreted as
apartment unit prices. Legacy shorthand without a matching explicit unit claim
and the rental path retain their behavior. Provenance uses `PRICE-006` for the
supported calculation and `PRICE-007` for an unresolved unit-price total.
The parser registry/version allowlist is unchanged to avoid altering public
corpus inclusion; the new provenance rules identify this correction. Applying
it to existing persisted records would require a separate, explicitly scoped
reprocessing operation.

## Golden fixture findings

The first full regression run exposed stale golden labels that encoded the same
100× assumption, including UP-04. Investigation also caught an unrelated tile
rate and an overly broad approximation-word check; both were corrected before
the final run. A rate must match the extracted price, and approximation words
must directly qualify an area rather than occur in contact boilerplate.

Nineteen demonstrated `correct_price` fixture cells were corrected, with a
versioned journal in `data/golden/unit_price_corrections_v1.json`:

- Ten have supported rate × matching advertised-area totals.
- Nine cannot establish a total: structured/narrative areas disagree, or the ad
  contains multiple apartment, net/gross or terrace areas. They explicitly expect
  `MISSING`, meaning the parser must leave the price unset for quarantine.

The golden evaluator now scores an explicit `MISSING` expectation against `None`;
it does not drop those trials. All 901 rows and all other fixture fields remain
unchanged. No thresholds or stored baseline scores were relaxed or rewritten.
Golden price accuracy remains **99.7780%** and overall **99.9445%**, exactly the
stored baseline. The nine missing totals remain unresolved source evidence;
areas were not rounded, converted or selected to manufacture prices.

## Isolated replay and QA

The reproducible in-memory replay uses actual `ParsingService`,
`NormalizationService(session=None)` and `ListingValidator`. It loads only the
trusted pre-fix method from commit `2cc30f7` for the before arm, without switching
Git state. No persistence, database session or HTTP request is needed.

The frozen archived cohort contains **220 records**: Gjirafa 33, Merrjep 32,
Pro-rks 38, Vision 32, Topia 33, MyRealEstate 32 and Harta 20.
Exactly **four** records change. Their only normalized-field differences are
`sale_price` and `price_per_sqm`; provenance changes accordingly. All other
normalized fields and all validation results are unchanged. The remaining
**216 records are identical** in the before/after comparison. This is a bounded
diagnostic cohort, not an exhaustive corpus replay.

The replay exercises generic validation, without persistence-only ETL/location
steps. Existing Harta ETL and source-specific safeguards are separately covered
by regression tests and were not changed.

- Focused parser, normalizer, provenance, validation, golden, Merrjep and Harta
  regressions: **168 passed, 1 skipped**, 14.84 seconds. The skip needs a test DB.
- Full suite: **928 passed, 45 skipped, 1 unchanged pre-existing failure**,
  3 warnings, 54.25 seconds.
- Known failure remains
  `test_home_trust_snapshot.py::test_legacy_weekly_runners_keep_crawl_exit_code[run_weekly.ps1]`:
  the test expects `exit $LASTEXITCODE`, while the pre-existing dirty runner uses
  `exit $result`. Both files retain their baseline hashes.
- Ruff check and format pass for all five changed Python files.
- Frozen replay output reproduces byte-for-byte. The input SHA-256 is recorded.
- All **360 pre-existing modified/untracked files** retain their original hashes.

Private replay outputs: `reports/generated/unit_price_remediation/verified/`
and `reports/generated/unit_price_remediation/reproduced/`.

```powershell
.venv/Scripts/python.exe scripts/research/replay_unit_price_remediation.py --snapshots .tmp/independent-evidence/snapshots_private.json --baseline-ref 2cc30f7 --output reports/generated/unit_price_remediation/new_replay
```

## Scope and decision

**PASS:** all four defects have source-supported corrections, missing/ambiguous
evidence produces tested quarantine outcomes, focused checks pass and the full
suite introduces no remaining regressions. The nine additional golden source
ambiguities are documented rather than given invented totals.

Source-quality policy 1.1.0, weights, deduplication activation, Harta collection,
Metrik/Azure and existing database records are untouched. No push or deployment
was performed. Only task-owned parser/provenance changes, regression fixtures,
golden expectation corrections, replay tooling and this report enter the commit.
