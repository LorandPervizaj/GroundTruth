# Autonomous weekly GroundTruth pipeline — final report

## Executive summary

The repository now contains a fail-closed, observable weekly GroundTruth-to-Metrik release transaction. It derives catch-up from a verified watermark, runs the existing eight-source crawl/ETL/analytics flow, applies source and data-quality gates, records statistical shadow predictions, versions and hashes the public release, packages it, and supports a separate persistent Azure research Job. A second workflow verifies the bundle again, builds an immutable serving image, deploys it to the existing Container App, checks the public contract, and automatically restores the previous image on failure. Telegram is primary notification; SMTP/Gmail is optional.

Repository implementation is complete through Phase 17. Live cloud enablement is not claimed because the Azure subscription has not yet demonstrated an allowed PostgreSQL Flexible Server SKU, the local research database has not been migrated/restored in Azure, and notification/OIDC secrets are not configured by repository code.

## Before vs after

Before: a Windows operator started weekly crawling against local Docker PostgreSQL, reviewed output, generated artifacts, built/pushed an image, and updated Azure manually.

After: a private cloud Job performs research work independently of the PC; verified state controls catch-up; structured gates block bad data; versioned bundles cross the private/public boundary; GitHub deploys only verified artifacts and rolls back failed production revisions.

## Final architecture

```text
Monday 03:00 UTC
  -> private Azure Container Apps Job (GroundTruth research image, no ingress)
       -> public portals/APIs
       -> dedicated persistent PostgreSQL 16/PostGIS Flexible Server
       -> crawl checkpoints + verified watermark on private Azure Files
       -> source QA -> ETL QA -> analytics/dedup -> statistical QA
       -> hashed/versioned release bundle on private Azure Files

Monday 15:00 UTC
  -> GitHub Actions via Azure OIDC
       -> download + SHA verify + internal artifact verify
       -> immutable Metrik image -> existing private ACR
       -> existing ca-metrik-api
       -> health/ready/meta/markets/lookup/compare/valuation/reports/UI smoke
       -> success, or restore previous immutable image and verify rollback

Public requests -> Metrik only -> verified artifacts + separate public writable DB
Private raw/parsed/normalized research data never enters the public image/API.
```

## Git safety

- Original upstream SHA: `4aa9cbf1c14bb492d6940adcf78875e7c61d057d`.
- Baseline checkpoint SHA: `f7e913095f4130006a4cfc9e5980fdc8109ac217`.
- Baseline tag: `pre-autonomous-weekly-release-20260923`.
- Implementation branch: `feat/autonomous-weekly-release`.
- Implementation tip before this report: `e78036b`.
- Remote: `https://github.com/LorandPervizaj/GroundTruth.git`.
- Branch and baseline tag were pushed successfully.
- No reset, clean, rebase, history rewrite, force push, or secret commit was used.

Implementation commits:

- `5ef7dc9` canonical weekly release command
- `628d6c5` watermarks, catch-up, state, locking
- `7c4bf8a` source-health gate
- `697545e` ETL/data-quality gate
- `678470f` statistical sanity shadow gate
- `eeabe86` GitHub workflow parse repair
- `3e010bd` release metadata and packaging
- `0031b6f` private Azure research environment
- `d3136f2` schedule and manual control
- `5fce7b0` immutable deployment and rollback
- `cac47b5` Telegram notifications
- `3e0b8c7` optional email reports
- `bce6855` public DB durability plan
- `9aca444` workflow/rollback tests
- `5b77404` shadow calibration history
- `e78036b` Docker private-data exclusion and immutable SHA injection

## Azure resources

Existing serving resources: resource group `rg-metrik-beta-eus2`, ACR `acrmetrikbetalgy2mu`, Container App `ca-metrik-api`, its Container Apps environment, managed identity, and Log Analytics.

Planned research resources from `infra/azure/research.bicep`: `job-groundtruth-weekly`, `cae-groundtruth-research`, a dedicated PostgreSQL Flexible Server/PostGIS instance, `pipeline-state` and `verified-releases` private file shares, research Log Analytics workspace, and a user-assigned identity with ACR pull. Exact globally unique database/storage names include the deployment suffix.

## Database architecture

The research database owns raw, parsed, normalized, validation, lineage, lifecycle, observations, snapshots, and ETL metrics. It must be persistent and private. The public database owns runtime product submissions/events only; it does not become a research query backend. The live public sidecar is currently ephemeral and is addressed separately in `PUBLIC_DATABASE_DURABILITY_PLAN.md`.

## Pipeline stages and gates

1. Lock/preflight and run identity.
2. Verified-watermark lookback resolution.
3. Existing weekly crawl/ETL/analytics pipeline.
4. Source-health gate: RED blocks.
5. ETL/data-integrity gate: RED blocks.
6. Statistical sanity: shadow/report by default; RED blocks after promotion.
7. Release metadata and versioned bundle build.
8. Artifact verification: any failure blocks.
9. Deployment-boundary bundle/hash/artifact verification.
10. Immutable build/push and previous-target capture.
11. Container App deployment and production smoke.
12. Automatic rollback and rollback smoke on failure.

Each research stage records start/end/duration, status, counts, details, and error in atomic JSON.

## Watermark and recovery design

Only a fully verified release advances `last_verified_data_through`. Lookback includes one overlap day, has a seven-day minimum, and is capped at 56 days. Failed runs retain their evidence without advancing state. Existing raw-content, observation, lifecycle, and snapshot uniqueness plus resumable checkpoints make retries bounded and idempotent. Azure Files locking and GitHub concurrency prevent overlap.

## QA rules

Source policies use completion, errors, configurable per-source minimums, and the median of recent successful runs. ETL policies use existing parse/normalize/validation facts and never redefine listing validity. Deterministic RED blocks immediately. Statistical changes compare inventory, medians with sample sizes, comparables, rent-yield coverage, field coverage, and distributions. New heuristic thresholds remain shadowed for 3–5 cycles; GREEN/YELLOW/RED evidence is retained for operator calibration.

## Scheduler

Research: Monday `03:00 UTC` (`04:00/05:00 Europe/Belgrade`, depending on DST). Deployment pickup: Monday `15:00 UTC`. Both support manual dispatch. Job retry limit is one, execution timeout is 12 hours, and overlapping publication jobs do not cancel one another.

## Secrets

Names only: `AZURE_CLIENT_ID`, `AZURE_TENANT_ID`, `AZURE_SUBSCRIPTION_ID`, research PostgreSQL password/`DATABASE_URL`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`, optional `SMTP_USERNAME`, `SMTP_PASSWORD`, `SMTP_FROM`, `PIPELINE_EMAIL_TO`, and existing Metrik health/database secrets. GitHub variables hold non-secret resource names.

## Deployment and rollback

The deploy workflow downloads the newest (or explicitly selected) bundle, checks its SHA sidecar, verifies internal hashes/schemas (including lookup data, comparables, annual report, and rent-yield data), checks `publishable`, creates `metrik-api:<release-id>-<git-sha>`, records its digest, captures the prior image/revision, updates the app, and asserts `/api/meta` exposes the candidate release. Failure after deployment restores `PREVIOUS_IMAGE` and reruns the same smoke suite.

## Notifications

Telegram messages summarize release/run IDs, data-through date, source states, normalized/quarantined counts, failed stage, publication state, image/revision, and rollback status. Errors are truncated; tokens are never logged. Optional email adds detailed stage summaries and is never safety-critical.

## Tests

- Focused automation/workflow suites passed throughout implementation.
- Bicep compilation: passed.
- Workflow YAML parsing: passed.
- PowerShell smoke syntax: passed.
- Final full local suite on 2026-09-23: `569 passed, 33 skipped, 1 warning` in 32.34 seconds.
- The warning is an upstream Starlette `httpx` deprecation.
- Skips are environment/feature dependent, including unavailable local PostgreSQL/browser services.

## Remaining risks

- Azure for Students may still block every suitable Flexible Server SKU.
- No cloud research DB migration or Azure point-in-time restore has been executed.
- No live Telegram/email delivery has been tested.
- GitHub OIDC federation, environments, secrets, variables, and least-privilege role assignments require account configuration.
- The new scheduled workflows exist only on the feature branch until merged into the default branch.
- Statistical thresholds need 3–5 real weekly calibration cycles.
- The live public sidecar remains ephemeral until P1 is implemented.

## Deferred work

- P1 public writable database migration.
- Statistical gate promotion after calibration.
- Private networking hardening after subscription/SKU selection.
- Optional SMTP enablement.
- Any parser repair prompted by future source changes.

## Operator cheat sheet

See `docs/AUTONOMOUS_WEEKLY_PIPELINE_RUNBOOK.md` for exact commands covering manual run, status, retry, scheduler pause/resume, publication disable, last-release deployment, rollback, logs, Telegram testing, backup verification, restore drills, and Windows fallback.
