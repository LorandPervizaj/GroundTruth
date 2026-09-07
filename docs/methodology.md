# GroundTruth Methodology

How we know what we know. If someone challenges a chart, this document should answer the question before they ask it.

**Methodology version:** `1.0.0` (semantic — independent from parser)  
**Parser:** `parser-v1.3.0`  
**Primary sources:** Public Kosovo listing portals (see active corpus in `/api/meta`)

Every published report must state: *Generated using Methodology v1.0.0.*

---

## 1. Scope and limitations

### What this dataset is

- **Prishtina apartment rentals** aggregated from public listing portals, as of the latest ETL run.
- ~2,400 unique listings (deduped by `source_listing_id`, latest observation).
- ~90% rent, ~10% sale; ~99.6% Prishtina; ~99.8% apartments.

### What this dataset is not

- Not a representative sample of Kosovo residential real estate.
- Not a sale-market index (insufficient sale volume and quality).
- Not causal — observational listings only; no transaction prices.
- Not complete for area — ~9% of listings have no area signal in source HTML.

### How we state coverage

We report **two area metrics** when relevant:

| Metric | Definition |
|--------|------------|
| Overall area coverage | % of all listings with `area_sqm` populated |
| Coverage when signal present | % extracted when `area_raw` or description contains area |

The second metric reflects parser quality; the first reflects source + parser combined.

---

## 2. Data acquisition

| Parameter | Value |
|-----------|-------|
| Sources | Public Kosovo residential listing portals (multi-source active corpus) |
| Crawl policy | Conservative — see [CRAWL_POLICY.md](CRAWL_POLICY.md) (delays, autothrottle, skip-existing, private operator only) |
| Raw storage | Immutable `raw_listings` with `content_hash` (local research DB — not public) |
| Duplicate crawls | Same `source_listing_id` may have multiple `raw_listing_id`; analysis uses latest |
| Facebook | Manual import only — no automated Marketplace scrape ([FB_MARKETPLACE.md](FB_MARKETPLACE.md)) |

---

## 3. ETL pipeline

```
raw_listings → parsed_listings → normalized_listings → validation
                                      ↓
                            invalid_listings (flagged, never deleted)
```

| Stage | Version field | Reproducible from |
|-------|---------------|-------------------|
| Crawl | `spider_version` | Raw payload |
| Parse | `parser_version` | Raw payload + parser code |
| Normalize | `normalization_version`, `gazetteer_version` | Parsed record + gazetteer JSON |
| Lineage | `data_lineage` | Links ETL run → listing |

ETL command: `uv run groundtruth etl run --reprocess --source gjirafa`

After each run:

- Neighborhood `market_snapshots` (daily, idempotent)
- Per-listing `listing_observations` (daily, unique per listing)
- Forensic audit → `reports/generated/audit_YYYY-MM-DD/`

---

## 4. Parser design

Parser v1.3.0 is **frozen**. Changes require a new version tag and golden re-evaluation.

Key behaviors:

- Structured price first; description fallback for placeholders (`1 EUR`) and sale shorthand (`1,300 EUR` → €130,000 when €/m² implausible)
- Neighborhood from title/description patterns + 49-neighborhood gazetteer
- Street and complex fallbacks when neighborhood name is ambiguous
- Area from `area_raw` or description patterns; reject placeholders (0, 1) and values >500 m² without description confirmation

**Validation** applies business rules (min/max price, area, €/m²). Invalid listings are stored in `invalid_listings` with error codes — never silently dropped.

---

## 5. Validation methodology

### Parser KPIs (automated, every ETL)

| KPI | Target (v1.3.0) |
|-----|-----------------|
| Price coverage | 100% |
| Neighborhood coverage | >95% |
| Invalid rate | <3% |

Logged to `reports/generated/benchmark_log.csv`.

### Golden dataset (regression benchmark)

- 901 stratified auto-labels in `data/golden/golden_v1.csv`
- Evaluated by `scripts/evaluate_golden_dataset.py`

Automated accuracy confirms internal consistency, not independent ground truth.

### Forensic audit (Phase C)

Post-ETL audits write artifacts under `reports/generated/` (corpus, skew, annual report).

---

## 6. Confidence scoring

### Parser confidence (`confidence_score`)

Per-listing score from normalization match quality (neighborhood, street, complex, building match types). Used for weighting and calibration — **not** a substitute for sample size.

**Calibration protocol:** Sample 20 listings per confidence bin (0.5–0.6, …, 0.9–1.0). Recalibrate before public use if bins do not monotonically predict accuracy.

### Dataset confidence (slice-level)

For any analytic slice (neighborhood, segment, time window):

```
dataset_confidence =
  parser_accuracy
  × coverage_factor
  × source_diversity_factor
  × completeness_factor
  × sample_reliability
```

| Factor | Definition |
|--------|------------|
| `parser_accuracy` | Golden accuracy or calibrated bin accuracy (default 0.97 if unverified) |
| `coverage_factor` | Structural coverage of the slice (default 1.0) |
| `source_diversity_factor` | min(1.0, n_sources / 2) |
| `completeness_factor` | 1 − critical field missingness for fields used in the analysis |
| `sample_reliability` | min(1, √(n/100)) — smooth, no hard thresholds |

Computed by `groundtruth.analytics.dataset_confidence.compute_dataset_confidence()`.

Low `sample_reliability` downweights small slices continuously (n=4 → 0.20, n=100 → 1.00).

### Metric stability

When comparing the same metric across time periods, use `groundtruth.analytics.stability.assess_stability()`.

Classifications: `stable`, `moderately_stable`, `volatile` — based on CI overlap, relative change, and sample size.

Do not report month-over-month changes when CIs overlap and classification is `stable`.

---

## 7. Statistical reporting

Every comparative claim (e.g. neighborhood A vs B median rent/m²) must report:

| Statistic | Purpose |
|-----------|---------|
| n | Sample size |
| Median | Robust central tendency |
| IQR | Spread |
| MAD | Robust dispersion |
| Bootstrap 95% CI | Uncertainty on median difference |

Use `groundtruth.analytics.stats.summarize()` and `bootstrap_median_ci()`.

Non-parametric methods preferred — rent distributions are skewed.

---

## 8. Deduplication strategy

**Current:** Heuristic duplicate candidates (same neighborhood, area, bedrooms, price bucket). Manual labeling via `data/duplicate_candidates.csv`.

**Not yet applied:** Canonical property merge. All published analysis uses deduped unique `source_listing_id` unless stated otherwise.

---

## 9. Claim registry (immutable)

Every publishable statement is registered in `data/claims/registry.csv`. **Claims are never edited after publication.**

| Column | Purpose |
|--------|---------|
| `claim_id` | Stable ID (GT-001, …) |
| `statement` | Exact claim text |
| `claim_type` | fact / interpretation / negative / method |
| `etl_run_id` | Exact ETL metrics run |
| `etl_date` | Data snapshot date |
| `parser_version` | Parser version |
| `methodology_version` | Methodology semver (e.g. 1.0.0) |
| `notebook_path` + `notebook_hash` | Analysis reproducibility |
| `query_path` + `sql_hash` | Query reproducibility |
| `dataset_hash` | SHA-256 fingerprint of deduped normalized dataset |
| `n` | Sample size |
| `reviewer` | Human verifier |
| `status` | draft / reviewed / published / superseded / retracted |
| `superseded_by` | New claim ID if replaced |

When a claim changes, **supersede** it in `data/claims/registry.csv` — historical claims remain. Export public claims with `scripts/export_claims_api.py`.

---

## 10. Reproducibility guarantees

| Guarantee | Mechanism |
|-----------|-----------|
| Raw immutability | `raw_listings` never updated |
| Parser replay | Re-parse any raw row with tagged parser version |
| Version pins | `parser_version`, `gazetteer_version`, `normalization_version` on every row |
| ETL lineage | `data_lineage` links metrics run → listings |
| Audit trail | Daily audit HTML + CSV artifacts |
| History | `listing_observations` per listing per day |

### Notebook versioning

Store notebooks under `notebooks/` with naming:

```
notebooks/YYYY-MM-DD_<question-slug>.ipynb
```

Pin in claim registry: ETL date, parser version, git commit hash.

---

## 11. Update frequency

| Artifact | Frequency |
|----------|-----------|
| Crawl | Paused until post-publication |
| ETL reprocess | On parser change or monthly during active phase |
| Market snapshots | Each ETL run |
| Listing observations | Each ETL run |
| Forensic audit | Each ETL run |
| Research ledger | Weekly (one insight minimum) |
| Public report | Quarterly target after v0.2 |

---

## 12. Known biases

1. **Source bias:** Single portal; Gjirafa agent mix unknown.
2. **Geographic bias:** Almost entirely Prishtina.
3. **Property type bias:** Almost entirely apartments.
4. **Asking vs transaction:** Listed rents, not closed deals.
5. **Survivorship:** Delisted properties disappear unless captured in `listing_observations`.
6. **Parser bias:** Golden labels partially auto-generated — manual verification pending.
7. **Luxury skew:** Portal may over-represent mid/high segment.

---

## 13. First public report structure (target: 15–20 pages)

1. Scope and limitations (1–2 pp)
2. Methodology v1.0.0 (summary, 2–3 pp)
3. Dataset profile (composition, coverage, confidence, 2 pp)
4. **Facts** — five to ten observations (each with n, CI, stability, claim ID)
5. **Interpretations** — hypotheses clearly separated from facts
6. Technical appendix (SQL hashes, glossary, 2–3 pp)

Title: *Rental Market Analysis of Prishtina, 2026*

Register negative findings (no effect) as `claim_type=negative` to avoid revisiting disproven hypotheses.

---

## References

- `docs/architecture.md` — pipeline layout
- `data/claims/registry.csv` — claim registry
- `CHANGELOG.md` — parser version history
