# Harta research source integration

Status on 2026-10-21: **implemented adapter, live integration verification BLOCKED**.
See [Gate 3 evidence](HARTA_GATE_3.md). This is not approval for weekly collection
or a public Metrik release. This chat's Part 3 reference is this document and Gate 3.

## Authorization and observed access boundary

The owner confirms permission to collect relevant public Harta listings. No specific
rate limit or access exemption was supplied. The implementation uses public HTTPS,
robots rules, a fixed research user agent, concurrency 2, a one-second delay,
20-second timeout and two retries. It never logs in, rotates identities, solves
challenges or accesses profiles, contacts, media, maps or administrative endpoints.

During browser investigation Harta displayed `human-gate-title`, explaining that
automatic collection requires human verification, protected by Cloudflare Turnstile.
Collection stopped. **Do not use direct HTTP or a different endpoint to circumvent
this observed restriction.** An access arrangement with Harta must resolve it before
any further live run. No clearance is inferred from the general scraping permission.

## Observed source contract

Public pages inspected on 2026-10-21:

| Public surface | Observed behavior / integration consequence |
|---|---|
| `/robots.txt` | Public pages allowed; `/api/`, `/profile`, `/dashboard`, `/lovable/` excluded. |
| `/pronat`, `/me-qira` | Server-rendered public previews; browser map loads a different inventory. Previews are not complete discovery. |
| `/prona/banesa/prishtine` | Frontend route explicitly selects apartment/condo and Prishtina aliases, but returned **zero**, contradicting matching map listings. Not a reliable empty-market signal. |
| Public map frontend response | Observed GET `/_serverFn/2aa15913d61c7649952f4708ca3873509d830e6b390357e063048a8977b1041b` with bbox, filters, listingType, zoom, limit. Response reported `COALESCE types jsonb and text[] cannot be matched`. No invented API or replay of this failing function is wired into the spider. |
| `/property/<slug>-<id-prefix>` | Public property HTML contains TanStack hydration `property:$R[n]={...}` and `RealEstateListing` JSON-LD. Full UUID inside the property is authoritative. Frontend also constructs `/property/<UUID>`; this URL form remains live-unverified here. |

The literal reader accepts only the observed strings, numbers, booleans, null,
objects, arrays and inline `$R[n]=` assignments. It executes no JavaScript and rejects
expressions, references, missing fields, excessive nesting and oversized responses.
Version/shape changes fail closed.

The category frontend loader requests at most 24 records. No reliable pagination
or change-feed contract was established. **The current spider reads one bounded
category response; `max_pages` is a compatibility budget, not implemented pagination.**
It does not broaden discovery to the whole site or fabricate page parameters.
Repairing/confirming targeted discovery is essential before claiming completeness
or attempting the requested 50–100 listing pilot.

## Implementation map

| Component | Integration |
|---|---|
| `scrapers/harta_contract.py` | Public HTML extraction, strict municipality/type filtering, UUID identity, pre-storage allowlist. |
| `scrapers/spiders/harta.py` | BaseRealEstateSpider, bounded requests, source-only middleware, raw persistence subclass, run checkpoints and aggregate report. |
| `services/harta_parsing.py`, `services/parsing.py` | Version `0.1.0-harta`, source dispatch, raw/payload identity agreement, typed values and provenance. |
| `services/normalization.py` | Existing price/area normalizers, gazetteer and source-coordinate path reused without modifying its behavior. |
| `services/etl.py` | Existing validator runs; Harta critical source issues append validation failures and enter normal parsed-linked quarantine. Other sources take their previous path. |
| `portals/registry.py`, `versions.py` | Seventh registered source, last priority 6, `weekly=False`, `public=False`. The six existing active parser versions remain the public corpus allowlist. |
| `crawl/spider_commands.py`, `crawl/weekly.py` | Explicit research selection registered; automatic default job list unchanged. |
| `analytics/source_quality_population.py` | Absolute source `created_at` publication contract recognized; existing policy 1.1.0 unchanged. |

No migration, alternative listing database or alternate ETL system was introduced.
The raw pipeline subclass calls existing persistence and commits bounded individual
items; successful detail checks are saved in the existing scrape-run metadata.
This also avoids a later duplicate rollback discarding earlier Harta inserts.

## Field meanings and conservative decisions

| Harta field | GroundTruth handling |
|---|---|
| `id` | Full source UUID, independent of price/title/address; mismatch rejected. |
| `city`, `property_type`, `listing_type` | Exact Prishtina aliases; apartment/condo/studio; buy/rent. Ambiguous municipality, other category or unsupported transaction rejected. |
| `status` | Only active property accepted by parser. 404/410 counted as unavailable, without permanent deletion or whole-source inference. |
| `price_total`, `price`, `price_unit` | Explicit total preferred; `price` fallback only for `total`. €/m² never treated as total. Missing/contradictory totals quarantined. |
| `features.rental_period` | Monthly must be explicit. If hydration omits it, public JSON-LD `Rental Period` can supply evidence. Missing/daily period quarantined. |
| `living_area` | Interior area used for normalized area. |
| `surface_area`, `sqft` | Source total area and legacy total field; not silently substituted for interior or interpreted as square feet. Missing interior quarantined. Gross/interior differences retained as different concepts. |
| Description | Not retained. Only explicit labelled asking-price/area facts survive for discrepancy checks; ambiguous formatting quarantined. No price inferred from deposits/garage fees. |
| Address/city/neighborhood | Raw municipality/address retained; source street or first address component preserved and passed through existing resolver. No fabricated neighborhood/street. |
| `latitude`, `longitude` | Existing `source_coords` path; provenance explicitly unverified map pin. Never independent location verification. |
| `created_at` | Absolute publication timestamp, separate from scrape/check time and `updated_at`; missing/invalid stays unknown. |
| Bedrooms/bathrooms/floor/furnished | Explicit structured values only; missing remains missing. Single `floor_levels` value may supply floor. No room inference from size. |

Raw HTML, descriptions, contacts, owner/agent identifiers, profiles, images,
promotion metadata and environmental/analytical data are excluded before storage.
The observed diagnostic page had structured rent differing from its explicit
description asking price, and total area with no interior area. Both issues are
detected. This single example does not establish source-wide accuracy.

## Incremental and recovery behavior

Existing Harta raw records are read by source UUID (up to 10,000 recent versions).
The fingerprint covers summary identity, city/type/transaction, title, price, area,
rooms and any available update time. New/changed summaries request details;
identical summaries skip them until a seven-day detail recheck is due. Rechecks
are anchored to successful captured detail checks stored in scrape-run metadata,
including checks that produced no new raw version. Only previously stored UUIDs
can be skipped. Interrupted, unstored new items remain discoverable on restart.

The scan restarts the bounded index instead of persisting an invented pagination
cursor. The recent-raw/run lookup bounds can cause extra requests at larger scale;
they cannot make an unknown identity count as stored. Raw uniqueness and content
hashes remain authoritative. Absence from this partial index is never removal.
Conditional requests are not implemented: ETag/Last-Modified support was not
established. Detail summaries are not trusted indefinitely.

Every request including retries/robots is subject to the 110-request default cap.
HTTP 429/temporary errors back off; Retry-After seconds and HTTP dates are honored.
A cooldown over 60 seconds stops the run for a later retry. HTTP 401/403 or a
challenge stops access immediately. Network exceptions have bounded Scrapy retries.
Request, response-byte, status, detail, exclusion/change/recheck and parse counters
are recorded. An empty/changed discovery response exits unsuccessfully.

## Operator commands after source access/discovery is resolved

Do not run these to work around the current verification gate:

```powershell
.venv/Scripts/groundtruth.exe crawl harta --max-listings 75 --max-pages 1 --max-requests 110 --recheck-days 7
.venv/Scripts/groundtruth.exe etl run --source harta
.venv/Scripts/groundtruth.exe analytics source-quality report --source harta --as-of <UTC-ISO-TIME> --days 30 --segment --output reports/generated/harta/quality
```

Use the documented private research database environment, never a production URL.
Explicit weekly selection is available through `crawl weekly --only harta --stage crawl`;
check current CLI help before execution. It is never appended to automatic jobs,
even if Gate 3 later passes. Operator enablement remains a separate decision.

Generated reports stay local under `reports/generated/`. Quality weights remain
neutral **1.00**, proposed and inactive; independent location and publisher history
remain unknown. Historical six-source evaluations are not rewritten.
