# Architecture

**GroundTruth** is the research/engineering codebase; **Metrik** is the public product built from its analytics and release artifacts.

## Live publish path (current)

```text
Crawl → raw_listings (immutable, content-hash identity)
     → parsed_listings (parser_version)
     → normalized_listings + data_lineage
     → active corpus (latest row per source listing + corpus filters)
     → cross-portal dedup (analytics-layer; is_canonical_primary)
     → analytics / market lookups
     → release artifacts (lookup_cache + comparables + annual JSON)
     → Metrik FastAPI + static pages
```

Public Metrik prefers **disk release artifacts** (`reports/generated/lookup_cache/`). Dataset freeze manifests under `data/datasets/` label versions and fingerprints; they do **not** by themselves reconstruct or lock the served cache. Rebuild artifacts from the research DB, then verify before deploy.

See also [DATASET_V2_FREEZE.md](DATASET_V2_FREEZE.md), [DATA_HANDLING.md](DATA_HANDLING.md), [DEPLOYMENT.md](DEPLOYMENT.md).

## Deferred architecture (not on the live path)

The following remain in the schema / codebase for a possible future durable merge. They are **not** how Metrik currently canonicalizes inventory:

| Component | Status |
|-----------|--------|
| `canonical_properties` table | Deferred — do not treat as product SoT |
| `CanonicalPropertyRepository` | Unused in production callers |
| `DuplicateMerger` | Unused in production callers |
| `PropertyEventService` | Unused in production callers |

**Current product canonicalization:** `active_corpus_bundle()` → `apply_cross_dedupe()` → rows with `is_canonical_primary`.

Ops note: `groundtruth dedup report` exports analytics-layer groups; it does not populate `canonical_properties`.

## Evidence trail (research quality gates)

```text
Crawl → raw → parsed → normalized
     → golden eval gate (data/golden/)
     → post-ETL audit (corpus report, etl errors)
     → claims registry (data/claims/registry.csv)
     → dataset freeze manifest (data/datasets/dataset_v*.json)  # metadata / fingerprints
     → release build + verify → Metrik
```

## Stack

```
Python 3.13
  ↓
PostgreSQL 16 + PostGIS
  ↓
Docker (postgres + pgAdmin only for local research)
```

No Redis. Single private research host; scheduled ingest under [CRAWL_POLICY.md](CRAWL_POLICY.md). The public Metrik deploy does not run collectors.

## Pipeline stages (research)

```
Website → Raw → Parsed → Normalized → Active corpus → Cross-dedup → Analytics → Release → Metrik API
```

Raw data is never overwritten (append-only via content hash). Stages are CLI-orchestrated (crawl / etl / weekly / release), not a single always-on worker (except optional scheduled ingest).

## Versioning

Every scrape attaches:

| Field | Where |
|-------|-------|
| `run_id` | `scrape_run_id` on all pipeline tables |
| `scraped_at` | `raw_listings.scraped_at` |
| `spider_version` | `scrape_runs`, `raw_listings`, `parsed_listings`, `normalized_listings` |

This answers: *What changed between June and July?*

## Key tables

| Table | Purpose | Live product use |
|-------|---------|------------------|
| `raw_listings` | Immutable source payload | Research / replay |
| `parsed_listings` | Structured extraction | Research |
| `normalized_listings` | Cleaned, gazetteer-matched | **Yes** — corpus source |
| `market_snapshots` | Precomputed neighborhood metrics | Analytics / history |
| `canonical_properties` | Planned durable merge | **Deferred** |
| `listing_sources` / `property_events` / `price_history` | Planned provenance / lifecycle | **Deferred** (public DOM uses listing observations) |

## Module layout

```
src/groundtruth/
├── scrapers/           # Scrapy spiders
├── processing/
│   ├── normalizers/    # Field cleaning
│   └── deduplicator/   # Scorer used by analytics cross_dedup; merger deferred
├── analytics/
│   ├── corpus.py       # active_corpus_bundle (product SoT)
│   ├── cross_dedup.py  # Live cross-portal primary selection
│   ├── metrics/
│   └── …
├── services/
│   ├── lookup.py / lookup_cache.py
│   └── …
├── api/                # Metrik FastAPI
└── models/
```

## Deduplication

**Live path:** `analytics/cross_dedup.py` blocks candidates, scores with `DuplicateScorer`, union-find groups, picks primary by source priority + confidence.

**Deferred path:** DB `canonical_properties` merge persistence remains unwired for publish. `processing/deduplicator/` keeps `scoring.py` / `similarity.py` for live `cross_dedup`; `candidate_generation.py` and `merge.py` were removed as dead production code.

## Analytics highlights

### Neighborhood market table

Median €/m² | Inventory | Median Size | Median Rent | Yield | Luxury %

### Market health / buyer score / snapshots

Neighborhood rankings, budget recommendations, and snapshot rows support research and product caches; Metrik hot paths prefer precomputed lookup artifacts.

## Location resolution

Two complementary layers (not competing authorities):

| Layer | Module | Role |
|-------|--------|------|
| Field matching | `gazetteers/loader.py` (`GazetteerService`) | Exact/alias/fuzzy match for street, complex, neighborhood, building fields during normalization |
| Listing hierarchy | `gazetteers/location_resolver.py` (`LocationResolver`) | City → neighborhood → district → complex resolution for a whole listing via `NormalizationService` / `resolve_listing_location()` |

Do not collapse these into one class without redesigning both call sites.

## Validation vs valuation bounds

Three intentional bound layers:

1. **Ingestion validity** — `processing/validation.py` (`ListingValidator`): broad sanity so clearly broken rows are quarantined.
2. **Active corpus** — `analytics/corpus_filters.py` (`ACTIVE_CORPUS_WHERE`): parser version, age window, exclude informal sources, exclude validate-stage invalids.
3. **Valuation comparability** — `analytics/valuation.py` (`RENT_COMPARABLE_*` / `SALE_COMPARABLE_*`): stricter price/area bands so extremes that passed ingestion do not distort estimates.

Public analytics entry points must use `active_corpus_dataframe` / `ACTIVE_CORPUS_WHERE` (see `tests/test_corpus_authority.py`).

## Pipeline failure policy

Weekly pipeline (`crawl/weekly.py` + `scripts/run_weekly.ps1`):

| Failure | Behavior |
|---------|----------|
| One crawl source fails | Marked `failed` in checkpoint; other sources continue |
| ETL for one source fails | Marked `failed` on that source; siblings continue |
| Parse-failure rate spike | `check_parse_health` alerts; `assert_parse_health` can fail closed |
| Release artifact verify fails | `refresh_analytics` logs and **re-raises** (analytics stage not silent success) |
| Artifact transfer / publish | Public Metrik should keep last known-good verified release (ops); verify gate is mandatory before treating a build as releasable |

See `tests/test_pipeline_failure_safety.py` and `tests/test_weekly_ingest.py`.

## Public serving concurrency

Metrik API uses **in-process** lookup and comparables caches. Production entrypoint forces `workers=1` (`groundtruth serve` / prod CLI) so cache state stays coherent.

**Decision (P1-12):** horizontal multi-worker scaling is **not** required for one-market completion. Do **not** add Redis unless measured single-worker limits block a real production load. If that day comes, externalize cache with explicit failure behavior, local-dev mode, invalidation, and deploy topology documented first.

