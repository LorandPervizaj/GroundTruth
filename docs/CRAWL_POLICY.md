# Crawl policy — private research posture

**Scope:** Local research database only. Crawling is **not** part of the public Metrik product surface.

The public repo documents this policy so it does not read like an attack toolkit. Ingestion runs on a private machine under operator control. How-to: [SCRAPERS.md](SCRAPERS.md). This is not a license to scrape third-party sites; operators must comply with law, robots.txt, and source terms.

---

## Principles

1. **Public data only** — listing pages and APIs that are openly reachable without authentication.
2. **Low volume** — conservative request rates; no parallel hammering of a single host.
3. **Respect signals** — `ROBOTSTXT_OBEY = True` globally; honor HTTP 429/503 with backoff.
4. **Idempotent runs** — skip listings already stored; dedupe by content hash before insert.
5. **No Facebook automation** — Marketplace full scrape is **NO-GO**; manual import only ([FB_MARKETPLACE.md](FB_MARKETPLACE.md)).
6. **Research, not republication** — raw HTML stays local; the public site shows aggregated statistics only ([DATA_HANDLING.md](DATA_HANDLING.md)).

---

## Default Scrapy settings

Configured in `src/groundtruth/scrapers/settings.py` (overridable via `.env`):

| Parameter | Default | Notes |
|-----------|---------|-------|
| `ROBOTSTXT_OBEY` | `True` | Global default |
| `DOWNLOAD_DELAY` | `2.0` s | Base pause between requests |
| `RANDOMIZE_DOWNLOAD_DELAY` | `True` | Jitter 0.5×–1.5× |
| `CONCURRENT_REQUESTS` | `4` | Global cap |
| `AUTOTHROTTLE_ENABLED` | `True` | Adaptive slowdown under load |
| `AUTOTHROTTLE_TARGET_CONCURRENCY` | `2.0` | Soft target per domain |
| `AUTOTHROTTLE_MAX_DELAY` | `10.0` s | Upper backoff |
| `RETRY_HTTP_CODES` | includes `429` | Back off on rate-limit responses |

Environment: `SCRAPY_DOWNLOAD_DELAY`, `SCRAPY_CONCURRENT_REQUESTS`, `SCRAPY_FAST_MODE` in `.env.example`.

**Default posture is conservative** (`SCRAPY_FAST_MODE=false`): HTML and API spiders use autothrottle with modest concurrency. Opt into fast mode only for short, supervised research crawls.

Per-spider overrides exist for JSON API sources (slightly lower latency) but stay at **≤4 concurrent requests per domain** with autothrottle enabled when fast mode is off.

---

## Skip-existing & deduplication

- **`skip_existing=true`** (default on Gjirafa, MerrJep, Pro-RKS, Topia, Vision, MYRE) — detail/API rows for listing IDs already in `raw_listings` are not re-fetched (optionally limited to IDs seen within N days).
- **Content hash pipeline** — identical HTML/payload is not inserted twice (`ContentHashPipeline`).
- **MerrJep daemon** — background incremental crawl (`scripts/run_crawl_daemon.ps1`) resumes from last page; stops on stale index dates rather than paging forever.

These reduce redundant traffic during daily refresh cycles.

---

## Scheduled / daemon operation

| Mechanism | Purpose |
|-----------|---------|
| `scripts/run_crawl_daemon.ps1` | Long-running MerrJep incremental crawl (private host) |
| `scripts/crawl_daemon_status.ps1` | MerrJep daemon PID/state + invokes crawl monitor |
| `scripts/crawl_monitor.py` | Multi-spider health (`--spider` optional; default all six) |
| `scripts/stop_crawl_daemon.ps1` | Clean shutdown |
| ETL after crawl | Normalize + snapshot; no public exposure of raw HTML |

Daemons are **not** deployed with the public website. One operator machine, off-peak windows, manual start/stop.

---

## Source-specific notes

| Source | Transport | Rate posture |
|--------|-----------|--------------|
| Gjirafa | Static HTML (HTTP handler, not Playwright) | Autothrottle on; ≤4 concurrent/domain; `skip_existing` default. Spider sets `ROBOTSTXT_OBEY=False` (historical) — revisit if robots.txt blocks needed paths; global default remains `True`. |
| MerrJep | HTML + optional archive | 1.0 s delay; autothrottle; incremental daemon |
| Pro-RKS / Topia / Vision / MYRE | Public JSON APIs | ≤4 concurrent; autothrottle; no HTML bulk download |
| Facebook Marketplace | **Manual import only** | No automated crawler — see [FB_MARKETPLACE.md](FB_MARKETPLACE.md) |

---

## What we do not do

- Scrape login-gated, paywalled, or private messaging content
- Automate Facebook Marketplace or private groups
- Publish crawl command cookbooks or raw dumps in the public README
- Run distributed crawlers or rotate IPs to evade limits
- Republish listing descriptions, photos, or seller contact details on the public site
- Harvest phones/emails for lead generation or resale

Operator how-to (private host): [SCRAPERS.md](SCRAPERS.md).

---

## Operator checklist

- [ ] `.env` delays at or above defaults before a full crawl
- [ ] `skip_existing=true` for incremental runs
- [ ] Monitor logs for 429 spikes; pause daemon if seen
- [ ] Raw HTML retention per [DATA_HANDLING.md](DATA_HANDLING.md)
- [ ] Facebook data only via `groundtruth fb import` (manual JSONL)
- [ ] Confirm public site still exposes aggregates only (no listing text/PII)
