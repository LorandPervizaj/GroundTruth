# Dataset v2.0 freeze — Phase 5 checklist

**Frozen:** 2026-06-12  
**Manifest:** `data/datasets/dataset_v2.0.json`  
**Fingerprint:** `4d4956eb49bfb75fc8abb63c84090edeb3c137b8fd5752b0dd33bfbf8b536f20`

## Headline stats

| Metric | Value |
|--------|-------|
| Normalized listings (unique) | 19,522 |
| Invalid rate | 0.2% (34 rows) |
| Golden eval accuracy | 99.9% (n=901) |
| Canonical active (after cross-portal dedup) | 10,412 |
| Cross-portal duplicate groups | 629 |
| Duplicates removed | 2,539 |

## Sources (normalized)

| Source | Listings |
|--------|----------|
| MerrJep | 11,108 |
| Gjirafa | 4,157 |
| Pro-RKS | 3,634 |
| Topia | 357 |
| MyRealEstate | 156 |
| Vision | 110 |

## MerrJep crawl

| Segment | Status |
|---------|--------|
| Apartment sale (12-month window) | Complete — run #18, 2,101 listings |
| Apartment rent | Corpus has ~7,400+ MerrJep rent rows; index crawl considered sufficient for v2.0 freeze |

Incremental ETL after crawl chunks: `groundtruth etl run --source merrjep`

## Cross-portal dedup

- Report: `groundtruth dedup report`
- Register: `data/deduplication/cross_portal_groups.csv` (local; see `data/deduplication/README.md`)
- **Decision:** Ship v1 with analytics-layer dedup only; DB `canonical_properties` merge deferred
- Active corpus analytics use one row per canonical group via `active_corpus_bundle()`

## Public product scope

**Rent and sale** — reported separately (~60% rent / ~40% sale in normalized corpus). Thin segments use confidence tiers instead of guessed averages.

- Valuation: rent and sale modes
- Market profiles: rent and sale pulse where data allows
- Statistics: rent and sale charts and KPIs
- Documented in About, methodology, and `quality.public_product_scope` in manifest (`rent_and_sale`)

## API / UI

- `GET /api/meta` — `dataset_version`, `dataset_frozen_at`, `dataset_fingerprint`, `invalid_pct`, `golden_accuracy_pct`, `public_product_scope`
- `GET /api/methodology` — same freeze fields + `cross_portal_dedup_note`
- Methodology page shows frozen dataset line

## Commands used

```bash
groundtruth corpus report
groundtruth etl errors
groundtruth dedup report
python scripts/evaluate_golden_dataset.py --input-file data/golden/golden_v1.csv
python scripts/freeze_dataset.py --version v2.0 --golden-accuracy 99.9
```

## Artifacts

| Artifact | Path |
|----------|------|
| Frozen manifest | `data/datasets/dataset_v2.0.json` |
| Corpus report | `reports/generated/corpus_report_20260612.json` |
| Dedup register | `data/deduplication/cross_portal_groups.csv` |
