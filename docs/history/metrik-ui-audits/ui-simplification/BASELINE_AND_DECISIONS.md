# Metrik UI simplification — baseline and decision record

Date: 2026-09-18

## Baseline

- Current branch: `master` tracking `origin/master`.
- Dirty files: the worktree already contains a large analytics/data-contract change set plus edits to `web/statistics.html`, `web/market.html`, `web/compare.html`, `web/rent-yield.html`, `web/static/annual.js`, `web/static/compare.js`, `web/static/i18n.js`, `web/static/lookup.js`, `web/static/site.js`, and `web/static/style.css`. These are treated as pre-existing user work and preserved.
- Relevant existing failures: none in the targeted baseline. `46 passed, 22 skipped` (feature/environment-dependent skips).
- Application URL: `http://127.0.0.1:8765`.
- Pages verified: `/`, `/valuate`, `/find`, `/statistics`, `/compare`, `/rent-yield`, `/market/neighborhood/ulpiana`, `/market/neighborhood/marigona-residence`, `/about`, `/methodology`, `/contact`.
- Tests run: web shell, i18n parity, search frontend, lookup/compare/budget-match/valuation/rent-yield/annual/methodology APIs and price-distribution UI tests.
- Baseline screenshots: `reports/METRIK/ui-simplification/baseline/` at 375, 768, and 1280px (31 images; contact initially captured at 375px).
- Audit findings still present: Statistics overexposure, Market equal-weight breakdowns, Valuation placeholder architecture, Compare duplicate representations, Find demo-like preview, card-heavy About/Methodology, repeated global trust metadata.
- Audit findings already partly fixed by pre-existing work: median fallbacks, distribution rendering/cutoff semantics, chart infrastructure, some i18n and sample-denominator corrections.

## Decision matrices

### Statistics

| Element | Decision | Why / primary user value | Technical value | Default / mobile | Files |
|---|---|---|---|---|---|
| Title, period, freshness | KEEP | Establishes scope | Dataset provenance | Visible, compact | `statistics.html`, `annual.js`, `style.css` |
| Four headline KPIs | KEEP | Immediate market answer | Preserves calculated outputs | Visible; 2×2 mobile | same |
| Executive summary | MERGE | One concise interpretation | Keeps narrative | Visible | same |
| Primary activity trend | KEEP | Shows what changed | Preserves chart data | Visible | same |
| Neighborhood ranking | KEEP | Most useful comparison | Keeps market links/confidence | Visible, compact | same |
| Distribution, quality, segments, profiles, picks, secondary trends/tables | COLLAPSE | Valuable analysis, not first answer | All payloads/rendering retained | One “Explore more data” control; closed by default | same |
| Formula implementation details | MOVE_DOWN | Technical, not a market answer | Retained for reproducibility | Closed methodology disclosure | same |
| Repeated disclaimer panels | MERGE | Keep caveat once | No contract change | Plain metadata/callout | same |

### Market

| Element | Decision | Why / primary user value | Technical value | Default / mobile | Files |
|---|---|---|---|---|---|
| Name, type, headline price | KEEP | Immediate market answer | Direct API mapping | First content | `market.html`, `lookup.js`, `style.css` |
| Four metric cards | MERGE | Reduce equal-weight boxes | Values/samples retained | One answer block; stacks cleanly | same |
| `$$$$` tier | REMOVE | Ambiguous decoration | None | Hidden | same |
| Search/popular markets | MOVE_DOWN | Useful next navigation | Search retained | After answer; popular links reduced on mobile | same |
| City comparison | KEEP | Useful context | API mapping retained | Compact supporting block | same |
| Confidence panel | MERGE | Repeated trust concept | Confidence retained in answer metadata | No separate default card | same |
| Type/bedroom/size/history/distribution | COLLAPSE | Analytical depth | All tables/charts retained | One detailed-analysis disclosure | same |
| Recent observations | KEEP | Evidence preview | Real listing aggregates | First 3 then view all | same |
| Report error | MOVE_DOWN | Support action | Accountability retained | Secondary action | same |

### Valuation

| Element | Decision | Why / primary user value | Technical value | Default / mobile | Files |
|---|---|---|---|---|---|
| Input form | KEEP | Core task | Existing validation/API | Dominant | `valuate.html`, `app.js`, `style.css` |
| Experimental caveat | RESTYLE | Important qualification | Risk communication | Compact text | same |
| Placeholder appraisal/evidence/context/examples/drivers | REMOVE | Fake result architecture before submission | None before request | Not rendered | same |
| How it works | MERGE | Set expectation briefly | None | Compact three-step support | same |
| Result estimate/range/property summary | KEEP | Core answer | API result preserved | Dominant | same |
| Asking-price delta | KEEP | User-specific context | Existing math retained | After estimate | same |
| Evidence/drivers/comparables/methodology/limitations | COLLAPSE | Expert detail | All data retained | Coherent disclosures | same |

### Compare

| Element | Decision | Why / primary user value | Technical value | Default / mobile | Files |
|---|---|---|---|---|---|
| Selection | RESTYLE | Reduce picker weight | Existing endpoint/state retained | Compact setup | `compare.html`, `compare.js`, `style.css` |
| Empty preview cards/table | REMOVE | Look like results | None | Not rendered | same |
| Summary cards | MERGE | Highlight key differences | Metrics retained | Compact summary | same |
| Comparison table | KEEP | Best canonical scan | Full data retained | Primary result; responsive | same |
| Five charts | COLLAPSE | Optional duplicate representation | Chart capability retained | Closed visual-comparison disclosure | same |

### Find

| Element | Decision | Why / primary user value | Technical value | Default / mobile | Files |
|---|---|---|---|---|---|
| Guided form and advanced filters | KEEP | Strong existing flow | Request contract retained | Compact, filters closed | `find.html`, `find.js`, `style.css` |
| How-it-works panel | MERGE | Workflow is self-evident | None | Short support copy | same |
| Illustrative recommendations | REMOVE | Resemble real output | None | Not rendered | same |
| Result cards + table | MERGE | Avoid duplicate representation | Same response retained | Table desktop, rows/cards mobile | same |

### Remaining pages and global shell

| Element | Decision | Why / primary user value | Technical value | Default / mobile | Files |
|---|---|---|---|---|---|
| Home hero/search | KEEP | Best entry flow | Search retained | Dominant | `index.html`, `style.css` |
| Home six-step explanation | MERGE | Too much pre-search detail | None | Three concise steps | same |
| Rent Yield core table | KEEP | Already disciplined | Samples/confidence retained | Secondary metadata on mobile | `rent-yield.html`, `style.css` |
| About engineering pipeline/details | MOVE_DOWN | About should be human-facing | Technical story retained | Closed technical disclosure / fewer surfaces | `about.html`, `style.css` |
| Methodology sections | RESTYLE | Documentation should be readable, not ten cards | Full content retained | Divided prose flow | `methodology.html`, `style.css` |
| Footer raw counts | COLLAPSE | Global debug feel | Methodology retains detail | One freshness line | `site.js`, footer/style |
| Subnavigation | RESTYLE | Preserve discoverability with less height | Routes unchanged | Compact horizontal scroll on mobile | `site.js`, `style.css` |
