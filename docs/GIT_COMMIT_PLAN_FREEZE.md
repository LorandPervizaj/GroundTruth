# Git commit plan (freeze) — do not force-push

Branch: master (working tree dirty; **0** local commits ahead of origin).

## Exclude / never commit
- .env, .env.production, any real secrets
- Large generated dumps under .tmp/
- Optional: regenerate vs commit for 
eports/generated/lookup_cache/ (follow existing convention)

## Suggested commit groups
1. **docs/completion** — docs/COMPLETION_STATUS.md, docs/FINAL_COMPLETION_AUDIT.md, restore/mobile evidence reports, docs/GIT_COMMIT_PLAN_FREEZE.md
2. **config/env contract** — .env.example, .env.production.example
3. **API lifecycle** — comparables_warm.py, corpus_warm.py, pp.py, 	ests/test_comparables_warm_lifecycle.py
4. **completion tests** — observability/contract/chaos/release/bound/corpus/i18n/ready/public_payload tests added earlier
5. **product/metrik** — remaining intentional src/, web/, deploy, scripts changes in logical theme commits

## Commands (when authorized)
`
git status
git add -p   # or path-scoped adds per group
git commit -m "..."
# push only with explicit authorization
`
