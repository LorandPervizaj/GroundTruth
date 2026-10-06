# Performance testing with k6

Metrik uses Grafana k6 as a **regression detector** for the public read path.
It runs against a local Metrik instance, never against Azure production.

Metrik serves with one application worker because the lookup and comparables
caches are process-local. Numbers from this suite are not capacity claims and
say nothing about horizontal scaling.

## Quick start (Windows)

```powershell
winget install --id GrafanaLabs.k6 --exact        # once
.\scripts\performance\start-local-test-target.ps1  # disposable DB + migrations + Metrik
.\scripts\performance\k6.ps1 smoke                 # ~15 s
.\scripts\performance\k6.ps1 baseline              # ~60 s
.\scripts\performance\start-local-test-target.ps1 -Stop
```

Docker Desktop is needed only for the disposable database; k6 itself runs
natively.

## Local target and database isolation

`start-local-test-target.ps1` starts only the compose service `postgres-perf`
(`groundtruth-perf-postgres`, `127.0.0.1:15434`, database `groundtruth_perf`,
tmpfs storage), migrates it, and starts `groundtruth serve --no-reload` on
`127.0.0.1:8000` with:

- an explicit `DATABASE_URL` for that database,
- an empty `GROUNDTRUTH_ENV_FILE`, so `research.env` is never loaded,
- `APP_ENV=development` and rate limits off, matching CI.

It refuses to start if port 8000 is already taken (an existing Metrik may be
connected to another database). After startup it calls `/api/methodology`,
which counts listings through the server's own database session, and stops the
target unless the count is 0 and the server holds a connection to
`groundtruth_perf`. The research database (`groundtruth-postgres`) is never
started, stopped, or queried by these scripts.

Market data comes from the release artifacts in
`reports/generated/lookup_cache/`, as in CI and production.

## The wrapper

`scripts/performance/k6.ps1 <smoke|baseline> [-BaseUrl <url>] [-AllowRemote] [-AllowProduction]`

1. Accepts only `localhost`, `127.0.0.1`, or `::1` by default. Any other host
   needs `-AllowRemote`; `*.azurecontainerapps.io` additionally needs
   `-AllowProduction`. Do not load-test production: it is rate limited, it
   serves real users, and its database sidecar is not durable.
2. Finds k6 on `PATH` (or `C:\Program Files\k6\k6.exe` right after install).
3. Requires `GET /api/health` to return 200 and prints how to start a target if not.
4. Prints the target database when the target was started by the helper.
5. Runs `tests/load/k6_public_api.js` and writes to `.tmp/k6/` (gitignored):
   - `<timestamp>-<profile>.txt`: header plus the k6 end-of-test summary
   - `<timestamp>-<profile>-summary.json`: k6 `--summary-export`
   - `<timestamp>-<profile>-meta.json`: target, database, commit, k6 version, exit code
6. Exits with k6's exit code: 0 passed, 99 a threshold failed.

## What is covered

Each iteration batches five read-only requests and validates response shape,
so a fast but malformed response still fails:

| Request | Tag | Checks |
| --- | --- | --- |
| `GET /` | `home` | 200, HTML, renders Metrik |
| `GET /api/health` | `health` | 200, `status: ok` |
| `GET /api/meta` | `meta` | 200, dataset version present |
| `GET /api/markets` | `markets` | 200, non-empty list |
| `GET /api/lookup/neighborhood/ulpiana` | `lookup` | 200, slug and pulse data |

Write and side-effect endpoints (contact, feedback, events, alerts, product
submissions) are deliberately excluded. `/api/valuate` is excluded too: it is
rate limited (`API_RATE_LIMIT_VALUATE`, 30/hour by default) and does
per-request comparables work unlike the cached reads above.
If valuation needs load testing, add a separate, explicitly named script.

## Profiles

| Profile | Shape | Used by |
| --- | --- | --- |
| `smoke` | 3 VUs for 15 s | Pull requests and pushes in CI; quick local check |
| `baseline` | 0→10 VUs over 15 s, →25 VUs over 30 s, →0 over 15 s | Nightly CI; local regression comparison |

The suite has no warm-up stage. The lookup cache loads during application
startup, before `/api/health` returns 200; afterwards the first request to each
endpoint measured 10–15 ms versus 7–10 ms warm, which is too small to distort
the results.

## Thresholds

| Metric | Threshold |
| --- | --- |
| `checks` | rate > 99% |
| `http_req_failed` | rate < 1% |
| `http_req_duration` (all) | p95 < 750 ms, p99 < 1500 ms |
| `http_req_duration{endpoint:markets}` | p95 < 900 ms |
| `http_req_duration{endpoint:lookup}` | p95 < 1000 ms |

On the reference laptop four baseline runs measured p95 331–392 ms and p99
543–730 ms ([BASELINE.md](performance/BASELINE.md)), roughly half the gates. The gates
stay loose enough for GitHub-hosted runner variance while catching large
regressions. Do not tighten them from a single run.

## Reading results

Compare runs on the same machine and the same k6 version only. Look at `med`,
`p(95)`, and `p(99)` of `http_req_duration` and at `http_reqs` rate. Laptop
power management moves individual runs noticeably (two consecutive smoke runs
measured p95 87 ms and 142 ms), so repeat a run before treating a change as a
regression.

## CI

`.github/workflows/k6.yml` starts a disposable PostGIS service, applies
migrations, starts Metrik on `127.0.0.1:8000`, and runs the suite. It never
targets Azure. Pull requests and pushes that touch the serving path, the load
script, the local tooling, or this document run `smoke`; the nightly schedule
runs `baseline`; `workflow_dispatch` can choose either. Text and JSON summaries
are uploaded as the `k6-<run>` artifact for 14 days.

CI pins k6 `2.3.0`. The Windows winget package currently provides `2.2.0`.
Upgrade pins deliberately and keep thresholds unchanged for at least one
comparison run, so version changes are not mistaken for application regressions.
