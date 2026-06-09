# GroundTruth — Kosovo Real Estate Intelligence Platform

The scraper is an input. The asset is the data.

## What GroundTruth is

A reproducible market intelligence platform for residential real estate in Kosovo:

- **Ingestion** — multi-source listing collection (Gjirafa, MerrJep, agencies)
- **Extraction** — versioned parser pipeline with golden-dataset accuracy tracking
- **Lineage** — every statistic traces to `data_lineage` (raw → parser → ETL run)
- **History** — `market_snapshots` for trends no one can recreate retrospectively
- **Publication** — quarterly rental reports, neighborhood indices, methodology

## Six-month roadmap

| Month | Focus |
|-------|-------|
| 1 | Parser quality (v1.3.0 release criteria) |
| 2 | MerrJep integration |
| 3 | Analysis and publication |
| 4 | Dashboard |
| 5 | Historical trends |
| 6 | ML (neighborhood classifier first) |

Only months 1–2 are engineering-heavy. Months 3–6 extract value from data.

## ML roadmap (when ready)

1. Rule-based extraction
2. Gazetteers
3. Alias matching
4. ML neighborhood classifier (hybrid fallback)
5. Gradient boosting price estimator
6. Outlier detection for bargains
7. Recommendation engine

Skip deep learning unless the dataset reaches hundreds of thousands of verified labels.

## Publication targets

- Quarterly Kosovo Rental Report
- Neighborhood Price Index
- Rental Yield Rankings
- Inventory heat maps
- Affordability rankings
- Price reduction analysis

## Parser release criteria (v1.3.0)

- Invalid rate < 3%
- Neighborhood coverage > 95%
- Area coverage > 95%
- Price coverage = 100%
- Golden dataset accuracy > 97%

## Reproducibility

Every normalized listing has a `data_lineage` row:

```
listing_id → raw_id → parser_version → gazetteer_version → etl_run → created_at
```

Filter any report by parser version to reproduce or compare methodology changes.
