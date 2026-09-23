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

## Component inventory and observed contracts

| Area | Current implementation | Automation implication |
| --- | --- | --- |
| Raw persistence | `RawListing` is immutable-by-convention and constrained by `(source_website, source_listing_id, content_hash)`. | Re-fetching an unchanged listing cannot create uncontrolled identical raw rows. |
| Parse/normalize | `EtlService` records parse, normalize, validation, extraction-rate, duplicate-candidate, parser-version, normalization-version, and gazetteer-version metrics. Invalid rows are recorded separately with stage and error codes. | Release QA should aggregate these existing facts rather than reinterpret listing validity. |
| Source runs | `ScrapeRun` and Scrapy stats retain completion/error information; weekly source checkpoints retain crawl and ETL state plus run IDs. | Source-health decisions can be derived from durable database facts and existing checkpoints. |
| Observation history | `ListingObservation` has a uniqueness constraint for its observation identity; lifecycle rows are unique per source/listing. | Weekly retries can safely repeat lifecycle/observation operations. |
| Market snapshots | Snapshot uniqueness is `(snapshot_date, neighborhood_id)`. | A retried weekly analytics pass replaces or reuses the same logical period rather than multiplying snapshots. |
| Active corpus | Corpus filters select valid, active, current parser rows and cross-source primary rows. `run_audit(..., dedupe=True)` and corpus writers use the established cross-dedup logic. | The release orchestrator must invoke the existing analytics stage, not add another dedup definition. |
| Derived products | Weekly analytics writes snapshots, observations, audit artifacts, corpus artifacts, annual report, lookup cache, comparables, statistical QA, and source-skew output. Rent-yield is included through the public artifact/report generation path. | One successful analytics stage already covers the serving datasets; release build repeats the authoritative cache/report build and hash stamping. |
| Statistical gate | `run_statistical_qa` emits JSON/CSV evidence, stamps the manifest, raises on hard failure, and distinguishes pass-with-warnings. | Deterministic failures are blocking today; new historical heuristics should begin in shadow mode. |
| Release verification | Verifies manifest structure, each lookup hash, public schema/field allowlist, QA evidence hash/status, comparables files/hashes/revision, and annual-report hash. | This is the final data-publication gate and must remain fail-closed. |
| Runtime readiness | Production readiness requires loaded lookup/comparables caches, verified artifact integrity, and the configured database. | Deployment verification must wait for `/api/ready`, not merely a successful Azure update. |
| Product writes | `PRODUCT_WRITE_BACKEND=database` stores alerts, feedback, contact/product submissions, and product events in `product_submissions`. | The live sidecar contains user-generated operational data and its `EmptyDir` is a durability risk independent of research automation. |
| Deployment | GitHub Actions verifies artifacts, builds a SHA-tagged minimal image, scans it, pushes to ACR, updates `ca-metrik-api`, waits for readiness, and runs limited smoke tests. | Extend this path with release identity, complete smoke, previous-image capture, and rollback instead of creating a second CD system. |
| Backups | Compose-oriented `pg_dump`/restore scripts and disposable restore drills exist. Azure Flexible Server IaC specifies 7-day backup retention but is not deployed. | Cloud research DB provisioning needs an Azure-native restore drill and explicit migration steps; local DB remains a recovery copy. |

## Exact current weekly order

1. Resolve an interval and construct eight source jobs: MerrJep rent/sale, Gjirafa rent/sale, Pro-RKS, Vision, Topia, and MyRealEstate.
2. Run source subprocesses, capture their `scrape_run_id`, and persist per-source checkpoints.
3. Normalize each successful source run, optionally trailing directly behind its crawl.
4. Apply lifecycle absence only when all variants for the logical source are healthy.
5. Generate market snapshots and listing observations for the window end.
6. Run the audit with cross-dedup enabled and write audit artifacts.
7. Write active-corpus artifacts and export the annual report.
8. Build lookup and valuation-comparables caches.
9. Run statistical QA and stamp its evidence into the lookup manifest.
10. Write source-skew diagnostics and verify the complete release artifacts.

The existing weekly path therefore already performs more than its command name suggests. A new release command should wrap and record this flow, not call lower-level analytics a second time.

## Failure and observability behavior

- Crawl subprocess failures are retained per source and successful sources may continue.
- ETL failures are retained per source and do not silently become success.
- Lifecycle absence does not advance for unhealthy source groups.
- Analytics and artifact-verification failures propagate and stop the command.
- Weekly checkpoint JSON is operator-readable but is stored under ignored generated output and is not a release/deployment ledger.
- Structured application logging exists, while a single durable run summary spanning research and deployment does not.
- Current GitHub deployment concurrency prevents concurrent deploy jobs but there is no shared lock covering research execution outside Actions.

## Repository inconsistencies to address carefully

- `reports/generated/lookup_cache/**` and `data/api/annual_report.json` are version-controlled generated outputs. The workflow also supports downloading an external artifact bundle. Until a single artifact-transport authority is selected, both paths can drift.
- `groundtruth crawl weekly` builds and verifies artifacts during analytics, while `groundtruth release build-artifacts` builds them again. The canonical release operation must define one authoritative final build and avoid inconsistent timestamps/hashes.
- The Windows and cron schedulers invoke the older weekly crawl directly and use machine-local state; neither represents a cloud release transaction.
- Azure has both preferred Flexible Server IaC and an actually deployed sidecar fallback. Documentation correctly calls the sidecar ephemeral, but the live public configuration enables database-backed product writes.
- The current smoke script expects valuation to be unavailable, while the live Container App configuration has `VALUATION_PUBLIC_ENABLED=true`. Smoke expectations must be derived from the intended production contract before automation is enabled.
- The remote reports that the GitHub repository moved from `riverdoggo/GroundTruth` to `LorandPervizaj/GroundTruth`; pushes currently redirect successfully, but automation should use the canonical remote URL.

## Phase 1 conclusions

The safest minimal design is a release transaction layered above the existing weekly implementation. The new layer owns run identity, lock, verified watermark, gate summaries, release metadata, and deploy handoff. Existing crawler, ETL, corpus, dedup, analytics, statistical QA, and artifact-verification code remains authoritative. Cloud execution and database durability are infrastructure concerns around this command, not reasons to duplicate domain logic.

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
