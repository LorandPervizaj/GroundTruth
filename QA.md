# Metrik / GroundTruth QA

## Current Release

| Item | Value |
| --- | --- |
| Git HEAD | `9ac694d` |
| Working tree | Uncommitted remediation + dual-gate QA changes exercised below |
| Date | 2026-09-08 |
| Image | `metrik-api:latest` — Docker reported ~932 MB virtual; `inspect` size **206 MB** (~196–206 MB content) |
| Artifact corpus | lookup cache built `2026-09-07T13:08:22Z`, corpus_revision `2026-09-07T13:02:30Z`, entries=210 |

## Current Environment

| Item | Value |
| --- | --- |
| OS | Windows 10/11 (`win32 10.0.26200`) |
| Docker | 29.2.1 (Desktop) / Compose v5.1.0 |
| Python / uv | 3.13.13 / 0.11.19 |
| Stack project | `metrikqa` via `docker-compose.prod.yml` + gitignored `.env.production` |
| Edge | nginx `0.0.0.0:80/443` → app (internal `:8000`) → PostGIS 16 |
| TLS under test | Self-signed under `deploy/nginx/certs/`; `PUBLIC_BASE_URL=https://localhost` |
| Feature flags | `ALERTS_SIGNUP_ENABLED=false`, `VALUATION_PUBLIC_ENABLED=false`, `RUN_MIGRATIONS_ON_START=true`, `REQUIRE_SENTRY_DSN=false` |

## Overall Status

**Local/Compose Gate A (Limited Public Beta): GO** — invite-only on a production-shaped stack remains valid.

**Azure beta deployment: LIVE (read journeys)** on ACA default HTTPS hostname, but **Azure Beta Gate = NO-GO** for durable controlled beta until Azure Database for PostgreSQL Flexible Server (or equivalent durable DB + restore) is available on the subscription.

**Gate B (Full Public Launch): NO-GO**

---

# Azure Beta Deployment

## Azure Architecture

```text
Internet
  → Azure Container Apps ingress (managed TLS on *.azurecontainerapps.io)
  → ca-metrik-api (metrik-api + postgres:16 sidecar)
  → artifacts baked into immutable image (Option A)
```

Preferred Flexible Server path is in `infra/azure/main.bicep` but **blocked by Azure for Students region/SKU policy**. Fallback: `infra/azure/main-sidecar-pg.bicep` (EmptyDir Postgres — ephemeral).

nginx is **not** used on Azure (kept for Compose/VPS).

## Azure Resources

| Resource | Name | Notes |
| --- | --- | --- |
| Resource group | `rg-metrik-beta-eus2` | eastus2 |
| ACR | `acrmetrikbetalgy2mu` | Basic, private pulls via MI |
| Log Analytics | `log-metrik-beta` | Container logs |
| CAE | `cae-metrik-beta` | Consumption |
| Container App | `ca-metrik-api` | 0.5 vCPU / 1Gi + postgres sidecar 0.25/0.5Gi |
| Storage | `stmetrikbetalgy2mu` | Present; PG uses EmptyDir (Azure Files chmod incompatible with postgres) |
| Flexible Server | — | **BLOCKED** by subscription policy |

## Subscription / Region

| Item | Value |
| --- | --- |
| Subscription | Azure for Students (name only; ID omitted) |
| Region | **eastus2** (`westeurope` disallowed by policy) |
| App URL | `https://ca-metrik-api.livelydune-1ec3eb9a.eastus2.azurecontainerapps.io` |

## Container Registry

| Check | Result | Evidence |
| --- | --- | --- |
| ACR created | **PASS** | `acrmetrikbetalgy2mu.azurecr.io` |
| Image push (immutable tag) | **PASS** | `metrik-api:9ac694d-azure1` digest `sha256:a0b5089f…` |
| Research deps absent | **PASS** | build-push assert scrapy/playwright missing |

## Container App

| Check | Result | Evidence |
| --- | --- | --- |
| Startup | **PASS** | migrations + artifact verify + uvicorn |
| Image identity | **PASS** | SHA tag + digest (not latest-only) |
| TRUSTED_HOSTS | **PASS** | `*` required for ACA probe Host headers behind managed ingress |

## PostgreSQL

| Check | Result | Evidence |
| --- | --- | --- |
| Flexible Server | **BLOCKED** | All probed regions: restricted/empty SKUs for this subscription |
| Sidecar Postgres | **PASS** (ephemeral) | EmptyDir; private to replica via `127.0.0.1` |
| Migrations | **PASS** | alembic upgrade on start with retry |
| Durable DR | **FAIL** | EmptyDir lost on recycle; no PITR |

## Domain / TLS

| Check | Result | Evidence |
| --- | --- | --- |
| Default ACA HTTPS | **PASS** | Managed cert on `*.azurecontainerapps.io` |
| Custom domain | **BLOCKED** | No real domain configured |
| HTTP→HTTPS | **PASS** | ACA `allowInsecure=false` |

## Deployment Pipeline

| Check | Result | Evidence |
| --- | --- | --- |
| Bicep IaC | **PASS** | `infra/azure/*` |
| Manual deploy scripts | **PASS** | `scripts/azure/deploy.ps1`, `build-push.ps1` |
| GitHub Actions ACR→ACA | **PASS** (added, not yet run in GH) | `.github/workflows/azure-beta-deploy.yml` |

## Secrets Strategy

| Check | Result | Evidence |
| --- | --- | --- |
| ACA secrets for DB URL / health token | **PASS** | Not in Git; local `.tmp/azure-beta/secrets.env` gitignored |
| No secrets printed in QA | **PASS** | |

## Artifact Strategy

| Check | Result | Evidence |
| --- | --- | --- |
| Option A bake into image | **PASS** | Dockerfile COPY lookup_cache; verify-artifacts before push |
| Startup verification | **PASS** | `artifact_verification_ok entries=210` in ACA logs |

## Health / Readiness

| Check | Result | Evidence |
| --- | --- | --- |
| `/api/health` 200 | **PASS** | Live + ACA probes |
| `/api/ready` 200 | **PASS** | `{"ok":true}` |
| Corrupt artifact reject | **NOT TESTED** on Azure this pass | Prior local drill PASS; baked image would require new bad image deploy |

## Backup / Restore

| Check | Result | Evidence |
| --- | --- | --- |
| Flexible Server automated backup | **BLOCKED** | Service unavailable |
| Sidecar EmptyDir backup | **FAIL** | Not durable |
| Disposable local drill | **PASS** | Prior `backup_restore_drill.py` |

## Security

| Check | Result | Evidence |
| --- | --- | --- |
| Postgres not public | **PASS** | localhost sidecar only |
| Rate limits | **PASS** | alerts → 429 after prior bursts |
| Alerts disabled | **PASS** | 503 unavailable |
| Wrong Content-Type | **PASS** | 415 |
| Alerts/valuation off | **PASS** | flags false |

## Smoke Test

| Check | Result | Evidence |
| --- | --- | --- |
| `scripts/azure/smoke.ps1` | **PASS** | `AZURE_SMOKE_OK` against live ACA URL |

## Rollback

| Check | Result | Evidence |
| --- | --- | --- |
| Documented | **PASS** | `docs/AZURE_BETA.md` + prior image tags in ACR |
| Tested revision rollback | **NOT TESTED** | Multiple revisions created; deactivate used operationally |

## Cost

| Item | Estimate |
| --- | --- |
| ACR Basic + CAE + 0.75 vCPU always-on + storage + logs | ~€25–45 / month (order of magnitude) |
| Flexible Server B1ms | N/A (blocked) |
| Orphan `rg-metrik-beta` (westeurope empty) | delete initiated |

## Beta Gate

**NO-GO** (Azure durable beta)

Reason: application is reachable and core journeys work, but durable managed Postgres + restore is **BLOCKED** on this subscription; EmptyDir sidecar is explicitly **not** acceptable DR for a real-user beta that accepts writes.

---

## Azure validation matrix

| Area | Expected | Actual | Result |
| --- | --- | --- | --- |
| ACR image | Pullable | `metrik-api:9ac694d-azure1` in ACR | **PASS** |
| Container startup | Healthy | uvicorn + artifacts verified | **PASS** |
| Postgres | Private/healthy | Sidecar localhost; Flexible Server blocked | **PASS*** / **BLOCKED** |
| Migrations | Applied | alembic on start | **PASS** |
| Health | 200 | `/api/health` 200 | **PASS** |
| Readiness | 200 | `/api/ready` `{"ok":true}` | **PASS** |
| Corrupt artifact | Reject/not-ready | Not re-run on Azure | **NOT TESTED** |
| HTTPS | Valid | ACA managed TLS | **PASS** |
| Custom domain | Reachable | None | **BLOCKED** |
| Search | Works | 200 | **PASS** |
| Markets | Works | 200 | **PASS** |
| Compare | Works | 200 | **PASS** |
| Rent yield | Works | 200 | **PASS** |
| Alerts | Correctly disabled | 503/429 | **PASS** |
| Rate limit | Enforced | 429 | **PASS** |
| Public writes | Protected | 415 CT | **PASS** |
| Backup | Configured | EmptyDir only | **FAIL** |
| Restore | Tested | Not on Azure | **BLOCKED** |
| Logs | Accessible | `az containerapp logs` | **PASS** |
| Sentry | Configured | unset (log-only) | **FAIL** (accepted for lab) |
| Rollback | Tested/documented | Documented; not fully tested | **PARTIAL** |

\*Private sidecar healthy, but not the preferred managed Flexible Server.

## Beta Requirements Completed

- Production image in private ACR with immutable tag/digest
- ACA ingress TLS on default hostname
- Artifacts baked + verified at startup
- Core read journeys + honest alerts/valuation
- IaC + operator docs + smoke script
- Rate limit / write CT protections observed live

## Full Public Launch Requirements Remaining

- Azure Database for PostgreSQL Flexible Server (or equivalent durable DB) + proven restore
- Custom domain + managed cert validation
- Mandatory Sentry (or equivalent) with captured test exception
- Runtime vs migration DB role separation
- Automated CD run in GitHub (workflow present, not yet proven in Actions)
- Invite IP allowlist or other access gate if URL is shared widely
- Replace `TRUSTED_HOSTS=*` with tighter host policy once probe Host behavior is pinned
- Broader abuse testing on public edge

---

## Prior-issue verification (this pass)

| Issue | Classification | Evidence |
| --- | --- | --- |
| `/api/ready` 200/503 semantics | **FIXED** | Live 200 when ready; unit + break-the-fix |
| Alerts honesty (no fake email signup) | **FIXED** | Default off; API 503/429; UI `alert-unavailable` |
| Artifact hash verify at startup/readiness | **FIXED** | Prior corruption drill; hash unit test |
| Production rate-limit cannot disable | **FIXED** | Startup guard + break-the-fix |
| Public write Content-Type / limits / dedupe | **FIXED** | Code + prior live 415/429 evidence |
| `/api/rent-yield` EROFS crash on `:ro` | **FIXED** | Live 200 + 15 rows; `rent_yield_cache_write_skipped` |
| Slim image (no scrapy/playwright) | **FIXED** | Prior container probe; research extra optional |
| Valuation public disabled honesty | **FIXED** | API 503; i18n `valuate_public_disabled*` |
| Runtime vs migration DB roles | **PARTIALLY FIXED** | Script + migrate profile exist; compose still defaults `RUN_MIGRATIONS_ON_START=true` |
| Sentry mandatory | **PARTIALLY FIXED** | Optional warn; `REQUIRE_SENTRY_DSN` supported; not enforced in QA env |
| Real public TLS/DNS | **NOT VERIFIED** | Localhost self-signed only |
| Host-side backup/restore | **PARTIALLY FIXED** | Disposable drill PASS; real VPS host **NOT VERIFIED** |
| CD / immutable deploy | **PARTIALLY FIXED** | `.github/workflows/prod-image.yml` build+Trivy added; no auto-deploy to VPS yet |

---

## Gate A — Limited Public Beta

### Deployment

| Requirement | Status | Evidence |
| --- | --- | --- |
| `docker compose … config` | **PASS** | Validated against `.env.production` |
| Production image build | **PASS** | `metrik-api:latest` present and running |
| `up -d` / healthy containers | **PASS** | app healthy (~1h+), postgres healthy, nginx up |
| App non-root | **PASS** | `User=metrik` (uid 100) |
| Postgres not host-published | **PASS** | `docker port metrikqa-postgres-1` → empty / NONE |
| App not host-published | **PASS** | app ports NONE; only nginx 80/443 |
| No restart loops / stack traces | **PASS** | Stable healthy status; prior startup logs clean after rent-yield fix |

### TLS/DNS

| Requirement | Status | Evidence |
| --- | --- | --- |
| Real public DNS | **BLOCKED — REAL DOMAIN NOT AVAILABLE** | `PUBLIC_BASE_URL=https://localhost` |
| Public CA certificate | **BLOCKED** | Self-signed only |
| HTTPS locally | **PASS** (lab) | `https://localhost` smoke OK with verify=False |
| HTTP→HTTPS redirect | **PASS** (lab) | `http://localhost/api/ready` → **301** `https://localhost/api/ready` |
| Security headers | **PASS** (lab) | HSTS, XCTO, XFO, CSP, Referrer-Policy present |
| No direct backend exposure | **PASS** | Postgres/app unpublished |

**Remaining for public hostname:** provision DNS A/AAAA, mount real certs (or LB TLS), re-run external checks, set real `PUBLIC_BASE_URL`.

### Health/Readiness

| Requirement | Status | Evidence |
| --- | --- | --- |
| Ready → HTTP 200 | **PASS** | Live `{"ok":true}` |
| Not ready → HTTP 503 | **PASS** | Unit tests + prior corruption → not ready / nginx 502 |
| Fail closed on bad artifacts | **PASS** | Prior drill: corrupt hash → verify fail → restore → ready |
| HEALTHCHECK uses `/api/ready` | **PASS** | Compose + Dockerfile HEALTHCHECK |

### Artifact Integrity

| Requirement | Status | Evidence |
| --- | --- | --- |
| Manifests + hashes required | **PASS** | Startup fail-closed; `verify-artifacts` path |
| Corruption not silently served | **PASS** | Prior disposable corruption drill |
| Related revision agreement | **PASS** | Release verify tests + loaded corpus_revision |

### Database

| Requirement | Status | Evidence |
| --- | --- | --- |
| Private DB | **PASS** | Not published |
| Migrations apply | **PASS** | Head includes `g1h2i3j4k5l6` |
| Runtime least privilege | **TRANSITIONAL — ACCEPTABLE FOR BETA / MUST CLOSE BEFORE FULL PUBLIC LAUNCH** | `RUN_MIGRATIONS_ON_START=true`; migrate profile + `create_runtime_role.sql` ready but not enforced in QA env |

### Backup/Restore

| Requirement | Status | Evidence |
| --- | --- | --- |
| Disposable backup/restore drill | **PASS** | `uv run python scripts/backup_restore_drill.py` → recovered count=1; corrupt gzip rejected (2026-09-08) |
| Real deployment-host DR | **BLOCKED** | No production VPS host in this environment |

**Beta risk acceptance:** limited beta may proceed with documented disposable-drill proof + scheduled host backup once a VPS exists; unrestricted launch requires host restore proof.

### API

| Requirement | Status | Evidence |
| --- | --- | --- |
| Core read APIs | **PASS** | ready/meta/search/markets/compare/lookup/rent-yield/annual |
| Rent-yield on `:ro` mount | **PASS** | HTTP 200, 15 rows |
| Valuation disabled | **PASS** | POST `/api/valuate` → **503** unavailable |
| Alerts disabled / rate-limited | **PASS** | POST `/api/alerts` → **429** (residual) or **503** unavailable |

### Frontend

| Requirement | Status | Evidence |
| --- | --- | --- |
| Primary pages load | **PASS** | `/`, statistics, compare, rent-yield, valuate, alerts, contact, market detail |
| Alerts UI honesty | **PASS** | `alert-unavailable` present; signup closed |
| Valuation UI honesty | **PASS** | `valuate_public_disabled` / hint keys in i18n + app.js |
| Search silent-fail guard | **PASS** | Prior unit coverage; page loads 200 |

### Security

| Requirement | Status | Evidence |
| --- | --- | --- |
| Rate limits enforced | **PASS** | Alerts burst historically 503×3 then 429; live 429 |
| Docs disabled at edge | **PASS** | Prior QA (docs 404) |
| Ops routes not public | **PASS** | Prior QA nginx 404 for ops |
| Secrets not in repo | **PASS** | `.env.production` gitignored; example only |

### Public Writes

| Endpoint | Public for beta? | Data | Storage | Spam controls | Failure mode |
| --- | --- | --- | --- | --- | --- |
| `/api/alerts` | **No** (disabled) | Would be email + neighborhood | DB/jsonl when enabled | Rate limit; currently 503 | Unavailable / 429 |
| `/api/contact` | **Yes (controlled)** | Contact message fields | `product_submissions` / jsonl | JSON CT, body limit, rate limit, dedupe | 503 on persist fail |
| `/api/feedback` | **Yes (controlled)** | Feedback payload | same | same | same |
| `/api/public-report` | **Yes (controlled)** | Report payload | same | same | same |
| `/api/listing-submissions` | **Yes (controlled)** | Listing submission | same | same | same |
| `/api/events` | **Yes (controlled)** | Anonymous product events | same | rate limit | 503 on fail |

Minimum beta protections present: validation, Content-Type **415**, body-size limits, rate limiting, duplicate control, safe 503 on durable failure.

### Alerts

| Requirement | Status | Evidence |
| --- | --- | --- |
| No fake “email enabled” | **PASS** | Feature off; API unavailable; UI notice |
| API/FE agreement | **PASS** | Smoke + HTML marker |

### Valuation

| Requirement | Status | Evidence |
| --- | --- | --- |
| Kept disabled | **PASS** | Flag false; API 503 |
| No misleading enablement | **PASS** | Explicit unavailable copy |

### Observability

| Requirement | Status | Evidence |
| --- | --- | --- |
| Structured/JSON logs | **PASS** | `LOG_FORMAT=json` in prod compose |
| Startup / readiness / artifact failures logged | **PASS** | Prior logs + fail-closed |
| Sentry DSN set | **FAIL** (optional for beta) | Unset; `REQUIRE_SENTRY_DSN=false` |
| Logs alone for beta | **PASS** (accepted risk) | Operator can use `docker compose logs` |

### CI

| Requirement | Status | Evidence |
| --- | --- | --- |
| Full pytest | **PASS** | `uv run pytest -q` → **475 passed, 32 skipped** |
| Production image buildable | **PASS** | Image running |
| Prod image CI workflow | **PASS** (added) | `.github/workflows/prod-image.yml` build + Trivy CRITICAL/HIGH |

### Rollback

| Requirement | Status | Evidence |
| --- | --- | --- |
| Documented image/artifact rollback | **PASS** | `docs/DEPLOYMENT.md` rollback steps updated |
| Automated rollback system | **NOT APPLICABLE** (beta) | Manual acceptable |
| Migration risk understood | **PASS** | Prefer forward-fix; elevated migrate profile documented |

### End-to-End Smoke

| Requirement | Status | Evidence |
| --- | --- | --- |
| Journey script | **PASS** | `uv run python scripts/qa_gate_a_smoke.py` → `GATE_A_SMOKE_OK` |
| No 5xx on primary reads | **PASS** | All GETs 200 |
| Honest write/disabled features | **PASS** | alerts 429/503; valuate 503 |

---

## Beta Gate Decision

**GO**

Conditions for inviting real users:

1. Keep access invite-only / controlled until a real domain has TLS validation (Gate B).
2. Keep `ALERTS_SIGNUP_ENABLED=false` and `VALUATION_PUBLIC_ENABLED=false`.
3. Deploy only an image that includes the rent-yield read-only fix.
4. Ship hashed release artifacts only (`release build-artifacts` / `verify-artifacts`).
5. Accept log-only observability **or** set `SENTRY_DSN` before widening the invite list.
6. Schedule host backups as soon as a durable VPS exists; re-run restore drill there before claiming DR.

---

## Gate B — Full Public Launch

### Deployment Automation

| Requirement | Status | Evidence |
| --- | --- | --- |
| Minimal CD: build → scan | **PASS** (path added) | `prod-image.yml` |
| Deploy + health + release confirm | **FAIL** | No automated VPS deploy/rollback digest pipeline yet |
| Immutable tag/digest deploy | **FAIL** | Manual `latest` in QA |

### Runtime DB Privileges

| Requirement | Status | Evidence |
| --- | --- | --- |
| Separate migrate vs runtime roles | **FAIL** | Still transitional (`RUN_MIGRATIONS_ON_START=true`) |
| Migrate profile available | **PASS** | `docker compose --profile migrate run --rm migrate` |
| Runtime role SQL | **PASS** (artifact) | `scripts/sql/create_runtime_role.sql` — not applied as live prod config |

### Sentry / Observability

| Requirement | Status | Evidence |
| --- | --- | --- |
| `REQUIRE_SENTRY_DSN=true` in prod | **FAIL** | Currently false |
| Controlled exception captured | **FAIL** | Not proven |
| Operator-visible exceptions | **FAIL** for launch bar | Logs only |

### Security

| Requirement | Status | Evidence |
| --- | --- | --- |
| Edge hardening (lab) | **PASS** | Headers, redirects, unpublished DB |
| Image scan in CI | **PASS** (workflow added) | Trivy CRITICAL/HIGH gate |
| Real public config review | **BLOCKED** | No real domain deploy |
| Dependency/image scan on live host | **NOT VERIFIED** | |

### DR

| Requirement | Status | Evidence |
| --- | --- | --- |
| Disposable restore proven | **PASS** | Python drill |
| Host schedule + off-box storage + restore | **FAIL** | Host not available |
| Retention documented | **PASS** | Backup scripts + DEPLOYMENT |

### Release Integrity

| Requirement | Status | Evidence |
| --- | --- | --- |
| Hash + related revision checks | **PASS** | Code + tests |
| Mismatched disposable release rejection | **PASS** | Unit/release verify coverage |
| Live mixed-release adversarial on host | **NOT VERIFIED** this pass | Prior corruption drill covers fail-closed |

### Abuse Testing

| Requirement | Status | Evidence |
| --- | --- | --- |
| Controlled write burst | **PASS** | Alerts rate-limit evidence |
| Broader public-edge amplification suite | **FAIL** / incomplete | Not repeated as full launch suite this pass |

### User Trust Review

| Requirement | Status | Evidence |
| --- | --- | --- |
| Alerts/valuation honesty | **PASS** | Disabled + clear messaging |
| Broader copy audit (freshness claims, forms) | **PASS** for critical paths | No false notification/valuation promises found |

### Regression

| Requirement | Status | Evidence |
| --- | --- | --- |
| Full pytest | **PASS** | 475 / 32 skip |
| Break-the-fix re-run | **PASS** | See below |

---

## Public Launch Gate Decision

**NO-GO**

Blockers:

1. Real DNS/TLS not validated  
2. Runtime DB privilege separation not enforced  
3. Sentry (or equivalent) not mandatory and not proven  
4. Host-side backup/restore not proven  
5. Deploy automation incomplete (build/scan only)  

---

## Bugs Found

| ID | Severity | Description | Status |
| --- | --- | --- | --- |
| QA-P0-RENTYIELD | P0 | `/api/rent-yield` wrote cache under `:ro` → OSError/500 | **FIXED** (prior pass; reconfirmed live 200) |
| QA-OPS-PGVOL | P1 ops | Changing Postgres password against existing volume fails auth | **Documented** (fresh volume / known hazard) |
| QA-ART-HASH | P1 | Pre-hash manifests fail closed (correct) until rebuild stamps hashes | **Operational requirement**, not a code bug |

No new P0 discovered in this dual-gate pass.

## Fixes Applied

This dual-gate pass (implementation):

- `docker-compose.prod.yml`: optional `migrate` profile service  
- `.github/workflows/prod-image.yml`: build + research-absent check + Trivy  
- `scripts/qa_gate_a_smoke.py`: accept alerts **503|429**; assert valuation **503**  
- `docs/DEPLOYMENT.md`: migrate profile + explicit rollback steps  
- `.env.production.example`: clarify Sentry beta vs launch requirement  
- Valuation disabled UX keys (already in `web/static/app.js` / `i18n.js`)  
- Full rewrite of this `QA.md` into Gate A / Gate B structure  

Prior remediation still present: ready 503, alerts gate, artifact integrity, rate-limit guard, rent-yield RO tolerance, write hardening, slim Dockerfile.

## Known Risks

- Self-signed / localhost TLS only  
- App DB user still runs migrations on start  
- No live Sentry  
- 206 MB image still carries pandas/numpy/reportlab (justified for analytics PDF/API; further shrink optional)  
- `chown` layer duplicates ~257 MB in history (Docker layer accounting; not research tooling)  
- Backup proven only on disposable Postgres, not VPS  

## Deferred P2/P3 Items

- Multi-stage Dockerfile to avoid chown layer bloat  
- Automated VPS deploy with digest pin + health gate  
- Broader abuse/load matrix on public edge  
- Enable valuation only after release-validation data path is production-approved  
- Email alerts only after real notification delivery exists  

## Exact Validation Commands

```text
docker compose -p metrikqa -f docker-compose.prod.yml --env-file .env.production ps
docker compose -f docker-compose.prod.yml --env-file .env.production config
uv run python scripts/qa_gate_a_smoke.py
uv run python scripts/backup_restore_drill.py
uv run pytest -q
# Break-the-fix cycles (ready / rate-limit / alerts) — see evidence below
docker image inspect metrik-api:latest --format "{{.Size}}"
```

Results (2026-09-08):

- Stack: app/nginx/postgres up; app healthy; postgres/app ports unpublished  
- Smoke: `GATE_A_SMOKE_OK`  
- Backup drill: `BACKUP_RESTORE_DRILL_PASSED`  
- Pytest: **475 passed, 32 skipped**  
- Image size: **206113418** bytes  

## Break-the-Fix Evidence

| Control | Baseline | Break | Detected? | Restored |
| --- | --- | --- | --- | --- |
| Ready HTTP 503 when not ok | 2 passed | Force `status = 200` | **Yes** — 2 failed (`assert 200 == 503`) | 2 passed |
| Production rate-limit required | 1 passed | Bypass `api_rate_limit_enabled` check | **Yes** — DID NOT RAISE SystemExit | 1 passed |
| Alerts signup disabled | 5 passed | Bypass `alerts_signup_enabled` | **Yes** — 2 failed (got 200 vs 503) | 5 passed |
| Artifact incorrect hash | 1 passed | (unit already asserts rejection) | **Yes** — baseline remains green | n/a |

Prior pass also proved: artifact file corruption → not ready / nginx 502 → restore → ready.

## Release Sign-Off

| Role | Decision | Notes |
| --- | --- | --- |
| Release / QA / Prod owner (this pass) | **OPEN LIMITED PUBLIC BETA** | Controlled users only; no public DNS until TLS proven |
| Full public launch | **HARDEN BEFORE PUBLIC LAUNCH** | Close Gate B blockers listed above |

Signed: dual-gate QA pass, 2026-09-08.
