# Local research migration checkpoint — 2026-09-29

Status: safety fence established; database authority gate pending.

- Fetched all remote refs and tags. `master` and `origin/master` both resolve
  to `4ee092482cf40bf1b4f91f9bf9e6ecbbfc3ec5bb`.
- Created and pushed annotated rollback tag
  `pre-local-research-migration-20260929` at that commit.
- Created and pushed branch `infra/local-research-runner`.
- Tracked working tree was clean. The sole untracked file was the supplied
  factual audit, `RESEARCH_AUTOMATION_MIGRATION_AUDIT_2026-09-29.md`;
  it is preserved with this checkpoint rather than discarded or added to master.
- Disabled GitHub workflows 366000608 (GroundTruth weekly control) and
  366000610 (Deploy verified weekly release) pending replacement commissioning.
  Disabling the latter temporarily disables its manual trigger as well as cron.
- CI, Production image, and Azure beta deploy remain active.
- No live Azure resource, credential, workflow file, or Bicep definition changed.
  The audit records live source `08d393c`, revision `ca-metrik-api--0000026`;
  those are audit observations, not a new live verification.

Implementation must not continue until the existing research corpus is
identified, dumped outside Git, restored into disposable PostGIS, and compared.
No empty database initialization is permitted as a substitute for recovery.
Final completion additionally requires commissioning, failure drills, and two
successful scheduled weekly executions. Historical research definitions must
remain until that evidence exists.
