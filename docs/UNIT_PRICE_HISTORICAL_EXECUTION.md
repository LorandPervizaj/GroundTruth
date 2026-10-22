# GroundTruth — historical price remediation execution

2026-10-22 · **BLOCKED before database writes.**

This is the execution reference for this chat. It follows the
[historical impact assessment](UNIT_PRICE_HISTORICAL_IMPACT.md) and
[parser correction](UNIT_PRICE_ARITHMETIC_REMEDIATION.md).
The user approved the two bounded manifest batches. Approval does not establish
that live database preconditions or the restore gate passed.

## Authorization and manifest verification

The existing review manifest remains unchanged, including its historical
`REVIEW_ONLY_NOT_APPROVED` status. A separate private approved execution attempt
records the newer authorization and the failed availability gate.

Manifest: `reports/generated/unit_price_historical_impact/reviewed/remediation_review_manifest_private.json`.
Recomputed SHA-256 matches the authorized value exactly:

`b6126ad97dd3c60f95798eba3af132062f0445e1b76ceae1857e17d90c06b4cf`

All 659 manifest classifications reconcile: 402 supported price corrections,
256 unresolved-total quarantines, and one held source-unit outlier. The outlier
and 217 broader-syntax candidates remain outside authorization.

## Failed preflight gate

The configured endpoint passed the local URL guard: loopback `localhost`, port
15432, database `rema`. A read-only connection attempt using SQLAlchemy/psycopg
timed out on both `::1` and `127.0.0.1`. No connection was established, so the live
database identity, target fingerprints, lineage, validation state, dependent rows,
triggers, constraints and concurrent activity could not be verified.

Independent local diagnostics found:

- `docker ps` failed because the Docker Desktop Linux engine named pipe
  `//./pipe/dockerDesktopLinuxEngine` did not exist.
- Windows service `com.docker.service` was stopped.

The execution instruction explicitly requires stopping without database writes
when required preconditions cannot pass. Neither database remediation nor Docker
or database startup was attempted after this failure. No full backup, exact
database before-images or isolated restore drill could be completed.

## Actual execution outcome

| Batch | Authorized | Applied | Already-applied skips | Write failures | Not attempted |
|---|---:|---:|---:|---:|---:|
| A — price-only correction | 402 | 0 | 0 | 0 | 402 |
| B — missing-total quarantine | 256 | 0 | 0 | 0 | 256 |

Zero database write commands, quarantine additions or batch transactions were
executed. There are no transaction IDs. The counts above mean not attempted;
they are not evidence of successful idempotent skips or row-level verification.

No actual before/after corpus, neighborhood median or valuation-grid comparison
is available. The previous 15,648 → 15,621 source rows, 11,744 → 11,730 canonical
rows and 3,094 → 3,082 sale inputs remain projections, not observed corrections.
Live preservation, integrity and repeat-apply invariants remain unverified.

No remediation command or rollback mechanism is claimed implemented or tested.
Rollback was unnecessary because this attempt made no database mutation.

## Private audit and repository preservation

Approved execution attempt:
`C:\MetrikResearch\audits\historical-price-remediation-20261022-blocked\approved_execution_record.json`.

Local Git file-hash baseline:
`.tmp/historical-price-execution/baseline.json`.
The baseline records 373 existing files represented by the 360 dirty/untracked
status entries, including files within untracked directories. All baseline file
hashes were verified unchanged after preflight. Code revision at attempt start:
`a6a1f14dd51de2c79d7f49f9029b8723c73eca59`.

No source-quality policy, weights, Harta settings, matching activation, published
statistics, frontend or Azure configuration was changed. No push or deployment.

## Validation

Focused arithmetic, normalization, validation, corpus, cross-source deduplication
and source-quality regressions: **128 passed, 1 skipped in 10.05s**.
The database-dependent test was skipped. These passing tests do not establish
database restoration, transactional rollback or applied-data correctness.

Current full suite: **931 passed, 45 skipped, 1 failed, 3 warnings in 62.62s**.
This matches the prior baseline counts. The sole failure remains
`tests/test_home_trust_snapshot.py::test_legacy_weekly_runners_keep_crawl_exit_code[run_weekly.ps1]`:
the pre-existing test expects literal `exit $LASTEXITCODE`, while the pre-existing
runner uses `exit $result`. Neither file was changed by this task.
The log is `.tmp/historical-price-execution/full-pytest.log`.
Ruff is not applicable to the documentation-only committed change; no runtime
Python files were changed. Isolated database integration, restore, idempotency
and transaction rollback tests were not run because the database gate failed.

## Resume requirements

Restore local research database availability, then repeat every required gate:
exact manifest and frozen live fingerprints, schema/dependency review, concurrency
checks, full private backup, exact before-images and isolated restore drill.
Implement and test the guarded dry-run/apply/rollback command before either live
batch. Existing authorization remains bounded to the exact manifest; any live
drift must stop execution rather than be overwritten. Public release promotion
remains separate.

**Decision: BLOCKED. Historical database correction remains pending.**
