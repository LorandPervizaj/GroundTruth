# Data handling — PII, retention, public vs research

**Audit date:** 2026-06-12  
**Goal:** Third-party contact data in raw HTML never leaks publicly; controls are documented.

**Public product rule:** Metrik exposes aggregated market statistics only. Do not republish listing text, photos, or seller/agent contact details. Research collectors run on a private host — see [CRAWL_POLICY.md](CRAWL_POLICY.md) and [SCRAPERS.md](SCRAPERS.md).

---

## What is scraped

Public real-estate portals publish listing pages that often include:

- Property attributes (price, area, bedrooms, location labels)
- Marketing descriptions (may embed **phone numbers**, WhatsApp/Viber prompts, agency names)
- Seller/agent contact blocks (especially MerrJep HTML and Pro-RKS API `agent` objects)
- Image URLs and canonical listing URLs

**Not scraped for the public product corpus:** Facebook Marketplace automation (B1 NO-GO). Informal Facebook captures are quarantined separately — see [Informal tier](#informal-facebook-tier) below.

---

## What is stored (research database — local only)

| Layer | Table / path | Contents | PII risk |
|-------|--------------|----------|----------|
| Raw | `raw_listings.raw_html` | Full page HTML | **High** — contact blocks in HTML |
| Raw | `raw_listings.raw_payload` | JSON (titles, descriptions,`agent`, images) | **High** |
| Parsed | `parsed_listings.description_original` | Full listing text | **High** |
| Parsed | `parsed_listings.extra_fields` | Source metadata; `agent` stored **without** email/phone | Medium (name only) |
| Normalized | `normalized_listings` | Structured market fields + `original_url` | Low–medium (URL links to public ad) |
| Product logs | `data/product/*.jsonl` | User alert emails, feedback (gitignored) | User PII |
| Golden sets | `data/golden/*.csv` | Parser benchmark labels + description excerpts | **Internal only** — may contain historical contact text |
| Informal | `data/sources/facebook/**` | Manual/quarantine captures (gitignored) | **High** |

The research PostgreSQL database is **not deployed** with the public website. It runs on a local or private host.

---

## What is redacted before display

### Public API (internet-facing)

| Endpoint | Exposed fields | Contact data |
|----------|----------------|--------------|
| `GET /api/lookup/...` → `recent_listings` | source, id, **url**, price, area, bedrooms, lifecycle | No title/description/phone. URL points to public portal ad. |
| `POST /api/valuate` → `comparables` | id, area, bedrooms, rent € | No source URL or description |
| `GET /api/search` | neighborhood/street/complex names, listing counts | No listing-level data |
| Reports / annual JSON | Aggregated medians, neighborhood stats | No per-listing text |

**Web UI** renders the same API shapes — no listing titles, descriptions, phones, or agent names from scraped data.

### Parse-time controls

- **Pro Real Estate:** `agent.email` / `agent.phone` stripped at parse; only `fullName` retained in `extra_fields` (`processing/redaction.py`).
- **Active corpus filter:** `facebook` / `facebook-groups` sources excluded from public medians (`corpus_filters.INFORMAL_SOURCE_WEBSITES`).

### Debug / export tooling

Parser and ETL tooling redacts phones, emails, WhatsApp/Viber phrases, and messenger deep links from derived text by default (`processing/redaction.py`). Golden exports use the same redaction helpers.

---

## Retention & deletion

Configured in `.env` / `config.py`:

| Setting | Default | Meaning |
|---------|---------|---------|
| `RAW_HTML_RETENTION_DAYS` | 730 (2 years) | Drop `raw_html` column content after age |
| `RAW_PAYLOAD_RETENTION_DAYS` | 730 | Trim or archive full JSON payloads |
| `PARSED_DESCRIPTION_RETENTION_DAYS` | 730 | Clear `description_original` after normalization stable |

**Policy:**

1. **Raw HTML** — kept for parser QA and provenance during active development; purged after retention window once parser version is frozen for that source.
2. **Normalized facts** (price, area, neighborhood, dates) — retained for market history; no contact fields stored.
3. **Golden CSVs** — kept for parser regression; treat as confidential research artifacts; do not publish or attach to portfolio repos.
4. **Product logs** (`alerts.jsonl`, `feedback.jsonl`) — rotate locally; never commit (gitignored).

### Purge procedure (manual, post-retention)

```sql
-- Example: null raw HTML older than retention (run after backup)
UPDATE raw_listings
SET raw_html = NULL
WHERE scraped_at < NOW() - INTERVAL '730 days'
  AND raw_html IS NOT NULL;
```

Re-run only on the private research database. Document ETL revision in the research log before bulk purge.

---

## Informal Facebook tier

Facebook Marketplace automated scrape is **NO-GO** — ToS risk, duplicate overlap with public portals, and incompatible with a public repo posture. Only manual import (B1) and hand-logged group samples (B3) are allowed. See `docs/FB_MARKETPLACE.md` and `docs/CRAWL_POLICY.md`.

If any Facebook data is ingested (B2 informal tier, B3 group samples):

- Stored under `data/sources/facebook/**` (gitignored)
- Parser version `0.1.0-facebook-informal`
- **`INFORMAL_SOURCE_WEBSITES`** excludes `facebook` and `facebook-groups` from `ACTIVE_CORPUS_WHERE` — never blended into public medians, lookup pages, or annual report statistics
- Captures may contain poster handles and contact prompts; quarantine only, no public API exposure

---

## Git & artifact audit (2026-06-12)

| Check | Result |
|-------|--------|
| `raw_html` / DB dumps in git | **None** — `data/raw/**` gitignored |
| `reports/generated/**` HTML probes | Gitignored (local probe artifacts may contain portal contact HTML) |
| Raw HTML in tracked files | **None** |
| Golden CSVs in git | **Yes** — internal benchmark data; descriptions may contain historical phones; **not for public release** |
| Screenshots / Loom images in repo | **None found** |

Before portfolio demos: scrub screen recordings and screenshots for visible phone numbers from MerrJep/Gjirafa detail pages.

---

## Implementation reference

- Redaction: `src/groundtruth/processing/redaction.py`
- Pro-RKS agent strip: `src/groundtruth/services/pro_rks_parsing.py`
- Corpus exclusion: `src/groundtruth/analytics/corpus_filters.py`
- Public schemas: `src/groundtruth/schemas/lookup.py`, `schemas/valuation.py`

---

## Checklist

- [x] PII inventory (raw HTML, payloads, exports, golden sets)
- [x] No raw HTML / DB dumps in git or public artifacts
- [x] Public API audited — no phone/name in JSON responses
- [x] Web UI audited — no scraped contact fields
- [x] Redaction pass for derived/debug output
- [x] Retention policy defined (config + purge SQL)
- [x] `docs/DATA_HANDLING.md` written
- [x] README note: research DB local; public site aggregated only
- [x] Informal Facebook tier exclusion documented
- [x] Portfolio/screenshot review noted (no assets in repo)
