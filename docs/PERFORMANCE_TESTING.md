# Performance testing with k6

Metrik uses Grafana k6 for repeatable load checks against a local CI instance of the public website/API. The suite intentionally targets read-only public paths and does not load-test write endpoints such as valuation, contact, feedback, or events because those paths are rate-limited and/or have side effects.

## What is covered

`tests/load/k6_public_api.js` exercises a representative cached-read mix:

- `GET /`
- `GET /api/health`
- `GET /api/meta`
- `GET /api/markets`
- `GET /api/lookup/neighborhood/ulpiana`

The test validates response shape as well as status codes, so a fast but malformed response still fails checks.

## Profiles

`smoke` is the pull-request/push profile: 3 virtual users for 15 seconds.

`baseline` is the scheduled/manual profile: ramp to 10 virtual users, then 25 virtual users, then down over 60 seconds total.

The baseline is deliberately modest. Metrik currently serves with one application worker because lookup/comparables caches are process-local. This suite is meant to catch regressions in the existing architecture, not claim a horizontal-scaling capacity target.

## Thresholds

The current CI gates are:

- checks: greater than 99% successful
- failed HTTP requests: below 1%
- all requests: p95 below 750 ms and p99 below 1500 ms
- `/api/markets`: p95 below 900 ms
- market lookup: p95 below 1000 ms

These thresholds run against GitHub-hosted CI and should stay loose enough to tolerate runner variance while still catching large regressions. Tight production SLOs should be measured separately from a controlled environment.

## Local use

Start Metrik first:

```powershell
uv sync --all-extras
docker compose up -d postgres
uv run alembic upgrade head
uv run groundtruth serve --no-reload
```

Then, with k6 installed:

```powershell
k6 run -e BASE_URL=http://127.0.0.1:8000 -e K6_PROFILE=smoke tests/load/k6_public_api.js
```

For the longer profile:

```powershell
k6 run -e BASE_URL=http://127.0.0.1:8000 -e K6_PROFILE=baseline tests/load/k6_public_api.js
```

## CI behavior

`.github/workflows/k6.yml` starts a disposable PostGIS service, applies migrations, starts Metrik locally, and runs k6 against `127.0.0.1`. It never points the automated load test at Azure production.

Pull requests and pushes that touch the public serving path run the smoke profile. The scheduled workflow runs the baseline profile. A manual workflow dispatch can choose either profile.

The workflow pins k6 to `2.3.0` for reproducibility. Upgrade the pin deliberately and keep the thresholds unchanged for at least one comparison run so version changes are not confused with application regressions.
