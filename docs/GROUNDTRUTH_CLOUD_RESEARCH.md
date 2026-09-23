# Private GroundTruth cloud research environment

GroundTruth runs separately from the public Metrik Container App. The target is one scheduled Azure Container Apps Job, one persistent PostgreSQL Flexible Server with PostGIS, and two private Azure Files shares for pipeline state and verified bundles.

## Why this shape

- A once-weekly workload does not justify Kubernetes, Redis, queues, or always-on worker compute.
- Container Apps Jobs provide scheduled and manual execution, bounded retries, logs, and no public ingress.
- PostgreSQL Flexible Server provides persistent storage and point-in-time backup. `EmptyDir` is never used for research data.
- Azure Files survives job replicas and holds the verified watermark/run ledger and release bundles.
- The public application continues to consume only verified artifacts baked into its image.

## Build the private worker

```powershell
$sha = git rev-parse --short HEAD
$login = az acr show -n acrmetrikbetalgy2mu --query loginServer -o tsv
az acr login -n acrmetrikbetalgy2mu
docker build -f Dockerfile.research -t "$login/groundtruth-research:$sha" .
docker push "$login/groundtruth-research:$sha"
```

## Provision

Do not put the database password in a parameter file or shell history. Supply it through a secure deployment mechanism.

```powershell
az deployment group create `
  -g rg-metrik-research-eus2 `
  -f infra/azure/research.bicep `
  -p nameSuffix=<suffix> `
     acrName=acrmetrikbetalgy2mu `
     researchImage=<acr-login>/groundtruth-research:<git-sha> `
     postgresAdminPassword=<secure-value>
```

The Azure for Students subscription previously returned no permitted Flexible Server SKU. If provisioning still fails for policy/SKU reasons, do not substitute ephemeral PostgreSQL. Use a subscription/region that supports a persistent server or pause production enablement.

## Local database migration

1. Keep the local Docker database unchanged as a recovery copy.
2. Create an encrypted custom-format dump with `pg_dump` from the private workstation.
3. Transfer it through a private operator-controlled path; never commit or attach it to a public workflow artifact.
4. Restore to the new research server over TLS.
5. Run `uv run alembic upgrade head` and enable `CREATE EXTENSION postgis` if not already present.
6. Compare table counts, latest scrape timestamps, and representative normalized rows.
7. Run the canonical pipeline manually with automatic publishing disabled.
8. Exercise a point-in-time restore into a disposable server and record the result.
9. Retain the local database until migration plus restore verification succeeds.

The cloud database becomes authoritative only after those checks. Infrastructure creation alone is not proof of recoverability.
