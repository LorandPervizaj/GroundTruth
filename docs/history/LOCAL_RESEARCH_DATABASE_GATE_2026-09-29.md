# Local research database gate — 2026-09-29

> **HISTORICAL.** Pre-migration database gate. The migration to the local research runner is complete. Current operation: [LOCAL_RESEARCH_RUNNER.md](../LOCAL_RESEARCH_RUNNER.md); deployment: [DEPLOYMENT.md](../DEPLOYMENT.md).

Status: candidate corpus identified; authority confirmation pending. No research
automation implementation or source-database migration has been performed.

## Safety checkpoint

Checkpoint commit: `5507cc7439e01b0fae6728b114fd39e477122c99` on pushed branch
`infra/local-research-runner`. Annotated rollback tag
`pre-local-research-migration-20260929` (tag object
`f42b4a27fed4868d00002c757669a3ec3bab6516`) peels to
`4ee092482cf40bf1b4f91f9bf9e6ecbbfc3ec5bb`. Both master refs remain there.
GitHub workflows 366000608 and 366000610 are `disabled_manually`; CI,
Production image, and Azure beta deploy remain active. Azure was not changed.

## Database findings

Docker Desktop was deliberately started. Existing restart policies started
research Postgres and three old local QA containers. The QA app, nginx, and
Postgres were stopped immediately after inspection. No crawler was started.
QA Postgres was briefly restarted alone for a read-only inventory, then stopped.

- Container: `groundtruth-postgres`; actual database/owner: `rema`.
- Volume: `fartestate_postgres_data`, Compose logical name `postgres_data`;
  created June 8, 2026, 08:20:42 UTC. No new source volume was initialized.
- Existing port mapping: `127.0.0.1:15432 -> 5432`.
- PostgreSQL: 16.4, Debian build; PostGIS: 3.4.3.
- Database size reported by PostgreSQL: 3785 MB.
- Database Alembic revision: `c8d9e0f1a2b3`.
- Repository `uv run --no-sync alembic heads`: `h2i3j4k5l6m7` (sole head).
- Missing revisions: `g1h2i3j4k5l6` (corpus indexes), `h2i3j4k5l6m7`
  (listing lifecycle states). Neither was applied to the source database.

| Table | Rows | Total relation bytes |
| --- | ---: | ---: |
| raw_listings | 56,973 | 3,302,162,432 |
| parsed_listings | 57,230 | 273,154,048 |
| normalized_listings | 57,227 | 174,178,304 |
| invalid_listings | 8,739 | 24,969,216 |
| listing_observations | 445,846 | 157,499,392 |
| scrape_runs | 155 | 196,608 |
| etl_metrics | 173 | 270,336 |
| data_lineage | 57,227 | 14,409,728 |

Scrape runs span June 8, 08:33:53 UTC through September 21, 10:18:47 UTC;
latest finished run is September 21, 11:37:19 UTC. Normalized records have
scrape timestamps June 8, 08:34:14 through September 21, 11:32:35 UTC;
normalization timestamps June 22, 13:23:43 through September 21, 12:08:59 UTC.

| Source | Raw rows | Latest scrape (UTC) |
| --- | ---: | --- |
| gjirafa | 19,853 | September 21, 08:30:58 |
| merrjep | 27,325 | September 21, 11:32:35 |
| myrealestate | 1,407 | September 15, 19:58:43 |
| pro-rks | 7,003 | September 21, 08:17:04 |
| topia | 1,162 | September 21, 08:11:06 |
| vision | 223 | August 17, 09:40:29 |

This is a substantial historical corpus, but its dates and schema are behind
the requested baseline. Restore success proves recoverability, not that a
newer corpus never existed. Operator confirmation of the September 21 corpus
or identification of a newer recovery source remains necessary at this gate.

## Other recovery sources

Docker containers and volumes were inventoried. The other Metrik volume,
`metrikqa_postgres_data`, contains a 20 MB QA database with zero raw listings.
It is not a replacement corpus. Unrelated application databases were not altered.

Recursive filename searches covered accessible C: paths, including projects
and the user profile beyond the audit's former depth limit. Searches included
`.dump`, `.backup`, `.sql`, `.sql.gz`, `.dump.gz`, and named PostgreSQL/GroundTruth
ZIP candidates. No additional research dump was identified. Three existing QA
drill dumps are 103,358, 103,358, and 107,069 bytes. Other matching files are
application examples, migration SQL, editor backups, or test fixtures.

Some protected directories returned access denied. This is not proof that no
backup exists elsewhere, in differently named archives, on disconnected media,
or in remote storage. Local search paths/errors are retained outside Git in
`C:\MetrikResearch\logs\backup-search-paths.txt` and
`C:\MetrikResearch\logs\backup-search-errors.txt`.

## Recovery drill

Evidence is stored outside Git under `C:\MetrikResearch\logs` and the custom
format dump under `C:\MetrikResearch\backups`. No raw records, SQL schemas,
private logs, credentials, or dumps are published with this report.

Custom-format `pg_dump -Fc` completed with exit code 0. Its Windows copy is:

- `C:\MetrikResearch\backups\groundtruth-premigration-20260929.dump`
- Size: 1,968,201,818 bytes.
- SHA256: `34BD953EA2633E357469234723548B5AD4E18E523BB8EF72AFF3234533DFE0FE`.

Restored from that Windows copy into container
`groundtruth-restore-drill-20260929`, using the existing `postgis/postgis:16-3.4`
image, `--network none`, and no published ports. The first attempt against the
image's pre-initialized database stopped on an existing `tiger` schema. The
successful retry used a new database `research_restore`, created from
`template0`, then `pg_restore --exit-on-error --no-owner`. Restore exited 0.
This initialization was confined to the disposable recovery target.

Verified against the source inventory:

- All 21 public-table counts match, including all eight required tables.
- Alembic revision matches `c8d9e0f1a2b3`.
- PostGIS 3.4.3 is available; full extension version output matches.
- Schema-only dumps with ownership and privileges omitted match.
- Representative record hashes match for the first 100 records ordered by ID
  in each of `raw_listings` and `normalized_listings`. Raw values were not
  printed or added to Git. These sample hashes are not a whole-corpus checksum.

Local evidence: `source-comparison.txt`, `restored-comparison.txt`,
`source-schema.sql`, `restored-schema.sql`, `restore-compare.sql`, and
`database-inventory.txt` under `C:\MetrikResearch\logs`.
The disposable container is stopped and retained for further recovery checks.
The research source Postgres remains running. No crawler or runner is running.

## Blocking decision and next step

Recovery is proven for this candidate. Authority/freshness is not yet confirmed.
The user was asked whether September 21 is the authoritative corpus or a newer
backup should exist. Pending that answer, implementation stops at Phase 1 as
requested for a potentially stale database. Do not migrate the source, install
the runner, enable a schedule, publish a release, or remove research fallback
definitions on the strength of this restore alone.

Once authority is resolved, rehearse the two missing Alembic migrations on the
disposable copy before aligning the source and proceeding to the local runtime.
The full repository quality gate and deployment commissioning were not run:
only checkpoint/evidence documents changed. Completion remains unclaimed.

## Resolution — 2026-09-29

The owner confirmed the September 21 corpus as authoritative. The missed
September 28 crawl will be caught up by the first manual commissioning run.

The two missing migrations were rehearsed on the disposable restore, then
applied to `groundtruth-postgres`; normalized-listing counts were unchanged
(migration SQL retained in `C:\MetrikResearch\logs\migration-to-head.sql`).
`groundtruth research doctor` on the host afterwards reported PASS for
repository, database (PostgreSQL 16.4), PostGIS 3.4.3, Alembic
`h2i3j4k5l6m7`, durable directories, lock, and backup age; watermark and
verified release are in bootstrap state.
