# Metrik Production Deployment

Target for the first public deployment: one small VPS or VM, FastAPI app behind nginx, private Postgres, and prebuilt public artifacts copied from the private ETL host.

## 1. Build Release Artifacts

Run this on the private data/ETL machine after crawl + ETL + analytics:

```powershell
uv run groundtruth crawl weekly --stage analytics --force
uv run groundtruth release build-artifacts
uv run groundtruth release verify-artifacts
```

`verify-artifacts` checks file presence, manifest structure, per-file SHA256 hashes, valid lookup JSON / `MarketLookup` schema, and absence of forbidden listing fields (title/description/phone, etc.). Rebuild artifacts after upgrading so manifests include `sha256` / `artifact_hashes`.

Required artifacts:

- `reports/generated/lookup_cache/manifest.json`
- `reports/generated/lookup_cache/**.json`
- `reports/generated/lookup_cache/rent_comparables.json.gz`
- `reports/generated/lookup_cache/sale_comparables.json.gz`
- `reports/generated/lookup_cache/comparables_meta.json`
- `data/api/annual_report.json`

Copy `reports/generated/lookup_cache/` to the web host at the same relative path, or mount it into the app container at `/app/reports/generated`.

## 2. Configure Production Environment

Create `.env.production` from `.env.production.example`.

Required production values:

- `APP_ENV=production`
- `LOG_FORMAT=json`
- `API_DOCS_ENABLED=false`
- `API_REQUIRE_LOOKUP_CACHE=true`
- strong `DATABASE_URL`, `POSTGRES_USER`, and `POSTGRES_PASSWORD`
- `PRODUCT_WRITE_BACKEND=database`
- `PUBLIC_BASE_URL=https://your-domain`

Never use the development database password on a reachable host.

## 3. Migrate Database

Run migrations before starting traffic. Preferred production path (dedicated migrate profile):

```bash
docker compose -f docker-compose.prod.yml --env-file .env.production --profile migrate run --rm migrate
```

Then set `RUN_MIGRATIONS_ON_START=false` so the runtime app user does not need DDL.

Local/dev fallback:

```bash
uv run alembic upgrade head
```

Limited beta may still use `RUN_MIGRATIONS_ON_START=true` (transitional). Full public launch must complete runtime/migration role separation (`scripts/sql/create_runtime_role.sql`).

The public app can run against a private Postgres instance. For a stricter split, use a read-only/reporting database for public lookup routes and keep raw research tables private.

## 4. Start The Stack

```bash
docker compose -f docker-compose.prod.yml --env-file .env.production up -d --build
```

Check readiness:

```bash
curl -fsS http://localhost/api/ready
# Ops only (requires X-Health-Token, blocked at nginx edge):
curl -fsS -H "X-Health-Token: $HEALTH_CHECK_TOKEN" http://localhost:8000/api/health/perf
```

In production `/api/ready` returns **HTTP 200** only when ready. Not-ready states return
**HTTP 503** with JSON like `{"ok": false, "reasons": ["lookup_cache_not_loaded", ...]}`.
Readiness requires loaded lookup/comparables caches and verified release artifact hashes.
`curl -fsS` fails on the 503, which is what HEALTHCHECK / compose expect.

## 5. nginx / TLS

`deploy/nginx/metrik.conf` provides:

- reverse proxy to the app container
- gzip
- static cache headers
- read/write API rate-limit zones
- small request body cap

Terminate TLS at your cloud load balancer or extend the nginx config with mounted certificates. Redirect HTTP to HTTPS once certificates are installed.

## 6. Product Writes

Production should use:

```env
PRODUCT_WRITE_BACKEND=database
```

This writes alerts, feedback, and anonymous events to `product_submissions`. Local development can keep `PRODUCT_WRITE_BACKEND=jsonl`.

## 7. Backups And Rollback

### Automated backup

Run on the deployment host (cron weekly recommended):

```bash
chmod +x scripts/backup_postgres.sh
./scripts/backup_postgres.sh
```

Environment overrides: `BACKUP_DIR`, `RETENTION_DAYS`, `COMPOSE_FILE`, `ENV_FILE`.

The script dumps Postgres with `pg_dump`, copies lookup cache + annual report JSON, and prunes old backups.

Validate backup/restore on a disposable Postgres (does not touch production):

```bash
# Linux/macOS
./scripts/backup_restore_drill.sh

# Windows (PowerShell) — requires a running Docker daemon
./scripts/backup_restore_drill.ps1
```

The drill creates a backup, restores it, checks a known row, then confirms a corrupt gzip is rejected.

### Restore

```bash
chmod +x scripts/restore_postgres.sh
./scripts/restore_postgres.sh backups/postgres_groundtruth_YYYYMMDDTHHMMSSZ.sql.gz
```

Restore is destructive — it drops and recreates the database. Re-copy artifact directories manually if needed.

Prefer an elevated migration role for alembic upgrade and a least-privilege runtime role for the API (scripts/sql/create_runtime_role.sql). Set RUN_MIGRATIONS_ON_START=false once migrations are run separately so the app user does not need DDL.

### Recovery assumptions (RPO / RTO)

Documented operating assumptions for limited beta (not a contractual SLA):

| Metric | Assumption | Notes |
|--------|------------|-------|
| RPO (data loss window) | Up to **7 days** for Postgres + release artifacts | Matches recommended weekly backup cron |
| RTO (restore time) | **1–4 hours** for a practiced operator | Restore dump + re-attach verified `lookup_cache` + annual JSON + `/api/ready` |
| Artifact integrity | Required | Prefer last **verified** release; never publish failed `verify_release_artifacts` |
| Schema rollback | Prefer forward-fix | Destructive DB restore only with explicit operator approval |

Evidence today: disposable Docker drill (`scripts/backup_restore_drill.*`) + corrupt gzip rejection tests. A production-volume restore must still be run once on the deployment host before calling recovery “proven in prod”.

### What to back up

- Postgres database
- `reports/generated/lookup_cache/`
- `data/api/annual_report.json`

### Application / artifact rollback

Operator rollback path (manual is acceptable for limited beta):

1. Tag current image before upgrade: `docker tag metrik-api:latest metrik-api:previous`.
2. On bad release: `docker tag metrik-api:previous metrik-api:latest` (or pull prior digest), then `docker compose -f docker-compose.prod.yml --env-file .env.production up -d app`.
3. Restore the previous `reports/generated/lookup_cache/` and `data/api/annual_report.json` from backup.
4. Confirm `GET /api/ready` returns HTTP 200 before restoring traffic.
5. Database: only roll back schema if a migration was applied and is known-reversible; prefer forward-fix migrations. Document migration risk before each release.

## 8. Security Hardening

Production checklist (Sprint 1):

- `PRODUCT_WRITE_BACKEND=database` (enforced at startup)
- `HEALTH_CHECK_TOKEN` set — `/api/health/perf` and `/api/metrics` require `X-Health-Token` header (nginx blocks them at the edge)
- `API_RATE_LIMIT_ENABLED=true` (enforced at startup; cannot be disabled in production)
- `ALERTS_SIGNUP_ENABLED=false` until automated notifications exist
- Security headers via nginx + FastAPI middleware
- Rate limiting: nginx burst zones + app-level slowapi sustained limits
- Strongly recommended: `SENTRY_DSN` (set `REQUIRE_SENTRY_DSN=true` for public production)

Never use the development database password on a reachable host.

## 10. First go-live checklist

- [x] Release artifacts build/verify CLI (`groundtruth release build-artifacts`)
- [x] Prod compose + nginx configs in repo
- [x] Public docs posture (aggregates only; crawlers off public host)
- [ ] VPS/VM provisioned; DNS A/AAAA for domain
- [ ] `.env.production` on host (strong secrets, real `PUBLIC_BASE_URL`, `HEALTH_CHECK_TOKEN`)
- [ ] TLS certificates mounted / LB termination
- [ ] Copy verified `lookup_cache/` + `annual_report.json` onto host
- [ ] `alembic upgrade head` then `docker compose -f docker-compose.prod.yml --env-file .env.production up -d --build`
- [ ] `/api/ready` healthy; smoke home, market, statistics, rent-yield
- [ ] Weekly backup cron + restore drill once (`scripts/backup_restore_drill.sh` or `.ps1`)
- [ ] `SENTRY_DSN` configured (or explicitly accepted risk for internal-only beta)
- [ ] Keep research crawlers on the private ETL machine only

