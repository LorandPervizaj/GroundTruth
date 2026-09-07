# Dashboard notes

The live Metrik UI is static HTML/JS under `web/`, served by the FastAPI app.

Any future map or browse UI must stay within the **public allowlist**:

- Aggregated neighborhood / market metrics
- Sample size and confidence
- Links that send users to the **original public portal URL** (no hosted copies of listing text, photos, or contact blocks)

Do **not** build a scraped listings mirror, contact directory, or downloadable dump of portal content. See `docs/DATA_HANDLING.md` and `docs/CRAWL_POLICY.md`.
