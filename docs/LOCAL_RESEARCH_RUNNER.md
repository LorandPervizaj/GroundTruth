# Local research runner — operator runbook

GroundTruth research runs on the local Windows research host. Public Metrik
stays on Azure. The only thing that crosses from the host to the public side is
a verified public release bundle, published as an immutable GitHub Release.

```text
local Windows research host              GitHub                     Azure (public)
┌──────────────────────────────┐   ┌──────────────────────────┐   ┌──────────────┐
│ self-hosted runner           │   │ Release                  │   │ ca-metrik-api│
│ Docker PostGIS (research DB) │──▶│ groundtruth-release-<id> │──▶│ new revision │
│ C:\MetrikResearch            │   │  .tar.gz + .sha256       │   │ or rollback  │
└──────────────────────────────┘   └──────────────────────────┘   └──────────────┘
      groundtruth-weekly-local.yml      weekly-release-deploy.yml (GitHub-hosted)
```

The Azure research plane (`infra/azure/research.bicep`,
`groundtruth-weekly-control.yml`) was never provisioned and is not used.

## Host layout

| Path | Purpose |
| --- | --- |
| `C:\MetrikResearch\config\research.env` | Database URL, Telegram, durable paths. Never committed, never uploaded. |
| `C:\MetrikResearch\state` | Watermark (`state.json`), OS-backed `weekly-release.lock`, crawl checkpoints, run results in `runs\`. |
| `C:\MetrikResearch\releases` | Verified bundles and checksums produced by the pipeline. |
| `C:\MetrikResearch\backups` | Custom-format `pg_dump` files. Local only. |
| `C:\MetrikResearch\logs` | Host logs, including `prepare-host.log`. |
| `C:\MetrikResearch\runner` | GitHub runner `metrik-research-<COMPUTERNAME>`. Jobs check out under `_work`. |
| `C:\MetrikResearch\bin` | Installed copy of `scripts/research/prepare-host.ps1`. |

`research.env` must define at least `DATABASE_URL`, `GROUNDTRUTH_PIPELINE_STATE_DIR`,
`GROUNDTRUTH_RELEASE_OUTPUT_DIR`, `GROUNDTRUTH_BACKUP_DIR`,
`GROUNDTRUTH_POSTGRES_CONTAINER`, and optionally `TELEGRAM_BOT_TOKEN` and
`TELEGRAM_CHAT_ID`. The workflow points `GROUNDTRUTH_ENV_FILE` at it; the CLI
loads it at startup without overriding variables already set in the process.

Research Postgres is the existing Compose container `groundtruth-postgres`
(`postgis/postgis:16-3.4`, volume `fartestate_postgres_data`, bound to
`127.0.0.1:15432`). Public Metrik never connects to it.

## Host availability

The runner runs in the owner's Windows session, not as a service, because
Docker Desktop only serves the logged-in user and the account has no admin
rights. `scripts/research/install-host-tasks.ps1` registers:

- **GroundTruth research runner**: at logon; runs `run.cmd` hidden; restarts on failure.
- **GroundTruth research host prepare**: at logon and Mondays 03:30 local with
  wake-to-run; starts Docker Desktop if needed, starts only
  `groundtruth-postgres`, and starts the runner task if it is not running.

Re-run the installer after changing either script. The host must stay logged
in (a locked screen is fine) and on AC power with the lid open during the
research window. The current power plan never sleeps on idle.

## Weekly sequence

`groundtruth-weekly-local.yml`, job `research` on labels
`self-hosted, Windows, X64, groundtruth-research`, only on `master`:

1. Check out the exact commit, install the locked `research` environment.
2. `groundtruth research doctor --expected-sha <sha>`: repository, database,
   PostGIS, Alembic at head, writable durable directories outside the checkout,
   free disk, lock available, watermark, last verified release, backup age.
   Any FAIL stops the run. A stale backup is a WARN only.
3. `groundtruth research backup --label pre-weekly`.
4. `groundtruth pipeline weekly-release`: crawl, ETL, source-health gate,
   data-quality gate, statistical gate, release build and verification,
   watermark update. This is the only place GroundTruth logic runs.
5. `groundtruth research publication-candidate`: outcome must be `verified`
   or `warning`; bundle must be in the release directory, match its SHA256,
   contain only `lookup_cache/` and `data/api/{annual_report,rent_yield}.json`,
   and carry a publishable manifest for this release id and commit.
6. Create GitHub Release `groundtruth-release-<release_id>` at the run commit
   with exactly the bundle and checksum. Fails if the release or tag exists.
7. `groundtruth research backup --label post-weekly` (failure notifies but does
   not block the release).
8. Job `deploy` calls `weekly-release-deploy.yml` with that exact tag.

`weekly-release-deploy.yml` (GitHub-hosted) checks out the release tag, and
`scripts/release/install-verified-release.sh` downloads exactly two assets,
runs `sha256sum --check` and `groundtruth release verify-bundle`, and installs
them. The workflow then runs `release verify-artifacts`, builds
`metrik-api:<release_id>-<sha>`, confirms scraper packages are absent, runs
Trivy (HIGH/CRITICAL fails), pushes, captures the previous image, deploys,
smoke-tests `/api/meta` against the release id, and restores the previous
image on failure.

## Failure contract

| Failure | Result |
| --- | --- |
| Runner offline, Docker or Postgres down, doctor FAIL | No backup-dependent work, no release, no deployment. |
| Source, data-quality, or statistical gate RED | Pipeline fails; no release, no deployment. |
| Bundle checksum/content/manifest mismatch | No release, or deploy refuses before build. |
| Deploy fails before the revision switch | Production unchanged. |
| Deploy fails after the switch | Previous image restored and smoke-tested. |

Telegram receives: research started, pipeline result, release published,
deployment started, deployment success or failure (with rollback status), and
a GitHub-hosted notice whenever the research job does not succeed.

A research job whose runner never comes online just sits queued; GitHub
cancels it only after 24 hours. `groundtruth-weekly-watchdog.yml` runs on a
GitHub-hosted runner and classifies the latest weekly run:

| State | Meaning |
| --- | --- |
| `ok` | Succeeded, running, or queued within `max_queue_minutes` (default 45). |
| `runner_offline` | The research job was never picked up: host asleep, off, logged out, or runner task stopped. |
| `workflow_failed` | The runner ran the job and it failed; the alert names the failed step. |
| `blocked` | The run has not created its research job, usually because an older run holds the concurrency group. |
| `not_created` | No weekly run exists in the last 20 hours. |

Any state other than `ok` sends a Telegram alert and fails the watchdog run.

## Manual operations

```powershell
# Start a research run (same as Telegram /scrape_start)
gh workflow run groundtruth-weekly-local.yml --ref master
# Research without deploying, or with an explicit catch-up window
gh workflow run groundtruth-weekly-local.yml --ref master -f deploy=false -f days=9
# Redeploy one exact verified release
gh workflow run weekly-release-deploy.yml --ref master -f release_tag=groundtruth-release-<release_id>
# Host health, with config loaded the same way the workflow does it
$env:GROUNDTRUTH_ENV_FILE = 'C:\MetrikResearch\config\research.env'
uv run groundtruth research doctor
```

Cancelling a run (GitHub UI, `gh run cancel`, or Telegram `/scrape_stop`) is
safe: the pipeline lock is an OS file lock released when the process exits,
including on crash or power loss. The lock file's metadata (run id, host, pid,
time) is informational only.

## Telegram control

`/scrape`, `/scrape_start`, `/scrape_stop` call the GitHub Actions API from the
public app. Configure on `ca-metrik-api`:

- Secret `groundtruth-github-token`: fine-grained personal access token,
  repository access **only** `LorandPervizaj/GroundTruth`, permissions
  **Actions: Read and write** (Metadata: Read is implied). No classic PAT.
- Env `GROUNDTRUTH_GITHUB_TOKEN=secretref:groundtruth-github-token`.
- Optional env `GROUNDTRUTH_GITHUB_REPOSITORY`, `GROUNDTRUTH_GITHUB_WORKFLOW`
  (defaults `LorandPervizaj/GroundTruth`, `groundtruth-weekly-local.yml`).

`/auto_update` and the public app's 30-minute polling thread are retired.

## Backups and restore drill

Every run takes a `pre-weekly` and a `post-weekly` dump. Retention keeps every
backup from the four most recent ISO weeks plus the newest of each of the three
most recent months. Dumps never leave the host.

A backup counts as proven only after a restore. Run this drill monthly, never
inside the weekly workflow:

```powershell
$dump = Get-ChildItem C:\MetrikResearch\backups\research-*.dump | Sort-Object LastWriteTime | Select-Object -Last 1
docker run -d --name groundtruth-restore-drill --network none -e POSTGRES_PASSWORD=drill postgis/postgis:16-3.4
docker cp $dump.FullName groundtruth-restore-drill:/tmp/drill.dump
docker exec groundtruth-restore-drill createdb -U postgres -T template0 research_restore
docker exec groundtruth-restore-drill pg_restore -U postgres -d research_restore --exit-on-error --no-owner /tmp/drill.dump
docker exec groundtruth-restore-drill psql -U postgres -d research_restore -c "SELECT version_num FROM alembic_version; SELECT count(*) FROM normalized_listings;"
docker rm -f groundtruth-restore-drill
```

Compare the Alembic revision and table counts with the source database before
deleting the drill container.

## Security invariants

- The repository is public. `groundtruth-weekly-local.yml` only allows
  `workflow_dispatch` and `schedule`; `tests/test_automation_workflows.py` fails
  if any workflow using a self-hosted runner gains another trigger.
- Repository setting: fork pull-request workflows require approval for all
  outside contributors.
- The runner opens no inbound port; it connects out to GitHub.
- Published releases hold only public serving artifacts. Database dumps, raw
  pages, pipeline state, logs, and `research.env` never leave the host.

## Enabling the schedule

Only after manual commissioning and the failure drills, add to
`groundtruth-weekly-local.yml`:

```yaml
  schedule:
    - cron: "0 3 * * 1"
```

and give `groundtruth-weekly-watchdog.yml` a later check, for example
`cron: "0 4 * * 1"`, which is 60 minutes after the scheduled start.

Do not re-add a schedule to `weekly-release-deploy.yml`. There is one weekly
decision: research, then its verified release, then deployment.

## Code deploys keep the live data release

`azure-beta-deploy.yml` runs on code pushes to `master`. Before building, it
reads `release_id` from live `/api/meta` and reinstalls that exact GitHub
Release through `scripts/release/install-verified-release.sh`, the same
download-and-verify path the weekly deploy uses. Smoke tests then require
`/api/meta` to report that release. When production serves no verified
release (`release_id` null), it deploys the committed artifacts as before.

If production is down and `/api/meta` cannot be read, the deploy stops. Re-run
it with the `data_release_tag` input set to the release that should be served.
