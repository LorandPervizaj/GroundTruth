# Metrik production deployment

Public Metrik runs on **Azure Container Apps** (`ca-metrik-api`). Images are
built and rolled out only by GitHub Actions. The research database never
connects to production; production receives data only through verified release
bundles published as immutable GitHub Releases.

Research-side operation (runner, weekly pipeline, backups) is documented in
[LOCAL_RESEARCH_RUNNER.md](LOCAL_RESEARCH_RUNNER.md). Azure provisioning and
IaC are in [AZURE_BETA.md](AZURE_BETA.md).

## Two deploy paths

| Workflow | Trigger | What it ships |
| --- | --- | --- |
| `weekly-release-deploy.yml` | Called by `groundtruth-weekly-local.yml` after a release is published, or `workflow_dispatch` with an exact `release_tag` | Current code at the workflow commit **plus** the exact data release `groundtruth-release-<release_id>` |
| `azure-beta-deploy.yml` | Push to `master` touching `src/`, `web/`, `alembic/`, `data/api/`, `Dockerfile`, dependencies, `infra/azure/`, `scripts/azure/`; or `workflow_dispatch` | New code with the **data release currently live** (read from `/api/meta`), or an explicit `data_release_tag` |

Neither workflow has a schedule. A data release reaches production only after a
research run publishes it; a code push never replaces live data with the
committed `lookup_cache`.

## Verified release contract

A release bundle `groundtruth-release-<release_id>.tar.gz` plus its `.sha256`
contains only public serving artifacts:

- `lookup_cache/` (manifest with per-file SHA256, market lookup JSON,
  `rent_comparables.json.gz`, `sale_comparables.json.gz`, `comparables_meta.json`, QA summaries)
- `data/api/annual_report.json`, `data/api/rent_yield.json`

`scripts/release/install-verified-release.sh <tag>` downloads exactly those two
assets, runs `sha256sum --check` and `groundtruth release verify-bundle`
(checksum, public-only paths, publishable manifest for that release id), then
installs them. `groundtruth release verify-artifacts` re-checks manifest
structure, per-file hashes, lookup schema, and the absence of listing-level
fields before any image is built.

## Weekly release deploy sequence

1. Validate the exact tag; check out the release tag and, separately, current
   deploy tooling from the workflow commit.
2. Download, verify, and install the release; run `release verify-artifacts`.
3. Build `metrik-api:<release_id>-<sha>` from `Dockerfile` (web extras only) and
   assert Scrapy and Playwright are absent from the image.
4. Trivy scan; any fixable HIGH or CRITICAL finding fails the deploy.
5. Push to ACR and record the digest.
6. Capture the currently running image and revision.
7. `az containerapp update` with a unique revision suffix, then
   `scripts/azure/wait-for-revision.sh` waits for that revision to be ready and
   to report the expected release.
8. `scripts/azure/smoke.ps1 -ExpectedReleaseId <id>` checks health, readiness,
   meta, markets, lookup, compare, rent yield, reports, and write-endpoint
   guards against the live URL.
9. On any failure after the revision switch, the previous image is redeployed
   and smoke-tested. Deployment evidence is uploaded as a workflow artifact.

Telegram receives start, success, and failure (with rollback status)
notifications when the bot secrets are configured; notification failures never
block a deploy.

## Manual operations

```powershell
# Redeploy one exact verified release (also the manual rollback for data)
gh workflow run weekly-release-deploy.yml --ref master -f release_tag=groundtruth-release-<release_id>

# Redeploy current code with a specific data release
gh workflow run azure-beta-deploy.yml --ref master -f data_release_tag=groundtruth-release-<release_id>
```

To roll back code without a workflow, point the app at a previous immutable
image:

```bash
az containerapp update -g <resource-group> -n ca-metrik-api --container-name metrik-api \
  --image <acr>.azurecr.io/metrik-api:<previous-tag> --revision-suffix manual-<n>
```

Release artifacts are baked into the image, so they roll back with it. Treat
schema changes as forward-fix only.

## Runtime configuration

Production refuses to start when the settings are unsafe
(`groundtruth.startup.validate_production_settings`). Required values:

- `APP_ENV=production`, `API_REQUIRE_LOOKUP_CACHE=true`, `API_RATE_LIMIT_ENABLED=true`, `API_DOCS_ENABLED=false`
- `PRODUCT_WRITE_BACKEND=database`
- `HEALTH_CHECK_TOKEN`, at least 24 characters (protects `/api/health/perf`, `/api/metrics`, and readiness detail)
- `FORWARDED_ALLOW_IPS` other than `*`
- `DATABASE_URL` without development placeholder passwords, held as a Container App secret
- `SENTRY_DSN` when `REQUIRE_SENTRY_DSN=true`

Probes: liveness `/api/health` (always 200 while the process serves), readiness
`/api/ready` (503 until lookup and comparables caches are loaded and release
hashes verify).

## Public database

The public database holds only application schema and product writes
(`product_submissions`: contact, feedback, events). It is currently a Postgres
sidecar on `EmptyDir` storage, which is **not durable**. The durable target and
migration plan are in
[PUBLIC_DATABASE_DURABILITY_PLAN.md](PUBLIC_DATABASE_DURABILITY_PLAN.md).

## Self-hosted alternative (not production)

`docker-compose.prod.yml` and `deploy/nginx/metrik.conf` run the same image behind
nginx on a single host. They remain for local production-like QA and as a
fallback, not as the production path.

```bash
docker compose -f docker-compose.prod.yml --env-file .env.production --profile migrate run --rm migrate
docker compose -f docker-compose.prod.yml --env-file .env.production up -d --build
```

`scripts/backup_postgres.sh`, `scripts/restore_postgres.sh`, and
`scripts/backup_restore_drill.{sh,ps1}` back up and restore that stack's
database plus release artifacts. Research database backups are separate and
described in [LOCAL_RESEARCH_RUNNER.md](LOCAL_RESEARCH_RUNNER.md).
