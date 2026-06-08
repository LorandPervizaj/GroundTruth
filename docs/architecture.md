# Architecture

## Stack

```
Python 3.13
  ↓
PostgreSQL 16 + PostGIS
  ↓
Docker (postgres + pgAdmin only)
```

No Redis. Single machine, single user, scheduled scraping.

## Pipeline Stages

```
Website → Raw → Parsed → Normalized → Dedup Score → Canonical → Analytics → Report → Dashboard
```

Every stage is independent. Raw data is never overwritten.

## Versioning

Every scrape attaches:

| Field | Where |
|-------|-------|
| `run_id` | `scrape_run_id` on all pipeline tables |
| `scraped_at` | `raw_listings.scraped_at` |
| `spider_version` | `scrape_runs`, `raw_listings`, `parsed_listings`, `normalized_listings` |

This answers: *What changed between June and July?*

## Key Tables

| Table | Purpose |
|-------|---------|
| `raw_listings` | Immutable source payload |
| `parsed_listings` | Structured extraction |
| `normalized_listings` | Cleaned, gazetteer-matched |
| `canonical_properties` | Deduplicated best-known record |
| `listing_sources` | Provenance links |
| `property_events` | Listed → price reduced → removed lifecycle |
| `price_history` | Price snapshots over time |
| `market_snapshots` | Nightly precomputed neighborhood metrics |

## Module Layout

```
src/groundtruth/
├── scrapers/           # Scrapy spiders
├── processing/
│   ├── normalizers/    # Field cleaning
│   └── deduplicator/
│       ├── candidate_generation.py
│       ├── similarity.py
│       ├── scoring.py
│       └── merge.py
├── analytics/
│   ├── metrics/
│   │   ├── price.py
│   │   ├── rent.py
│   │   ├── yield.py
│   │   ├── premium.py
│   │   └── luxury.py
│   ├── market_table.py     # LinkedIn-ready table
│   ├── market_health.py    # Neighborhood rankings
│   ├── buyer_score.py      # Budget recommendations
│   └── snapshots.py        # Nightly market_snapshots
├── services/
│   ├── report_service.py   # Output → reports/generated/
│   └── event_service.py    # property_events detection
└── models/

reports/
├── templates/          # Source templates (in git)
└── generated/          # Output PDFs/CSVs (gitignored)
```

## Recommended Build Order

```
Gjirafa scraper → 5000 listings → cleaning → normalization → deduplication
  → generate report → publish on LinkedIn → THEN build dashboard
```

Do not skip to the dashboard after scraping.

## Deduplication

Split into four concerns:

1. **candidate_generation** — limit O(n²) with neighborhood/price bands
2. **similarity** — per-field comparison functions
3. **scoring** — weighted confidence (score only by default)
4. **merge** — explicit merge when confirmed

## Analytics Highlights

### Neighborhood Market Table

One table: Median €/m² | Inventory | Median Size | Median Rent | Yield | Luxury %

### Market Health Score

Price growth + inventory + yield + luxury % + stability + construction = ranked neighborhoods

### Buyer Score

Given €150,000 → ranked neighborhoods by value (€/m², size, inventory, yield)

### Market Snapshots

Nightly `market_snapshots` rows precompute all dashboard metrics.
