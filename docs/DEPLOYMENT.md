# Metrik Production Deployment

Target for the first public deployment: one small VPS or VM, FastAPI app behind nginx, private Postgres, and prebuilt public artifacts copied from the private ETL host.

## 1. Build Release Artifacts

Run this on the private data/ETL machine after crawl + ETL + analytics:

```powershell
uv run groundtruth crawl weekly --stage analytics --force
uv run groundtruth release build-artifacts
uv run groundtruth release verify-artifacts
```

Required artifacts:

- `reports/generated/lookup_cache/manifest.json`
- `reports/generated/lookup_cache/**.json`
- `reports/generated/lookup_cache/rent_comparables.json.gz`
- `reports/generated/lookup_cache/sale_comparables.pkl`
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

Run migrations before starting traffic:

```bash
uv run alembic upgrade head
```

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

In production `/api/ready` is only healthy when lookup and comparables caches are loaded.

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

### Restore

```bash
chmod +x scripts/restore_postgres.sh
./scripts/restore_postgres.sh backups/postgres_groundtruth_YYYYMMDDTHHMMSSZ.sql.gz
```

Restore is destructive — it drops and recreates the database. Re-copy artifact directories manually if needed.

### What to back up

- Postgres database
- `reports/generated/lookup_cache/`
- `data/api/annual_report.json`

Rollback procedure:

1. Restore the previous app image.
2. Restore the previous lookup cache directory.
3. Restore the previous annual report JSON.
4. Run `/api/ready` before putting traffic back.

## 8. Security Hardening

Production checklist (Sprint 1):

- `PRODUCT_WRITE_BACKEND=database` (enforced at startup)
- `HEALTH_CHECK_TOKEN` set — `/api/health/perf` and `/api/metrics` require `X-Health-Token` header (nginx blocks them at the edge)
- Security headers via nginx + FastAPI middleware
- Rate limiting: nginx burst zones + app-level slowapi sustained limits
- Optional `SENTRY_DSN` for error tracking

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
- [ ] Weekly backup cron + restore drill once
- [ ] Keep research crawlers on the private ETL machine only

