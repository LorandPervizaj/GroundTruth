# Market data contract and operations

## Pipeline contract

The supported flow is crawl → normalize/ETL → validation → lifecycle update → canonical cross-source deduplication → population selection → metric calculation → statistical QA → release verification → publication.

A failed or partial crawl never proves absence. Lifecycle state is advanced only for a successful source checkpoint. Listings progress from `ACTIVE` to `POSSIBLY_INACTIVE` and then `INACTIVE` according to source policy; reappearance returns them to `ACTIVE`. A canonical property group is current when any member is active.

## Four datasets, four purposes

- Current inventory: lifecycle-backed active canonical groups; no recency proxy.
- Recent pricing corpus: valid canonical listings in an explicit 365-day window.
- Historical observations: time-series observations with period-level minimum samples.
- Valuation comparables: transaction-specific, location- and area-filtered estimate inputs.

These populations may overlap, but are not interchangeable. API responses expose `pricing_window_days`, `inventory_as_of`, `corpus_revision`, and `generated_at` so consumers can tell which contract applies.

## Release gates

`groundtruth corpus market-integrity` writes the baseline diagnostics. `groundtruth dedup benchmark` measures labelled-pair precision, recall, blocking recall, threshold sensitivity, and emits error cases by source pair. The release builder runs statistical QA and stamps its result and hash into the manifest. Release verification rejects missing or failed QA, revision mismatch, impossible sample sizes, semantic registry mismatch, alias divergence, duplicate buckets, and invalid artifact hashes.

Large week-over-week shifts are warnings for review; hard semantic and integrity failures block publication. Public lookup, compare, market-summary, and rent-yield surfaces are checked against the canonical lookup metrics.

## Rollback

1. Do not publish a manifest that fails QA or verification.
2. Restore the last verified lookup-cache directory, annual report, and rent-yield artifact as one release unit.
3. Restore its manifest; never mix entries from different corpus revisions.
4. Reload the application cache and run release verification.
5. Preserve the failed artifacts and QA details for diagnosis.

Schema rollback keeps the deprecated aliases until all tracked consumers have migrated. Lifecycle-table rollback is application-first: deploy code that no longer writes the table before reverting its migration. Raw crawls and normalized records are evidence and must not be deleted as part of an analytics rollback.

## Operating commands

```text
groundtruth corpus market-integrity
groundtruth dedup benchmark
groundtruth crawl weekly --stage analytics --skip-crawl
groundtruth release verify-artifacts
pytest
```

Generated reports belong under `reports/generated`; reviewed labels belong under `data/deduplication` and should be extended with difficult real-world pairs over time.
