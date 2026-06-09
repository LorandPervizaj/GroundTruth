# GroundTruth — Kosovo Real Estate Intelligence Platform

The scraper is an input. The asset is the data.

Market intelligence for residential real estate in Prishtina and Fushë Kosovë. See [docs/PLATFORM.md](docs/PLATFORM.md) for roadmap and publication strategy.

## Stack

| Layer | Tools |
|-------|-------|
| Language | Python 3.12+ (project uses 3.13) |
| Package manager | uv |
| Database | PostgreSQL 16 + PostGIS |
| Containers | Docker (Postgres + pgAdmin only) |

No Redis. Single machine, scheduled scraping.

## Quick Start

```powershell
# Install uv (once)
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"

cd c:\Projects\GroundTruth

# Install Python 3.13 + all dependencies
uv sync --all-extras

# Playwright browsers
uv run playwright install

# Environment
copy .env.example .env

# Database
docker compose up -d postgres pgadmin

# Migrations
uv run alembic revision --autogenerate -m "initial schema"
uv run alembic upgrade head

# Verify
uv run pytest
uv run groundtruth version
```

## Project Structure

```
src/groundtruth/               # Application code
reports/
  templates/            # Report templates (in git)
  generated/            # Output PDFs/CSVs (gitignored)
data/gazetteers/        # Neighborhood/complex lookup tables
docs/                   # Architecture and methodology
tests/
```

## Build Order

```
Gjirafa scraper → 5000 listings → clean → normalize → deduplicate
  → report.pdf → LinkedIn → THEN dashboard
```

## Key Features

- **Versioning**: every scrape has `run_id`, `scraped_at`, `spider_version`
- **property_events**: listed → price reduced → removed lifecycle
- **market_snapshots**: nightly precomputed metrics for fast dashboard
- **Market Health Score**: ranked neighborhoods
- **Buyer Score**: best neighborhoods for a given budget

## Reports

Generated output goes to `reports/generated/` — never beside source code.

```powershell
uv run python -c "
from groundtruth.services.report_service import ReportService
# ReportService().generate_neighborhood_summary(df)
"
```

## Development

```powershell
uv run ruff check src tests
uv run pytest -v
```
