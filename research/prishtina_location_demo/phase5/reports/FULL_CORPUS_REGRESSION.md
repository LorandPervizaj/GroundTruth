# Full-corpus regression

Frozen October23 population: **63,686 observations;27,273 latest source identities;
15,620 eligible latest rows;11,730 deduplicated pricing units**. All reconcile.
The separate read-only current snapshot has **65,245 observations
and 27,828 latest identities**, drift
1,559 observations. Lifecycle observations are not normalized
rows and are never counted as independent geographic observations.

Stored historical assignments (A), prePhase5 resolver/reference replay (B), new
resolver replay (C), and independently approved correction scope (D) are distinct.
Old and new resolvers consume the same original parsed source inputs; stored
normalized assignments are output comparison fields, not new geographic evidence.

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

These flags overlap. Rows and latest identities are different grains; pricing-unit
flags use only frozen canonical primary IDs, not sums of duplicate source rows.
Substring prevention is a software matching correction, not a new property survey.
Possible regressions are deliberately retained in regression_cases.csv; no claim
is made that every old or new location is geographically verified. The unsupported
school count differs from Phase3's1,854 risk flag because this replay compares all
old resolver/stored school assignments, while Phase3 applied a narrower diagnostic.
All Phase4 pending decisions remain pending. Zero independent location changes
have been approved or applied.
Unresolved-for-review population (no accepted market identity or complex
ambiguity): 4,366 observations. This is a review queue, not permission
to recover, relocate or exclude them automatically.
