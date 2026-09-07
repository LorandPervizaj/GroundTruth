# Metrik / GroundTruth

[![CI](https://github.com/riverdoggo/GroundTruth/actions/workflows/ci.yml/badge.svg)](https://github.com/riverdoggo/GroundTruth/actions/workflows/ci.yml)

Prishtina residential **market intelligence** — aggregated statistics, not a listing board.

| Layer | Role |
|-------|------|
| **Metrik** | Public website and API — neighborhood medians, inventory, valuation, with sample size and confidence on every metric |
| **GroundTruth** | Private research pipeline used to build those aggregates (local database; not deployed with the public site) |

This project is **not affiliated with** any real-estate portal, agency, or marketplace. Third-party site names appear only as data-source labels in research docs.

## What is (and is not) public

**Public Metrik** shows aggregated market metrics. It does **not** republish listing titles, descriptions, photos, seller/agent contact details, or raw scraped HTML.

**GroundTruth** keeps raw research data on a private host under operator control. See [docs/DATA_HANDLING.md](docs/DATA_HANDLING.md).

## Responsible use

- Intended for research and for operating your own Metrik instance with **aggregated** outputs.
- Operators must follow [docs/CRAWL_POLICY.md](docs/CRAWL_POLICY.md): public pages/APIs only, honor robots.txt and rate limits, no login-gated or messaging scrapes, no Facebook Marketplace automation.
- You are responsible for complying with applicable law and each source’s terms. This repository is **not legal advice** and does **not** grant rights to third-party content.
- Do not use this codebase to build a competing listings mirror, lead-gen scraper, or contact harvester.

Ingestion command details live in the operator guide: [docs/SCRAPERS.md](docs/SCRAPERS.md) (private research host only).

## Stack

| Component | Choice |
|-----------|--------|
| Language | Python 3.13 |
| Packages | [uv](https://docs.astral.sh/uv/) |
| Database | PostgreSQL 16 + PostGIS |
| API / site | FastAPI + static HTML/JS (`web/`) |
| Research ingest | Scrapy-based collectors (see crawl policy) |

## Quick start (local Metrik)

```powershell
uv sync --all-extras
copy .env.example .env
docker compose up -d postgres
uv run alembic upgrade head
uv run groundtruth serve
```

Open **http://127.0.0.1:8000/**

If Docker cannot bind host port `5432` (common on Windows with Hyper-V port exclusions), set `POSTGRES_PORT` and matching `DATABASE_URL` in `.env` (for example `15432`).

## Layout

```
src/groundtruth/   CLI, API, ETL, analytics, research collectors
web/               Metrik pages and static assets
data/gazetteers/   Neighborhood / district / street / complex lookup
data/golden/       Parser regression set (internal; may contain historical text)
data/claims/       Published claims registry
data/api/          Frozen public report JSON
docs/              Architecture, methodology, deploy, data handling
scripts/           Ops helpers for private research hosts
```

## Quality

```powershell
uv run pytest
uv run ruff check src tests
```

## Production (Metrik only)

Ship release artifacts and run the **website/API** stack — not the research crawlers:

```powershell
uv run groundtruth release build-artifacts
uv run groundtruth release verify-artifacts
docker compose -f docker-compose.prod.yml --env-file .env.production up -d --build
```

Details: [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md).

## Docs

| Doc | Topic |
|-----|--------|
| [CHEATSHEET.md](docs/CHEATSHEET.md) | Local site + high-level ops |
| [SCRAPERS.md](docs/SCRAPERS.md) | Private-host collector usage |
| [architecture.md](docs/architecture.md) | Pipeline and versioning |
| [methodology.md](docs/methodology.md) | Metrics and confidence |
| [CRAWL_POLICY.md](docs/CRAWL_POLICY.md) | Rate limits and source rules |
| [DATA_HANDLING.md](docs/DATA_HANDLING.md) | Retention and public allowlist |
| [DATASET_V2_FREEZE.md](docs/DATASET_V2_FREEZE.md) | Dataset freeze |
| [DEPLOYMENT.md](docs/DEPLOYMENT.md) | Production host |
