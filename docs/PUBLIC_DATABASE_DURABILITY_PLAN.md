# Public Metrik database durability review

Review date: 2026-09-23

This is P1 and is intentionally separate from the P0 GroundTruth automation project. No public database migration or deletion is performed by the weekly pipeline.

## Verified live state

- Container App: `ca-metrik-api`, ready revision `ca-metrik-api--0000019` at review time.
- Containers: `metrik-api` and `postgres`.
- PostgreSQL data volume: `pgdata`, `storageType: EmptyDir`.
- `PRODUCT_WRITE_BACKEND=database`.
- `DATABASE_URL` points to the sidecar through a Container App secret.
- `ALERTS_SIGNUP_ENABLED=false`, but other product writes remain enabled.
- No Azure PostgreSQL Flexible Server exists in the subscription at review time.

`EmptyDir` is replica-scoped and is lost when the replica is replaced. The current sidecar is therefore suitable only for a disposable demonstration, not durable production writes.

## Data stored in the public database

The public runtime creates/uses the application schema through Alembic, but its unique writable product responsibility is `product_submissions`, an append-only table with:

- `kind`: submission/event category.
- `payload`: validated JSONB including its timestamp and category-specific fields.
- standard creation/update timestamps.

Current writers include contact submissions, feedback, alerts when enabled, product submissions, and anonymous product events/analytics. Payloads may include user PII such as email addresses and contact text. They require access control, retention policy, backup, and tested restoration.

The public API does not need the private GroundTruth raw/parsed/normalized tables for release-backed lookup and valuation reads. Release artifacts remain the public market-data authority. The public database should contain only runtime schema/product-write data and any minimal migration metadata needed by the application.

## Recommended target

Use a separate Azure Database for PostgreSQL Flexible Server for public runtime writes. Do not share the private GroundTruth research server.

- PostgreSQL 16, TLS required.
- Burstable minimum viable SKU initially, subject to measured load.
- 32 GiB with autogrow.
- 7–14 day point-in-time backup retention.
- Private networking preferred; an Azure-services firewall is only a transitional beta posture.
- Separate migration owner and least-privilege runtime role.
- `RUN_MIGRATIONS_ON_START=false` after one controlled migration job.
- Application connection string held in the Container App secret store or Key Vault reference.

## Migration plan

1. Provision the durable public server without changing the Container App.
2. Create the database, migration owner, and restricted runtime role.
3. Apply Alembic migrations with the migration identity.
4. Quiesce public write endpoints or place them in maintenance mode.
5. Export only `product_submissions` and required sequence state from the sidecar. Treat the dump as sensitive.
6. Import into the durable server and compare row counts by `kind`, min/max timestamps, and sequence value.
7. Update the Container App `database-url` secret and create a candidate revision.
8. Verify readiness plus contact/feedback/event writes against controlled test records.
9. Restore traffic and monitor errors/latency.
10. Retain the old revision only as short-lived rollback evidence; remember that its sidecar remains ephemeral.
11. Exercise point-in-time restore into a disposable server before declaring durability proven.

## Rollback

If candidate verification fails before accepting new writes, reactivate the prior Container App image/revision. If new writes have reached the durable server, do not blindly switch back to the old sidecar because that would fork data. Keep the durable database and correct the application configuration, or reconcile explicitly under an incident procedure.

## Blocking constraint

The current Azure for Students subscription previously returned no allowed Flexible Server SKU. P1 production completion requires either an allowed region/SKU on this subscription or another subscription. An Azure Files-mounted PostgreSQL container is not recommended, and `EmptyDir` must not be treated as a durability substitute.
