# Git and rollback

Original HEAD: `882bac71e243ba73a5203a93bfac6aa028185f43`. Original branch:
`codex/unit-price-historical-impact`. Original checkout remains at that branch with its existing
dirty work preserved. Implementation branch: `codex/prishtina-phase5` in
`C:/Users/lorandp/.codex/worktrees/prishtina-phase5/FartEstate`. The exact focused commit and final status are recorded in
validation/git_final.json; no remote push is authorized.

Preflight source hashes, backups and the preexisting source diff are in this
phase's ignored rollback/ and validation/ folders. The exact implementation and
reverse patches are retained there before commit. No DB rollback is needed:
Phase5 performed no DB writes or historical migrations.

Safest rollback is to leave the isolated checkout unused. If the focused commit
is later applied to another branch, use a normal `git revert <recorded commit>`
after checking that branch's current changes. For uncommitted application, first
run `git apply --check <reverse.patch>` and apply only when the patch matches.
Never reset, clean, stash or destructively restore the original dirty checkout.
Keep old stored reference/version metadata readable; do not rewrite historical
foreign keys as part of code rollback. Managed worktree archival is optional and
must not discard required private audit artifacts.
