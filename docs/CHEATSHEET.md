# Cheat sheet — local site and ops

Windows / PowerShell from the repo root.

**Public posture:** Metrik serves aggregated market stats only. Raw listing content stays on a private research database. See [DATA_HANDLING.md](DATA_HANDLING.md) and [CRAWL_POLICY.md](CRAWL_POLICY.md).

Collector commands (private research host): **[SCRAPERS.md](SCRAPERS.md)**.

---

## First-time setup (once)

```powershell
uv sync --all-extras
copy .env.example .env
docker compose up -d postgres
uv run alembic upgrade head
```

If host port `5432` is blocked (Windows Hyper-V exclusions often include it), set `POSTGRES_PORT` / `DATABASE_URL` in `.env` to another port (e.g. `15432`).

---

## Start the website

```powershell
docker compose up -d postgres
uv run groundtruth serve
```

Open **http://127.0.0.1:8000/**

Default bind is `127.0.0.1:8000`. Stop with `Ctrl+C` in that terminal.

---

## Research ingest (summary)

Prefer the gated ingest flow documented in [SCRAPERS.md](SCRAPERS.md):

```powershell
scripts\run_ingest.cmd
```

That script is for a **private** operator machine. Do not publish crawl dumps or attach raw HTML to public releases.

Policy / rate limits: [CRAWL_POLICY.md](CRAWL_POLICY.md).

---

## Quick health checks

```powershell
docker compose ps
curl http://127.0.0.1:8000/api/ready
uv run pytest
```

---

## Production (short)

```powershell
uv run groundtruth release build-artifacts
uv run groundtruth release verify-artifacts
docker compose -f docker-compose.prod.yml --env-file .env.production up -d --build
```

Production deploys the Metrik **website/API**, not research crawlers. Full guide: [DEPLOYMENT.md](DEPLOYMENT.md).
