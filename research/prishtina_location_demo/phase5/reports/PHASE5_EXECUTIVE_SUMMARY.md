# Phase5 executive summary

Implemented actual local resolver/parser/reference changes on an isolated branch,
not a research-only replacement resolver. All seven owner equivalences, confirmed
subareas and one Sllovenia Sport identity with two parents are represented. Source
city provenance and context-sensitive school/road/landmark matching are corrected.
Historical IDs, original source wording and explicit pricing compatibility remain.

Validated all **63,686 frozen** and **65,245 current** normalized
observations. The exact 11,730-unit baseline and annual report were reproduced. Alias
consolidation relabels 0 fixed units; actual dedup recomputation changes 0 groups.
New property-location assignments remain source assertions requiring review.

| Outcome | All observations | Latest source listings | Frozen pricing units |
|---|---:|---:|---:|
| School specificity prevented, previous resolver | 2,220 | 1,059 | 453 |
| Stored school assignment would be reduced | 2,220 | 1,059 | 453 |
| Previously missed Kalabria matches | 259 | 82 | 37 |
| Ahmet/letter-corridor false matches prevented | 130 | 44 | 23 |
| Substring-only false location hits prevented | 270 | 179 | 59 |
| Rruga A/B/C area matches retained | 6,431 | 2,790 | 1,030 |
| Explicit proximity/developer membership overclaims prevented | 640 | 337 | 119 |
| Sllovenia Sport with both parent relationships | 510 | 126 | 64 |
| Previously missing source-text matches | 3,096 | 977 | 536 |
| Source city differs from old parsed city | 816 | 550 | 410 |
| Non-equivalent old/new market disagreements | 2,250 | 1,049 | 396 |
| Potential recall regressions requiring review | 257 | 219 | 113 |
| Old/new resolver neighborhood slug differs | 6,049 | 2,526 | 1,148 |

Full suite: 949 passed, 38 skipped. No
historical DB records changed; no migrations, public cache writes, deployments or
remote pushes. Independent geographic corrections applied:0. Remaining ambiguity
and potential regressions are explicitly listed rather than silently accepted.
See IMPLEMENTATION_READINESS.md for controlled-testing limits and ROLLBACK_GUIDE.md
for the focused local implementation record.
