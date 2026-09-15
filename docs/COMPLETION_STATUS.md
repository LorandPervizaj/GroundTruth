# Metrik / GroundTruth - Completion Status Audit

**Audit Date:** 2026-09-15
**Auditor:** Local completion pass (C:\\Projects\\FartEstate source of truth)
**Repository State:** Local working tree ahead of origin/master (many uncommitted changes)

---

## Baseline QA Results (2026-09-15)

### Test Suite
| Result | Count |
|--------|-------|
| Passed | 498 |
| Skipped | 33 |
| Failed | 0 |
| XFailed | 0 |

Prior documented fail (`tests/test_web_shell.py::test_load_site_footer_has_links`) is **fixed** on disk (`web/partials/site-footer.html` has `data-i18n="insights_subnav_compare"`).

Targeted re-check (2026-09-15): footer + release verify + backup integrity + cross-dedup + deduplicator = **17 passed**.

### Notes
- Full suite green before authority-test additions.
- Exception noise seen: `Exception in thread comparables-warm` after pytest exit (non-failing; track as P2 observability).

---

## Issues Register

### P0 - BLOCKERS

| ID | Area | Problem | Evidence | Impact | Required State | Proposed Solution | Files Affected | Status | Verification evidence |
|----|------|---------|----------|--------|----------------|-------------------|----------------|--------|------------------------|
| P0-01 | Deduplication | Dual dedup systems | architecture + `cross_dedup.py` vs `processing/deduplicator/` | Inconsistent analytics risk | One live path | Live = `analytics/cross_dedup.py`; scorer retained; dead merge/candidate modules removed | `cross_dedup.py`, `processing/deduplicator/`, `architecture.md` | VERIFIED | Dead files deleted; architecture updated; related tests pass |
| P0-02 | Location | Dual location modules | `loader.py` vs `location_resolver.py` | Divergence fear | Clear authority | Complementary layers documented in architecture | gazetteers/*, normalization | VERIFIED | Architecture section + existing `test_location_resolver.py` |
| P0-03 | Validation bounds | Different ingestion vs valuation bands | validation.py vs valuation.py filters | Unclear canonicity | Document + tests | Named `RENT_COMPARABLE_*` / `SALE_COMPARABLE_*`; comments; `tests/test_bound_authority.py` | validation.py, valuation.py, tests | VERIFIED | Bound authority tests pass; architecture documents 3 layers; full suite 479 passed |
| P0-04 | Active corpus | Public analytics must not bypass corpus | corpus_filters + services | Silent bad medians | Invariant tests | `tests/test_corpus_authority.py` asserts public modules reference active corpus | corpus_filters, services/*, analytics/* | VERIFIED | Corpus authority tests pass; public modules list covered; full suite 479 passed |
| P0-05 | Release integrity | Must reject corrupted artifacts | `release.py`, `test_release_verify.py` | Bad release to Metrik | Fail-closed verify | Existing tests: missing manifest, bad hash, missing file, schema mismatch, forbidden fields, revision mismatch | release.py, test_release_verify.py | VERIFIED | Deliberate corruption cases covered; tests pass |
| P0-06 | Pipeline failure safety | Limited automated failure-mode tests | run_weekly.ps1, crawl/weekly.py | Misleading publish | Safe continue/stop + visibility | Documented policy; tests for verify re-raise + parse-health fail-closed + crawl feedback | weekly.py, parse_health.py, test_pipeline_failure_safety.py | VERIFIED | Architecture failure policy + safety tests green; full multi-source chaos still optional hardening |
| P0-07 | Backup/restore | Need proven restore | backup drills | Data loss risk | Proven restore | Lab drill + real QA schema restore into disposable Postgres | scripts/backup_*, reports/generated/REAL_SCHEMA_RESTORE_DRILL.md | VERIFIED | BACKUP_RESTORE_DRILL_PASSED + REAL_SCHEMA_RESTORE_PASSED (24 product_submissions; 21 public tables) |
| P0-08 | Alerts incomplete | Was fake-success risk | alerts.js, config alerts_signup_enabled=false | Misleading UX | Honest Option B or remove | Local watchlist + email panel unavailable + honest i18n copy | web/alerts*, config.py | VERIFIED | JS never claims email success; signup disabled; copy honest |
| P0-09 | Footer i18n test fail | Missing insights_subnav_compare | test_web_shell.py | Red CI | Green | Attribute present in site-footer.html | web/partials/site-footer.html | VERIFIED | Targeted test passes; full suite 0 failed |

### P1 - HIGH (unchanged backlog unless noted)

| ID | Area | Status |
|----|------|--------|
| P1-01 | Frontend states completeness | VERIFIED | Core journeys have loading/empty/error; rent-yield retry added 2026-09-15 |
| P1-02 | Mobile usability | VERIFIED | Live Playwright audit @375/768/1280: no horizontal overflow; mobile loads <1s; report reports/generated/qa_mobile_a11y_perf.json |
| P1-03 | Accessibility | VERIFIED | All audited pages have skip-link + main#main-content; market route now runs shared a11y shell; privacy/terms/404 wrapped |
| P1-04 | Translation completeness | VERIFIED | SQ/EN key sets match (947); usage coverage via tests/test_i18n_parity.py |
| P1-05 | Performance (i18n/Chart.js/API) | PARTIAL | Mobile DOMContentLoaded ~0.4–0.75s on live edge; Chart.js lazy; no Lighthouse CI yet |
| P1-06 | Trust layer / metric explanations | VERIFIED | confidence.js + methodology progressive disclosure on market/statistics/valuate; freshness badges present |
| P1-07 | Security hardening review | VERIFIED | production hardening + public payload contract + redaction + rate-limit tests green |
| P1-08 | Deployment reproducibility | VERIFIED (local) | Docker build `metrik-api:local-qa` succeeded; live metrikqa stack healthy; `/api/ready` 200; home 200; `/api/markets` 200 |
| P1-09 | Rollback drill evidence | VERIFIED | ROLLBACK_TRAFFIC_DRILL_PASSED: swap to local-qa → ready → restore pre-rollback → ready + home 200 |
| P1-10 | Observability gaps (+ comparables-warm thread noise) | VERIFIED | Live /api/health + gated /api/metrics; test_observability_probes; thread noise remains P2 |
| P1-11 | API contract safety | VERIFIED | test_api_contract_hardening + public_payload_contract |
| P1-12 | Cache/worker single-process limit | VERIFIED | Documented single-worker decision; CLI forces workers=1; no Redis |

### P2 / P3

| ID | Area | Status |
|----|------|--------|
| P2-01 | .env example drift | VERIFIED | .env.example + .env.production.example aligned to Settings (freeze pass) |
| P2-03 | Doc consistency | VERIFIED | FINAL audit rewritten to COMPLETE WITH OPERATOR GATE |
| P2-04 | Deferred FB / canonical_properties | DEFERRED | Informal FB tier excluded from public medians; no Metrik serving dependency |
| P2-thread | `comparables-warm` thread exception after tests | DISCOVERED |
| P3-01 | CSS cleanup | DEFERRED |

---

## Workstream Prioritization (live)

**Done / verified:** P0-01 through P0-09 (incl. REAL_SCHEMA_RESTORE_PASSED); P1-01 through P1-04, P1-06 through P1-12; P1-05 accepted without Lighthouse CI.

**Open (accepted residuals only):** P2 env drift / deferred FB / comparables-warm noise; local→origin git sync (process).

---

## Local vs Git

`git status` shows large local delta vs `origin/master` (modified + untracked including COMPLETION_STATUS, release verify tests, azure workflows, portal registry, etc.). Treat **this folder** as source of truth until intentionally pushed.

---

## Next Actions

1. Run disposable backup drill on a Docker host when available (`scripts/backup_restore_drill.ps1`)
2. Begin P1 trust layer + frontend states + security review
3. Staging deploy + rollback drill evidence
4. P0/P1 product gates closed 2026-09-15 evening; residuals accepted (see close-out)

**Last full suite:** 2026-09-15 — 484 passed, 33 skipped, 0 failed.


## P1 progress (2026-09-15)

- Fixed i18n gaps (SQ missing listing/ptype/recent_* keys; both missing error_generic + market_distribution_rent_unit).
- Added `tests/test_i18n_parity.py`.
- Rent-yield recoverable error now offers Retry.
- Documented public serving concurrency (single worker / no Redis) in architecture.md.
- P1 backlog closed in evening close-out (see below). Residual: P1-05 Lighthouse CI optional/accepted.


## Ops evidence (2026-09-15)

- Docker Desktop started; daemon ready.
- `docker build -t metrik-api:local-qa .` succeeded (~937MB).
- Image smoke: `docker run --rm --entrypoint /app/.venv/bin/python metrik-api:local-qa -c "from groundtruth.api.app import app; print('app_import_ok')"`.
- Live compose project `metrikqa`: app+nginx+postgis healthy.
- Verified: `GET /api/ready` → 200 `{"ok":true}`; `GET /` → 200; `GET /api/markets` → 200.
- `scripts/backup_restore_drill.ps1` → **BACKUP_RESTORE_DRILL_PASSED** (seed→backup→drop→restore row count=1; corrupt gzip rejected). Fixed Cleanup missing-container + corrupt-check exit-code handling.
- Timestamp: 2026-09-15 08:18 UTC


## UX/rollback evidence (2026-09-15)

- Playwright live audit: `reports/generated/qa_mobile_a11y_perf.json` — **ok: true**, 33 checks, 0 failures.
- A11y fixes: semantic `<main id="main-content">` on public pages; market route applies `inject_accessibility_shell`; privacy/terms/404 wrapped.
- Rollback drill: tag `pre-rollback` → deploy `local-qa` as latest → `/api/ready` 200 → restore previous image → `/api/ready` 200 + home 200 → **ROLLBACK_TRAFFIC_DRILL_PASSED**.
- Remaining for absolute COMPLETE: prod-volume restore operator gate; optional Lighthouse CI; sync/push local tree to origin.
## Completion close-out (2026-09-15 evening)

### Newly VERIFIED
- **P1-10 Observability:** Live edge `GET /api/health` → 200 `{"status":"ok"}`; `GET /api/metrics` with `X-Health-Token` → 200 counters; unauthenticated metrics → 404 (intentional hide). App image retagged `metrik-api:local-qa` → `latest` and metrikqa app recreated. Tests: `tests/test_observability_probes.py`.
- **P1-11 API contract:** Expanded `tests/test_api_contract_hardening.py` (OpenAPI core paths, markets/lookup/valuate shapes, no secret echo). Existing public payload allowlist still green.
- **P0-07 prod-volume restore (QA):** `REAL_SCHEMA_RESTORE_PASSED` — see `reports/generated/REAL_SCHEMA_RESTORE_DRILL.md`.
- **Chaos/readiness:** `tests/test_chaos_readiness.py` (corrupt artifacts → ready fail-closed; valuate 503 when comparables not ready; HTTP 503 ready).
- **Live release→Metrik path:** `/api/ready` 200, `/api/lookup/neighborhood/ulpiana` 200 (~9KB), `/api/markets` 200, `/api/meta` 200 on https://127.0.0.1.

### Targeted pytest (close-out)
`test_observability_probes` + `test_api_contract_hardening` + `test_chaos_readiness` → **12 passed**.

### Accepted residuals (not blocking limited production)
- **P1-05:** No Lighthouse CI; live mobile DOMContentLoaded timings accepted.
- **P2-01:** `.env` example drift.
- **P2-04:** Deferred Facebook / canonical_properties weight.
- **P2-thread:** `comparables-warm` exception noise after pytest exit.
- **Git:** Large local delta vs origin/master — sync is a separate ops decision (do not force-push).

### Image note
Running stack uses `metrik-api:latest` (== `local-qa` digest `3125e827c3cb`) with health/metrics/trusted_hosts present in-image.

## Freeze verification close-out (2026-09-15)

**Decision:** COMPLETE WITH OPERATOR GATE (see docs/FINAL_COMPLETION_AUDIT.md).

### Reproduced
- Full suite: **498 passed / 33 skipped / 0 failed**
- Live metrikqa: health/ready/markets/meta/lookup/home/valuate/find/compare/statistics 200
- Metrics: 404 unauth / 200 auth
- Mobile/a11y re-audit: 33/33 ok
- Real-schema restore recheck: 21 tables, product_submissions=24
- Clean build: metrik-api:freeze-verify (2d98a5df57c9) deployed as latest
- Warm lifecycle stop present in running image

### Fixed this pass
- P2-01 env example drift
- P2-thread comparables/corpus warm shutdown join

### Operator gates
- Commit/push local working tree (no secrets)
- Remote production promotion

