# Market impact: fixed eligibility, actual project calculations

All four scenarios retain **11,730 units** (4,423 sale;6,987 rent;320 other).
A reproduces Phase3 group memberships and annual report payload exactly. B applies
owner-confirmed aliases with duplicate groups fixed. C reruns the actual cross-portal
dedup implementation after canonical grouping: **0 changed duplicate memberships**.
D contains only independently approved geography changes: **0**, so equals A.
Alias consolidation changes labels for **0 fixed pricing units**, not physical
property locations. Geographic recoveries are not mixed into these accepted scenarios.

All four annual report payloads are identical to the frozen baseline. A draft
counter incorrectly treated1,725 null-to-null neighborhood labels as changes;
that audit error is corrected and regression-tested. Actual alias movements:0.

| Market | Before units | Canonical units | Sale €/m² before → after | Monthly rent before → after | Sale/rent comparable pools after |
|---|---:|---:|---|---|---|
| Arbëria | 684 | 684 | 1570 → 1570 | 550 → 550 | 164 / 344 |
| Emshir | 605 | 605 | 1480 → 1480 | 400 → 400 | 259 / 192 |
| Pejton / Lakrishte | 389 | 389 | 2400 → 2400 | 600 → 600 | 73 / 216 |
| Vranjevc / Kodra e Trimave | 29 | 29 | 800 → 800 | 850 → 850 | 2 / 7 |
| 4 Lullat / Dodona | 230 | 230 | 1720 → 1720 | 350 → 350 | 36 / 117 |
| Sofalia | 73 | 73 | 1240 → 1240 | 1500 → 1500 | 12 / 15 |
| Bregu i Diellit | 726 | 726 | 1640 → 1640 | 400 → 400 | 243 / 280 |


Full per-neighborhood/property-type counts, medians, threshold/sample flags,
sale/rent comparable pools and deltas are in neighborhood_market_impact.csv.
Yield outputs use the project's real annual-report yield helper. These are asking
prices, not achieved transaction prices or financial forecasts. Comparable rules
and sample thresholds are unchanged, including valuation's minimum30 comparables.

## Overlapping Sllovenia Sport projection

The proposed source-text resolver identifies **64 distinct frozen pricing
units** for Sllovenia Sport. Each parent report can explicitly include those same
64 units, but their combined total is **64**, not
128. Entity membership is a research projection, not
independent property verification. Legacy production aggregates/cache files are
unchanged; production consumers must adopt non-additive set membership deliberately.
