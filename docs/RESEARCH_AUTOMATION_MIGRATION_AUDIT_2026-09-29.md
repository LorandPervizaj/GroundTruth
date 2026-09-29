# Research automation migration audit — 2026-09-29

Read-only forensic audit of the GroundTruth/Metrik autonomous research plane.
No files other than this report were edited. No GitHub, Azure, database, crawler,
or Git state was changed.

Audit time: 2026-09-29. Repository `C:\Projects\FartEstate`, GitHub
`LorandPervizaj/GroundTruth`. Working branch at audit time: `master`.

## Verdict

The public Azure Metrik site is deployed and is independent of the research
plane. The autonomous Azure research plane was designed and committed. It was
not provisioned. The weekly deploy workflow is enabled, has run once, and
failed before it could change production. A local Windows research host is
described by `docker-compose.yml`, but Docker is stopped, so the local
database could not be inspected. No GitHub self-hosted runner is registered.

Safe migration boundary: keep the public serving plane, and replace only the
unimplemented research job, research database, and research file shares with
a local Docker Postgres plus a self-hosted runner. Do that in a later change.
This audit does not implement it.

## 1. Exact Git history timeline

Baseline and recovery anchors:

| Anchor | Object | Meaning |
| --- | --- | --- |
| Pre-automation baseline | `4aa9cbf1c14bb492d6940adcf78875e7c61d057d` | Parent of the first automation commit. Public Metrik before this work. |
| Recovery tag | `pre-autonomous-weekly-release-20260923` | Annotated tag object `69df9a2317af06ec7ce05f87729ad870e5a89687`. It peels to commit `f7e913095f4130006a4cfc9e5980fdc8109ac217`. |
| Tagged commit parent | `4aa9cbf` | `4aa9cbf` is an ancestor of the tag. The tag is the checkpoint commit, one commit after the baseline. |
| PR #1 head | `fff4d28e095796c539de2bee397e5fff9ebb6d39` | Branch `feat/autonomous-weekly-release`. |
| PR #1 merge | `49051ec1ed848365409788ffc912a0d2b768a1b1` | Merge into `master` on 2026-09-24. |
| PR #2 head | `8c66a87eff1c51342cb352e32db8df7046447b94` | Trivy pin only. |
| PR #2 merge | `98734a7c06dd810cdbe565735abc525d3b9f427f` | Merge into `master` on 2026-09-24. |
| Current `master` | `4ee092482cf40bf1b4f91f9bf9e6ecbbfc3ec5bb` | Matches `origin/master`. Docs-only commit after the deployed source. |
| Deployed source | `08d393cc57713de8250936a8751ec09a85485d73` | Live image `metrik-api:08d393c`. Diff to `master` is only this audit's predecessor doc. |

`master` compared with the recovery tag is 68 files, +8865 / −4525. That
range includes release-safety code, Telegram, public-image scan repairs, and
the Azure research design. It is not an Azure-only delta.

### Range `4aa9cbf..fff4d28` — PR #1

All times are +0200.

| Commit | Date | Subject | Class |
| --- | --- | --- | --- |
| `f7e9130` | 2026-09-23 13:09 | chore: checkpoint before autonomous weekly pipeline | Neutral checkpoint. Tagged recovery point. |
| `8252a7e` | 2026-09-23 13:11 | docs: audit autonomous pipeline current state | Docs. |
| `8eb058c` | 2026-09-23 13:14 | docs: complete forensic pipeline audit | Docs. |
| `5ef7dc9` | 2026-09-23 13:17 | feat: add canonical weekly release command | Provider-neutral orchestration. |
| `628d6c5` | 2026-09-23 13:19 | feat: persist verified release watermarks | Provider-neutral state. |
| `7c4bf8a` | 2026-09-23 13:22 | feat: gate releases on source health | Provider-neutral gate. |
| `697545e` | 2026-09-23 13:24 | feat: gate releases on ETL data quality | Provider-neutral gate. |
| `678470f` | 2026-09-23 13:28 | feat: add shadow statistical sanity gate | Provider-neutral gate. |
| `eeabe86` | 2026-09-23 13:29 | fix: avoid secrets context in workflow condition | Public Azure deploy workflow. |
| `3e010bd` | 2026-09-23 13:31 | feat: version and package verified releases | Provider-neutral release bundle. |
| `0031b6f` | 2026-09-23 13:34 | feat: define private Azure research environment | Azure research design. |
| `d3136f2` | 2026-09-23 13:36 | feat: schedule and control weekly research job | Azure research control workflow. |
| `5fce7b0` | 2026-09-23 13:39 | feat: deploy verified releases with rollback | Azure public deploy of a verified bundle. |
| `cac47b5` | 2026-09-23 13:41 | feat: add Telegram operations notifications | Provider-neutral notifications. |
| `3e0b8c7` | 2026-09-23 13:42 | feat: add optional email operations report | Provider-neutral notifications. |
| `bce6855` | 2026-09-23 13:44 | docs: plan durable public database migration | Public-database docs. |
| `9aca444` | 2026-09-23 13:46 | test: cover automation workflows and rollback | Tests for Azure workflows and Bicep. |
| `5b77404` | 2026-09-23 13:47 | feat: persist statistical shadow calibration | Provider-neutral calibration record. |
| `e78036b` | 2026-09-23 13:48 | security: exclude private data from worker images | Research image hardening. |
| `ff3ca96` | 2026-09-23 13:56 | docs: complete autonomous pipeline rollout | Docs plus small release/workflow edits. |
| `b0d6950` | 2026-09-23 14:48 | feat: route product submissions to Telegram owner | Public site Telegram. |
| `041f3a3` | 2026-09-23 15:00 | feat: add owner-only Telegram bot commands | Public site Telegram. |
| `04e47e4` | 2026-09-24 13:27 | chore: refresh secure dependencies and formatting | Neutral dependency refresh. |
| `61d8b98` | 2026-09-24 13:29 | ci: preserve release bytes and fetch audit history | Release-byte safety. |
| `fff4d28` | 2026-09-24 13:31 | test: track deterministic dedup benchmark fixture | Neutral test fixture. |

### PR #2, separate from the ranges above

PR #2, “ci: repair Trivy action pin”, is merge `98734a7` with parent
`49051ec` and head `8c66a87` (2026-09-24 13:35).

Changed files only:

- `.github/workflows/azure-beta-deploy.yml`
- `.github/workflows/prod-image.yml`

Both change `aquasecurity/trivy-action@0.28.0` to `aquasecurity/trivy-action@v0.36.0`.
`master` still pins `v0.36.0` in both files. PR #2 does not add research
resources, jobs, or Telegram behavior.

### Range `98734a7..4ee0924` — post-PR fixes

| Commit | Date | Subject | Class |
| --- | --- | --- | --- |
| `0578ba4` | 2026-09-28 14:13 | ci: sign Azure deploys in with OIDC and name the api container | Public Azure deploy. Also adds `--container-name metrik-api` to the weekly deploy workflow. |
| `f5d3224` | 2026-09-28 14:19 | ci: drop flagged build packages from the production image | Public image scan. |
| `297bb41` | 2026-09-28 14:23 | ci: remove setuptools and msgpack leftovers from the image | Public image scan. |
| `14a94ef` | 2026-09-28 14:26 | ci: strip bundled setuptools and msgpack wheels from the image | Public image scan. |
| `5b8ef7f` | 2026-09-28 14:28 | ci: print where setuptools and msgpack remain in the image | Temporary public-image debug step. |
| `78c4d19` | 2026-09-28 14:31 | ci: remove system pip so image scans ignore its vendored packages | Public image scan. Removes the debug step. |
| `2f3c30b` | 2026-09-28 14:50 | Let the owner bot start, stop, and watch the weekly scrape | Azure job control from the public app. |
| `6815a99` | 2026-09-28 15:02 | Stop request logs from recording the Telegram bot token | Public app logging. |
| `50b0f7d` | 2026-09-28 17:42 | Merge production Azure and scraper control fixes | Merge of `98734a7` and `6815a99`. |
| `08d393c` | 2026-09-28 17:47 | ci: satisfy repository-wide verification after reconciliation | Formatting only. This is the deployed source. |
| `4ee0924` | 2026-09-28 17:53 | docs: record research infrastructure reconciliation | Docs only. Current `master`. Not in the live image. |

## 2. Exact rollback and recovery anchors

Use these, and do not invent a new reset:

| Purpose | Anchor | What it restores |
| --- | --- | --- |
| Code before any autonomous-pipeline commit | `4aa9cbf` | Public Metrik without release orchestration, research Bicep, or owner Telegram. |
| Named recovery tag | `pre-autonomous-weekly-release-20260923` → `f7e9130` | Same tree as the checkpoint commit. Its parent is `4aa9cbf`. |
| Last pre-repair public automation merge | `49051ec` | PR #1 as merged, before the Trivy pin and the September 28 deploy repairs. |
| Last Trivy-pin-only master | `98734a7` | PR #2 merged. Public deploy still lacked OIDC and `--container-name`. |
| Last scraper-control commit before master merge | `6815a99` | Branch tip that was merged by `50b0f7d`. |
| Source inside the live image | `08d393c` | Behavior of production. `4ee0924` adds documentation only. |
| Live revision | `ca-metrik-api--0000026` | Image `acrmetrikbetalgy2mu.azurecr.io/metrik-api:08d393c`. |

`50b0f7d` parents are `98734a7` (first) and `6815a99` (second).

Rolling `master` back to `4aa9cbf` or the recovery tag would also remove
valid work: release gates, Telegram owner notifications, OIDC public deploy,
the container-name fix, and the production image scan repair. That is the
wrong rollback for a research-host migration.

## 3. Azure resources designed versus actually deployed

Subscription inspected: `Azure for Students`, id
`c73c2fd1-9b7f-4221-a868-757128f2e416`, state Enabled, default account.
The subscription resource list contains six resources, all in
`rg-metrik-beta-eus2` (`eastus2`).

Other resource groups exist and contained no resources in that list:
`vulcan-forge-rg`, `vulcan-forge-rg-uks`, `vulcan-forge-rg-eastus2`,
`probe-rg-eastus2`, `vulcan-forge-rg-westus2`, `vulcan-forge-rg-ncus`,
`probe-rg-northcentralus`, `NetworkWatcherRG`, `vulcan-forge-rg-canada`.

### Designed by `infra/azure/research.bicep` and not deployed

| Designed name | Exists |
| --- | --- |
| `job-groundtruth-weekly` | No. `az containerapp job list` on `rg-metrik-beta-eus2` is `[]`. No `Microsoft.App/jobs` resource in the subscription. |
| Dedicated research PostgreSQL Flexible Server (`psql-groundtruth-research-<suffix>`) | No. `az postgres flexible-server list` is `[]`. |
| Research database `groundtruth` on that server | No server, so no database. |
| Research storage account (`stgtresearch<suffix>`) | No. The only storage account is the public one below. |
| Azure Files share `pipeline-state` | No. |
| Azure Files share `verified-releases` | No. |
| Research Container Apps environment `cae-groundtruth-research` | No. |
| Research managed identity `id-groundtruth-research-job` | No. |
| Research Log Analytics workspace `log-groundtruth-research` | No. |
| ACR repository `groundtruth-research` | No. ACR repository list is only `metrik-api`. |

This audit did not re-query Flexible Server SKU catalogs. Zero servers exist.
The 2026-09-28 reconciliation doc records that Burstable SKUs were not offered.
Treat current SKU availability as still requiring operator confirmation.

### Public resources that do exist

| Resource | Type | Role |
| --- | --- | --- |
| `rg-metrik-beta-eus2` | Resource group | Only group with Metrik resources. |
| `cae-metrik-beta` | Container Apps environment | Public environment. |
| `ca-metrik-api` | Container App | Public API plus Postgres sidecar. |
| `acrmetrikbetalgy2mu` | Container Registry | Public images only (`metrik-api`). |
| `id-metrik-beta-app` | User-assigned identity | Public app and GitHub OIDC deploy identity. |
| `log-metrik-beta` | Log Analytics | Public environment logs. |
| `stmetrikbetalgy2mu` | Storage account | Public template account. |

Live public app, verified this audit:

- Latest ready revision: `ca-metrik-api--0000026`
- Image: `acrmetrikbetalgy2mu.azurecr.io/metrik-api:08d393c`
- Identity: user-assigned `id-metrik-beta-app`
- Containers: `metrik-api`, `postgres`
- Volume `pgdata`: `EmptyDir`
- Scale: min 1, max 1

The storage account has one file share, named `pgdata`. The running app does
not mount it. The sidecar volume of the same name is `EmptyDir`. There is no
`pipeline-state` or `verified-releases` share.

Federated credential names on `id-metrik-beta-app`: `github-azure-beta`,
`github-azure-beta-ids`. Subjects were not recorded.

### Role assignments related to research or job control

On `rg-metrik-beta-eus2`, principal `89d6c8e2-3de1-46b5-8ce3-df6212487ed6`
(`id-metrik-beta-app`):

| Role | Scope | Needed by |
| --- | --- | --- |
| Container Apps Contributor | Resource group | Public image updates through GitHub OIDC. |
| Metrik scrape job operator | Resource group | Bot commands that call Container Apps Jobs. Custom role. |

Custom role `Metrik scrape job operator` is assignable only on
`rg-metrik-beta-eus2`. Actions:

- `Microsoft.App/jobs/read`
- `Microsoft.App/jobs/start/action`
- `Microsoft.App/jobs/stop/action`
- `Microsoft.App/jobs/executions/read`
- `Microsoft.App/jobs/stop/execution/action`

On the ACR:

| Role | Principal | Needed by |
| --- | --- | --- |
| AcrPull | `id-metrik-beta-app` | Public app image pull. |
| AcrPush | `id-metrik-beta-app` | GitHub OIDC image push. |
| Reader | `id-metrik-beta-app` | `az acr show` during public deploy. |
| AcrPush | `lp3911@rit.edu` | Operator push. |

No role assignment exists for `id-groundtruth-research-job` because that
identity was never created.

### Public Container App environment variable names

Values were not read. Names on container `metrik-api`:

`APP_ENV`, `LOG_FORMAT`, `LOG_LEVEL`, `API_DOCS_ENABLED`,
`API_REQUIRE_LOOKUP_CACHE`, `PRODUCT_WRITE_BACKEND`, `API_RATE_LIMIT_ENABLED`,
`ALERTS_SIGNUP_ENABLED`, `VALUATION_PUBLIC_ENABLED`, `RUN_MIGRATIONS_ON_START`,
`REQUIRE_SENTRY_DSN`, `REPORTS_GENERATED_DIR`, `PUBLIC_BASE_URL`,
`FORWARDED_ALLOW_IPS`, `DATABASE_URL`, `HEALTH_CHECK_TOKEN`, `TRUSTED_HOSTS`,
`TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`, `TELEGRAM_WEBHOOK_SECRET`,
`AZURE_SUBSCRIPTION_ID`, `AZURE_CLIENT_ID`, `GROUNDTRUTH_AZURE_RESOURCE_GROUP`,
`GROUNDTRUTH_AZURE_JOB_NAME`.

The last four exist only so the public process can call the Azure job API.
The job they name is not deployed.

## 4. GitHub automation designed versus actually configured

Workflows, all `active`:

| Workflow | Id | State |
| --- | --- | --- |
| Azure beta deploy | 358605699 | active |
| CI | 291916283 | active |
| GroundTruth weekly control | 366000608 | active |
| Production image | 358605700 | active |
| Deploy verified weekly release | 366000610 | active |
| Dependency Graph | 291279224 | active |

Environments: only `azure-beta`. `groundtruth-research` does not exist.

Repository-level variables: none. Repository-level secrets: none.

Environment `azure-beta` variable names:

- `METRIK_AZURE_ACR_NAME`
- `METRIK_AZURE_CONTAINER_APP`
- `METRIK_AZURE_RESOURCE_GROUP`

Environment `azure-beta` secret names:

- `AZURE_CLIENT_ID`
- `AZURE_SUBSCRIPTION_ID`
- `AZURE_TENANT_ID`
- `METRIK_AZURE_ACR_NAME`
- `METRIK_AZURE_RESOURCE_GROUP`
- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_ID`

Explicit absences:

| Name | Exists |
| --- | --- |
| Environment `groundtruth-research` | No |
| Variable `GROUNDTRUTH_STORAGE_ACCOUNT` | No |
| Variable `GROUNDTRUTH_RELEASE_SHARE` | No |
| Variable `GROUNDTRUTH_AZURE_RESOURCE_GROUP` | No |
| Variable `GROUNDTRUTH_AZURE_JOB_NAME` | No |
| Any research resource or job variable | No |

`weekly-release-deploy.yml` reads `GROUNDTRUTH_STORAGE_ACCOUNT` and
`GROUNDTRUTH_RELEASE_SHARE` from `vars`, and the public target from
`METRIK_AZURE_*` vars, using environment `azure-beta`.

`groundtruth-weekly-control.yml` requires environment `groundtruth-research`
and vars `GROUNDTRUTH_AZURE_RESOURCE_GROUP` and `GROUNDTRUTH_AZURE_JOB_NAME`.

### Recent executions

Deploy verified weekly release:

| Run | When | Event | SHA | Result |
| --- | --- | --- | --- | --- |
| [36482216010](https://github.com/LorandPervizaj/GroundTruth/actions/runs/36482216010) | 2026-09-28 20:52 UTC | schedule | `4ee0924` | failure |

Failed step: `Resolve and download verified bundle`. Azure login had already
succeeded. The log shows empty `RESEARCH_STORAGE_ACCOUNT` and
`test -n "$RESEARCH_STORAGE_ACCOUNT"` exiting 1. Later steps, including
`Deploy candidate revision` and `Restore previous production image after failure`,
were skipped. `Telegram failure notification` succeeded. This run did not
replace the public image.

GroundTruth weekly control: no runs.

Azure beta deploy, latest relevant runs:

| Run | Event | SHA | Result |
| --- | --- | --- | --- |
| [36446296042](https://github.com/LorandPervizaj/GroundTruth/actions/runs/36446296042) | push | `08d393c` | success |
| [36425824213](https://github.com/LorandPervizaj/GroundTruth/actions/runs/36425824213) | workflow_dispatch | `6815a99` | success |
| [36424528921](https://github.com/LorandPervizaj/GroundTruth/actions/runs/36424528921) | workflow_dispatch | `2f3c30b` | success |
| [36422429559](https://github.com/LorandPervizaj/GroundTruth/actions/runs/36422429559) | workflow_dispatch | `78c4d19` | success |

Earlier `workflow_dispatch` runs on `0578ba4`, `f5d3224`, `297bb41`, and
`14a94ef` failed. Production image workflow
[36446296116](https://github.com/LorandPervizaj/GroundTruth/actions/runs/36446296116)
succeeded for `08d393c`.

The Monday cron remains active. The next Monday will fail the same way and
send another Telegram failure until the workflow is changed. This audit left
it enabled.

## 5. Local research infrastructure actually available

Inspected without starting Docker, Postgres, or a crawler.

| Item | Observed |
| --- | --- |
| Docker CLI | `Docker version 29.8.0, build 88096ef` |
| Docker engine | Not running. Pipe `dockerDesktopLinuxEngine` is absent. |
| Windows service `com.docker.service` | Stopped, start type Manual. |
| WSL | Distro `docker-desktop` is Stopped, version 2. |
| `docker ps` / volumes | Not available while the engine is stopped. Not started. |
| Compose definition | `docker-compose.yml` defines `postgis/postgis:16-3.4` as `groundtruth-postgres`, bind `127.0.0.1:5432`, volume `postgres_data`, plus pgAdmin. |
| Port 5432 | Nothing listening. |
| PostgreSQL Windows service | None found. |
| Database existence, size, Alembic revision, table sizes, row counts | UNKNOWN. No server was running, and none was started. |
| Repository Alembic head (code, not a database) | `h2i3j4k5l6m7` (`listing_lifecycle_states`), parent `g1h2i3j4k5l6`. |
| Pipeline-state directory | `reports/generated/pipeline_state` does not exist. Code default is that path unless `GROUNDTRUTH_PIPELINE_STATE_DIR` is set. |
| Release-output directory | `reports/generated/releases` does not exist. Code default is `reports/generated/releases` unless `GROUNDTRUTH_RELEASE_OUTPUT_DIR` is set. |
| Disk | Drive C: about 353.9 GB used, 121.6 GB free. |
| Backup files found at depth 3 | `.tmp/drills/metrikqa_public_20260915.dump` (103,358 bytes), `.tmp/drills/metrikqa_public_freeze.dump` (103,358), `.tmp/drills/metrikqa_schema_20260915_104013.dump` (107,069), plus two large Merrjep crawl logs (`.bak`, 238 MB and 1.44 GB). `scripts/sql/create_runtime_role.sql` is a script, not a backup. |
| GitHub self-hosted runners on this repository | `total_count` 0. |
| Local runner marker | No `.runner` file under `C:\Projects`, `C:\actions-runner`, or the user profile at depth 3. `C:\actions-runner` does not exist. |

The small dumps are drill artifacts from 2026-09-15. They are not evidence of
a current research corpus. Whether `postgres_data` inside the stopped Docker
Desktop disk still holds an older database is UNKNOWN.

## 6. File-by-file KEEP / ADAPT / RETIRE / REMOVE

Public Metrik “depends” means the live API process imports it or the public
deploy workflow ships it. Telegram “depends” means owner messages or the
webhook stop working if the file is removed without a replacement.

| File | Introduced | Later modifications | Purpose | Azure-specific? | Public Metrik depends? | Telegram depends? | Tests depend? | Recommendation |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `.github/workflows/groundtruth-weekly-control.yml` | `d3136f2` | none | Dispatch start/status for the Azure job. | Yes | No | No | `test_automation_workflows.py` | RETIRE, then REMOVE after a runner workflow exists. It has never run. |
| `.github/workflows/weekly-release-deploy.yml` | `5fce7b0` | `cac47b5`, `ff3ca96`, `0578ba4` | Download a verified bundle from Azure Files, rebuild `metrik-api`, deploy, roll back, notify Telegram. | Mixed. Deploy target is the public app. Source of bytes is the missing research share. | The workflow can change production if it gets past the download. The only run failed before deploy. | Failure/success steps use Telegram secrets. | `test_automation_workflows.py` | ADAPT. Keep verify, immutable tag, smoke, and rollback. Replace the Azure Files download. |
| `.github/workflows/azure-beta-deploy.yml` | `207422e` (pre-automation) | `eeabe86`, `8c66a87`, `0578ba4` | Build, scan, and deploy the public image with OIDC. | Public Azure | Yes | No | Indirectly, via production | KEEP |
| `.github/workflows/prod-image.yml` | `207422e` | `8c66a87`, `5b8ef7f`, `78c4d19` | Production image scan. | Public image | Yes, as a gate | No | No direct automation test | KEEP |
| `infra/azure/research.bicep` | `0031b6f` | none | Full private research stack. | Yes | No runtime dependency. Path filter `infra/azure/**` on the public deploy workflow means deleting it on `master` triggers a public redeploy. | No | `test_research_schedule_is_monday_and_single_replica` | RETIRE. Do not deploy it. REMOVE only together with that test and with awareness of the path filter. |
| `Dockerfile.research` | `0031b6f` | `e78036b` | Private worker image. Entrypoint is `groundtruth pipeline weekly-release`. Mounts `/mnt/state` and `/mnt/releases`. | Written for the Azure job. The command itself is portable. | No. Public `Dockerfile` is separate. Never pushed (no ACR repo). | No | No direct image test found | ADAPT as the local worker image, or RETIRE if the host runs `uv` without this image. |
| `Dockerfile` | pre-automation | `0578ba4`, `f5d3224`, `297bb41`, `14a94ef`, `78c4d19` | Public image. System pip removed so Trivy ignores vendored packages. | Public image | Yes | No | Image scans in CI | KEEP |
| `src/groundtruth/automation/__init__.py` | `5ef7dc9` | `628d6c5` | Package marker. | No | Shipped in the image. Not imported by the API lifespan. | No | Automation tests | KEEP |
| `src/groundtruth/automation/models.py` | `5ef7dc9` | `628d6c5`, `3e010bd` | Run-result model. | No | No | Notifications consume it | Yes | KEEP |
| `src/groundtruth/automation/state.py` | `628d6c5` | none | Watermarks and lock under a local directory. | No. Azure only supplies the directory via env. | No | No | Weekly-release tests | KEEP |
| `src/groundtruth/automation/source_health.py` | `7c4bf8a` | none | Source gate. | No | No | Result text can be notified | Yes | KEEP |
| `src/groundtruth/automation/data_quality.py` | `697545e` | none | ETL gate. | No | No | Result text can be notified | Yes | KEEP |
| `src/groundtruth/automation/statistical_sanity.py` | `678470f` | none | Shadow statistical gate. | No | No | Result text can be notified | Yes | KEEP |
| `src/groundtruth/automation/weekly_release.py` | `5ef7dc9` | many through `e78036b`; also `5fce7b0`, `cac47b5`, `3e0b8c7`, `3e010bd`, `5b77404` | Crawl, gates, package, notify. | No | No | Calls `safe_notify_pipeline_result` | `test_automation_weekly_release.py` | KEEP |
| `src/groundtruth/automation/notifications.py` | `cac47b5` | `3e0b8c7` | Telegram and optional SMTP for pipeline results. | No | No | Yes, for pipeline results. Separate from website contact. | `test_automation_notifications.py` | KEEP |
| `src/groundtruth/commands/pipeline_commands.py` | `5ef7dc9` | `628d6c5` | CLI `groundtruth pipeline weekly-release`. | No | CLI import only. API does not call it. | Indirect | Weekly-release tests | KEEP |
| `src/groundtruth/release.py` | pre-automation | `3e010bd`, `0031b6f`, `5fce7b0`, `ff3ca96` | Version and bundle verified public artifacts. | Output directory is env-driven, not Azure-specific. | Public verify path uses release metadata. | No | `test_release_metadata.py`, `test_release_verify.py` | KEEP |
| `src/groundtruth/services/product_notifications.py` | `b0d6950` | `041f3a3`, `2f3c30b` | Website contact/feedback/report/listing Telegram, plus owner commands. | Command dispatch calls scrape control. Delivery is Telegram. | Yes. Routes import it. | Yes | `test_product_notifications.py`, webhook tests | KEEP. ADAPT only the scrape-command dispatch if Azure job control is removed. |
| `src/groundtruth/services/scrape_control.py` | `2f3c30b` | `6815a99` | ARM start/stop/status and 30-minute watch using the app identity. | Yes | Yes. `app.py` lifespan starts the watch thread. Website pages do not need Azure to answer. | Progress messages use `notify_product_submission`. | `test_scrape_control.py` | ADAPT or REMOVE only in the same change as `app.py`. |
| `src/groundtruth/api/routes_product_writes.py` | pre-automation | `b0d6950`, `041f3a3` | Contact, feedback, reports, listings, Telegram webhook. | No | Yes | Yes | `test_telegram_webhook.py` | KEEP |
| `src/groundtruth/api/app.py` | pre-automation | `2f3c30b`, `6815a99`, `08d393c` | API app. Starts scrape watch. Suppresses httpx URL logs. | The watch is Azure-specific. The rest is public serving. | Yes | Indirect | Webhook tests construct the app | KEEP. Remove the watch import only when scrape control is removed. |
| `.env.example` | pre-automation | `cac47b5`, `3e0b8c7`, `0578ba4`, `2f3c30b` | Documents Telegram, SMTP, and Azure job env names. | Job names are Azure-specific. | Docs only | Docs only | No | ADAPT. Keep Telegram names. Mark job names obsolete after migration. |
| `tests/test_automation_workflows.py` | `9aca444` | none | Asserts Bicep schedule and OIDC workflows. | Yes | No | Asserts secrets are not echoed | This is the test | ADAPT when workflows change. |
| `tests/test_automation_weekly_release.py` | `5ef7dc9` | through `e78036b` | Orchestration gates. | No | No | No | This is the test | KEEP |
| `tests/test_automation_notifications.py` | `cac47b5` | `3e0b8c7` | Pipeline Telegram/email. | No | No | Yes | This is the test | KEEP |
| `tests/test_scrape_control.py` | `2f3c30b` | `08d393c` formatting | Azure job client behavior. | Yes | No | Command text | This is the test | ADAPT or REMOVE with `scrape_control.py`. |
| `tests/test_product_notifications.py` | `b0d6950` | `041f3a3` | Owner notification format and commands. | Help text mentions scrape commands | No | Yes | This is the test | KEEP. Update help assertions if commands change. |
| `tests/test_telegram_webhook.py` | `041f3a3` | none | Webhook secret header. | No | Yes | Yes | This is the test | KEEP |
| `docs/GROUNDTRUTH_CLOUD_RESEARCH.md` | `0031b6f` | `d3136f2`, `e78036b` | How to deploy the Azure research stack. | Yes | No | No | No | RETIRE / REPLACE |
| `docs/AUTONOMOUS_WEEKLY_PIPELINE_RUNBOOK.md` | `ff3ca96` | none | Operator runbook for the Azure weekly path. | Mixed | No | Describes Telegram | No | REPLACE |
| `docs/AUTONOMOUS_WEEKLY_PIPELINE_FINAL_REPORT.md` | `ff3ca96` | none | Completion claim for the Azure design. | Mixed | No | No | No | RETIRE as historical. It describes a design, not a deployed system. |
| `docs/AUTONOMOUS_PIPELINE_CURRENT_STATE.md` | `8252a7e` | `8eb058c` | Early forensic notes. | Mixed | No | No | No | RETIRE as historical. |
| `docs/RESEARCH_INFRASTRUCTURE_RECONCILIATION_2026-09-28.md` | `4ee0924` | none | 2026-09-28 designed-versus-live matrix. | Yes | No | No | No | KEEP as a point-in-time record. This audit supersedes it for migration. |
| `docs/PUBLIC_DATABASE_DURABILITY_PLAN.md` | `bce6855` | none | Public sidecar durability. | Public Azure | Describes production data risk | No | No | KEEP. It is about the public sidecar, not the research job. |
| `docs/STATISTICAL_QA_CALIBRATION.md` | `5b77404` | none | Shadow-mode calibration. | No | No | No | Related tests | KEEP |

## 7. Commit-by-commit Azure-specific versus provider-neutral matrix

| Commit | Azure-specific | Provider-neutral | Notes |
| --- | --- | --- | --- |
| `f7e9130` |  | yes | Checkpoint. Recovery tag target. |
| `8252a7e`, `8eb058c` | docs about both | docs | Historical audits. |
| `5ef7dc9` |  | yes | Weekly command. |
| `628d6c5` |  | yes | Watermarks. |
| `7c4bf8a` |  | yes | Source health. |
| `697545e` |  | yes | Data quality. |
| `678470f` |  | yes | Statistical shadow gate. |
| `eeabe86` | public workflow |  | Secrets-in-`if` fix. Keep. |
| `3e010bd` |  | yes | Release bundle format. |
| `0031b6f` | yes | release.py touch is neutral | Research Bicep and worker image. |
| `d3136f2` | yes |  | Weekly control workflow. |
| `5fce7b0` | yes, public deploy plus research share | release metadata fields | Rollback design is worth keeping. |
| `cac47b5` | wires Telegram into the Azure deploy workflow | notification module | Keep the module. |
| `3e0b8c7` |  | yes | Optional email. |
| `bce6855` | public database docs |  | Keep. |
| `9aca444` | tests lock Azure workflow shape |  | Must change with the workflows. |
| `5b77404` |  | yes | Calibration persistence. |
| `e78036b` | worker image | release content filter | Image was never deployed. |
| `ff3ca96` | runbook |  | Replace the runbook. |
| `b0d6950`, `041f3a3` |  | yes | Public Telegram. Keep. |
| `04e47e4`, `61d8b98`, `fff4d28` |  | yes | Dependencies, release bytes, fixture. |
| `49051ec` | merge | merge | PR #1. |
| `8c66a87`, `98734a7` | public scan pin |  | PR #2. Keep the pin. |
| `0578ba4` | public OIDC and container name |  | Required for current deploys. Also edits weekly deploy. |
| `f5d3224`, `297bb41`, `14a94ef`, `5b8ef7f`, `78c4d19` | public image |  | Scan repair. Keep `78c4d19` outcome. |
| `2f3c30b` | yes | Telegram command routing | Azure job client inside the public app. |
| `6815a99` |  | yes | Stops token URLs in logs. Keep. |
| `50b0f7d` | merge | merge | Brings scraper control onto `master`. |
| `08d393c` |  | yes | Formatting. Live source. |
| `4ee0924` | docs |  | Reconciliation note. |

## 8. Names that become obsolete

These names belong to the research plane. GitHub variables in the first
group were never created, so there is nothing to delete there. Container App
names and the custom role do exist.

GitHub, designed and absent:

- Environment `groundtruth-research`
- `GROUNDTRUTH_STORAGE_ACCOUNT`
- `GROUNDTRUTH_RELEASE_SHARE`
- `GROUNDTRUTH_AZURE_RESOURCE_GROUP` as a GitHub variable
- `GROUNDTRUTH_AZURE_JOB_NAME` as a GitHub variable

Live public Container App env names that exist only for Azure job control:

- `AZURE_SUBSCRIPTION_ID` on the app (this is not the GitHub secret of the same name)
- `AZURE_CLIENT_ID` on the app (managed-identity client id for IMDS, not the GitHub secret)
- `GROUNDTRUTH_AZURE_RESOURCE_GROUP`
- `GROUNDTRUTH_AZURE_JOB_NAME`

Azure RBAC that exists only for that job client:

- Custom role `Metrik scrape job operator`
- Its assignment on `id-metrik-beta-app` at `rg-metrik-beta-eus2`

Code and workflow names that become unused after the replacement exists:

- `infra/azure/research.bicep` resource names `job-groundtruth-weekly`, `cae-groundtruth-research`, `id-groundtruth-research-job`, `pipeline-state`, `verified-releases`
- `.github/workflows/groundtruth-weekly-control.yml`

Do not delete the GitHub secrets `AZURE_CLIENT_ID`, `AZURE_TENANT_ID`, or
`AZURE_SUBSCRIPTION_ID`. The public deploy uses those same names.

## 9. Names public Azure Metrik still uses

GitHub environment `azure-beta` secrets:

- `AZURE_CLIENT_ID`
- `AZURE_TENANT_ID`
- `AZURE_SUBSCRIPTION_ID`
- `METRIK_AZURE_ACR_NAME`
- `METRIK_AZURE_RESOURCE_GROUP`
- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_ID`

GitHub environment `azure-beta` variables:

- `METRIK_AZURE_ACR_NAME`
- `METRIK_AZURE_CONTAINER_APP`
- `METRIK_AZURE_RESOURCE_GROUP`

Container App env names the public site and bot still need:

- Serving and security: `APP_ENV`, `LOG_FORMAT`, `LOG_LEVEL`, `API_DOCS_ENABLED`, `API_REQUIRE_LOOKUP_CACHE`, `PRODUCT_WRITE_BACKEND`, `API_RATE_LIMIT_ENABLED`, `ALERTS_SIGNUP_ENABLED`, `VALUATION_PUBLIC_ENABLED`, `RUN_MIGRATIONS_ON_START`, `REQUIRE_SENTRY_DSN`, `REPORTS_GENERATED_DIR`, `PUBLIC_BASE_URL`, `FORWARDED_ALLOW_IPS`, `DATABASE_URL`, `HEALTH_CHECK_TOKEN`, `TRUSTED_HOSTS`
- Telegram: `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`, `TELEGRAM_WEBHOOK_SECRET`

Identity and roles the public deploy still needs on `id-metrik-beta-app`:

- `AcrPull`, `AcrPush`, `Reader` on `acrmetrikbetalgy2mu`
- `Container Apps Contributor` on `rg-metrik-beta-eus2`
- Federated credentials `github-azure-beta` and `github-azure-beta-ids`

Resources the public site still needs:

- `ca-metrik-api`, `cae-metrik-beta`, `acrmetrikbetalgy2mu`, `id-metrik-beta-app`, `log-metrik-beta`
- The in-app Postgres sidecar and its `EmptyDir` volume

`stmetrikbetalgy2mu` and its `pgdata` share are public-template leftovers.
The live revision does not mount that share. Confirm it is unused before any
later cleanup. It is not a research share, and this audit did not delete it.

## 10. Tests requiring replacement

Replace or rewrite when the Azure research path is removed:

| Test | Why |
| --- | --- |
| `tests/test_automation_workflows.py::test_research_schedule_is_monday_and_single_replica` | Asserts `research.bicep` cron, Azure Files, and a single replica. |
| `tests/test_automation_workflows.py::test_manual_control_uses_oidc_and_no_client_secret` | Asserts `groundtruth-weekly-control.yml`. |
| `tests/test_automation_workflows.py::test_deploy_workflow_verifies_before_deploy_and_has_rollback` | Asserts today's `weekly-release-deploy.yml` step order. Keep the safety assertions; change the Azure Files assumptions. |
| `tests/test_automation_workflows.py::test_workflows_never_echo_notification_secrets` | Lists `groundtruth-weekly-control.yml`. Keep the secret-echo rule for whatever replaces it. |
| `tests/test_scrape_control.py` | Mocks Azure management-plane job start, stop, and executions. |
| Help text in `tests/test_product_notifications.py` and `tests/test_scrape_control.py` | Expects `/scrape`, `/scrape_start`, `/scrape_stop`, and `/auto_update`. |

Keep as they are unless behavior changes:

- `tests/test_automation_weekly_release.py`
- `tests/test_automation_notifications.py`
- `tests/test_telegram_webhook.py`
- `tests/test_product_notifications.py` contact/owner delivery cases
- `tests/test_release_metadata.py`
- `tests/test_release_verify.py`

## 11. Documentation requiring replacement

Replace before operators follow them:

- `docs/GROUNDTRUTH_CLOUD_RESEARCH.md`
- `docs/AUTONOMOUS_WEEKLY_PIPELINE_RUNBOOK.md`

Treat as historical, and stop using them as deploy instructions:

- `docs/AUTONOMOUS_WEEKLY_PIPELINE_FINAL_REPORT.md`
- `docs/AUTONOMOUS_PIPELINE_CURRENT_STATE.md`
- `docs/RESEARCH_INFRASTRUCTURE_RECONCILIATION_2026-09-28.md`

Keep:

- `docs/PUBLIC_DATABASE_DURABILITY_PLAN.md`
- `docs/STATISTICAL_QA_CALIBRATION.md`
- `docs/AZURE_BETA.md` and `docs/DEPLOYMENT.md` for the public site, after a later pass confirms they do not tell operators to apply `research.bicep`

This audit did not rewrite those files.

## 12. Risks of removing each Azure-research component

| Component | Risk if removed now |
| --- | --- |
| `research.bicep` | No deployed resource disappears. A `master` push that deletes `infra/azure/**` matches `azure-beta-deploy.yml` path filters and will rebuild and redeploy public Metrik. |
| `Dockerfile.research` | No deployed image disappears. Local worker build instructions disappear. |
| `groundtruth-weekly-control.yml` | No live job is affected. It has zero runs. Tests that read the file fail. |
| `weekly-release-deploy.yml` schedule | Leaving it enabled causes a Monday failure and a Telegram failure message. Removing the file removes the only coded rollback deploy. The only execution never reached deploy or rollback. |
| Azure Files download inside that workflow | Production is unaffected today because the variable is empty and the step exits first. Replacing it is required before a local bundle can publish. |
| `scrape_control.py` alone | Public startup breaks. `app.py` imports `start_scrape_watch`. |
| Scrape commands, with `app.py` updated in the same change | Website and contact Telegram keep working. Owner `/scrape*` and `/auto_update` stop. The 30-minute thread stops. |
| Custom role and the four job env names | Website keeps working. `/scrape` on the current image starts returning “not configured” or an identity error instead of “not deployed”. |
| `id-metrik-beta-app` AcrPull / AcrPush / Reader / Container Apps Contributor | Public deploy and image pull break. These are not research-job roles. |
| `product_notifications.py` or the webhook route | Contact, feedback, reports, listings, and owner commands stop reaching Telegram. |
| `automation/**` and `pipeline weekly-release` | Public HTTP API does not import them. The research command and its tests stop. |
| Public sidecar `EmptyDir` | Out of scope. Removing it destroys the live public database on the next replica recycle. Do not touch it in a research migration. |
| `stmetrikbetalgy2mu` / share `pgdata` | Not mounted by revision `0000026`. Still confirm emptiness before any later delete. |

## 13. Exact recommended migration boundary

Do not cross this line in the migration:

**Stays on Azure, unchanged in behavior**

- `ca-metrik-api` revision lineage, public `Dockerfile`, `azure-beta-deploy.yml`, `prod-image.yml`
- OIDC federated credentials, ACR, `id-metrik-beta-app` pull/push/reader and Container Apps Contributor
- Telegram webhook, contact/feedback/report/listing notifications
- httpx log suppression from `6815a99` / `08d393c`
- Release gates and `groundtruth release` bundle format
- Public Postgres sidecar and its `EmptyDir` volume

**Leaves Azure because it was never deployed**

- Research Flexible Server, research storage account, `pipeline-state`, `verified-releases`
- `cae-groundtruth-research`, `id-groundtruth-research-job`, `job-groundtruth-weekly`
- GitHub environment `groundtruth-research` and the four missing `GROUNDTRUTH_*` research variables
- ACR repository `groundtruth-research`

**Moves to the local Windows host**

- Postgres/PostGIS from `docker-compose.yml` (`postgis/postgis:16-3.4`), only after an explicit start that this audit did not perform
- `groundtruth pipeline weekly-release` writing `reports/generated/pipeline_state` and `reports/generated/releases`
- A new GitHub self-hosted runner. None exists today.
- Optional use of `Dockerfile.research` as that worker image

**Must be rewritten, not deleted blindly**

- `weekly-release-deploy.yml`: accept a bundle produced by the runner, then keep verify, immutable tag, smoke, and rollback
- `scrape_control.py` and the lifespan hook: either report runner status, or remove commands and import together
- `test_automation_workflows.py` and `test_scrape_control.py`
- The three Azure research docs listed in section 11

**Do not do**

- Do not reset `master` to `4aa9cbf` or the recovery tag.
- Do not point `ca-metrik-api` `DATABASE_URL` at the local research database.
- Do not apply `research.bicep` on this subscription as a temporary database.
- Do not replace the public sidecar with the research server.
- Do not remove Telegram secrets or the public OIDC secrets.

## 14. Confirmation that no live public production dependency would be removed

The live public process depends on:

- image `metrik-api:08d393c` in `acrmetrikbetalgy2mu`
- revision `ca-metrik-api--0000026` in `cae-metrik-beta`
- env names in section 9, including Telegram and `DATABASE_URL`
- `id-metrik-beta-app` for image pull
- the sidecar Postgres on `EmptyDir`

It does not depend on a research Flexible Server, a research storage account,
`pipeline-state`, `verified-releases`, `cae-groundtruth-research`,
`id-groundtruth-research-job`, or `job-groundtruth-weekly`. Those objects are
absent, and the public site is healthy on revision `0000026` without them.

The public process does import `scrape_control.py` and does carry the four
job-control env names. That is a live code dependency on a module, and a live
configuration dependency for bot job commands. It is not a dependency on a
deployed research resource. Removing the module without editing `app.py`
would break startup. Removing the missing Azure resources removes nothing
that is running.

`weekly-release-deploy.yml` is a latent production writer. Its only run
stopped before `Deploy candidate revision`. Disabling or rewriting it does
not roll back revision `0000026`.

## 15. UNKNOWN facts that still require operator confirmation

1. Whether Docker Desktop's stopped disk still contains volume `postgres_data`, and whether that volume has a `groundtruth` database. The engine was stopped and was not started.
2. If that database exists: Alembic revision, database size, per-table sizes, and row counts for `raw_listings`, `parsed_listings`, `normalized_listings`, `invalid_listings`, `listing_observations`, and `scrape_runs`.
3. PostgreSQL and PostGIS versions inside that volume. Compose requests `postgis/postgis:16-3.4`. The running version was not queried.
4. Whether Flexible Server SKUs are still unavailable in this subscription. This audit proved that no server exists. It did not repeat the SKU catalog query.
5. Whether share `pgdata` on `stmetrikbetalgy2mu` is empty and safe to ignore. The live app does not mount it. Contents were not listed.
6. Whether organization-level GitHub runners exist outside this repository. Repository runners are zero.
7. Whether any research backup exists outside depth 3 of this repo. The dumps found are small 2026-09-15 drill files.
8. Whether the operator wants the active Monday cron left in place until the replacement workflow is ready. It will fail again and send Telegram.
9. Whether `vulcan-forge-*` and `probe-*` resource groups are unrelated leftovers. They contained no resources in the subscription list.
10. Production source versus `master`: the live image is `08d393c`. `master` `4ee0924` adds only `docs/RESEARCH_INFRASTRUCTURE_RECONCILIATION_2026-09-28.md`. Behavior matches, documentation on the server does not include that file or this audit.
