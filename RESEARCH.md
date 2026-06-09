# GroundTruth Research Ledger

Applied research on Kosovo residential rental markets. **This file is the heart of the project** — more valuable than the code over time.

Publishable findings must also be registered in `data/claims/registry.csv`.

**Operating rule:** one documented insight per week. See `docs/PRINCIPLES.md`.

---

## Ledger entry template

```markdown
## YYYY-MM-DD — [Short question]

### Question
Why does X?

### Hypothesis
(optional) Expected direction and mechanism.

### Dataset
- ETL date:
- Parser version:
- n (unique listings):
- Filters applied:

### Method
- SQL / notebook path / script
- Statistical method (median, bootstrap CI, etc.)

### Result
Concrete numbers. Always include n.

### Limitations
Scope, missing data, no causal inference, etc.

### Status
draft | reviewed | published | superseded | retracted

### Claim type
fact | interpretation | negative | method

### Claim ID
GT-XXX (register via `scripts/manage_claims.py` — never edit published claims; supersede instead)

### Facts vs interpretations
- **Facts:** medians, n, inventory counts, CIs — direct observations
- **Interpretations:** demand, premium, tightening — hypotheses, visually separated in reports
```

---

## 2026-06-08 — Does the parser survive scale?

**Question:** Does parser v1.2.0 maintain quality at 7,245 listings?

**Method:** ETL run on full Gjirafa dataset; `groundtruth etl errors`; coverage KPIs.

**Result:**

| Metric | 277 listings | 7,245 listings |
|--------|--------------|----------------|
| Neighborhood coverage | 98.6% | 88.8% |
| Invalid rate | 2.9% | 12.3% |
| Mean confidence | 0.94 | 0.87 |

**Interpretation:** 277 listings tested correctness; 7,245 tested robustness. The parser did not survive scale. Primary invalid driver: `price_too_low` from comma-thousands parsing (`125,000 EUR` → €125) plus normalization backfilling rent from description.

**Limitations:** Dataset is ~90% rentals; sale-market conclusions invalid. Duplicate crawl restarts inflated duplicate candidates.

**Action:** Parser v1.3.0 — fix price comma parsing, stop description backfill in normalization.

---

## 2026-06-08 — What caused 12.3% invalid rate?

**Question:** What are the top validation failure reasons?

**Method:**

```sql
-- Equivalent: groundtruth etl errors
SELECT unnest(error_codes), COUNT(*) FROM invalid_listings GROUP BY 1;
```

**Result:**

| Error | Count |
|-------|-------|
| price_too_low | 868 |
| price_per_sqm_too_low | 670 |
| area_too_large | 13 |

682 invalid snapshots tagged `sale`, 186 `rent`. Sample: `rent=125000, sale=125` on same listing.

**Interpretation:** One root-cause parser bug (price parsing), not 868 separate website inconsistencies. Fixing comma-thousands parsing should drop invalid rate dramatically.

**Limitations:** Classification `website_inconsistency` over-counts parser bugs.

---

## 2026-06-08 — Is heating coverage real?

**Question:** Why does ETL report 100% heating coverage?

**Method:** `SELECT heating_type, COUNT(*) FROM normalized_listings GROUP BY 1`

**Result:** 7,018 `unknown`, 227 with real values (~3%).

**Interpretation:** `HeatingNormalizer` returns `UNKNOWN` whenever a description exists. Coverage metric counted non-null, not meaningful extraction. Fixed: UNKNOWN = missing.

**Limitations:** Heating analysis untrustworthy until parser v1.3.0 golden labels exist.

---

## 2026-06-08 — Rental vs sale composition

**Question:** Can we publish a general residential market report?

**Method:** `SELECT listing_type, COUNT(*) FROM normalized_listings GROUP BY 1`

**Result:** 6,563 rent (90.6%), 682 sale (9.4%).

**Interpretation:** Current dataset is a **rental market dataset**. First publication should be *"Rental Market Analysis of Prishtina 2026"*, not a combined sale/rent report.

**Limitations:** Gjirafa-only; MerrJep needed for sale-market coverage.

---

## 2026-06-09 — Parser v1.3.0 full reprocess

**Question:** Did the price-swap fix meet Phase A release criteria?

**Method:** `groundtruth etl run --reprocess --source gjirafa` on full raw dataset (11,823 normalized rows after duplicate raw records).

**Result:**

| Metric | v1.2.0 @ 7k | v1.3.0 reprocess |
|--------|---------------|------------------|
| Price coverage | 100% | **100%** |
| Neighborhood coverage | 88.8% | **89.0%** |
| Area coverage | 90.1% | **90.2%** |
| Invalid rate | 12.3% | **6.4%** |
| Heating (real) | ~3% | **3.1%** |

**Interpretation:** Price comma-thousands fix cut invalid rate roughly in half (12.3% → 6.4%). Not enough for <3% target. Neighborhood regression unchanged — still the primary blocker for >95%. Parser cannot be frozen.

**Limitations:** 11,823 rows include duplicate raw crawls (same listing, multiple raw_ids). Dedup not applied. Golden dataset not yet labeled for accuracy KPIs.

**Action:** Phase A continues — neighborhood extraction fixes before MerrJep. Phase B (golden labeling) can proceed in parallel.

---

## 2026-06-09 — Parser v1.3.0 frozen; is golden accuracy real?

**Question:** Does 100% golden accuracy mean the parser is excellent, or did we benchmark against ourselves?

**Method:** Auto-labeled 901 rows from raw HTML via `build_golden_labels.py`. Export 100 random rows with raw `price_raw`, `area_raw`, title, description alongside auto-labels: `export_golden_manual_review.py`.

**Result:** Automated evaluation reports 100% on price, area, neighborhood, type (n=901). Labels were generated using the same normalizers and extraction rules as the parser.

**Interpretation:** The 100% score is necessary but not sufficient. It confirms internal consistency, not independent ground truth. Before any public claim, a human must verify the 100-row sample. If manual accuracy ≥97%, the benchmark is trustworthy. If not, labels were circular.

**Limitations:** Auto-labels require gazetteer match for neighborhood — biases toward easy cases.

**Action:** Complete `golden_v1_manual_review_100.csv` review. Log result here before Phase E publication.

---

## 2026-06-09 — Area coverage ceiling on Gjirafa v1 corpus

**Question:** Why is overall area coverage 90.3% when the Phase A target is >95%?

**Method:** Audit unique listings (n=2,404). Classify `area_raw` as good (>1), placeholder (0/1), or missing. Check description for area keywords.

**Result:** 2,148 rows have valid `area_raw`; 256 have placeholder/missing with no area in description. Parser extracts area for **99.6%** of rows where any source signal exists. Theoretical max overall coverage ≈90.6%.

**Interpretation:** Report both numbers. Do not inflate KPIs. Gjirafa rental listings often omit size entirely.

**Limitations:** Single source; MerrJep may have better structured area fields.

**Action:** Use "coverage when signal present" in methodology section of first market report.

---

## 2026-06-09 — Phase C forensic audit baseline

**Question:** What does the dataset actually represent?

**Method:** `uv run python scripts/audit_dataset.py` on post-v1.3.0 ETL data (deduped unique listings).

**Result:** `reports/generated/audit_2026-06-09/` on 2,404 unique listings:

| Finding | Value |
|---------|-------|
| Rent vs sale | 89.8% / 10.2% |
| Prishtina vs other | 99.6% / 0.4% |
| Apartments | 99.8% |
| Area missing | 9.4% |
| Neighborhood missing | 4.2% |
| Bathrooms / building / year | 100% missing (not extracted) |
| Heating meaningful | 3.3% present |

**Interpretation:** Dataset is **Prishtina apartment rentals**, not Kosovo residential market. Bathrooms and construction year are not parser outputs yet — do not analyze them until extraction exists.

**Action:** Re-run audit after each ETL. Add one RESEARCH entry per chart used in Phase E report.

---

## Negative findings (record explicitly)

```markdown
### Question
Does apartment floor significantly affect rent/m²?

### Result
No statistically meaningful difference (bootstrap CI on difference includes zero).

### Status
published (negative)

### Claim ID
GT-XXX (claim_type=negative)
```

---

## Next research questions (queue)

1. Do furnished apartments command higher rent/m² after controlling for area? (Claim: TBD)
2. Which neighborhoods offer best value per m²? (n and bootstrap CI required)
3. Golden manual review — what is independent accuracy on 100-row sample? (GT-002)
4. Confidence calibration — do 0.9+ scores predict fewer field errors?
5. Does floor affect rent/m²? (candidate negative finding)

---

## Analytics maturity path

```
Descriptive → Comparative → Inferential → Predictive
```

Current stage: **descriptive / early comparative**. Every notebook must end with **future questions** (see `notebooks/NOTEBOOK_TEMPLATE.md`).
