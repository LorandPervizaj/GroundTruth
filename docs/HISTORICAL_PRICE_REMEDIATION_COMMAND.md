# Historical price remediation command

The command is bounded to the approved 402 Gjirafa asking-price corrections and
256 unresolved-total quarantines. It does not replay ETL. Authorization and the
original frozen input are pinned by SHA-256; the review manifest is never edited.
Actual execution evidence belongs in [the execution report](UNIT_PRICE_HISTORICAL_EXECUTION.md).

## Preconditions and default dry-run

Use the existing private local `rema` database on loopback port 15432. The command
reads its URL from `C:\MetrikResearch\config\research.env` without printing it.
It rejects other endpoints. The isolated test flag selects only the named restore
database `rema_price_remediation_test_20261022` on the same private server.

```powershell
$remediationArgs = @(
  '--manifest', 'reports/generated/unit_price_historical_impact/reviewed/remediation_review_manifest_private.json',
  '--manifest-sha256', 'b6126ad97dd3c60f95798eba3af132062f0445e1b76ceae1857e17d90c06b4cf',
  '--snapshot', 'reports/generated/unit_price_historical_impact/frozen_inputs_private.json',
  '--audit-dir', 'C:/MetrikResearch/audits/historical-price-20261022',
  '--execution-id', 'live-20261022'
)
.venv/Scripts/python.exe scripts/research/remediate_historical_prices.py @remediationArgs
```

Dry-run is the default and performs no database writes. It checks the frozen row
fingerprints, identities, original-source description hashes, source replay,
parser lineage, validation results and replacement arithmetic. It also checks the
held outlier. The 217 alternate-syntax candidates are disjoint from the targets.

## Apply and private audit

Before apply, complete the full private backup and isolated restore drill.
The backup receipt must record verified restoration, the exact manifest hash,
the expected isolated database and the backup file hash. Apply rechecks that
the backup file still has those exact bytes.

```powershell
.venv/Scripts/python.exe scripts/research/remediate_historical_prices.py @remediationArgs --apply --backup-receipt C:/MetrikResearch/backups/historical-price-20261022/backup_receipt.json
```

Each batch has its own transaction, journal and transaction ID. A short table
writer lock plus target row locks prevent concurrent ETL changes during checks
and updates. Lock acquisition times out rather than proceeding around another
writer. All original target preconditions must pass before the first batch.

Only normalized `sale_price`/`price_per_sqm`, parsed `sale_price`, its sale-price
provenance and a remediation audit marker change. Raw source claims remain intact.
Parser and normalization versions, areas, locations, confidence and dates remain
intact. The new provenance rule identifies the corrected arithmetic or unresolved
total without changing the parser allowlist.

Batch B adds one linked `VALIDATE` rejection containing only `missing_price` per
target. It does not delete or edit older exclusions. Existing linked lineage and
observations remain history rather than being regenerated.

Private journals are fsynced before transaction commit and include exact before
images, owned fields, new values, added rejection rows, execution identity, code
revision and transaction ID. An atomic audit marker in the parsed row lets a
repeat identify its own committed state. A prepared journal can be reconciled
after a lost completion receipt. An incomplete intent that never reached commit
requires inspection rather than blind replay.

After apply, the command compares full target rows and dependent history, then
checks content fingerprints of every public base table outside the exact owned
rows. This includes full raw payloads and HTML. Unexpected changes trigger scoped
rollback. Repeating the same successful apply verifies its post-state and skips
all 658 targets, adding no records.

## Exact rollback

```powershell
.venv/Scripts/python.exe scripts/research/remediate_historical_prices.py @remediationArgs --rollback
```

Rollback runs batches in reverse order, with a separate transaction per inverse
batch. It first requires all owned price values, provenance, audit markers and
added rejection rows to match the recorded post-state. A later edit to an owned
price aborts instead of being overwritten. Later unrelated columns, JSON keys
and rejection rows are preserved. Only this execution's rejection rows and
database audit markers are removed. Earlier history and private audit journals
remain. Sequence counters are not rewound.

Private journals are operational recovery evidence and must be retained with
the backup. They contain sensitive source data and must remain outside Git.
Rollback of a completed inverse batch is a no-op. If the client is interrupted
during rollback commit, inspect its `rollback_prepared` intent and live owned
fields before retrying; the command does not guess an ambiguous inverse outcome.

## Isolated verification

`tests/test_historical_price_remediation.py` has an always-on authorization guard
test and three opt-in integration tests. `GROUNDTRUTH_REMEDIATION_TEST_URL` must
select only the exact isolated restored test database; it must never name `rema`.
The tests exercise fingerprint drift, mid-transaction failure, both complete
batches, repeat-safe application, refusal to overwrite a later owned-price edit,
and rollback preserving later unrelated fields and exclusion evidence. Test-created
changes are then removed on the isolated copy and exact before-images compared.

Public statistics, source weights, Harta collection/matching and deployment are
outside this command.
