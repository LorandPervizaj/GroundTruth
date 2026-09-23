# Autonomous weekly pipeline operator runbook

## Normal Monday sequence

At 03:00 UTC Monday, `job-groundtruth-weekly` starts the private research image. It derives the catch-up interval from the last verified watermark, crawls all automated sources, runs ETL/analytics/QA, verifies artifacts, and writes a versioned bundle to the private `verified-releases` Azure Files share. At 15:00 UTC, the GitHub deploy workflow retrieves the newest verified bundle, verifies it again, builds an immutable Metrik image, deploys it, smoke-tests production, and rolls back on failure.

## Manual weekly run

Local fallback:

```powershell
uv run groundtruth pipeline weekly-release
uv run groundtruth pipeline weekly-release --days 21
```

Cloud:

```powershell
az containerapp job start -g <research-rg> -n job-groundtruth-weekly
```

Or dispatch `GroundTruth weekly control` with action `start`.

## Inspect status and logs

```powershell
az containerapp job execution list -g <research-rg> -n job-groundtruth-weekly -o table
az containerapp job logs show -g <research-rg> -n job-groundtruth-weekly --follow
az containerapp logs show -g rg-metrik-beta-eus2 -n ca-metrik-api --follow
```

Inspect `/mnt/state/state.json` and the matching run JSON on the state share for stage counts/errors. GitHub deployment evidence is retained as the `deployment-<release-id>` Actions artifact.

## Retry and missed-week catch-up

Start the job again. Completed crawl/ETL checkpoints and uniqueness constraints make retry safe. The verified watermark advances only after artifact verification. A missed week increases the next requested interval automatically, with one-day overlap and a 56-day safety cap.

## Failed source, parser breakage, CAPTCHA, or blocking

1. Read the source-health entry and referenced scrape run.
2. Confirm whether the source changed, robots policy changed, or blocking/CAPTCHA occurred.
3. A RED source blocks release verification; production remains unchanged.
4. Do not automatically rewrite/deploy a parser. Fix it through a reviewable Git change and parser fixtures/tests.
5. Re-run the job after the software fix. Checkpoints resume healthy stages where appropriate.

## Database outage

The job fails before advancing the watermark. Restore database access, confirm TLS connectivity, then manually restart it. Never point GroundTruth at the public Metrik sidecar.

## GroundTruth backup and restore

List backups and restore points:

```powershell
az postgres flexible-server backup list -g <research-rg> -n <research-server> -o table
az postgres flexible-server show -g <research-rg> -n <research-server> --query "{earliest:backup.earliestRestoreDate,retention:backup.backupRetentionDays}"
```

Verify restoration by creating a disposable point-in-time server, checking table counts and representative rows, running artifact verification against it, then deleting the disposable server only after evidence is recorded. Do not overwrite the authoritative server during a drill.

## Release verification or image-build failure

No Container App update occurs. Inspect the run record or Actions log, correct the cause, and retry. Never bypass `groundtruth release verify-artifacts`.

## Deployment failure and rollback

The workflow captures `PREVIOUS_IMAGE` and `PREVIOUS_REVISION` before deployment. On smoke failure it updates the Container App back to `PREVIOUS_IMAGE` and reruns smoke tests.

Manual rollback:

```powershell
$previous = '<immutable-acr-image-from-deployment-evidence>'
az containerapp update -g rg-metrik-beta-eus2 -n ca-metrik-api --image $previous
powershell -File scripts/azure/smoke.ps1 -BaseUrl https://ca-metrik-api.livelydune-1ec3eb9a.eastus2.azurecontainerapps.io
```

## Deploy the last verified release

Dispatch `Deploy verified weekly release` and enter the exact `groundtruth-release-<release-id>.tar.gz` bundle filename. The workflow still verifies the sidecar, internal hashes, manifest, and live application.

## Pause and resume

Pause research scheduling by moving the cron to an impossible date; running executions must be stopped separately if necessary:

```powershell
az containerapp job update -g <research-rg> -n job-groundtruth-weekly --cron-expression "0 0 31 2 *"
az containerapp job stop -g <research-rg> -n job-groundtruth-weekly --job-execution-name <execution>
```

Resume Monday scheduling:

```powershell
az containerapp job update -g <research-rg> -n job-groundtruth-weekly --cron-expression "0 3 * * 1"
```

Disable or resume automatic publication independently:

```powershell
gh workflow disable weekly-release-deploy.yml --repo LorandPervizaj/GroundTruth
gh workflow enable weekly-release-deploy.yml --repo LorandPervizaj/GroundTruth
```

## Telegram test and rotation

Store `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` as secrets in both relevant GitHub environments and as Container Apps Job secrets/env references. Test without printing the token:

```powershell
$uri = "https://api.telegram.org/bot$env:TELEGRAM_BOT_TOKEN/sendMessage"
Invoke-RestMethod -Method Post -Uri $uri -Body @{ chat_id=$env:TELEGRAM_CHAT_ID; text='GroundTruth notification test' }
```

Rotate by creating a new bot token, updating secret stores, sending a test, then revoking the old token. Never place tokens or chat IDs in Git.

## Optional Gmail reporting

Configure `SMTP_HOST`, `SMTP_PORT`, `SMTP_USERNAME`, `SMTP_PASSWORD`, `SMTP_FROM`, and `PIPELINE_EMAIL_TO`. For Gmail, use an app password. Email failure never changes release safety.

## Local Windows fallback

```powershell
docker compose up -d postgres
uv run alembic upgrade head
uv run groundtruth pipeline weekly-release
uv run groundtruth release verify-artifacts
```

Do not advance the cloud state manually unless the same release was verified against the authoritative research database.

