# Part 3 — Harta Gate 3 evidence

**2026-10-21 · Overall PARTIAL · Gate 3 BLOCKED · Weekly/public enablement NOT READY.**

Reference: [source integration and operating contract](HARTA_SOURCE_INTEGRATION.md).
Gate 1 commit `69b7590` and Gate 2 commit `1e7c807` exist. Work started from
`1e7c807` on `codex/source-quality-evaluation`, then created `codex/harta-integration`.
Origin is the existing GroundTruth repository; no push or deployment occurred.

## Evidence boundary and blockers

Owner authorization for relevant public listings was accepted. Direct public HTTP
investigation and browser/network inspection were performed. The browser subsequently
displayed a Cloudflare Turnstile human-verification gate explicitly protecting
property data from automated collection. Live collection stopped without solving
or bypassing it. The task's source-access boundary prevents the requested pilot.

Independently, `/prona/banesa/prishtine` returned zero while the public browser map
displayed matching properties. The lightweight map response returned the source error
`COALESCE types jsonb and text[] cannot be matched`. The category route has a 24-record
loader limit and no established pagination. Therefore the committed HTML adapter is
preliminary, not a verified replacement for complete filtered discovery.

No production or research database ingestion, migration, all-six-source recrawl,
weight activation, public statistics regeneration or recurring job enablement ran.
Tests use isolated mocks/synthetic records, not the research database.

## Actual collection and efficiency results

| Requested pilot metric | Actual result |
|---|---|
| Pilot started / ended | Not started; access blocked |
| Pilot requests made | 0 |
| Discovered / eligible pilot records | Unavailable |
| New ingested listings | 0 |
| Changed / unchanged pilot listings | Unavailable |
| Successfully parsed / normalized pilot records | 0 / 0 |
| Persisted invalid/quarantined pilot records | 0 |
| Incremental live rerun savings | Unavailable; no live rerun |
| Requests or bytes per usable listing | Undefined; no pilot denominator |
| Representative review | 1 diagnostic detail, not the required 30 |

Seven explicit direct HTTP investigation requests returned HTTP 200, with no 429;
their response-body sizes were recorded separately from browser traffic. The
browser loaded ordinary site assets, including map/images, during discovery.
Those requests are not included in the seven direct requests or claimed as pilot
efficiency evidence. The collector itself schedules property HTML only and stores
no media. No claim of zero asset traffic across the whole investigation is made.

One matching public property detail captured before the restriction was reviewed.
Its structured price differed from the labelled description price; its displayed
total area had no interior counterpart. The parser detects both and would quarantine
the record through normal ETL. Source UUID, transaction, address, bedrooms and an
absolute publication timestamp were available. Coordinate correctness is unverified.
No 95% critical-field accuracy claim is possible from one diagnostic record.

## Implemented and tested offline

Seventh-source registry and CLI, strict public HTML literal extraction, UUID identity,
Prishtina apartment scope, minimized raw payloads, versioned parser dispatch,
normalization/gazetteer reuse, source consistency issues in existing validation
quarantine, bounded retry/access middleware, raw/run checkpoint reuse, aggregate
reporting and explicit weekly selection are implemented.

Six-source priorities and automatic job list remain unchanged. Harta is last at
priority 6. A separate public-approval flag keeps Harta out of the active public
parser allowlist and public fallback source labels. Deduplication algorithms and
quality policy/formula are unchanged. Existing sources still use their prior paths.

Tests include 16 synthetic critical parser cases, geography/category/identity
rejection, malformed/challenged HTML, privacy/provenance, incremental skips and
periodic rechecks, detail removal and content hashing, request allowlist/budget,
Retry-After stop, dispatch/normalization/quarantine, inherited raw storage/checkpoint
behavior and research-only registration. They are not substitutes for live evidence.

## Quality assessment

The existing calculator generated policy **1.1.0** output from the actual empty
pilot population: all six criteria and source composite **UNKNOWN**, evidence
coverage **0%**, sample **0**, proposed weight **1.00**, inactive. The single
diagnostic was not converted into a representative source score or verified
publisher history/location evidence. Original six-source proposed weights and
historical reports remain untouched.

Local generated artifacts:

- `reports/generated/harta_pilot_report.json`: explicit BLOCKED pilot metrics and investigation boundary.
- `reports/generated/harta/quality/source_quality_report.json`: existing calculator output, no_data population.
- `reports/generated/harta/quality/source_quality_summary.csv` and report schema.
- `.tmp/harta/`: preservation hashes, diagnostic captures and test logs; private, not committed.

## QA and Git preservation

Final focused regression command:

```powershell
.venv/Scripts/python.exe -m pytest tests/test_harta.py tests/test_source_quality.py tests/test_source_quality_reporting.py tests/test_source_quality_evaluation.py tests/test_portal_registry.py tests/test_version_registry.py tests/test_validation.py tests/test_confidence.py tests/test_parser_kpis.py tests/test_normalizers.py tests/test_pipeline_failure_safety.py tests/test_corpus.py tests/test_corpus_authority.py tests/test_cross_dedup.py tests/test_source_skew.py -q --tb=short
```

Result: **151 passed** in 11.64 seconds, including the added Harta canonical-winner
compatibility test. Log: `.tmp/harta/regression-final.log`.

Full suite command `.venv/Scripts/python.exe -m pytest -q --tb=short`:
**831 passed, 45 skipped, 1 pre-existing failure, 3 warnings** in 59.12 seconds.
Log: `.tmp/harta/full-suite-final.log`. This preceded the final added dedup test;
that test passed in the focused regression. Skips retain existing opt-in E2E,
dedicated test-database and platform/tool constraints. No tests use research data.
Ruff check and format verification cover the 15 changed Python files excluding
the already dirty weekly runner; CLI `crawl harta --help` succeeds.

Initial focused run passed 73 tests after updating the expected
quality summary count from six sources (24 segments) to seven (28 segments).
The first full run exposed the version-registry test's six-source assumption;
it was updated to verify all seven parser services and the six public versions.
No assertion was removed to conceal an extraction or pipeline failure.

The known unrelated failure is
`tests/test_home_trust_snapshot.py::test_legacy_weekly_runners_keep_crawl_exit_code[run_weekly.ps1]`:
it expects literal `exit $LASTEXITCODE`, while the pre-existing dirty runner uses
`exit $result`. Runner and test bytes are checked against the pre-task snapshot.

Before editing: 242 modified tracked files and extensive untracked QA work were
recorded. Only `crawl/weekly.py` overlaps a pre-existing dirty file; its four-line
explicit Harta selection hunk is staged separately. The previous file contents are
recoverable and hash-verified after subtracting that hunk. All other pre-existing
file bytes are checked unchanged (359 pre-existing files other than the overlapping
weekly module). No reset, clean, stash, force-push or broad
staging was used. No captured property details or credentials enter the commit.

## Decision and remaining acceptance work

**BLOCKED**, not PASS: essential real-source access and targeted discovery are
unresolved. The adapter is reviewable and offline-tested; the integration mission
is not complete. Obtain an authorized access arrangement from Harta that resolves
the observed human gate, confirm/fix its public filtered listing response and
pagination, then run a controlled 50–100 eligible-record pilot through private raw
storage and ETL. Review at least 30 representative listings, measure price/area
accuracy, rerun incrementally and measure savings, reconcile all counters and
regenerate the evidence-backed quality assessment. Close any defects before
re-deciding Gate 3. Automatic weekly and public-release approval remain separate.
