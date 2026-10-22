# GroundTruth — historical price remediation execution

2026-10-22 · **PASS — both approved private database batches applied and verified.**

This is the execution reference for this chat. It supersedes the infrastructure
blocker recorded in commit `134cf54`. Docker Desktop became available after the
user opened it. The existing `groundtruth-postgres` container was started on its
existing `fartestate_postgres_data` volume, bound to `127.0.0.1:15432`.
No volume was recreated, PostgreSQL reset, or empty research database initialized.

References: [historical assessment](UNIT_PRICE_HISTORICAL_IMPACT.md),
[arithmetic code correction](UNIT_PRICE_ARITHMETIC_REMEDIATION.md), and
[reusable apply/rollback command](HISTORICAL_PRICE_REMEDIATION_COMMAND.md).

## Authorization and preflight

Exact review manifest SHA-256 remained unchanged:
`b6126ad97dd3c60f95798eba3af132062f0445e1b76ceae1857e17d90c06b4cf`.
Its historical `REVIEW_ONLY_NOT_APPROVED` status was preserved; a separate
`USER_APPROVED_EXACT_MANIFEST` execution receipt records the later authorization.

All 659 target fingerprints matched the frozen assessment before writing.
All 63,686 normalized/eligibility projections matched; identities, original
source fields and description hashes, parsed lineage, prices, validation results
and replacements were independently replayed from the original database records.
Membership reconciled to 402 corrections + 256 quarantines + one held outlier.
Raw 23992 / normalized 272603 and all 217 alternate-syntax candidates were excluded.

The live endpoint guard verified local `rema` on port 15432. There were no active
database writers, running research/crawl scheduled tasks or identified ETL/crawler
processes. Actual triggers, constraints and dependent tables were inspected.
No user triggers, unexpected dependencies or unvalidated constraints were found.
Apply repeated these gates and used writer locks plus target row locks.

## Full backup and restore drill

Private backup: `C:\MetrikResearch\backups\historical-price-20261022\rema.dump`.
Complete PostgreSQL custom-format dump: **2,303,414,867 bytes**.
SHA-256: `6c94372a5e2eb71f56b3e92238785a04e5373524a56ae1e983f026b9b0d6cfb9`.

The dump was restored with `pg_restore --exit-on-error --no-owner --no-acl` into
the isolated `rema_price_remediation_test_20261022` database on the local server.
Restore exited zero. Content fingerprints matched for **all 22 public base
tables**, including every raw payload and HTML value. All 659 exact target and
dependent before-image sets also matched. Schema constraints were validated.

`backup_receipt.json`, `full_database_fingerprints.json` and
`exact_before_images_private.json` in that private backup directory record the
drill. Before-images include 659 normalized rows, 659 parsed rows, 621 raw rows,
659 lineage rows, 9 older rejection rows and 5,044 linked observations.
The one held target is included in recovery evidence, not correction scope.
Both the full backup and isolated restored database are retained.

## Actual persisted outcomes

Runtime code revision: `a79b5290f05a96bc27800da22de246ca7374fbeb`.
Execution ID: `live-20261022`. Each batch has a separate journal and transaction.

| Batch | Authorized | Applied | Skipped | Failed | Transaction ID |
|---|---:|---:|---:|---:|---|
| A — supported asking-price correction | 402 | 402 | 0 | 0 | 8103 |
| B — unresolved-total quarantine | 256 | 256 | 0 | 0 | 8104 |

All 658 normalized rows and associated parsed price/provenance fields match
their approved replacements. Areas, dates, location, confidence, other fields,
version identifiers and original raw claims remain unchanged. These are asking
prices; no completed transaction prices or unsupported area conversions are inferred.

The four original cases now contain these actual normalized values (EUR):

| Raw ID | Normalized ID | Before total | Actual corrected total | Actual corrected EUR/m2 |
|---|---|---:|---:|---:|
| 26890 | 275498 | 130,000 | 104,000 | 1,300.00 |
| 27285 | 275893 | 85,000 | 51,000 | 850.00 |
| 45140 | 290854 | 115,000 | 94,300 | 1,150.00 |
| 76665 | 312328 | 140,000 | 189,000 | 1,400.00 |

All 256 unsupported totals and their dependent unit prices are null. Exactly
256 linked `VALIDATE` records containing only the new `missing_price` issue were
added. All 9,542 older rejection records remain unchanged; the table now has
9,798 rows. Six already-excluded Batch B versions retain their older reasons.
No previously invalid listing became valid. Of the 256 quarantined historical
versions, 250 were previously valid, including 27 currently selected source rows.

## Database preservation and integrity

Full target-row comparisons permit only the approved price/provenance fields and
execution markers. Fingerprints of every public base table outside the exact
owned changes match before/after. Raw history, existing lineage, historical
observations, canonical records, other portals, the held outlier and broader
syntax candidates remain unchanged.

All **63,028 other normalized versions** remain unchanged. Normalized/parsed
row counts and identities are unchanged: no new logical listing rows were created.
All **43 foreign-key checks found zero orphans**; there are zero invalid indexes.

Repeated apply returned **0 applied, 402 skipped** for A and **0 applied,
256 skipped** for B. It added no quarantine records and passed the same full-row,
integrity and full-table preservation checks again. Initial apply and repeat
receipts are retained separately.

## Actual private analytics versus frozen projection

The corrected database was read directly using the frozen cutoff and existing
corpus filters, cross-source deduplication threshold 85 and valuation logic.
No public cache/statistics generator was run.

| Measure | Frozen before | Projected after | Actual after |
|---|---:|---:|---:|
| Active source rows | 15,648 | 15,621 | 15,621 |
| Canonical active rows | 11,744 | 11,730 | 11,730 |
| Sale input rows | 3,094 | 3,082 | 3,082 |

All 206 neighborhood/transaction/property groups match the projected after
medians, including all nine named apartment-neighborhood changes. All 96 valuation
diagnostic cases match their projected comparable counts, methods and weighted
points. Forty points change from the frozen before state; there are no readiness
transitions. Largest sampled change remains Qendra, 90 m2: EUR 211,983.90 to
EUR 219,772.69 (+EUR 7,788.80, +3.67%). This diagnostic grid is not a worst-case
bound or a published valuation refresh. No snapshot drift or implementation
discrepancy was observed.

## Transaction, rollback and regression tests

The isolated restored database exercised original fingerprint drift rejection,
forced mid-batch failure with zero persisted changes, both complete batches,
repeat-safe application, refusal to overwrite a later owned-price edit, and
exact rollback preserving later unrelated columns, JSON keys and rejection rows.
After removing only test-created later changes, complete target/dependent
before-images matched again. Both inverse batches were repeat-safe. No live
rollback was necessary; PostgreSQL sequence counters are intentionally not rewound.

An initial isolated test connection stalled before opening a database session;
the fixture was corrected to explicit IPv4 with a five-second timeout, then the
complete test run was restarted successfully.

- Focused parser, normalization, validation, corpus, cross-deduplication,
  source-quality and isolated database tests: **132 passed, 1 skipped in 99.77s**.
  This includes all three opt-in database integration tests.
- Full suite under committed code: **932 passed, 48 skipped, 1 failed**, three
  warnings, 56.75s. This preserves the earlier 931/45/1 baseline: one new guard
  test passes and three new opt-in database tests skip in the default run, having
  passed separately above.
- The sole failure remains the pre-existing weekly-runner literal exit-code
  assertion in `tests/test_home_trust_snapshot.py`; its unchanged runner uses
  `exit $result`, while the test expects `exit $LASTEXITCODE`.
- Ruff check and format checks pass for all three new Python files.
- All **373 pre-existing files represented by 360 dirty/untracked status entries**
  retain their original hashes. Unrelated work was neither staged nor committed.

## Private audit and exact rollback route

Audit directory:
`C:\MetrikResearch\audits\historical-price-20261022\live-20261022`.

It contains per-batch journals with exact before-images, old/new prices and
provenance, quarantine IDs and full added rows, transaction IDs and code revision;
`initial_apply_receipt.json`, `idempotency_receipt.json`,
`post_write_invariants.json`, `actual_analytics_private.json` and the actual
63,686-row projection. Verification scripts and logs are retained privately too.
The test log is `C:\MetrikResearch\audits\historical-price-integration-20261022.log`.

Use the exact arguments and `--rollback` route in the
[command documentation](HISTORICAL_PRICE_REMEDIATION_COMMAND.md). It restores
only owned prices and JSON keys and removes only this execution's added rejection
rows and database audit markers, preserving earlier history and later unrelated
writes. It aborts if a later write changed an owned field. Private journals remain
the recovery history. A whole-database restore over `rema` was not performed.

The approved scope is complete. Source-quality policy 1.1.0, source weights,
Harta collection/matching, valuation logic, published Metrik statistics, frontend,
Azure and deployment configuration were unchanged. No push or deployment.
Historical observation snapshots deliberately retain their original recorded
values; this bounded task corrects the authorized normalized/parsed versions.

**Decision: PASS — private persisted corrections and all required gates verified.**
