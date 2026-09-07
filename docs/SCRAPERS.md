# Scrapers — operator guide

**Audience:** Operators of a **private** GroundTruth research host.

**Not for the public product.** Metrik publishes aggregated market statistics only. Raw HTML, listing text, photos, and seller contact data stay on the research database and must not be republished.

Before any crawl, read:

- [CRAWL_POLICY.md](CRAWL_POLICY.md) — rate limits, robots.txt, what we do not do  
- [DATA_HANDLING.md](DATA_HANDLING.md) — PII retention and public allowlist  
- [FB_MARKETPLACE.md](FB_MARKETPLACE.md) — Facebook automation is **NO-GO**

---

## Responsible use

1. Crawl only **public** listing pages / public JSON APIs that do not require login.
2. Keep defaults conservative (`ROBOTSTXT_OBEY`, download delays, autothrottle). Do not disable them to evade limits.
3. Use `skip_existing` for incremental runs so you do not re-fetch the same IDs.
4. You are responsible for complying with each source’s terms, robots rules, and applicable law. This repo is not legal advice and is not a license to scrape third-party sites.
5. Do not distribute crawl dumps, raw HTML, or contact data with the public site or a public portfolio zip.

---

## Prerequisites

```powershell
uv sync --all-extras
copy .env.example .env
# Edit .env: DATABASE_URL, and if Windows blocks 5432, set POSTGRES_PORT (e.g. 15432)
docker compose up -d postgres
uv run alembic upgrade head
```

Confirm the DB is reachable before crawling.

---

## Recommended: gated ingest (all sources)

Asks for a **1–4 week** lookback, crawls configured sources, then asks before normalize + site refresh:

```powershell
scripts\run_ingest.cmd
# or
uv run groundtruth crawl ingest
```

Useful flags:

| Goal | Command |
|------|---------|
| Fixed lookback | `uv run groundtruth crawl ingest --weeks 2` |
| Skip ETL confirm | `uv run groundtruth crawl ingest --weeks 2 --yes` |
| One source | `uv run groundtruth crawl ingest --weeks 2 --only gjirafa-rent,merrjep` |
| Already crawled | `uv run groundtruth crawl ingest --skip-crawl --yes` |

Logs: `reports\generated\weekly\ingest_*.log`

---

## Scheduled weekly pipeline

```powershell
uv run groundtruth crawl weekly
# optional Windows Task Scheduler registration:
powershell -File scripts\register_weekly_schedule.ps1
```

| Goal | Command |
|------|---------|
| Crawl only | `uv run groundtruth crawl weekly --stage crawl --force` |
| ETL only | `uv run groundtruth crawl weekly --stage etl --force` |
| Analytics only | `uv run groundtruth crawl weekly --stage analytics --force` |
| Sequential (debug) | `uv run groundtruth crawl weekly --stage crawl --force --no-parallel` |

Skips if the last weekly run was under ~7 days unless `--force`.

Interactive daemon helper: `scripts\run_weekly.cmd`.

---

## Per-source CLI (manual)

After any crawl: `uv run groundtruth etl run` (optionally `--source <name>`).

| Source | Typical command |
|--------|-----------------|
| Gjirafa rent | `uv run groundtruth crawl gjirafa-rent` |
| Gjirafa sale | `uv run groundtruth crawl gjirafa-sale` |
| MerrJep (production detail) | `uv run groundtruth crawl merrjep --detail` |
| Pro-RKS | `uv run groundtruth crawl pro-rks` |
| Topia | `uv run groundtruth crawl topia` |
| Vision | `uv run groundtruth crawl vision` |
| MyRealEstate | `uv run groundtruth crawl myrealestate` |

Shared options on most spiders:

- `--skip-existing` / `--no-skip-existing` (default: skip)
- `--skip-existing-days N` (0 = skip any previously seen ID)
- `--max-pages`, `--max-listings` (caps for supervised runs)

MerrJep modes:

| Mode | Flag | Writes DB? |
|------|------|------------|
| Discovery (index only) | default / `--discovery-only` | No |
| Archive sample | `--archive-only` | No |
| Production | `--detail` | Yes |

---

## MerrJep incremental daemon (private host)

Long-running incremental crawl — not part of the public website deploy.

| Script | Purpose |
|--------|---------|
| `scripts\run_crawl_daemon.ps1` | Start MerrJep daemon |
| `scripts\crawl_daemon_status.ps1` | Status |
| `scripts\stop_crawl_daemon.ps1` | Stop |
| `scripts\crawl_monitor.py` | Multi-spider health |

---

## After crawl

```powershell
uv run groundtruth etl run
uv run groundtruth crawl weekly --stage analytics --force
```

Or finish via ingest confirmation so normalize + homepage trust snapshot run together.

---

## What this guide does not cover

- Facebook Marketplace / private groups automation — forbidden; manual import only  
- Login-gated, paywalled, or messaging content  
- Distributed crawlers, proxy farms, or IP rotation to bypass rate limits  
- Publishing raw listing content on Metrik
