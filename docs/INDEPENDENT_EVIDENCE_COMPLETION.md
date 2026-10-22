# Independent evidence verification — completion

2026-10-22 · **EVIDENCE-LIMITED**, investigation complete.

Reference: [findings, interpretation and reproduction](INDEPENDENT_EVIDENCE_VERIFICATION.md).

| Gate | Decision | Evidence |
|---|---|---|
| E1 — Matching evidence | PASS | Twenty case investigations; 1 true, 2 false, 17 justified unresolved. Descriptions, fields, dates, stored price versions and 100 published media responses examined. Case-specific manual queue supplied. Held-out independent controls unavailable and disclosed. |
| E2 — Source reliability | PASS | All 180 snapshots/1,080 checks revisited. Publisher truth, parser/normalizer errors, semantic unknowns, placeholders and source-internal conflicts separated. Per-field denominators and limited uncertainty supplied. Unchanged policy 1.1.0 scores reproduced; proposed weights neutral and inactive. |
| E3 — Integration safety | PASS | Focused/regression tests below; nine frozen report files replay byte-identically. Read-only DB access, unchanged six table counts/high waters, unchanged 360 pre-existing file hashes. No production, frontend, public-statistics, runtime matching or weight activation changes. |

## Actual QA

- Focused evidence/Harta/matching/source-quality suite: **166 passed in 11.15s**.
- Full suite: **907 passed, 45 skipped, 1 unchanged pre-existing failure**,
  3 warnings, 49.80s.
- Known failure:
  `tests/test_home_trust_snapshot.py::test_legacy_weekly_runners_keep_crawl_exit_code[run_weekly.ps1]`.
  Test expects literal `exit $LASTEXITCODE`; the pre-existing dirty runner uses
  `exit $result`. Both files retain their baseline hashes.
- Ruff check and format: three task Python files pass.
- Executed companion notebook: three code cells, actual captured outputs,
  no DB/network access.
- Reproduction: all **9/9** files in the reviewed/replay directories byte-identical.
  Four historical input digests checked before each replay.

Database checks (before = after):

| Table | Rows | Maximum ID |
|---|---:|---:|
| raw_listings | 65,732 | 76,802 |
| parsed_listings | 63,689 | 312,482 |
| normalized_listings | 63,686 | 312,465 |
| invalid_listings | 9,542 | 30,572 |
| scrape_runs | 208 | 219 |
| etl_metrics | 222 | 286 |

Counts/high waters establish no ingestion/deletion drift; read-only transactions
and the absence of mutation code provide the separate no-write boundary. They are
not advertised as a cryptographic comparison of every database column.

## Deliverables and limitations

All five requested deliverables are present: matching report, source reliability
report, versioned proposed weights, unresolved-only queue and this completion note.
Private detailed files are indexed in the findings document. Full listing URLs,
UUIDs, descriptions, contacts and images are not committed. The durable findings
include only case references, brief analytical observations and aggregate evidence.

No portal-wide precision, false-match rate, real-world publisher-error rate or
physical-location accuracy is established. The three selectively resolved matches
are insufficient to validate a threshold; archived agreement establishes source
representation only. Harta stays provisional 48.815 with weight 1.00 inactive.

## Git and next action

Verified starting commits: `69b7590`, `1e7c807`, `e9b8567`, `bc232dc`, `5b09614`.
Branch: `codex/independent-evidence-verification`, based on `5b09614`.
Only task-owned evidence summarization, replay, tests, documentation and notebook
are staged for the resulting commit. All 360 unrelated modifications/untracked
files were preserved byte-for-byte. No push, deployment or outreach was performed.

Smallest next evidence request: review HCM-002 and HCM-008 in the prepared manual
queue using redacted unit plans or dated cross-posting links. A separate bounded
parser task should address the four explicit unit-price arithmetic defects;
Topia area-basis remediation needs its own valuation-safety review.
