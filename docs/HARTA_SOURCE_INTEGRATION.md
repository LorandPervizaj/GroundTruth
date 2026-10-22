# Harta research source integration

Status on 2026-10-22: **Gate 3 PASS for the bounded private research integration**.
This document and [Gate 3 evidence](HARTA_GATE_3.md) are this chat's implementation references.
The original broader plan remains [GroundTruth plan](GROUNDTRUTH_SOURCE_QUALITY_HARTA_PLAN.md).
No weekly or public release is enabled.

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
parser 0.2.0-harta, normal normalization, validation, parsed-linked quarantine and
source-quality policy 1.1.0. No schema migration or alternative store was introduced.
Registry priority remains 6, `weekly=False`, `public=False`; six existing sources,
winner priorities and public parser allowlist are unchanged.

| Source field | Handling |
|---|---|
| UUID | Stable source identity, verified against requested detail UUID. |
| city/type/transaction/status | Exact scope and active state checked again on details. |
| price_total / price_unit | Explicit total preferred; price fallback only for total. Per-m²/payment/deposit figures never become total price. Numeric locale groups validated. |
| living_area | Interior area for normalized area; absent remains unknown and quarantined. |
| surface_area / sqft | Total area/legacy alias retained separately; never silently converted into interior area or interpreted as square feet. HTML may derive sqft from surface_area. |
| features.rental_period | Explicit monthly evidence required. JSON-LD can supplement legacy HTML; unknown or conflicting periods remain validation issues. |
| description | Full text discarded; only labelled numeric consistency facts and transaction/property conflict flags retained. |
| address/street/municipality | Source evidence retained and passed through existing resolver; no fabricated location. |
| coordinates | Source map-pin provenance, sanity checked, never independent location verification. |
| created_at / updated_at | Publication/update evidence distinct from collection/check time; absent dates remain unknown. |
| bedrooms/bathrooms/floor/furnished | Explicit values only; no inference from area. |

Pre-storage allowlists remove contacts, profiles, owner/agent IDs, media, promotion
metadata and full HTML/description. Parser checks include conflicting totals,
transaction/property claims, interior exceeding total, incompatible municipality,
invalid coordinates and stale relative publication labels. Kosovo bounds establish
sanity only. The live first sample has interior area for just 1 of 50 records;
49 quarantines are a material source limitation, not permission to weaken validation.

## Incremental collection and recovery

Two bounded state queries load latest UUID/time/hash for up to 10,000 identities and
metadata from 100 recent runs. New or changed summaries fetch details; unchanged
ones skip details until a seven-day recheck. Fingerprints cover selected summary
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

Load the private research database environment and verify its destination before
running these commands. The verified local pilot used rema on loopback port 15432.

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
only 2% usable records. Before expanding to recurring production collection, assess
inventory coverage and seek better interior-area evidence. Any area-policy change
requires explicit review. Public inclusion and deployment remain separate decisions.

Private reports remain under `reports/generated/harta/`. Source quality is
provisional: the 50-record first population scores 46.415, with weight 1.00 proposed
and inactive. Unknown independent location and historical reliability remain
unknown. Historical six-source evaluations are preserved.
