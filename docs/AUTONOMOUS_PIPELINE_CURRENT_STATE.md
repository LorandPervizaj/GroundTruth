# Autonomous pipeline: current state audit

Audit date: 2026-09-23

## Existing flow

```text
public portal/API
  -> Scrapy source command
  -> scrape_runs + raw_listings
  -> source parser / normalization service
  -> parsed_listings + normalized_listings
  -> validation flags / lifecycle state
  -> latest-source-row + cross-source dedup active corpus
  -> snapshots, lookup cache, comparables, annual report, rent yield
  -> statistical QA
  -> hashed release manifest
  -> minimal Metrik image (no Scrapy or Playwright)
  -> ACR
  -> Azure Container App
```

The private/public boundary is already sound: research data remains in PostgreSQL on the research host, while the public image receives only allow-listed, hashed artifacts. The production Dockerfile intentionally excludes Scrapy and Playwright.

## Reusable components

- `groundtruth crawl weekly` already runs all eight automated source variants, scales page budgets with catch-up days, uses per-source subprocesses, supports parallelism, and persists resumable weekly checkpoints.
- Spider persistence and `skip_existing` controls provide retry idempotency. Scrape runs retain source-level counters and errors.
- The weekly analytics stage already records observations/lifecycle state and builds corpus, cross-dedup, market snapshots, lookup cache, comparables, annual report, rent-yield data, and statistical QA.
- `groundtruth release build-artifacts` builds the public artifact set; `verify-artifacts` validates required files, hashes, schema/public-field constraints, comparables consistency, and a passing QA result.
- `Dockerfile` bakes the verified lookup cache and `data/api` into the serving image.
- `scripts/azure/build-push.ps1` and `.github/workflows/azure-beta-deploy.yml` already verify, build an immutable image, push to ACR, update the Container App, and wait for readiness.
- `scripts/azure/smoke.ps1` exercises health, readiness, metadata, markets, lookup, compare, reports, rent yield, valuation behavior, write controls, and principal frontend pages.
- Existing PostgreSQL backup/restore scripts and integrity tests provide a base for research-database recovery drills.

## Gaps

1. No canonical release-level run record joins crawl checkpoints, QA, artifact identity, image identity, deployment, and final outcome.
2. Catch-up is based on weekly state or latest scrape completion, not the last successfully verified release data watermark.
3. Source health is printed for an operator but has no persisted GREEN/YELLOW/RED release decision or configurable historical comparison.
4. ETL integrity counts are not consolidated into a release gate result.
5. Statistical QA exists, but new anomaly policy has no explicit shadow-mode lifecycle tied to release runs.
6. Release metadata lacks a release ID, source Git SHA, previous release ID, and explicit data-through watermark.
7. The crawler and research database currently depend on the operator's Windows host.
8. The existing Azure deploy workflow has no automatic rollback and only partial production smoke coverage.
9. There is no Telegram notifier or concise stage-oriented operational summary.
10. There is no Monday cloud scheduler for the complete research-to-production transaction.
11. The live public PostgreSQL sidecar uses `EmptyDir`; writable product data is not durable. This is a separate P1 issue and must not be silently changed by the research pipeline.

## Chosen extension strategy

- Add a `groundtruth pipeline weekly-release` orchestrator that calls the existing weekly, analytics, release-build, and verification implementations.
- Persist release-run state as JSON in an operator-selected durable state directory and publish the same structured record as a workflow artifact. The verified watermark advances only after artifact verification; deployment fields advance only after live verification.
- Use an atomic filesystem lock plus CI concurrency to prevent overlap. Existing DB/source uniqueness remains the data-level idempotency control.
- Derive catch-up from the last verified watermark, bounded by configurable minimum and maximum days.
- Add conservative deterministic gates immediately; keep newly introduced historical/statistical heuristics in shadow mode by default.
- Run the canonical command on a scheduled cloud runner against a persistent Azure PostgreSQL/PostGIS research database. The public Container App remains serving-only.
- Extend one deployment workflow path with immutable release tags, previous-image capture, full smoke tests, rollback, and Telegram notification.
- Represent the persistent research database and supporting Azure resources as Bicep. Migration and restore remain explicit operator operations.

## Live infrastructure verified during audit

- Subscription: Azure for Students.
- Public app: `ca-metrik-api` in `rg-metrik-beta-eus2`.
- ACR: `acrmetrikbetalgy2mu`.
- Live image at audit: `acrmetrikbetalgy2mu.azurecr.io/metrik-api:4aa9cbf-devsync-202609220036`.
- Public database: PostgreSQL 16 sidecar with `EmptyDir`; no Flexible Server currently exists in the subscription.
- Container App minimum replicas: 1.

## Scope separation

P0 is the autonomous research-to-release pipeline and its persistent research database. P1 is migration of public writable product data away from the ephemeral sidecar. P1 receives a plan, not an implicit migration.
