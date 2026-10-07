# Metrik / GroundTruth

[![CI](https://github.com/LorandPervizaj/GroundTruth/actions/workflows/ci.yml/badge.svg)](https://github.com/LorandPervizaj/GroundTruth/actions/workflows/ci.yml)
[![k6 performance](https://github.com/LorandPervizaj/GroundTruth/actions/workflows/k6.yml/badge.svg)](https://github.com/LorandPervizaj/GroundTruth/actions/workflows/k6.yml)

Residential real-estate **market intelligence** for Prishtina: neighborhood
medians, inventory, rent yield, and valuation ranges, each published with its
sample size and confidence. Aggregated statistics, not a listing board.

### Live site: **[Metrik on Azure](https://ca-metrik-api.livelydune-1ec3eb9a.eastus2.azurecontainerapps.io)**

`https://ca-metrik-api.livelydune-1ec3eb9a.eastus2.azurecontainerapps.io`

Public, no login. The site opens in Albanian; use the **Shqip / English** toggle
in the top-right corner to switch languages. The current release is
`2026-W40-3578e069fab9`, with data through 4 October 2026: 11,888 active
listings after removing 4,390 cross-portal duplicates from 16,278 raw listings.
These figures change with each weekly release; `/api/meta` always shows the
live values.

![Metrik home page](docs/images/home.jpg)

## Tour of the site

All figures are **asking prices** from public portal listings, not confirmed
transaction prices. Every number is shown with its sample size and a confidence
level, and thin samples are flagged instead of hidden.

| Page | URL | What it shows |
| --- | --- | --- |
| Home | [`/`](https://ca-metrik-api.livelydune-1ec3eb9a.eastus2.azurecontainerapps.io/) | Search box for any neighborhood, district, or residential complex; popular-market chips; a "find areas by budget" shortcut; a five-step "How it works" guide |
| Market page | [`/market/neighborhood/ulpiana`](https://ca-metrik-api.livelydune-1ec3eb9a.eastus2.azurecontainerapps.io/market/neighborhood/ulpiana) | One area's sale €/m², median sale price, median rent, and active listings; comparison with the city average; sub-markets; breakdowns by property type, bedrooms, and size; price distribution; recent listings |
| Statistics | [`/statistics`](https://ca-metrik-api.livelydune-1ec3eb9a.eastus2.azurecontainerapps.io/statistics) | Citywide annual report (active listings, rent share, median €/m², median rent), executive summary, and a downloadable PDF report |
| Compare | [`/compare`](https://ca-metrik-api.livelydune-1ec3eb9a.eastus2.azurecontainerapps.io/compare) | Two or three neighborhoods side by side: prices, inventory, and sample confidence |
| Rent yield | [`/rent-yield`](https://ca-metrik-api.livelydune-1ec3eb9a.eastus2.azurecontainerapps.io/rent-yield) | Gross annual yield ranking by neighborhood, with the median rent, median sale price, and sample counts behind each figure |
| Value my property | [`/valuate`](https://ca-metrik-api.livelydune-1ec3eb9a.eastus2.azurecontainerapps.io/valuate) | Rent or sale estimate for a given area, size, and bedroom count, with a confidence range and the comparable listings it used (marked experimental) |
| Find a neighborhood | [`/find`](https://ca-metrik-api.livelydune-1ec3eb9a.eastus2.azurecontainerapps.io/find) | Budget, size, and bedroom filters that recommend neighborhoods and show how many listings fit |
| About, methodology | [`/about`](https://ca-metrik-api.livelydune-1ec3eb9a.eastus2.azurecontainerapps.io/about), [`/methodology`](https://ca-metrik-api.livelydune-1ec3eb9a.eastus2.azurecontainerapps.io/methodology) | Data sources, cleaning and deduplication, metric definitions, and limitations |
| Contact / report | [`/contact`](https://ca-metrik-api.livelydune-1ec3eb9a.eastus2.azurecontainerapps.io/contact) | Contact form, data-error reports, and listing submissions; these are forwarded to the owner's Telegram chat |

### Market page

Search for an area, or open one from the home page chips, to get its headline
numbers, its position against the Prishtina average, and the breakdowns behind
them.

![Ulpiana market page](docs/images/market.jpg)

### Statistics and rent yield

The Statistics section holds the annual report, neighborhood comparison, and
rent-yield ranking.

![Market statistics](docs/images/statistics.jpg)

![Rent yield ranking](docs/images/rent-yield.jpg)

### Explore: value a property or find a neighborhood

The Explore section estimates fair rent or price from comparable listings and
recommends neighborhoods that match a budget.

![Value my property](docs/images/valuate.jpg)

![Find a neighborhood](docs/images/find.jpg)

The JSON API that backs these pages lives under `/api/` (for example
`/api/meta`, `/api/search?q=ulpiana`, `/api/lookup/neighborhood/ulpiana`,
`/api/rent-yield`). Interactive API docs are disabled in production.

## What this repository contains

| Part | Role | Where it runs |
| --- | --- | --- |
| **GroundTruth** | Private research pipeline: collects public listings, parses, normalizes, deduplicates across sources, computes metrics, and gates each weekly release | Local Windows research host with a private PostgreSQL/PostGIS database |
| **Metrik** | Public website and API (FastAPI + static HTML/JS) serving only verified release artifacts | Azure Container Apps |

Both live in one Python package (`src/groundtruth`). The production image
installs only the `web` extra; crawler dependencies never ship to Azure.

This project is not affiliated with any real-estate portal, agency, or
marketplace.

## Architecture

```text
 Local Windows research host               GitHub                         Azure (public)
┌────────────────────────────────┐   ┌───────────────────────────┐   ┌────────────────────────┐
│ self-hosted runner             │   │ Release (immutable)       │   │ ACR: metrik-api:<id>   │
│ groundtruth-weekly-local.yml   │   │ groundtruth-release-<id>  │   │ Container App revision │
│ PostGIS research DB (private)  │──▶│   .tar.gz + .sha256       │──▶│ smoke test             │
│ pipeline weekly-release        │   │ weekly-release-deploy.yml │   │ rollback on failure    │
└────────────────────────────────┘   └───────────────────────────┘   └────────────────────────┘
```

Inside the research run:
crawl → raw → parsed → normalized → active corpus → cross-source dedup →
metrics → release artifacts. Product canonicalization is analytics-layer
(`is_canonical_primary`); the `canonical_properties` table remains deferred.
See [docs/architecture.md](docs/architecture.md).

## Public/private data boundary

**Stays on the research host:** raw HTML, listing text and photos, seller and
agent contact data, the research database and its backups, pipeline state,
logs, and `research.env`.

**Crosses to the public side:** one release bundle containing `lookup_cache/`
(aggregated market lookups, comparables, manifest with per-file SHA256) and
`data/api/{annual_report,rent_yield}.json`. The bundle verifier rejects any
other path, and artifact verification rejects listing-level fields.

The public database holds only application schema and product writes
(contact, feedback, events). Details: [docs/DATA_HANDLING.md](docs/DATA_HANDLING.md).

## Stack

| Concern | Choice |
| --- | --- |
| Language, packaging | Python 3.13, [uv](https://docs.astral.sh/uv/) with a frozen `uv.lock` |
| Database | PostgreSQL 16 + PostGIS, Alembic migrations |
| API and site | FastAPI, Uvicorn, static HTML/JS in `web/` |
| Research collectors | Scrapy, scrapy-playwright (research extra only) |
| CI/CD | GitHub Actions, self-hosted Windows runner for research only |
| Hosting | Azure Container Apps, Azure Container Registry |
| Quality | pytest, Playwright, ruff, pip-audit, gitleaks, Trivy, k6 |

## Local development

```powershell
uv sync --all-extras
copy .env.example .env
docker compose up -d postgres
uv run alembic upgrade head
uv run groundtruth serve
```

Open http://127.0.0.1:8000/. The site serves market data from the committed
release artifacts in `reports/generated/lookup_cache/`.

If Docker cannot bind port `5432` (Hyper-V port exclusions on Windows), set
`POSTGRES_PORT` and the matching `DATABASE_URL` in `.env`, for example `15432`.

On the research host, the compose `postgres` service **is** the research
database. Use the disposable databases below for tests and load tests.

## Research pipeline

```powershell
uv run groundtruth pipeline weekly-release
```

This is the single research entrypoint. Stages: crawl and ETL over a catch-up
window derived from the last verified watermark, source-health gate,
data-quality gate, statistical sanity checks (shadow mode, non-blocking),
release build, release verification, and watermark update. Any blocking gate
failure stops the run with no release.

In production it runs only through `.github/workflows/groundtruth-weekly-local.yml`
on the self-hosted runner, which adds a host doctor, pre- and post-run database
backups, publication-candidate verification, and Telegram notifications.

**Runs are currently started manually** (`gh workflow run groundtruth-weekly-local.yml --ref master`
or the Telegram `/scrape_start` command). The workflow has no `schedule:`
trigger yet; [LOCAL_RESEARCH_RUNNER.md](docs/LOCAL_RESEARCH_RUNNER.md#enabling-the-schedule)
describes when to add the Monday cron.

## Release and production deployment

1. The research job publishes `groundtruth-release-<release_id>` as a GitHub
   Release with exactly the bundle and its checksum. Existing tags are never
   overwritten.
2. `weekly-release-deploy.yml` downloads that exact release, verifies checksum,
   contents, and manifest again, and runs `groundtruth release verify-artifacts`.
3. It builds an immutable `metrik-api:<release_id>-<sha>` image, confirms
   crawler packages are absent, and fails on fixable HIGH/CRITICAL Trivy findings.
4. It pushes to ACR, creates a new Container App revision, waits for it to
   report the expected release, and smoke-tests the live API.
5. On failure after the switch, it redeploys the previous image and verifies it.

Code-only changes go through `azure-beta-deploy.yml` on pushes to `master`; it
keeps whichever verified data release is live. Full procedure, manual
redeploys, and runtime settings: [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md).

## Running on Azure

Metrik runs as a single Azure Container App, `ca-metrik-api`, in East US 2. Its
infrastructure is defined in [infra/azure/](infra/azure/).

| Piece | Setup |
| --- | --- |
| App container | `metrik-api` image from Azure Container Registry, 0.5 vCPU / 1 GiB, external HTTPS ingress to port 8000, one replica |
| Database | PostgreSQL 16 sidecar in the same app (0.25 vCPU / 0.5 GiB) holding only schema and product writes. Its storage is `EmptyDir`, so data is lost when the replica is recycled; [PUBLIC_DATABASE_DURABILITY_PLAN.md](docs/PUBLIC_DATABASE_DURABILITY_PLAN.md) covers the move to a durable database |
| Market data | Baked into the image from the verified release bundle (`reports/generated/lookup_cache/`), and the app refuses to start without it |
| Runtime settings | `APP_ENV=production`, JSON logs, rate limiting on, API docs off, migrations on start; the database URL, health-check token, and Sentry DSN come from Container App secrets |
| Logs | Log Analytics workspace attached to the Container Apps environment |
| Deploy identity | GitHub Actions signs in to Azure with OIDC; no Azure credentials are stored in the repository |

Each deploy creates a new revision. The workflow waits until
`scripts/azure/wait-for-revision.sh` confirms that revision is healthy and
serving the expected release, then `scripts/azure/smoke.ps1` checks the live
pages and API. If either step fails, the previous image is redeployed and
smoke-tested again. Provisioning notes: [docs/AZURE_BETA.md](docs/AZURE_BETA.md).

## Telegram owner bot

A private Telegram bot keeps the owner informed and gives remote control over
research runs. It answers only the chat configured in `TELEGRAM_CHAT_ID`, and
Telegram must send the webhook secret header to `/api/telegram/webhook`;
messages from any other chat are ignored and logged.

| Command | What it does |
| --- | --- |
| `/status` | Whether Metrik is online, plus the live release, data-through date, and QA result |
| `/latest` | Latest verified release and its data-through date |
| `/quality` | Latest data-quality result |
| `/deployment` | Production release and the source commit it was built from |
| `/sources` | Points to the source-health summary sent after each research run |
| `/scrape` | State of the current or most recent research workflow run |
| `/scrape_start` | Starts `groundtruth-weekly-local.yml` on the research host through the GitHub API |
| `/scrape_stop` | Cancels a running research workflow |
| `/help` | Lists the commands |

The bot also sends messages without being asked:

- **Research run:** started, pipeline result with the source-health summary,
  release verified and published, post-run backup failure, or run failed.
- **Deployment:** started, deployed and verified, or failed. A failure message
  says whether the previous image was restored.
- **Site activity:** contact messages, feedback, data-error reports, and
  listing submissions from the public site.

Configuration lives outside the repository. Workflows read
`TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` from GitHub secrets. The research
host reads the same pair from `research.env` (see
[docs/LOCAL_RESEARCH_RUNNER.md](docs/LOCAL_RESEARCH_RUNNER.md)). The live app
needs both plus `TELEGRAM_WEBHOOK_SECRET`; the webhook returns 403 when that
secret is missing or the request header does not match it.

## Testing and quality gates

```powershell
.\scripts\test-db.ps1        # disposable PostGIS on 127.0.0.1:15433, migrated
uv run pytest -q
uv run ruff check src tests scripts
uv run ruff format --check src tests scripts
```

- **Database isolation:** database-backed tests use only
  `GROUNDTRUTH_TEST_DATABASE_URL`; they skip without it. `tests/conftest.py`
  refuses any URL whose database name lacks `test` or matches the application
  or research database, and ignores `DATABASE_URL` and `GROUNDTRUTH_ENV_FILE`.
- **Browser tests:** `RUN_E2E=1 uv run pytest tests/e2e -q` (Playwright Chromium).
- **Release verification:** `uv run groundtruth release verify-artifacts`;
  parser regression gates in `tests/test_parser_ci_gates.py` against `data/golden/`.
- **Security:** CI runs `pip-audit` and gitleaks; deploys run Trivy.
  `tests/test_automation_workflows.py` fails if a workflow on the self-hosted
  runner gains a trigger that could run fork code.
- **CI:** `ci.yml` runs all of the above on pushes and pull requests to `master`.

### Performance testing

```powershell
winget install --id GrafanaLabs.k6 --exact          # once
.\scripts\performance\start-local-test-target.ps1   # disposable DB + Metrik on 127.0.0.1:8000
.\scripts\performance\k6.ps1 smoke                  # 3 VUs, 15 s
.\scripts\performance\k6.ps1 baseline               # up to 25 VUs, 60 s
.\scripts\performance\start-local-test-target.ps1 -Stop
```

The wrapper refuses non-local targets unless explicitly overridden, writes
results to `.tmp/k6/`, and returns k6's exit code. k6 is a regression detector
for the single-worker serving path, not a capacity benchmark. See
[docs/PERFORMANCE_TESTING.md](docs/PERFORMANCE_TESTING.md) and the reference
[baseline](docs/performance/BASELINE.md).

## Repository layout

```text
src/groundtruth/   CLI, API, ETL, analytics, release, research automation, collectors
web/               Metrik pages and static assets
alembic/           Database migrations
tests/             pytest suite, e2e/ (Playwright), load/ (k6)
data/              Gazetteers, golden parser set, claims, dataset manifests, published API JSON
reports/generated/lookup_cache/   Committed release artifacts served by Metrik
scripts/           research/ host setup, release/ install, azure/ deploy, performance/ k6
infra/azure/       Bicep for the Container App, registry, and database
.github/workflows/ CI, k6, research, release deploy, code deploy, watchdog
docs/              Current documentation; docs/history/ holds point-in-time records
```

## Operations

| Task | Document |
| --- | --- |
| Run, monitor, and recover the research host | [docs/LOCAL_RESEARCH_RUNNER.md](docs/LOCAL_RESEARCH_RUNNER.md) |
| Deploy, redeploy, or roll back public Metrik | [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) |
| Provision Azure resources | [docs/AZURE_BETA.md](docs/AZURE_BETA.md) |
| Operate collectors | [docs/SCRAPERS.md](docs/SCRAPERS.md) |
| Everyday local commands | [docs/CHEATSHEET.md](docs/CHEATSHEET.md) |

## Responsible use

- Collectors run only on a private host and follow
  [docs/CRAWL_POLICY.md](docs/CRAWL_POLICY.md): public pages only, robots.txt
  and rate limits honored, no login-gated or messaging scrapes, no Facebook
  Marketplace automation.
- Metrik publishes aggregates. It does not republish listing text, photos,
  seller or agent contact details, or raw HTML.
- You are responsible for complying with applicable law and each source's
  terms. This repository is not legal advice and grants no rights to
  third-party content. Do not use it to build a listings mirror, lead-generation
  scraper, or contact harvester.

## Documentation

| Document | Topic |
| --- | --- |
| [architecture.md](docs/architecture.md) | Pipeline, versioning, deferred components |
| [methodology.md](docs/methodology.md) | Metrics, confidence, methodology versions |
| [METRIC_REGISTRY.md](docs/METRIC_REGISTRY.md) | Definition of every public metric |
| [MARKET_DATA_CONTRACT.md](docs/MARKET_DATA_CONTRACT.md) | Pipeline and lifecycle contract |
| [STATISTICAL_QA_CALIBRATION.md](docs/STATISTICAL_QA_CALIBRATION.md) | Shadow statistical gates |
| [DATA_HANDLING.md](docs/DATA_HANDLING.md) | PII, retention, public allowlist |
| [CRAWL_POLICY.md](docs/CRAWL_POLICY.md) | Source rules and rate limits |
| [LOCAL_RESEARCH_RUNNER.md](docs/LOCAL_RESEARCH_RUNNER.md) | Research host runbook |
| [DEPLOYMENT.md](docs/DEPLOYMENT.md) | Production deployment and rollback |
| [PUBLIC_DATABASE_DURABILITY_PLAN.md](docs/PUBLIC_DATABASE_DURABILITY_PLAN.md) | Plan to replace the non-durable public DB sidecar |

See [CONTRIBUTING.md](CONTRIBUTING.md) for development guidance and
[SECURITY.md](SECURITY.md) for private vulnerability reporting.
| [PERFORMANCE_TESTING.md](docs/PERFORMANCE_TESTING.md) | k6 profiles, thresholds, results |
| [DATASET_V2_FREEZE.md](docs/DATASET_V2_FREEZE.md) | Dataset v2.0 freeze record |
| [history/](docs/history/README.md) | Superseded audits and designs, kept as evidence |
