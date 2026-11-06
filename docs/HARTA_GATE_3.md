# Harta.info — Gate 3 recovery result

**2026-10-22 · PASS for bounded private research integration · Public API collector implemented and piloted.**
Reference and operator runbook: [Harta source integration](HARTA_SOURCE_INTEGRATION.md).
**Follow-up area diagnosis:** original cohort now has 3 accepted / 47 quarantined;
collection expansion is paused. Current source contract is parser 0.3.0-harta.
The original Gate 3 pilot below remains historical evidence; source data usefulness
is limited despite collector correctness. See the runbook's area diagnosis section.
Follow-up QA: 894 passed, 45 skipped, the same pre-existing runner failure; Ruff
passes. Quality is now 48.815 provisional, neutral weight 1.00 inactive.
The subsequent [identity-matching pilot](HARTA_CROSS_SOURCE_MATCHING_PILOT.md)
does not pass its evidence gate: 40 unresolved primary pairs, matching support
not enabled. Collector correctness does not imply verified apartment identity.
This supersedes the access-blocked report at `9f3025e`; Git preserves earlier evidence.
Gate 1 (`69b7590`) and Gate 2 (`1e7c807`) remain intact.

## Implementation and access

Since `fc7d67c`, recovery added atomic raw/checkpoint persistence, bounded state
loading, parser 0.2.0 semantic validation, budgets and richer failure reporting.
The current change replaces empty category discovery with the public frontend's
observed properties read interface, ordinary server-issued CSRF session, exact
scope filters and 25-row inclusive range pagination. No stealth, proxy rotation,
CAPTCHA solving or fake verification tokens are implemented. The owner explicitly
authorized public-property collection and Harta's robots override. Other sources'
settings are unchanged. A normal CSRF-backed POST returned 200; the earlier bare
POST's 403 was not proof this public session interface required a Turnstile bypass.
HTTP 401/403/challenge stops remain. No administrator message was sent.

## Discovery and measured pilot

Active Prishtina apartment/condo/studio sales and rentals are filtered at source;
explicit daily/nonmonthly rentals are excluded. Unknown rental periods quarantine.
Five-row probes verified disjoint pages; the live pilot fetched two 25-row pages.
The API count is page length, not a trusted inventory total. Both runs ended
`bounded_complete`, with discovery_complete=false. Neither establishes full
municipality coverage. Offset pagination is not a snapshot of changing inventory.
No identities were inferred removed from absence.

First capture: 2026-10-21 20:52:01–20:53:15 UTC, run 217.
Repeat: 2026-10-22 07:07:13–07:07:26 UTC, run 218.
Docker Desktop was stopped between captures; the local research container was
restarted before ETL and repeat. Failed connection attempts performed no ingestion.

| Metric | First pilot | Incremental rerun |
|---|---:|---:|
| HTTP requests / responses | 53 / 53 | 4 / 4 |
| Eligible summaries | 50 | 50 |
| New / changed / unchanged | 50 / 0 / 0 | 0 / 1 / 49 |
| Detail requests / successes | 50 / 50 | 1 / 1 |
| Discovery requests, including CSRF | 3 | 3 |
| Parsed / normalized versions | 50 / 50 | 1 / 1 |
| Valid normalized versions | 1 | 0 |
| Quarantined versions | 49 | 1 |
| Response bytes | 49,865 | 7,235 |
| Duration seconds | 73.656 | 13.192 |
| HTTP 429 / 403 / retries / persistence failures | 0 / 0 / 0 / 0 | 0 / 0 / 0 / 0 |

The repeat avoided 49 of 50 detail fetches (98%), reduced total requests 92.45%
and bytes 85.49%. It captured one actual source change rather than reporting it
unchanged. First-run cost per usable listing is 53 requests and 49,865 bytes;
repeat cost per usable listing is undefined because no new version passed validation.
These are measured bounded runs, not whole-site performance projections.

Database audit: 50 Harta identities, 51 raw/parsed/normalized versions, one versioned
identity and zero duplicate UUID/content-hash groups. The additional version is the
changed listing. Non-Harta raw 65,631 (max 76,701), parsed 63,588 (max 312,381),
normalized 63,585 (max 312,364): unchanged from baseline. No six-source crawl,
schema migration, public statistics refresh, Azure deployment or push occurred.

## Source quality and independent checks

All first-pilot records parsed and normalized; validation accepted 1 and rejected 49.
49 lack explicit interior living_area. One also lacks a valid total price; another
has price_too_low. Total surface_area is retained separately and never substituted
for interior. Thirty first-run identities in deterministic hash order, supplemented
by the one interior-area-present record (31 total: 25 sales and 6 rentals), were
compared with independently extracted public property HTML.
All 31 returned 200. Numeric strings, date formats and the HTML total-area alias
were compared semantically. Missing-in-both is missingness agreement, not coverage.

Of the original 30 records, 29 historical price representations agreed and one
listing changed price between captures. One of the 29 had no valid asking price;
agreement on missingness does not count as present-price accuracy. The
new raw version from run 218 agrees with a further public HTML check. The reviewed
scope, price/units and area evidence agree after accounting for that source change.
No present field was fabricated to improve completeness. Independent comparisons
found agreement for 30 present prices (including the reconciled source change),
31 total-area values and the one present interior-area value. End-to-end database
checks passed for all 31 identities, parsed/normalized prices, area handling,
transaction/property type, municipality, preserved address, dates and quarantine
outcomes. No unsupported interior values were created for the other 30.
These are **automated representation comparisons**, not independent publisher
audits or physical location checks. The acceptance target is at least 95% accuracy
for source-present critical fields, not 95% interior-area coverage; it is met in
this sample, with the very small interior-area evidence explicitly qualified.

Unchanged scoring policy 1.1.0, first 50-record population:

| Dimension | Score |
|---|---:|
| Validity | 2.0 |
| Completeness | 69.625 |
| Independent location | UNKNOWN |
| Consistency | 100.0, only 1 comparable accepted record |
| Freshness | 93.4 |
| Historical reliability | UNKNOWN |
| Composite | 46.415, provisional |
| Proposed weight | 1.00, inactive, insufficient evidence |

Location precision 24.2 is separate from independent location correctness.
Generic ETL golden-corpus accuracy printed in logs is not Harta pilot accuracy.
The separate 35-sale/15-rental reports and unknown criterion coverage remain
available locally; historical six-source reports were not rewritten.

## QA and repository preservation

Final full suite: **869 passed, 45 skipped, 1 pre-existing failure**, 3 warnings,
70.93 seconds. Known unchanged failure:
`test_legacy_weekly_runners_keep_crawl_exit_code[run_weekly.ps1]` expects literal
`exit $LASTEXITCODE`; the pre-existing dirty runner uses `exit $result`.
No tests were weakened. Final focused Harta tests: **70 passed in 8.99 seconds**;
Ruff check and formatting pass for the five changed Python files. New API tests
cover ordinary CSRF, read-only scope,
page count versus inventory total, malformed/empty/stalled responses, minimized
details, unchanged skipping, daily exclusions and pagination through excluded pages.
Existing ORM tests cover interruption recovery, duplicate content, ETL quarantine,
quality compatibility and preservation of six-source dedup winner priority.

Branch `codex/harta-public-api`, baseline `9f3025e`. Only task-owned source,
tests and the two existing Harta documents are staged for this change. All 360
pre-existing modified/untracked files were SHA-256 verified unchanged. Private
source evidence, tokens, URLs with credentials and generated reports stay outside
Git. The original plan and unrelated frontend/automation changes are preserved.

Local evidence: `reports/generated/harta/{first,repeat}_crawl.json`,
`{first,repeat}_etl.json`, `database_audit.json`, `public_html_review.json`,
`etl_review.json`, `quality/`, and `reports/generated/harta_pilot_report.json`.
Logs and preservation hashes: `.tmp/harta-api-integration/`.

## Gate 3 and operational readiness

**PASS for the bounded private research collector.** A real 50-record pilot,
31 independent detail checks, source-present critical-field comparisons, real
incremental replay, persistence audit and relevant regressions support the decision.
Low source completeness is represented by quarantine and the provisional quality
score; it is not hidden or treated as an extraction success for missing fields.
Whole-municipality inventory completeness and physical location accuracy are not
established by this bounded pilot. The collector is ready for explicitly selected
private research runs with the documented budgets and quarantine monitoring.
Recurring production enablement is not authorized or performed. Registry remains
weekly=false/public=false, priority 6 and quality weight 1.00 inactive.

The main source-data improvement is obtaining trustworthy interior-area values or
a documented source definition showing which area concept is supplied. Any policy
change to accept total area needs explicit review; do not relabel it as interior.
Before expanding recurring collection, assess inventory coverage and operational
quarantine usefulness. Public release remains a separate controlled decision.
