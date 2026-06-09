# Parser Changelog

## v1.3.0 (2026-06-09)

- Fix comma-thousands price parsing (`125,000 EUR` → €125,000 not €125)
- Stop normalization re-extracting price from description (fake rent/sale split)
- Placeholder price fallback (`1 EUR` → description extraction)
- Sale price shorthand fixup (`1,300 EUR` → €130,000 when €/m² implausible)
- Expanded neighborhood title/description patterns (me qera, lagjen, shitje, streets)
- Street and complex fallbacks for neighborhood resolution (Muharrem Fejza, Royal City)
- Area extraction patterns (`m/2`, `sip:`, `prej X m`); reject placeholder `area_raw` 0/1
- `UNKNOWN` heating treated as missing in coverage KPIs
- `data_lineage` table for reproducible statistics
- Market snapshot idempotent re-run (delete same-day rows before insert)
- Golden dataset v1: 901 auto-labeled rows, 100% parser accuracy

**Release metrics (11,823 listings, ETL 2026-06-09):** price 100%, neighborhood 95.8%, area 90.3% (99.6% when source has area signal), invalid 2.4%, golden 100% (n=901)

## v1.2.0

- Neighborhood blocklist (facebook, numrin false positives)
- Title-first neighborhood extraction
- Expanded Prishtina gazetteer (49 neighborhoods)
- `parser_version` + `scraped_at` on pipeline records

## v1.0.0

- Initial Gjirafa HTML parser
- Raw → parsed → normalized pipeline
