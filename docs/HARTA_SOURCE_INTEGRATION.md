# Harta research source integration

Status on 2026-10-22: **Gate 3 PASS for the bounded private research integration**.
This document and [Gate 3 evidence](HARTA_GATE_3.md) are this chat's implementation references.
The original broader plan remains [GroundTruth plan](GROUNDTRUTH_SOURCE_QUALITY_HARTA_PLAN.md).
No weekly or public release is enabled. **Area diagnosis: collection expansion is
paused; 3/50 original identities now pass validation, with 47 still quarantined.**
The [cross-source identity pilot](HARTA_CROSS_SOURCE_MATCHING_PILOT.md) reviewed
40 primary pairs but established no verified apartment identities. Research
matching support and field transfer remain disabled. Six-portal calibration was
assessed separately; every proposed source weight remains 1.00 inactive.

## Observed public request contract

The current public frontend bootstraps `GET https://harta.info/api/security/csrf`,
then sends read-only `POST https://harta.info/api/local-db` operations with the
server-issued `x-harta-csrf-token`, normal session cookies, Origin and Referer.
This route returned actual properties and powers this adapter. The earlier bare
POST's 403 did not establish that this ordinary CSRF flow was unavailable.
The token remains in memory and is never logged or persisted. No login, stealth,
identity rotation, fabricated Turnstile token or challenge solver is implemented.
HTTP 401/403 and challenge responses still stop collection.

The owner explicitly authorized public-property collection and ignoring Harta's
robots.txt exclusions. Only Harta sets `ROBOTSTXT_OBEY=False`. Fixed identity:
`GroundTruthResearch/0.1 (authorized public property research)`. Concurrency 2,
one-second randomized delay, AutoThrottle target 1, 20-second timeout, two bounded
retries. No profiles, owner/agent records, contacts, media, maps or admin operations.
The earlier browser HumanGate observation remains historical evidence, not a claim
that every public read-only interface rejects normal public sessions.

`harta_api.py` permits only bounded `properties` selects with explicit columns:

- Status `active`; city exactly Prishtinë/Prishtina/Prishtine/Pristina.
- Apartment/condo/studio; transaction buy/sale/rent. Explicit nonmonthly rental
  periods are excluded before details; unknown periods enter normal validation.
- Order `created_at` descending, UUID ascending; inclusive `range` pages of 25.
- Detail reads add UUID equality and limit 1. No wildcard selection or writes.

Two five-row probes verified disjoint range pages; the live pilot used two 25-row
pages. The API `count` equals returned-page length even when another page exists;
it is **not** a trusted inventory total. Short pages terminate the filtered scan;
first-page empty results, malformed objects and stalled pagination fail explicitly.
Pilot record/page limits produce `bounded_complete`, never full inventory coverage.
Offset pagination over changing inventory is not a snapshot: duplicates are tracked,
and concurrent inserts/updates can shift pages. No absence implies removal.

Public `/property/<UUID>` HTML worked for all 30 reviewed records. The bounded
TanStack literal reader and JSON-LD extraction remain available for independent
checks and legacy fixtures; category HTML is not the live discovery route.
The earlier empty category and failing map function are superseded as collector
interfaces, not evidence of empty inventory. No map-function replay is required.

## Existing architecture and field meanings

The adapter uses BaseRealEstateSpider, existing raw persistence, ScrapeRun metadata,
parser 0.3.0-harta, normal normalization, validation, parsed-linked quarantine and
source-quality policy 1.1.0. No schema migration or alternative store was introduced.
Registry priority remains 6, `weekly=False`, `public=False`; six existing sources,
winner priorities and public parser allowlist are unchanged.

| Source field | Handling |
|---|---|
| UUID | Stable source identity, verified against requested detail UUID. |
| city/type/transaction/status | Exact scope and active state checked again on details. |
| price_total / price_unit | Explicit total preferred; price fallback only for total. Per-m²/payment/deposit figures never become total price. Numeric locale groups validated. |
| living_area | Structured interior claim. If absent, only an explicit, unambiguous description net/interior claim can supply area, with its provenance. Otherwise quarantine remains. |
| surface_area / sqft | Unclassified reported surface/legacy alias. It is not consistently gross or total, and never substitutes for interior or becomes square feet. Description evidence may identify its basis for an individual record. |
| features.rental_period | Explicit monthly evidence required. JSON-LD can supplement legacy HTML; unknown or conflicting periods remain validation issues. |
| description | Full text discarded; typed net/interior/gross/total/terrace/unspecified numeric facts and consistency flags retained. Negative, ranged, conflicting and nonliving-component claims cannot fill interior area. |
| address/street/municipality | Source fields and features.street/neighborhood/locality/village preserved with provenance. Matching candidates remain unverified; no fabricated location. |
| coordinates | Source map-pin provenance, sanity checked, never independent location verification. |
| created_at / updated_at | Publication/update evidence distinct from collection/check time; absent dates remain unknown. |
| bedrooms/bathrooms/floor/furnished | Explicit values only; no inference from area. |

Pre-storage allowlists remove contacts, profiles, owner/agent IDs, media, promotion
metadata and full HTML/description. Parser checks include conflicting totals,
transaction/property claims, interior exceeding total, incompatible municipality,
invalid coordinates and stale relative publication labels. Kosovo bounds establish
sanity only. The original sample had structured interior area in 1/50 records.
Two explicit description claims now supply additional source-claimed interior/net
area, bringing accepted records to 3/50. Remaining 47 quarantines are not bypassed.

## Area diagnosis and purpose-specific usability — 2026-10-22

The diagnosis rechecked all 50 original UUIDs and examined another 50 in the same
Prishtina apartment sale/rent frame. Only the original 50 were refreshed through
the existing raw/ETL pipeline; the additional cohort remains a private diagnostic
projection. No wider recurring collection or additional DB identities were added.

| Measure | Original before | Original repaired | Additional diagnostic |
|---|---:|---:|---:|
| Identities | 50 | 50 | 50 |
| Structured living_area present | 1 | 1 | 0 |
| Explicit description interior/net recovered | — | 2 | 2 |
| Accepted after unchanged validation | 1 | 3 | 2 |
| Quarantined | 49 | 47 | 48 |
| Usability | 2% | 6% | 4% |
| Street/address matching candidates | — | 50 | 50 |

In the original 49 quarantines, 2 had usable explicit description claims that the
old extractor missed. The other 47 lack structured or unambiguous description
interior evidence in the observed public fields. Across 100 records, all have
surface_area, only 1 has structured living_area, no plot_area is populated, and
no alternate area feature keys are exposed. This describes inspected public data,
not proof that no unpublished area information exists anywhere at Harta.

Observed examples explain why a universal area rule is unsafe:

- `96 m² neto` and `130 m² faktike` describe different assertions; the first can
  support source-claimed net area. The latter remains an unclassified actual-area
  assertion, not silently treated as gross/interior.
- `125 m² hapësirë banimi + 94 m² terasë` identifies living space and terrace
  separately. Reported surface_area is 171, whose basis is unspecified; no sum,
  conversion or reconciliation is invented.
- `50 m² neto | 65 m² bruto` explicitly distinguishes net and gross. Its source
  surface_area equals 50, disproving a consistently-gross interpretation.
- `66 m² (neto)` is another explicit claim. Unlabelled m² and gross-only values
  remain insufficient for interior valuation. All four recoverable description
  records were independently checked against public HTML and agreed.

Only three source surface values can be labelled net by matching explicit
description evidence; 97 remain unspecified. One explicit gross value exists,
retained separately. A gross-area asking-price ratio can be projected for that
record as **research only**, never into normalized interior price_per_sqm. One
record and nonstandard source definitions cannot validate pooled gross-area
statistics. There is no universal gross-to-interior conversion.

The two cohorts contain 68 sales and 32 rentals; all 5 accepted diagnostic records
are sales. All 100 returned apartment type: the sample cannot establish rates for
condos/studios or all Harta. The original publication dates span Aug 30–Oct 21,
the additional dates Jul 9–Aug 29, 2026. Empty descriptions occur in 3/50 versus
26/50; older/format composition is a material confound, not a causal finding.
The samples span 21 and 19 property publisher-account proxies (37 distinct), and
36 of 37 groups lack structured interior area throughout their sampled records.
Owner/assigned-agent IDs were pseudonymized for this analysis only; no profiles,
contacts or agency registry were fetched. These proxies do not establish verified
agency identity or publisher reliability. Small groups cannot support rankings.

`analytics/harta_evidence.py` supplies a read-only, purpose-specific projection.
Actual pipeline errors determine valuation eligibility. Quarantined records retain
UUID, URL, raw/parsed/normalized IDs, content hash, capture time and source-claimed
street/address/neighborhood/coordinate provenance in the existing lineage and
private evidence export. Address and map pin remain matching candidates, never
independent location verification or automatic canonical matches. No alternative
listing database or source-priority change was introduced.

Parser accuracy, completeness and publisher trust are separate: the 4 recovered
claims agree with independent HTML; 95/100 diagnostic records still have no usable
interior area; publisher reliability remains UNKNOWN. Actual original-cohort
quality policy 1.1.0 recalculates validity 2→6, completeness 69.625→75.125,
location precision 24.2→47.0, freshness 93.4 unchanged and composite
46.415→48.815 provisional. Independent location correctness and historical
reliability remain UNKNOWN. Proposed weight remains **1.00 inactive**.

Reproducible analysis code: `scripts/research/analyze_harta_area.py`.
Companion executed notebook: `reports/research/harta_area_diagnosis.ipynb`.
Private input capture and area snippets are under `.tmp/harta-area-diagnosis/`;
aggregates, actual ETL/quality evidence and purpose-specific candidate exports are
under `reports/generated/harta/area_diagnosis/`. Neither full descriptions nor
publisher identifiers are committed. For a read-only replay:

```powershell
.venv/Scripts/python.exe scripts/research/analyze_harta_area.py --input .tmp/harta-area-diagnosis/source_diagnostic_private.json --output reports/generated/harta/area_diagnosis --research-env C:/MetrikResearch/config/research.env
```

Without `--research-env`, replay uses in-memory normalization only: resolved DB
reference IDs and historical quality comparison are unavailable. Additional-cohort
quality is explicitly diagnostic, not persisted pipeline evidence.

The actual repair refresh was run 219: 53 requests, 50 existing UUIDs re-fetched,
50 parsed/normalized versions, 3 accepted and 47 quarantined. Historical captures
and parsed results are retained. Database identity count remains 50; no duplicate
UUID/content-hash groups exist. All six other sources retain their baseline
raw/parsed/normalized counts and maximum IDs. The 360 pre-existing changed and
untracked file hashes are preserved. No push, deployment or collection enablement.

Final regression: **894 passed, 45 skipped, one pre-existing failure**, 3 warnings,
45.05 seconds. The unchanged failure is the weekly PowerShell runner literal
`exit $LASTEXITCODE` assertion; its pre-existing implementation uses `exit $result`.
Ruff check and format pass for all nine changed Python files. The area test module
adds explicit net/gross/living/terrace separation, preservation of missingness,
conflicts, negation, approximate/ranged values, garage exclusion, joined sentences,
location provenance and read-only purpose classification. No test or valuation
threshold was weakened. Logs: `.tmp/harta-area-diagnosis/`.

## Incremental collection and recovery

Two bounded state queries load latest UUID/time/hash for up to 10,000 identities and
metadata from 100 recent runs. New or changed summaries fetch details; unchanged
ones skip details until a seven-day recheck. Checkpoint format 3 forces a one-time
detail recheck of older captures so typed area and location evidence can be stored.
The original-cohort refresh's 50 `changed` scheduler counts are format invalidations,
not a claim that all 50 publishers edited their properties. Fingerprints cover selected summary
price, area, rooms, scope, address, coordinates and publication fields. The public
summary projection has no reliable updated_at/change feed or description: changes
only in unselected fields are reconciled at the periodic detail recheck.

Each detail's raw content and checkpoint commit atomically through the existing
pipeline/repository and source-local savepoint. A checkpoint must match stored
content hash and fingerprint version. Malformed, legacy, future and unpersisted
checkpoints cannot skip requests. Duplicate content is confirmed before checkpoint
advancement; summary fingerprints never alter raw detail hashes. Interruption
tests exercise recovery from committed items without spider close.

The scan restarts filtered pages; it does not claim a persistent snapshot cursor.
No ETag/Last-Modified support has been established. Explicit 404/410 or empty scoped
detail reads produce bounded unavailability observations, not permanent deletion.
Retries, bytes, status, parse/persistence errors, deadlines and request budgets are
reported. Retry-After over 60 seconds stops for a later run. `bounded_complete`
means the selected budget ended normally; errors and partial discovery still fail.

## Operator runbook

**Collection expansion remains paused.** The following general commands document
the collector; do not use default discovery to broaden the current 50-ID corpus.
Any authorized repair run must be restricted to the existing UUID allowlist.
Load and verify the private research environment. The local pilot used rema on
loopback port 15432.

```powershell
.venv/Scripts/groundtruth.exe crawl harta --max-listings 50 --max-pages 2 --max-requests 70 --max-seconds 240 --recheck-days 7
.venv/Scripts/groundtruth.exe etl run --source harta
.venv/Scripts/groundtruth.exe analytics source-quality report --source harta --as-of <UTC-ISO-TIME> --days 30 --segment --output reports/generated/harta/quality
```

Default limits are 75 details, 4 pages, 110 requests and 300 seconds. A page limit
also bounds scans consisting entirely of unchanged or excluded summaries. Join
crawl metrics to ETL by scrape_run_id; the spider does not claim valid counts.
For parser upgrades use existing source-scoped `etl run --source harta --reprocess`
after reviewing the intended raw population. Never point tests at the research DB.

Explicit research weekly selection exists through `crawl weekly --only harta
--stage crawl`; it is not an automatic job. The collector is ready for explicit,
bounded private research runs with quarantine monitoring; the measured sample has
only 6% usable original-cohort records after repair. Before expanding collection, assess
inventory coverage and seek better interior-area evidence. Any area-policy change
requires explicit review. Public inclusion and deployment remain separate decisions.

Private reports remain under `reports/generated/harta/`. Source quality is
provisional: the repaired 50-identity population scores 48.815, with weight 1.00 proposed
and inactive. Unknown independent location and historical reliability remain
unknown. Historical six-source evaluations are preserved.
