# Harta.info — Gate 3 recovery result

**2026-10-21 · Status BLOCKED · Adapter 0.2.0-harta · Operator weekly enablement NOT READY.**

Reference and operator runbook: [Harta source integration](HARTA_SOURCE_INTEGRATION.md).
This document supersedes the initial attempt in commit `fc7d67c`; that commit retains
its original evidence. Gate 1 (`69b7590`) and Gate 2 (`1e7c807`) remain intact.

## Implementation since fc7d67c

- Atomic per-item checkpoints now require confirmed stored content. A crash before
  spider close preserves committed progress; unpersisted callbacks cannot skip work.
- Latest source UUID/time/hash lookup uses two bounded queries and avoids loading raw
  payloads. Legacy, malformed, future or mismatched checkpoint evidence is ignored.
- Summary fingerprints include source availability/address/coordinate/area/date fields
  where exposed. Summary metadata no longer changes raw detail content hashes.
- The existing raw pipeline/repositories remain in use. Source-local savepoints
  contain duplicate constraints without the base pipeline batch commit separating
  raw content from its checkpoint. Repeated details do not
  create duplicate raw versions. No new schema, index, broker or listing store.
- Parser version 0.2.0 handles validated Kosovo/European/English number separators,
  separates total versus per-m²/payment/deposit figures, preserves interior versus
  total area, and quarantines additional source contradictions. Source street
  numbers, construction status and coordinate provenance are retained.
- Wall-time limits, request/status/retry/byte counts and explicit incomplete statuses
  improve reporting. Partial discovery is failed in scrape-run tracking, rather
  than being reported completed merely because requests ended successfully.
- Seen IDs and explicit 404/410 observations are retained as bounded run evidence;
  partial discovery/challenges never imply mass removal.
- Weekly command construction forwards budgets and crawl-window metadata. Harta
  stays excluded from default jobs and public corpus versions; other source paths,
  fixed winner priorities and scoring policy are unchanged.

## Source discovery and access: verified facts and limits

Recovery baseline: `fc7d67cac4bee4363806673444dcc5568f7b1518` on
`codex/harta-integration`; work continues on `codex/harta-gate3-recovery`.

Fresh direct HTTP checks around 19:09 UTC:

| Surface | HTTP | Body bytes | Result |
|---|---:|---:|---|
| Public robots.txt | 200 | 183 | Public pages allowed; /api/, /profile/, /dashboard/, /lovable/ excluded |
| Prishtina apartment category | 200 | 22,667 | Zero inventory; no challenge body |
| Current frontend JS bundle | 200 | 2,500,044 | Application owns HumanGate and loads Turnstile |

A public browser inspection reproduced the HumanGate on the map route at roughly
19:11 UTC. Collection stopped without interacting with or bypassing the challenge.
Images, media, fonts, Mapbox and analytics tracking were blocked during this
recovery browser session. Blocked map assets also limit interpretation of that
session's displayed map count; it is not new inventory/completeness evidence.

The initial attempt observed actual matching map properties while the category
returned zero, and a lightweight public map response reported
`COALESCE types jsonb and text[] cannot be matched`. This failing function was not
replayed to circumvent the gate. The precise discrepancy cause remains unverified;
it must not be attributed to caching or separate populations without evidence.
The category's 24-record loader is not a verified pagination/completeness contract.

Neither local environment file supplies Harta access configuration. No approved
authenticated session was available, so authenticated/public comparison was not
performed. Detail retrieval was not retested after the gate. HTTP 200 public
HTML is not treated as a technical exemption from the observed application policy.

The administrator requirements in the integration runbook specify identity,
observed-egress evidence, exact read-only paths, a proposed conservative rate,
application/WAF configuration, required data fields and log minimization. No
administrator message was sent and no source configuration was changed.

## Live pilot and performance

| Metric | First pilot | Incremental rerun |
|---|---|---|
| Status | BLOCKED before pilot | NOT RUN |
| Requests | 0 | 0 |
| Eligible listings discovered | Unavailable | Unavailable |
| New ingested records | 0 | 0 |
| Changed / unchanged records | Unavailable | Unavailable |
| Detail requests | 0 | 0 |
| Valid normalized records | 0 | 0 |
| Persisted quarantine records | 0 | 0 |
| Bytes transferred | 0 | 0 |
| Live request savings | Unavailable | Unavailable |

Diagnostic access checks above are separate from pilot metrics. No full six-source
crawl, research database ingestion, production write, schema migration, public
statistics regeneration, Azure deployment or recurring enablement was performed.

**Separate synthetic scheduling result:** 50 synthetic summaries scheduled 51
requests initially (one discovery + 50 details) and one discovery on the identical
repeat, avoiding 50 detail requests (98.04% of scheduled requests). These are
in-memory scheduling counts, not HTTP measurements, usable-listing counts or live
performance. Crash/dedup persistence is verified separately through actual ORM
repository tests. No live concurrency tuning is justified by these fixtures.

Local evidence: `reports/generated/harta/fixture_incremental_comparison.json`.

## Data quality and GroundTruth integration

The redacted observed-response fixture preserves public field shape and the
previous diagnostic's structured/description price disagreement and absent
interior area. Identity, address and coordinates are redacted; no free-text
contacts, profiles or images are retained. This remains one diagnostic, not the
required 30 independently checked records. No 95% extraction accuracy claim is made.

Real ORM tests use isolated in-memory SQLite tables for RawListing, ScrapeRun,
ParsedListing, NormalizedListing, InvalidListing, EtlMetrics and DataLineage. They
exercise inherited raw persistence, duplicate constraints, interrupted-run checkpoint
loading, parser dispatch, existing normalization, actual ETL quarantine persistence
and the existing quality calculator. SQLite's JSONB spelling and PostgreSQL-like
ISO temporal insert casts are adapted in the test harness. This is not a claim
that a live PostgreSQL pilot has run. Ordinary tests make no source requests.

Additional cases cover locale separators, studio/missing rooms/2+1, payment-plan
and per-m² distinctions, wrong municipalities, conflicting transaction/property
claims, coordinate sanity, absolute/relative date conflicts, wall limits and
weekly option forwarding. Existing Harta/existing-six-source dedup regressions
preserve the prior winner over a higher-confidence Harta candidate.

Quality policy **1.1.0** is unchanged. The actual empty pilot population produces
**no_data**, sample **0**, coverage **0%**, all six dimensions and composite
**UNKNOWN**, proposed weight **1.00**, inactive. The ORM fixture's rejected record
score is synthetic test evidence and is not mixed into the real source report.

## QA

Focused recovery/Harta/registry tests: **71 passed**. Final broader regression:
**176 passed** in 13.33 seconds, covering Harta, ORM recovery, quality, registry,
validation, normalization, corpus, dedup, failure safety and weekly orchestration.
Log: `.tmp/harta-recovery/regression-final.log`. Ruff check/format cover all eight
changed Python files; `crawl harta --help` succeeds with `--max-seconds`. Full suite:

```powershell
.venv/Scripts/python.exe -m pytest -q --tb=short
```

Result: **863 passed, 45 skipped, 1 pre-existing failure, 3 warnings** in 58.94 seconds.
Log: `.tmp/harta-recovery/full-suite-final.log`. This final run includes the
savepoint/checkpoint and shared-default updates.

Unchanged known failure:
`tests/test_home_trust_snapshot.py::test_legacy_weekly_runners_keep_crawl_exit_code[run_weekly.ps1]`.
The pre-existing runner uses `exit $result` while the test expects literal
`exit $LASTEXITCODE`. Both files are hash-verified untouched. Skips retain existing
opt-in E2E, dedicated database and platform/tool prerequisites. No test was weakened
to hide a source extraction or persistence failure.

## Artifacts and Git preservation

- `docs/HARTA_SOURCE_INTEGRATION.md`: current source contract, field meanings,
  administrator requirements and operator runbook.
- `tests/fixtures/harta/observed_redacted.json`: sanitized observed shape.
- `reports/generated/harta_pilot_report.json`: latest BLOCKED recovery evidence.
- `reports/generated/harta/quality/`: unchanged calculator's empty-population JSON,
  CSV and schema.
- `reports/generated/harta/fixture_incremental_comparison.json`: labelled synthetic
  scheduling comparison.
- `.tmp/harta-recovery/`: baseline hashes, access evidence, egress observation and QA
  logs. Private captures, IP observations and research outputs are not committed.

Baseline: 242 modified tracked files, empty index and 118 existing untracked files
under detailed status. All 360 pre-existing changed/untracked file hashes are
preserved. Recovery edits only task-owned files; no partial staging of the dirty
weekly runner is required this time. The original plan and unrelated QA/frontend/
automation work remain outside the commit. No reset/clean/stash, push or deployment.

## Gate 3 and smallest external action

**BLOCKED.** Essential authorized access and complete targeted discovery remain
unavailable. Local fixes do not satisfy the live evidence gate. Automatic weekly
collection and public inclusion stay disabled.

The smallest precise external action is for Harta's administrator to confirm a
working read-only listing route for the crawler's confirmed egress/trusted identity,
resolve the application HumanGate for that route, and provide functioning Prishtina
apartment sale/monthly-rent filters with pagination/completion semantics. A WAF-only
allowlist or successful empty category response is insufficient.

After that, verify connectivity/discovery with a few actual details; run the 50–100
eligible-record private pilot, independently review at least 30, measure critical
price/area accuracy and quarantines, run an equivalent incremental replay and
interruption recovery, then regenerate quality and Gate 3 evidence. Operator weekly
enablement remains a separate decision even after PASS.
