# Facebook Marketplace & Groups — Part B

**Status:** B0 decided · B1 scaffold (manual import only) · B2 informal tier · B3 group sampling  
**Decision record:** `data/experiment/fb_marketplace_decision.json`  
**Theme:** Optional enrichment, not a fourth official corpus source.

---

## Why B1 automated scrape is NO-GO

Facebook Marketplace is **not** crawled by this project. This is a deliberate ToS and product decision, not a technical limitation waiting to be solved.

| Concern | Why automation is rejected |
|---------|---------------------------|
| **Terms of Service** | Meta’s terms restrict unauthorized automated collection of Marketplace content. A public open-source repo must not ship or document a Facebook scraper. |
| **Signal vs effort** | Listings overlap heavily with Gjirafa, MerrJep, and agency portals already in the active corpus — marginal unique signal does not justify risk. |
| **Data quality** | Informal posts lack structured fields; contact-in-description noise is high without manual QA. |
| **Public product** | Even if ingested, informal tier rows are **excluded** from public medians (`INFORMAL_SOURCE_WEBSITES`). |
| **Acceptable path** | **Manual import only** (B1): operator copies public post metadata into JSONL; **B3** group samples are qualitative, biweekly, hand-logged. |

See also: [CRAWL_POLICY.md](CRAWL_POLICY.md) (no Facebook automation) · [DATA_HANDLING.md](DATA_HANDLING.md) (informal tier quarantine).

---

## B0 — Go / no-go (2026-06-12)

| Path | Decision | Rationale |
|------|----------|-----------|
| **B1** Full Marketplace scrape + normalize | **NO-GO** | ToS risk, fragility, high duplicate rate vs core portals |
| **B3** Periodic Prishtina RE group samples | **GO** | Low risk, qualitative signal, no median pollution |
| **B2** Informal tier separation | **GO** (always) | Defense in depth if any FB data is ingested |

### Criteria used

| Factor | B1 full scrape | B3 group sample |
|--------|----------------|-----------------|
| Signal vs core corpus | Marginal (heavy overlap) | Complementary (informal / early listings) |
| Maintenance | High (breaks often) | Low (manual, periodic) |
| ToS / legal | Unacceptable for automation | Acceptable if manual, public posts only |
| Field quality | Poor without manual QA | Explicitly low-confidence |
| Public median impact | Must never blend | Never blends (by design) |

**Revisit:** 2026-12-01 or after Dataset v2.0 freeze + 3 months of B3 samples.

---

## B1 — Manual Marketplace import (quarantine)

No automated scraper. Occasional manual captures only.

```bash
# Import a JSONL batch (one object per line — see data/sources/facebook/README.md)
uv run groundtruth fb import data/sources/facebook/batches/2026-06-12.jsonl

# List quarantined informal listings
uv run groundtruth fb status
```

Output: `data/sources/facebook/informal_listings.jsonl` (append-only, deduped by URL).

Parser version `0.1.0-facebook-informal` is **not** in `ACTIVE_PARSER_VERSIONS` — rows never enter public medians even if loaded to DB later.

---

## B2 — Informal source tier

Informal sources (`facebook`, `facebook-groups`) are excluded from:

- `active_corpus_dataframe()` / market lookup medians
- Public `/api/lookup` pulse and breakdowns
- Annual statistics exports

Implementation: `INFORMAL_SOURCE_WEBSITES` in `analytics/corpus_filters.py` + parser-version gate.

Informal data may be used internally via `groundtruth fb report` for qualitative review only.

---

## B3 — Group post sampling

Registry: `data/sources/facebook-groups/registry.json`

```bash
# Record a manual sample from a tracked group
uv run groundtruth fb sample \
  --group prishtina-patundshmeri \
  --snippet "2+1 Ulpiana 75m2 450eur qira" \
  --price 450 --type rent --neighborhood ulpiana

# Summarize recent samples + informal imports
uv run groundtruth fb report
```

Samples: `data/sources/facebook-groups/samples/YYYY-MM-DD.jsonl`

**Cadence:** biweekly manual pass (~15 min) across 3–5 groups before corpus QA reviews.

---

## Commands

| Command | Part |
|---------|------|
| `groundtruth fb decision` | B0 — print recorded decision |
| `groundtruth fb import <file.jsonl>` | B1 — normalize manual Marketplace rows |
| `groundtruth fb sample` | B3 — log a group post observation |
| `groundtruth fb report` | B3 — signal summary |
| `groundtruth fb status` | All — counts + policy reminder |
