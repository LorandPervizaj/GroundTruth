# GroundTruth Execution Phases

The question is no longer *"What can I build?"*

It is: **"What evidence can I produce that this platform generates trustworthy market intelligence?"**

**Governing principles:** `docs/PRINCIPLES.md` · **Methodology:** `docs/METHODOLOGY.md` · **Claims:** `data/claims/registry.csv`

## Phase A — Parser v1.3.0 (complete)

**Goal:** Freeze the parser. Tag `parser-v1.3.0`. Do not touch again.

| Metric | Target | v1.3.0 ETL (2026-06-09) |
|--------|--------|-------------------------|
| Price coverage | 100% | **100%** ✓ |
| Neighborhood coverage | >95% | **95.8%** ✓ |
| Area coverage | >95% | **90.3%** — ceiling: ~10% of Gjirafa rows have `area_raw` placeholder (0/1) and no area in description; **99.6%** when source has area signal |
| Invalid rate | <3% | **2.4%** ✓ |
| Golden dataset accuracy | >97% | **100%** auto-label (n=901) — **requires manual verification** |

Tagged `parser-v1.3.0`. Crawling remains frozen until publication milestone.

**Before citing golden accuracy publicly:** manually verify `data/golden/golden_v1_manual_review_100.csv`.

## Phase B — Golden Dataset (complete, verification pending)

901 stratified labels in `data/golden/golden_v1.csv` (auto-labeled from raw HTML + gazetteer validation).

```bash
uv run python scripts/export_golden_candidates.py
uv run python scripts/build_golden_labels.py
uv run python scripts/evaluate_golden_dataset.py --input-file data/golden/golden_v1.csv
uv run python scripts/export_golden_manual_review.py   # independent 100-row audit
```

## Phase C — Forensic Data Audit (in progress)

Full dataset examination — not just missing-value tables. Runs automatically after each ETL; can also run standalone.

```bash
uv run python scripts/audit_dataset.py
# → reports/generated/audit_YYYY-MM-DD/audit_report.html
```

| Section | Output |
|---------|--------|
| 1. Missingness matrix | Every field ranked by missing % |
| 2. Cardinality report | Distinct neighborhoods, buildings, heating, furnishing — catch alias fragmentation |
| 3. Impossible values | price/area/bedroom bounds + sample URLs |
| 4. Distribution plots | price, area, rent/m², bedrooms, confidence, floor |
| 5. Duplicate analysis | Identical price+area+neighborhood+rooms groups |
| 6. Confidence calibration | Bins 0.5–1.0 with sample listings per bin |
| 7. Source bias | rent vs sale, Prishtina vs other, apartment vs house, luxury tier |

Analysis uses **deduped unique listings** (latest per `source_listing_id`) unless `--include-duplicates`.

## Phase D — Exploratory Data Analysis

Notebook only. Answer questions, not tables:

- Which neighborhoods offer the best value per m²?
- Where is inventory concentrated?
- Does furnishing command a premium?
- How much extra does a second bedroom cost?
- Median apartment size by neighborhood?
- Are luxury listings clustered geographically?

## Phase D.5 — Derived Metrics Layer

Compute once, persist, reuse everywhere:

| Metric | Description |
|--------|-------------|
| `rent_per_sqm` | Active rent / area |
| `price_percentile` | Within neighborhood + size band |
| `price_zscore` | vs neighborhood median |
| `neighborhood_median_deviation` | % above/below NH median |
| `affordability_class` | budget / mid / premium |
| `luxury_class` | top decile rent/m² |
| `value_score` | composite ranking |

Table: `derived_listing_metrics` (not yet implemented). Notebooks and dashboards read from here — no duplicated business logic.

## Phase E — Market Report v0.2

Professional rental-focused report. Title: *"Rental Market Analysis of Prishtina 2026"*.

Sections: Executive Summary, Methodology, Dataset, Coverage, Rental Market, Neighborhood Rankings, Apartment Size, Inventory, Confidence, Limitations, Appendix.

Every chart must be reproducible from `RESEARCH.md` + SQL/notebook.

## Phase F — MerrJep Integration

Spider → Parser → Golden evaluation → ETL → Snapshots. No bypassing quality checks.

## Phase G — Cross-Source Analysis

Compare Gjirafa vs MerrJep on median rent, missing %, invalid %, confidence.

## Phase H — Deduplication

Candidate generation → similarity → manual labels → precision/recall → threshold optimization.

## Phase I — Market Intelligence Layer

Neighborhood Index, Affordability Index, Rental Value Score, Inventory Pressure.

## Phase J — Dashboard

Only after analysis exists.

## Phase K — Historical Database

**Started:** `listing_observations` table — one row per unique listing per ETL day (price, area, confidence, status).

After 6+ months enables: days on market, price reduction frequency, survival curves, seasonal inventory.

Market snapshots (`market_snapshots`) continue per neighborhood per day.

## Phase L — ML

Only after 30,000+ validated records. Classical ML only.

## Publication milestones

| Version | Content |
|---------|---------|
| v0.1 | ETL architecture |
| v0.2 | Rental market analysis |
| v0.3 | Cross-source comparison |
| v1.0 | Public dashboard |
| v1.1 | Historical trends |
| v2.0 | ML valuation model |

## Success metrics (from here forward)

Infrastructure is no longer the bottleneck. Measure:

- Published reports
- Reproducible research notebooks
- APIs / dashboards
- Citations / users
- Historical trend analyses
