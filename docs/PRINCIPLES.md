# GroundTruth Operating Principles

From parser v1.3.0 onward, progress is measured in **validated claims**, not features shipped.

---

## Unit of progress

| Before (engineering) | Now (methodology) |
|----------------------|-------------------|
| Parser fixes | Validated claim |
| Migrations | Reproducible analysis |
| Tests passing | Published insight |
| Tables / APIs | Historical dataset growth |

**Rule: one documented market insight per week.** Every Friday should answer a new question in `RESEARCH.md` and, if publishable, register it in `data/claims/registry.csv`.

---

## Infrastructure gate

> **No new infrastructure unless it enables a concrete research question or user-facing capability within the next two weeks.**

When tempted to build X, ask: *What question does X let me answer?*

If there is no immediate answer, defer it.

Examples:

| Build | Answer it enables | Verdict |
|-------|-------------------|---------|
| Bootstrap CI helper | "Is Ulpiana vs Dardania rent difference significant?" | Build now |
| `derived_metrics` table | Unknown — definitions still changing | Defer |
| MerrJep spider | Cross-source comparison report | Defer until first report published |
| Public dashboard | No report exists yet | Defer |

---

## Scope discipline

- **Geography:** Prishtina until first report is published and cited.
- **Sources:** Gjirafa only until golden verification + Phase E draft exist.
- **Metrics:** Do not persist derived metrics until notebook definitions stabilize.
- **Charts:** Every figure shows **sample size (n)**. Never present n=12 and n=1,200 with equal visual weight.

---

## Artifact hierarchy

```
Crawler → Parser → Validated Dataset → Research Ledger → Claim Registry → Products
```

The **claim registry is the API for truth**. Code is implementation detail.

1. `data/claims/registry.csv` — immutable publishable statements (supersede, never edit)
2. `RESEARCH.md` — research ledger including negative findings
3. `docs/METHODOLOGY.md` — methodology version `1.0.0` (independent from parser)
4. `reports/generated/` — audit artifacts, benchmarks, notebooks
5. Code — subservient to the above

After a year, the ledger and claim registry are more valuable than the codebase.

---

## Publication standard

A claim is **Verified** only when:

1. Recorded in the claim registry with query/notebook reference
2. Sample size and uncertainty documented (IQR, bootstrap CI, or equivalent)
3. Limitations stated explicitly
4. Reproducible from a pinned ETL snapshot + parser version

A claim is **Draft** until manual golden review (where applicable) is complete.

---

## What we optimize for (18–24 months)

- Primary historical rental dataset for Prishtina
- Reproducible methodology defensible under scrutiny
- Longitudinal observations (`listing_observations`) for survival and price-change analysis
- Portfolio evidence for data engineering / analytics roles

The moat is **time + methodology**, not scraper cleverness.
