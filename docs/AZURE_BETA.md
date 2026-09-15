# Metrik Azure Limited Public Beta

Operator guide for deploying the **public Metrik** product to Azure Container Apps.

This is additive to the existing Docker Compose / VPS path (`docs/DEPLOYMENT.md`). The private GroundTruth research/ETL host stays separate and only publishes verified release artifacts.

## 1. Architecture

```text
Internet (invitees / IP allowlist)
   ↓
Azure Container Apps ingress (TLS)
   ↓
Metrik FastAPI container (metrik-api:<git-sha>)
   ↓
Azure Database for PostgreSQL Flexible Server (TLS)

Private ETL / research host
   ↓
groundtruth release build-artifacts + verify-artifacts
   ↓
scripts/azure/build-push.ps1  (bakes lookup_cache into image)
   ↓
Azure Container Registry
```

**nginx is not used on Azure.** The app already serves `/static`, HTML pages, security headers, body limits, and SlowAPI rate limits. Compose nginx remains for local/VPS deployments.

**Artifact strategy (Option A):** verified `reports/generated/lookup_cache` is copied into the immutable image at build time. The public app mounts nothing writable for release data. `data/api` (including `annual_report.json`) is already in the image build context.

## 2. Required Azure services

| Service | SKU (beta) | Purpose |
| --- | --- | --- |
| Resource Group | — | `rg-metrik-beta-eus2` (Students: use an allowed region; `westeurope` may be blocked) |
| Container Registry | **Basic** | Private production images |
| Container Apps Environment | Consumption | Hosting |
| Container App | 0.5 vCPU / 1 Gi (+ optional 0.25/0.5Gi Postgres sidecar), min=1 max=1 | Metrik API |
| PostgreSQL Flexible Server | **Burstable B1ms**, 32 GiB, 7-day backup | Preferred app DB (`main.bicep`) |
| Postgres sidecar + EmptyDir | fallback only | `main-sidecar-pg.bicep` when Flexible Server is subscription-blocked (**not durable DR**) |
| Log Analytics | Pay-as-you-go, 30-day | Container logs |

Do **not** provision Kubernetes, Redis, Front Door, or App Gateway for beta.

**Azure for Students note (observed 2026-09-08):** Flexible Server SKUs were empty/restricted across probed regions. Use `main-sidecar-pg.bicep` only as a temporary lab/demo. Do **not** open a durable user beta on EmptyDir Postgres.

### Expected monthly cost (order of magnitude, eastus2)

| Item | Approx. |
| --- | --- |
| PostgreSQL B1ms + 32 GiB (when available) | ~€15–25 |
| Container Apps (0.5–0.75 vCPU always-on) | ~€10–25 |
| ACR Basic | ~€5 |
| Log Analytics (light) | ~€0–5 |
| **Total** | **~€30–55 / month** |

Scaling path: raise Container App replicas only with evidence; move Postgres to Flexible Server / General Purpose; add private networking before unrestricted public launch.

## 3. Required environment variables

Set via Container App secrets / env (see Bicep):

| Name | Notes |
| --- | --- |
| `APP_ENV` | `production` |
| `DATABASE_URL` | secret; `sslmode=require` |
| `PRODUCT_WRITE_BACKEND` | `database` |
| `API_REQUIRE_LOOKUP_CACHE` | `true` |
| `API_RATE_LIMIT_ENABLED` | `true` |
| `ALERTS_SIGNUP_ENABLED` | `false` |
| `VALUATION_PUBLIC_ENABLED` | `false` |
| `HEALTH_CHECK_TOKEN` | secret ≥24 chars |
| `PUBLIC_BASE_URL` | `https://<fqdn>` |
| `FORWARDED_ALLOW_IPS` | ACA private ranges (never `*`) |
| `RUN_MIGRATIONS_ON_START` | `true` for beta bootstrap; prefer false + migrate job later |
| `REQUIRE_SENTRY_DSN` | `false` for beta; `true` for full launch |
| `SENTRY_DSN` | optional for beta |

## 4. Secret configuration

Never commit secrets. Prefer:

```powershell
$env:METRIK_AZURE_POSTGRES_PASSWORD = "<url-safe password, 16+ chars>"
$env:METRIK_AZURE_HEALTH_CHECK_TOKEN = "<random 32+ chars>"
# optional:
$env:METRIK_AZURE_SENTRY_DSN = "https://..."
$env:METRIK_AZURE_INGRESS_IP_ALLOWLIST = "203.0.113.10/32"  # invite-only
```

Then run `scripts/azure/deploy.ps1`.

GitHub Actions should use repository/environment secrets (`AZURE_CREDENTIALS`, `METRIK_AZURE_*`) — never print them.

## 5. ACR image flow

```text
verify-artifacts → docker build (SHA tag) → az acr login → docker push → deploy digest/tag
```

```powershell
.\scripts\azure\build-push.ps1 -AcrLoginServer <acr>.azurecr.io
```

Image identity: `metrik-api:<git-sha>` (not `latest`-only).

## 6. Database provisioning

Created by `infra/azure/main.bicep`:

- Server: `psql-metrik-beta-<suffix>`
- DB: `metrik`
- Admin login: `metrik_admin` (parameter)
- TLS required (`sslmode=require`)
- Backup retention: 7 days (Azure automated)
- Firewall: “Allow Azure services” (`0.0.0.0` rule) — **transitional for beta**

**Credential hazard:** changing the password parameter does not rotate an already-provisioned Flexible Server admin password. Rotate with:

```bash
az postgres flexible-server update -g rg-metrik-beta -n <server> --admin-password <new>
```

Then update the Container App `database-url` secret and create a new revision.

## 7. Migration procedure

Beta default: `RUN_MIGRATIONS_ON_START=true` (controlled transitional DDL).

Preferred hardening:

1. Run one-shot migrate with elevated credentials.
2. Set `RUN_MIGRATIONS_ON_START=false`.
3. Use `scripts/sql/create_runtime_role.sql` for least-privilege runtime.

Compose migrate profile remains valid for VPS:

```bash
docker compose -f docker-compose.prod.yml --profile migrate run --rm migrate
```

## 8. Artifact release procedure

On the private ETL host:

```powershell
uv run groundtruth release build-artifacts
uv run groundtruth release verify-artifacts
.\scripts\azure\build-push.ps1 -AcrLoginServer <acr>.azurecr.io
# then update Container App image to the new SHA tag
```

Corrupt/missing artifacts → startup/readiness fail closed (`/api/ready` → 503; liveness `/api/health` remains 200).

## 9. Domain / TLS

1. Deploy first with the default `*.azurecontainerapps.io` hostname.
2. Add a custom domain on the Container App.
3. Create the DNS record required by Azure (A/CNAME/TXT as instructed).
4. Bind Azure-managed certificate.
5. Set `PUBLIC_BASE_URL=https://your.domain`.

Apex vs subdomain DNS differ — follow Azure’s validation instructions for the actual domain type.

If no domain is available: use the default HTTPS FQDN for invite-only beta and mark custom-domain validation **BLOCKED**.

## 10. Deployment procedure

```powershell
az login
az account set --subscription "<subscription>"
$env:METRIK_AZURE_POSTGRES_PASSWORD = "..."   # URL-safe alphanumeric recommended
$env:METRIK_AZURE_HEALTH_CHECK_TOKEN = "..."
# Preferred when Flexible Server is allowed:
.\scripts\azure\deploy.ps1 -ResourceGroup rg-metrik-beta-eus2 -Location eastus2
# Fallback when Flexible Server is blocked (ephemeral DB — lab only):
az deployment group create -g rg-metrik-beta-eus2 -f infra/azure/main-sidecar-pg.bicep ...
.\scripts\azure\smoke.ps1 -BaseUrl https://<fqdn>
```

Set `TRUSTED_HOSTS=*` on Azure Container Apps (ACA probe Host headers are not always the public FQDN). Tighten later once probe hosts are pinned.

IaC:

- `infra/azure/registry.bicep` — ACR + identity + Log Analytics
- `infra/azure/main.bicep` — Flexible Server + Container App (preferred)
- `infra/azure/main-sidecar-pg.bicep` — Postgres sidecar fallback (ephemeral EmptyDir)
- `infra/azure/parameters.beta.json` — non-secret defaults

## 11. Rollback procedure

1. Note previous working image: `metrik-api:<old-sha>`.
2. `az containerapp update -g rg-metrik-beta -n ca-metrik-api --image <acr>/metrik-api:<old-sha>`
3. Wait until `/api/ready` returns 200.
4. Artifacts roll back with the image (baked in).
5. DB migrations: assume forward-fix unless a specific down migration was validated.

## 12. Backup / restore procedure

- Azure Flexible Server automated backups (retention parameter, default 7 days).
- On-demand: `az postgres flexible-server backup` / portal.
- Restore: point-in-time restore into a **new** disposable server; point a disposable Container App revision at it; verify representative rows + `/api/ready`.
- Do not claim DR until a restore has been exercised.

## 13. Monitoring

- `az containerapp logs show -g rg-metrik-beta -n ca-metrik-api --follow`
- Log Analytics workspace created with the environment
- Optional Sentry via `SENTRY_DSN`
- Probes: liveness `/api/health`, readiness `/api/ready`

## 14. Cost considerations

- Keep `maxReplicas=1` until needed
- B1ms Postgres is enough for small beta traffic
- Delete unused resource groups after experiments
- Set a subscription budget alert in Azure Cost Management

## 15. Common failure modes

| Symptom | Likely cause |
| --- | --- |
| Revision not healthy / ready 503 | Missing/corrupt baked artifacts |
| DB connection errors | Firewall / wrong password / sslmode |
| TrustedHost 400 | `PUBLIC_BASE_URL` host mismatch |
| Rate limits all users together | `FORWARDED_ALLOW_IPS` not trusting ACA proxy |
| Startup refused | Placeholder secrets / rate limit disabled / jsonl writes |
| Image pull errors | ACR pull role / wrong tag |

## Beta access control

Application has no end-user login. For controlled beta:

1. Prefer `METRIK_AZURE_INGRESS_IP_ALLOWLIST` (Container App ingress IP restrictions), and/or
2. Share only the default Container Apps URL with invitees (no public marketing DNS), and/or
3. Bind a custom domain only when ready for a wider audience.

Keep alerts and valuation disabled until separately proven.
