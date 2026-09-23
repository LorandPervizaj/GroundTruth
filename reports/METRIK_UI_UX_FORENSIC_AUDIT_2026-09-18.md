# METRIK UI/UX CLUTTER & INFORMATION-DENSITY FORENSIC AUDIT

Audit date: 2026-09-18  
Repository state: current working tree, including pre-existing uncommitted changes  
Method: read-only source inspection plus rendered inspection of the local FastAPI application at 375×812, 768×900, 1280×900, and 1440×900  
Languages: Albanian and English  
Representative markets: `/market/neighborhood/ulpiana` and lower-data `/market/neighborhood/marigona-residence`

# PART A — Executive findings

1. **The statistics page is the dominant clutter hotspot.** At 1280px it renders 17 major sections, 22 headings, 24 panel/card-like surfaces, 9 tables, approximately 14 chart/canvas-related elements, 11 buttons, and 76 links. At 375px the document is approximately 14,816px tall. The page simultaneously presents headline KPIs, a distribution, executive narrative, conclusions, data quality, activity chart, two rankings, property-type composition, two segment tables, neighborhood profiles, two “where to look” tables, two trends, active-neighborhood table, formulas, and methodology. Evidence: `web/statistics.html:50-282`; render functions in `web/static/annual.js:217-990`.

2. **The Ulpiana market page exposes analytical depth at almost the same visual weight as its primary answer.** Rendered at 1280px: 14 sections, 15 headings, 18 panel/card-like surfaces, 23 badge-like elements, 8 chips, 4 tables, approximately 15 chart-related nodes, 11 buttons, and 35 links. The title is an `H2`, not an `H1`, while section headings are mostly `H3`; this weakens document semantics. Evidence: `web/market.html`; rendering in `web/static/lookup.js`; the rendered hierarchy begins with toolbar → popular-market chips → breadcrumb → pulse panel, so a user processes a search surface before the market answer.

3. **Mobile preserves nearly all desktop information rather than reprioritizing it.** At 375px, `/statistics` is ~14.8k px tall and `/market/neighborhood/ulpiana` ~5.46k px. The desktop rail collapses into the same long stream, while repeated panels, headings, info icons, and tables remain. This is not simply “more scrolling”: the hierarchy becomes an undifferentiated stack.

4. **Trust information is valuable but repeated across levels.** Sample size appears beside headline metrics, inside confidence badges/tooltips, in distribution prose, in table cells, and again in the confidence rail panel. Asking-price caveats occur in hero copy, chart notes, annual narrative, methodology, About, legal content, and footer-adjacent copy. Freshness appears in the home trust strip, statistics hero, compare results, and every footer. The data should remain available; default prominence is the issue.

5. **The global shell offers many simultaneous paths.** Desktop header exposes five primary destinations plus two language controls. Tools pages add a second two-item subnav; insights pages add a second three-item subnav. Market pages add global search, six popular-market chips, a breadcrumb, in-page CTAs, and the footer. The footer repeats About, Methodology, Privacy, Contact/Report, and Compare. Evidence: `web/static/site.js:15-120`, `web/partials/site-footer.html:1-15`.

6. **The valuation empty state explains the post-result experience before a result exists.** At 1280px the page renders 8 sections and 10 panel/card-like surfaces; the form competes with a pending “Market valuation” card, “What you get,” market context placeholders, similar-example placeholders, and value-driver chips. At 375px it is ~2,762px tall. Evidence: `web/valuate.html:27-196`. The primary task is clear, but the page pre-spends attention on evidence and future state.

7. **The statistics page mixes “answer,” interpretation, evidence, formulas, and documentation.** The “Formula (how the numbers are calculated)” block displays literal equations and internal target IDs such as `kpi_total`, `sale_price_chart`, and `nh_table`. This is advanced trust detail shown on the same page as the market story. Evidence: `web/static/annual.js:921-990` and corresponding annual payload.

8. **English is not a complete English experience.** Static UI headings switch, but rendered API-derived annual narratives remain Albanian; the market page retains Albanian sample strings (“Bazuar në … vëzhgime”), confidence labels, bedroom labels, listing-type labels, and “Shfaq të gjitha” in an English view. This makes already-dense pages require language switching mentally. Evidence: dynamic rendering in `web/static/annual.js`, `web/static/lookup.js`, translation application at `web/static/i18n.js:2235-2296`.

9. **Several labels conflate median and average terminology.** The methodology Albanian string states “mesatarja (median)” and confidence copy repeatedly says “mesatare të besueshme,” while the product otherwise emphasizes medians. Market property-type columns use an average/median mismatch in the rendered Albanian header (“ÇMIMI MESATAR”, “SIPËRFAQJA MESATARE”) while values and English headers identify medians. Compare code still reads `average_sale_psm_eur` for one card path (`web/static/compare.js:270,324`) but uses median fallback in the table (`:382`). These are comprehension and statistical-semantics risks, not just wordiness.

10. **The market headline mixes denominators.** The four pulse metrics show sale samples (151), rent samples (219), and recent-valid listing count based on the all-property corpus (567), while the page explains that price samples cover apartments/studios but listing count covers all property types. The explanation is accurate and valuable, but it is long and required to interpret the headline cards. Evidence: rendered Ulpiana copy; schema/producer chain in `src/groundtruth/schemas/lookup.py` and `src/groundtruth/services/lookup.py`.

11. **Card/panel containment is near-universal.** `.panel` applies white background, border, radius, padding, bottom margin, and shadow (`web/static/style.css:468-474`). Methodology has ten consecutive panels; About has ten; statistics 24 card/panel-like containers; valuation ten. Because most content is boxed, containment stops signaling importance.

12. **Info-tip proliferation adds interaction and layout noise.** The shared runtime dynamically builds tooltip icons and bubbles (`web/static/site.js:271-443`). Statistics and market headings repeatedly append “i”; on narrow viewports the audit detected width overflow around `.info-tip` and `.section-title-with-info`. Many tips explain content already described directly below the heading.

13. **Compare is conceptually clear but its selection UI is high-friction.** Three full neighborhood selectors each expose the same long option list, sample counts appear inside option labels, and preview cards plus “How it works” plus the eventual table repeat the same metric family. The result can answer “How are these areas different?”, but not until users complete a dense selection surface.

14. **Rent yield is one of the most disciplined analytical pages.** It has two sections, one primary table, one ranking explanation, and a clear dominant yield column. Its 6-column table is horizontally demanding on mobile, but its purpose and next action are clear. Preserve its directness.

15. **The home page is comparatively disciplined but duplicates trust/freshness.** The hero, search, budget-find link, popular markets, six-step “How it works,” annual-report teaser, and footer make the purpose clear. However, the trust strip and footer both communicate freshness and aggregation; “How it works” enumerates six downstream outputs before users have searched.

16. **About and Methodology substantially overlap.** About contains origin story, product definition, GroundTruth implementation, nine-stage pipeline, architecture diagram, methodology summary, metric definitions, confidence thresholds, limitations, and purpose. Methodology separately repeats corpus, normalization, statistics, confidence, deduplication, trends, limitations, and versioning. Both are useful, but About has become a second methodology document.

17. **Some inactive or unavailable functionality is still prominent.** Alerts dedicates a full panel to email notifications only to state they are unavailable; valuation visibly labels itself experimental and may be disabled by configuration; About explains that some features may be disabled. These are defensive/product-state messages competing with user tasks.

18. **The current design has strong, preservable DNA.** Restrained warm neutrals, dark green accent, Georgia display type, clear numeric formatting, compact confidence palette, generous outer gutters, straightforward forms, and explicit data caveats produce seriousness and trust. The problem is accumulation and equal visual weighting, not the visual identity.

# PART B — Current Metrik UI architecture

## Global shell

| Item | Visible text/purpose | Where | Responsive behavior | Competition/duplication |
|---|---|---|---|---|
| Brand | “Metrik”; home link | All pages | Top-left; remains above mobile menu | Appropriate and clear |
| Primary nav | Markets, Explore, Statistics, About Metrik, Contact/Report | All pages | Five links visible at ≥768; hamburger at 375, while language controls remain visible | About/Contact repeat in footer; Explore is a category label whose destination is Valuate |
| Language control | Shqip / English | All pages | Always visible; at 375 occupies a header row beside hamburger | Valuable, but incomplete dynamic translation undermines it |
| Tools subnav | Value My Property / Find a neighborhood | `/valuate`, `/find` | Horizontal two-tab bar; visible above page title | Clarifies sibling tools; repeats landing destinations from primary nav |
| Insights subnav | Annual report / Compare neighborhoods / Rent yield | `/statistics`, `/compare`, `/rent-yield` | Three tabs; wraps into two rows at 375 | On mobile consumes ~88–213px before page content; routes also repeat in footer/other CTAs |
| Market toolbar | Search Markets + six Popular Markets chips | Market pages | Full-width panel; chips wrap to three rows at 375 | Precedes breadcrumb/title and delays market answer |
| Breadcrumb | Prishtina › market name | Market pages | Visible above pulse panel | Useful location context; market name immediately repeats in title |
| Footer trust copy | What Metrik analyzes; refresh/source statement; exact corpus freshness/dedup counts | All pages | Stacked; long exact timestamp on narrow screens | Duplicates hero/page freshness and About/Methodology trust statements |
| Footer links | About, Methodology, Privacy, Contact/Report, Compare | All pages | Inline/wrapping | Four repeat primary/subnav choices |
| Report-data controls | “Report a data error,” Contact/Report tabs | Market and Contact | Market CTA sits in title/pulse header | Valuable correction path, but competes with first market answer |

## Navigation graph

`/` → market search → `/market/{type}/{slug}`; budget CTA → `/find`; annual teaser → `/statistics`.

`/valuate` ↔ `/find` through Tools subnav. Valuation result may also link to `/compare`, `/rent-yield`, `/statistics` (`web/valuate.html:265-271`).

`/statistics` ↔ `/compare` ↔ `/rent-yield` through Insights subnav. Statistics tables and market links lead to market profiles.

`/market/...` → valuation CTA, statistics distribution, methodology, report-data flow, other markets through search/chips, and Compare through footer.

Every page → About, Methodology, Privacy, Contact/Report, Compare through footer.

## Component system

- `.panel` is the default visual container (`web/static/style.css:468-474`). Variants include accent panels, form panels, chart panels, comparison panels, preview panels, error panels, and cards implemented as panels.
- `.rail-panel` gives market supporting content the same boxed treatment as main analytical sections.
- Chips appear as popular-market links, valuation property summaries, evidence chips, and other compact metadata. Their interaction semantics vary: some navigate, some summarize, some are decorative.
- Badges cover confidence, score, price tier, status, count, and comparison deltas. Similar pill geometry can indicate status, metadata, or action-adjacent content.
- `.info-tip` creates interactive disclosures on headings (`web/static/site.js:271-443`).
- Tables use consistent compact headers and numeric alignment, but many pages combine tables with cards containing the same metrics.
- Two secondary navigation families (`renderToolsSubnav`, `renderInsightsSubnav`) are generated by `web/static/site.js:57-79`.

## Design system

- Layout tokens: narrow ~800–960px, wide ~1140–2400px, market ~1380–2560px; responsive gutters (`web/static/style.css:134-137`).
- Surface tokens: warm background `#f6f5f1`, white panels, `#e2dfd8` borders, 4–12px radii, subtle shadows (`:3-10`, `:140-150`).
- Type: Segoe UI/system body, Georgia display, monospace technical/data option (`:64-67`).
- Accent: dark forest green `#1a4d38`, soft green background, muted sage; amber/brown for caution; blue neutral (`:19-39`).
- Confidence: high green, medium ochre, low tan/brown, insufficient gray (`:43-50`).
- Density tokens provide compact table/card/panel spacing and many small label sizes (`:72-126`).

# PART C — Page-by-page forensic audit

## PAGE: Homepage
ROUTE: `/`
PRIMARY USER QUESTION: What is Metrik and how do I inspect a market?
PRIMARY USER ACTION: Search a market.

ABOVE THE FOLD:
1. Global header and language controls.
2. Hero: “Understand the Prishtina apartment market in 30 seconds.”
3. One-sentence scope explanation.
4. Trust strip: updated-listing count and date.
5. Search panel, budget-find link, popular markets.

SECTION ORDER:
1. Hero/trust.
2. Search and popular markets.
3. Six-step How it works.
4. Latest market insight.
5. Footer.

VISIBLE COMPONENTS: 3 sections, 3 panel-like surfaces, 3 headings, 2 buttons, 20 links, 7 chip-like elements, 1 input, 10 paragraphs.

PRIMARY CTA: Search.  
SECONDARY CTA: Find areas by budget.  
TERTIARY ACTIONS: Six popular markets; annual report; footer links.  
TRUST / METHODOLOGY: trust strip plus three-line footer provenance/freshness.  
TABLES/CHARTS/ACCORDIONS/TOOLTIPS: none.  
BADGES/CHIPS: six popular-market chips plus trust strip.  
FOOTNOTES: footer provenance.  
NEXT STEPS: market profile, Find, statistics.

PAGE PURPOSE TEST: The desired action and current emphasis align. Secondary competition comes from the six-step story and two separate trust surfaces.  
FIRST-5-SECONDS: **CLEAR**.

## PAGE: Valuation
ROUTE: `/valuate`
PRIMARY USER QUESTION: What is this property probably worth?
PRIMARY USER ACTION: Supply property inputs and request estimate.

ABOVE THE FOLD:
1. Header + tools subnav.
2. Title and rent-comparable description.
3. Experimental-validation warning.
4. Input panel.
5. On desktop, pending appraisal and evidence preview are simultaneously visible.

SECTION ORDER:
1. Input form.
2. Error state (hidden until needed).
3. How it works.
4. Pending/result appraisal.
5. Evidence.
6. Market context.
7. Similar examples.
8. Value drivers.
9. Result-only comparison, next steps, comparables/methodology/limitations details.

VISIBLE COMPONENTS (empty): 8 visible sections, ~10 panel/card surfaces, 6 headings, 6 buttons, 9 links, 9 chips, 1 details disclosure, 4 inputs. Result markup adds up to three more details/panels and three next-step CTAs (`web/valuate.html:201-305`).

PRIMARY CTA: Estimate fair rent/sale.  
SECONDARY CTA: Optional asking-price comparison.  
TERTIARY: Similar examples, drivers, next steps, three disclosures.  
TRUST: experimental warning, confidence range, badge, comparables, evidence chips, methodology, limitations.  
ACCORDIONS: optional asking input; result comparables; methodology; limitations.  

Required for “worth?”: point estimate, reasonable range, property summary, status/error.  
Evidence supporting it: confidence, sample/comparables, market position, value drivers.  
How model works: methodology summary, dataset, factors, excluded cases, limitations.

PAGE PURPOSE TEST: Primary task is clear, but empty-state evidence and result placeholders compete before the first estimate.  
FIRST-5-SECONDS: **CLEAR** for action; **PARTIALLY CLEAR** for what result will matter.

## PAGE: Find
ROUTE: `/find`
PRIMARY USER QUESTION: Which areas fit my budget and desired property?
PRIMARY USER ACTION: Set budget/size and find neighborhoods.

ABOVE THE FOLD: header; tools subnav; title/subtitle; guided-discovery panel; at mobile most of the first viewport is controls.

SECTION ORDER: discovery form → How it works → two illustrative recommendation cards → instruction → actual result cards/table or empty/error.

VISIBLE COMPONENTS (preview): 3 sections, 9 panel/card-like surfaces, 2 headings, 10 buttons, 9 links, 6 inputs, 1 details disclosure.  
PRIMARY CTA: Find neighborhoods.  
SECONDARY: advanced filters.  
TERTIARY: open market profile/value typical apartment after results.  
TRUST: confidence badge per result and detailed result table.  

PAGE PURPOSE TEST: The sequence is fundamentally preserved, but example result cards visible before running the tool look like live results and add premature density.  
FIRST-5-SECONDS: **CLEAR**.

## PAGE: Statistics
ROUTE: `/statistics`
PRIMARY USER QUESTION: What is happening in Prishtina’s residential market?
PRIMARY USER ACTION: Read headline story; optionally inspect evidence/download report.

ABOVE THE FOLD: header; insights subnav; title; dataset/update sentence; info tip; PDF CTA; asking-price disclaimer; KPI panel. On 375px the KPI panel begins near the bottom of the first viewport.

SECTION ORDER:
1. Asking-price disclaimer.
2. Four annual KPIs.
3. Sale price distribution with percentile strip and dense sample/cutoff prose.
4. Executive summary.
5. “What is happening?” multi-paragraph conclusions.
6. Data quality/confidence.
7. Market activity chart.
8. Expensive/affordable rankings.
9. Market snapshot and property-type table.
10. Bedroom and size segments.
11. Neighborhood profiles.
12. Where to look (investment and affordability).
13. Sale trend.
14. Rent trend.
15. Most active neighborhoods.
16. Formulas.
17. Methodology.

VISIBLE COMPONENTS: 17 sections, 24 panel/card-like surfaces, 22 headings, 11 buttons, 76 links, 11 badges, 9 tables, ~14 chart nodes, 28 paragraphs, 2 details/disclosures.

PRIMARY CTA: No single behavioral CTA; primary content is the four KPIs.  
SECONDARY: Download PDF.  
TERTIARY: tables/market links/info tips/formulas/methodology.  
TRUST: freshness, disclaimer, sample text, confidence badges, data quality, chart caveats, formulas, methodology, footer provenance.  

PAGE PURPOSE TEST: Current UI makes the existence of a comprehensive annual report more prominent than one coherent market story.  
FIRST-5-SECONDS: **PARTIALLY CLEAR**; page identity is clear, but the primary insight is not.

## PAGE: Compare
ROUTE: `/compare`
PRIMARY USER QUESTION: How are 2–3 neighborhoods different?
PRIMARY USER ACTION: Select neighborhoods and compare.

ABOVE THE FOLD: header; insights subnav; title/subtitle; three selectors; Compare button. At 375px the CTA reaches ~726px.

SECTION ORDER: selection panel → How it works → three placeholder/summary cards → visual comparison charts (after run) → detailed table.

VISIBLE COMPONENTS (empty): 4 sections, 13 panel/card-like surfaces, 4 headings, 3 buttons, 10 links, 3 selectors. Each selector repeats roughly 45 market options. Result code adds five chart metrics and a table (`web/static/compare.js:220-405`).

PRIMARY CTA: Compare.  
SECONDARY: market-profile links from results.  
TRUST: confidence in cards and result table; result freshness.  

PAGE PURPOSE TEST: Purpose is obvious, but the repeated long selectors and three placeholder cards create setup density.  
FIRST-5-SECONDS: **CLEAR** before results; scannability of completed comparison is **PARTIALLY CLEAR** because five metrics, cards, charts, and table repeat.

## PAGE: Rent yield
ROUTE: `/rent-yield`
PRIMARY USER QUESTION: Which neighborhoods have the highest gross asking-price yield?
PRIMARY USER ACTION: Scan/sort ranking and open a neighborhood.

ABOVE THE FOLD: header; insights subnav; title/info tip; one-sentence definition; ranking panel; “show all” button; table begins.

SECTION ORDER: hero → explanation/count control → 6-column table → footer.

VISIBLE COMPONENTS: 2 sections, 2 panels, 2 headings, 4 buttons, 28 links, 1 table, 6 columns, chart-related responsive representation nodes.  
PRIMARY ANSWER: Gross yield ranking.  
TRUST: rent and sale sample counts; asking-price disclaimer.  
FIRST-5-SECONDS: **CLEAR**.

## PAGE: Market profile
ROUTE: `/market/{type}/{slug}`
PRIMARY USER QUESTION: What are prices and market conditions in this place?
PRIMARY USER ACTION: Read headline market metrics; optionally inspect segments or value a property.

ABOVE THE FOLD: header → search/popular-market panel → breadcrumb → title/report control/tier badge → long scope/denominator clarification → four metric cards. At 375px the pulse title begins around 497px and headline values are mostly below the fold.

SECTION ORDER (Ulpiana): toolbar; breadcrumb/pulse; submarkets; sales by type; typical indicators; bedroom table; size table; medium-term trend; two distributions; recent listings; valuation CTA; city comparison rail; percentile rail; confidence rail; footer.

VISIBLE COMPONENTS: 14 sections, 18 panel/card-like surfaces, 15 headings, 11 buttons, 35 links, 23 badge-like nodes, 8 chips, 4 tables, ~15 chart nodes, 17 paragraphs.

PRIMARY CTA: No single CTA; consume market headline.  
SECONDARY: Value apartment.  
TERTIARY: report error, submarkets, recent listings expansion, city distribution, methodology, other markets.  
TRUST: sample beneath every pulse; confidence in segment cells; distribution sample prose; final confidence panel; footer freshness.

PAGE PURPOSE TEST: The desired answer is the four pulse metrics; current design makes toolbar, chips, report control, tier/city delta, scope caveat, and four equal metrics compete before the user can identify one key number.  
FIRST-5-SECONDS: **PARTIALLY CLEAR** desktop; **UNCLEAR** mobile for the important number.

### Lower-data state: Marigona Residence

The page correctly presents “Insufficient data,” explains that 46-listing corpus and breakdowns are indicative, hides unavailable medians with dashes, and retains samples. However, it still shows four empty/weak headline cards, property-type table, typical indicators, no-history trend, ten recent listings, valuation CTA, city comparison, and confidence panel. The reduced data lowers value but not proportional UI volume.

## PAGE: About
ROUTE: `/about`
PRIMARY USER QUESTION: What is Metrik, why does it exist, and can I trust it?
PRIMARY USER ACTION: Understand project and provenance.

SECTION ORDER: hero → origin story → what Metrik is → GroundTruth → nine-stage “how it works” → architecture diagram → methodology summary → metrics/confidence → reading guidance → technical disclosure → limitations → purpose.

VISIBLE COMPONENTS: 10 sections, 10 panels, 11 headings, 32 paragraphs, 1 details disclosure, 13 links.  
FIRST-5-SECONDS: **CLEAR**, but long-form purpose turns into engineering documentation.

## PAGE: Methodology
ROUTE: `/methodology`
PRIMARY USER QUESTION: How are Metrik’s numbers produced and bounded?
PRIMARY USER ACTION: Inspect/cite method.

SECTION ORDER: cite → scope → active corpus → normalization/gazetteer → statistics → sample confidence → deduplication → trends/price quality → limitations → versioning.

VISIBLE COMPONENTS: 10 sections/panels, 11 headings, 10 paragraphs, 12 links.  
FIRST-5-SECONDS: **CLEAR**. Density is appropriate for an explicitly technical destination, though ten identical panels flatten hierarchy.

## PAGE: Contact / Report / Submit listing
ROUTE: `/contact`
PRIMARY USER QUESTION: How do I contact Metrik, report data, or submit a listing?
PRIMARY USER ACTION: Choose one of three tabs and submit the relevant form.

VISIBLE INITIAL STATE: 1 section/panel, 1 heading, 6 buttons, 12 links, 4 visible inputs. Hidden report and listing forms contain many more fields (`web/contact.html:59-158`).  
FIRST-5-SECONDS: **CLEAR**. Tabs appropriately contain complexity.

## PAGE: Alerts
ROUTE: `/alerts`
PRIMARY USER QUESTION: How can I watch markets or receive price alerts?
PRIMARY USER ACTION: Add a market to local watchlist.

SECTION ORDER: local watchlist → add locally → unavailable email alert.  
VISIBLE COMPONENTS: 3 sections/panels, 4 headings, 6 buttons, 2 inputs, long neighborhood select.  
FIRST-5-SECONDS: **CLEAR**, but an entire unavailable-email panel is low-value default content. Watchlist is valuable local utility.

## PAGE: Privacy
ROUTE: `/privacy`
PRIMARY USER QUESTION: What data is collected and how is it used?
SECTION ORDER: collect → use → retention → cookies → contact.  
VISIBLE: 5 panels, 6 headings, 11 paragraphs.  
FIRST-5-SECONDS: **CLEAR**. Density appropriate for legal content.

## PAGE: Terms
ROUTE: `/terms`
PRIMARY USER QUESTION: What conditions govern use?
SECTION ORDER: service → accuracy → acceptable use → liability.  
VISIBLE: 4 panels, 5 headings, 10 paragraphs.  
FIRST-5-SECONDS: **CLEAR**.

## PAGE: 404
ROUTE: unmatched route
PRIMARY USER QUESTION: What happened and where can I go?
VISIBLE: title, one sentence, one return-to-market CTA, global footer.  
FIRST-5-SECONDS: **CLEAR**. Preserve.

# PART D — Information-density analysis

Rendered counts are estimates based on visible DOM at 1280px before user interaction; dynamic result states add content.

| Page | Sections | Panel/card-like | Headings | Buttons | Links | Badges | Chips | Details | Tables | Chart-like | Paragraphs |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Home | 3 | 3 | 3 | 2 | 20 | 0 | 7 | 0 | 0 | 0 | 10 |
| Valuate empty | 8 | 10 | 6 | 6 | 9 | 1 | 9 | 1 | 0 | 0 | 9 |
| Find preview | 3 | 9 | 2 | 10 | 9 | 0 | 0 | 1 | 0 | 0 | 5 |
| Statistics | 17 | 24 | 22 | 11 | 76 | 11 | 0 | 2 | 9 | ~14 | 28 |
| Compare empty | 4 | 13 | 4 | 3 | 10 | 0 | 0 | 0 | 0 | 0 | 6 |
| Rent yield | 2 | 2 | 2 | 4 | 28 | 0 | 0 | 0 | 1 | ~3 | 7 |
| Market Ulpiana | 14 | 18 | 15 | 11 | 35 | 23 | 8 | 0 | 4 | ~15 | 17 |
| Market low-data | 9 | 13 | 8 | 6 | 31 | 5 | 7 | 0 | 2 | ~1 | 13 |
| About | 10 | 10 | 11 | 2 | 13 | 0 | 0 | 1 | 0 | 0 | 32 |
| Methodology | 10 | 10 | 11 | 2 | 12 | 0 | 0 | 0 | 0 | 0 | 10 |
| Contact initial | 1 | 1 | 1 | 6 | 12 | 0 | 0 | 0 | 0 | 0 | 5 |
| Alerts | 3 | 3 | 4 | 6 | 12 | 0 | 0 | 0 | 0 | 0 | 7 |
| Privacy | 5 | 5 | 6 | 2 | 13 | 0 | 0 | 0 | 0 | 0 | 11 |
| Terms | 4 | 4 | 5 | 2 | 13 | 0 | 0 | 0 | 0 | 0 | 10 |
| 404 | 1 | 1 | 1 | 2 | 13 | 0 | 0 | 0 | 0 | 0 | 6 |

Highest simultaneous processing demand: Statistics, Market, Valuation, Compare. Highest content volume that is context-appropriate: Methodology/legal. Lowest density with strongest purpose alignment: 404, Rent Yield, Contact initial state.

# PART E — Copy-density analysis

## Primary copy

- Home hero, search labels, market title/pulse labels, valuation inputs/result, Find inputs/results, Statistics four KPIs, Compare selectors/core metrics, Rent Yield ranking.

## Supporting copy

- How-it-works sequences, popular markets, city comparison, typical indicators, result-next-step links, annual interpretation.

## Technical copy

- Sample sizes, confidence tiers, corpus freshness, asking-price qualification, distribution cutoffs, formulas, dedup details, parser/version descriptions, limitations.

## Repeated/defensive/low-value copy with evidence

| Exact copy/key | File/page | Load issue | Value |
|---|---|---|---|
| “All figures are asking prices … not confirmed transaction prices.” | `web/statistics.html:50-53`, plus distribution notes and annual narrative | Same caveat repeats at page, chart, narrative, About, Methodology, Terms | High information; repeated placement |
| “Apartment market · prices and samples … apartments and studios; listing count covers all property types.” | market pulse, `web/market.html`/`lookup.js` | Necessary to reconcile denominators, but long caveat sits before headline answer | High |
| “Based on {n} observations” / `sample_badge_title` | `web/static/i18n.js:489,1583` | Repeated under four pulse cards and again in confidence/distribution content | High, overexposed |
| `conf_tooltip` and confidence panel thresholds | `i18n.js:1064-1075,2154-2165` | Same sample/confidence relationship appears in tooltip and rail panel | High, duplicated |
| Footer exact corpus line with canonical/raw/removed counts | `web/static/site.js:125-145` | Appears on every page, including privacy/terms/404; visually technical for global footer | Advanced trust detail |
| “Experimental: this model has not yet passed…” | valuation hero | Essential risk disclosure, but precedes task and is paired with more methodology later | High |
| Empty-state “What you get after estimating” + three claims | `web/valuate.html:136-150` | Explains result before action and duplicates result evidence | Medium |
| Find sample recommendation values (€420, 18/64%, €80) | `web/find.html:113-136` | Can be mistaken for live data and adds density before user submits | Low/medium |
| Email alerts unavailable | `web/alerts.html:48-61` | Entire panel says capability does not exist | Low |
| Internal formula targets “Shown in: kpi_total…” | `annual.js:921-990` | Implementation identifiers are irrelevant to most public readers | Low for normal users; medium for auditors |
| “Higher yield is not automatically a better investment.” | rent yield | Useful guardrail, concise | High; preserve |

## Ambiguous or misleading terminology

| Exact label/copy | Evidence | Issue |
|---|---|---|
| Albanian “mesatarja (median)” | Methodology statistics text (`i18n.js` methodology keys) | “Mesatare” commonly implies arithmetic mean; parenthetical English term does not fully resolve it |
| “ÇMIMI MESATAR / SIPËRFAQJA MESATARE” in property-type table | Rendered market SQ vs English “MEDIAN PRICE / MEDIAN AREA” | Language variants imply different statistics |
| Compare card uses `average_sale_psm_eur` | `web/static/compare.js:270,324` | UI copy calls metric median asking sale price; source field name implies average; table later prefers median (`:382`) |
| “Recent valid listings” with “Based on 567 observations” | Ulpiana pulse | Visible value and sample denominator differ; explanation is elsewhere in same panel |
| “$$$$” price tier | Market title | Meaning is not self-explanatory and looks like rating/price level without legend |
| “Strong confidence” | Market confidence | Methodology clarifies it is sample-size tier, not formal statistical confidence; default label can overstate epistemic certainty |
| “Typical apartment” / typical indicators | Market and compare | Area/bedroom/price may be computed from different eligible subsets and need careful denominator reading |

## SQ / EN consistency

Static keys are extensive (`web/static/i18n.js` Albanian section begins near line 18; English near 1115). However, dynamic data strings are incompletely localized. In rendered English:

- Statistics executive summary, conclusions, quality narrative, and some values remain Albanian.
- Market sample statements, confidence terms, bedroom units, rent/sale listing types, and expand control remain Albanian.
- Statistics quality badge displayed “E MIRË” beneath English heading.
- English Find preview values retain `/muaj`.
- Market English DOM included a transient “Not found” heading after re-render, indicating dynamic state/render coupling deserves QA.

The information remains valuable, but mixed-language paragraphs materially increase cognitive load and reduce trust.

# PART F — Navigation complexity

Primary navigation is understandable but broad: Markets, Explore, Statistics, About, Contact. “Explore” routes to Valuation while Find is only revealed through the tools subnav or home CTA. Insights are reachable through primary Statistics, a three-item subnav, homepage teaser, valuation next steps, market links, and footer Compare.

Breadcrumbs are useful only on market pages. Their duplication of the immediate market title is conventional and low-cost.

The footer repeats four routes already in header/subnav. Its exact freshness line makes it a trust/status surface as well as navigation.

Routes with most competing paths:

- `/compare`: insights subnav, footer on every page, valuation next steps, statistics context.
- `/statistics`: primary nav, insights subnav, home teaser, valuation next steps, market distribution links.
- `/valuate`: Explore primary nav, tools subnav, homepage flow, market CTA, Find result CTA.
- `/methodology`: footer, About link, market confidence link, valuation details, statistics methodology.

# PART G — Market page deep audit

| Element | Distinct question? | Meaning obvious? | Current hierarchy | Duplicate? | Technical knowledge | Default visibility evidence |
|---|---|---|---|---|---|---|
| Breadcrumb | Where am I? | Yes | Before title | Repeats title | No | Low-cost |
| Title | Which market? | Yes | H2 inside pulse | No | No | Essential |
| `$$$$` tier + city delta | Is it expensive? | Partly | Beside title/report CTA | City delta repeats rail | Low | Useful but ambiguous/repeated |
| Four pulse metrics | What are prices/inventory? | Mostly | Primary grid | Sale price repeats typical indicators | Low | Essential, but four equal weights |
| Sample under each pulse | Can I trust it? | Yes | Same weight repeated four times | Confidence panel/table samples | Medium | Valuable, aggressive |
| Submarkets | What finer areas exist? | Yes | First panel after pulse | Popular-market chips are separate | No | Useful for specific entities |
| Property-type sale table | Does type change price? | Yes | Early | Typical/segment tables overlap | Medium | Analytical depth |
| Typical indicators | What is typical? | Partly | Three equal metrics | Sale median already in pulse | Low | One metric duplicated |
| Bedroom table | How do rooms affect prices? | Yes | Main column | Compare/statistics segments elsewhere | Medium | Analytical depth |
| Size table | How does size affect price? | Yes | Main column | Statistics segments elsewhere | Medium | Analytical depth |
| Medium-term trend | Is market changing? | Yes | Full panel even when unavailable | Statistics trend | Medium | Empty state still consumes section |
| Price distributions | What is range? | Yes | Two chart panels + prose | Rail percentile distribution repeats sale distribution | Medium | High value, duplicated presentation |
| Recent listings | What observations underlie it? | Yes | Ten dense text rows | Samples already summarized | Low | Evidence, but long |
| Valuation CTA | What next? | Yes | Full panel | Header/Explore path | No | Useful |
| City comparison rail | Is this above/below city? | Yes | Prominent rail | Header delta repeats | Low | Useful support |
| Percentile rail | Where in distribution? | Yes | Prominent rail | Main distribution | Medium | Duplicate analytical view |
| Confidence rail | Are figures reliable? | Yes | Persistent full panel | Samples/badges/tooltips | Medium | High-value trust, repeated |
| Footer freshness | How fresh is corpus? | Yes | Global footer | Other freshness/sample signals | Medium | Advanced trust |

The market page answers many distinct questions, but not all deserve equal default weight. Data contracts should remain; this audit only identifies presentation competition.

# PART H — Valuation page deep audit

States found in markup/runtime:

- Empty: default inputs, preview appraisal, evidence/context/example/driver placeholders.
- Input: rent/sale mode, neighborhood autocomplete, area slider, bedrooms, optional asking-price details.
- Validation: inline neighborhood/loading hints and error panel.
- Loading: submit state controlled by `web/static/app.js`.
- Result: `renderResult` (`app.js:891-999`) fills estimate, interval, badge, summary chips, evidence, context, comparables, drivers, next steps.
- Low confidence/insufficient evidence: confidence notes and error handling (`app.js:975+`), plus server schema fields.
- Asking-price comparison: `renderMarketDelta` (`app.js:804-843`).
- Comparables expanded: `details-comparables`, `web/valuate.html:285-289`.
- Methodology expanded: `details-methodology`, `:291-299`.
- Limitations expanded: `details-limitations`, `:301-305`.
- Error: dedicated error panel (`:93-97`).

The result attempts to answer value, uncertainty, confidence, supporting evidence, neighborhood median, market position, asking-price delta, comparables, causal/value drivers, method, limitations, and three next steps. All are useful; only the estimate/range/property identity are required for the primary question.

Interaction complexity: optional asking price is a reasonable disclosure; three result disclosures are defensible; but evidence chips plus driver chips plus comparables preview plus expanded comparables form multiple parallel evidence systems.

# PART I — Find / Compare / Statistics / Rent Yield deep audits

## Find

The intended sequence is visible and logical. Interruptions are: tools subnav, explanatory subtitle, a full How-it-works panel, two fake/preview result cards, instruction copy, then actual results. Advanced filters are appropriately disclosed. Result cards and result table likely duplicate the same neighborhood metrics (`web/static/find.js:178-299`). Confidence is useful for analytical users but should not displace fit/budget outcome.

## Compare

Selector complexity is high because each of three native selects contains the complete market list with counts. Completed results render summary cards (`compare.js:309-354`), five comparison charts (`:220-307`), and a metric table (`:357-405`), making cards/charts/table three representations of overlapping facts. Confidence appears in cards; freshness appears after the table. On mobile the selection task is clear, but a completed multi-column comparison will require horizontal/vertical scanning.

## Statistics

Primary market story is not singular. Four headline metrics are followed immediately by a large price distribution; interpretation appears later. There are 9 tables and multiple charts. Annual-report information is the whole page, not a supporting layer, while formulas and methodology are appended at equal panel weight. Technical detail dominates after the first few sections.

## Rent yield

Useful data begins quickly: title, one-sentence definition, one caution, table. Six columns are all decision-relevant: neighborhood, yield, rent, sale, rent n, sale n. At 375px heading/info layout overflows and table scanning is horizontally demanding, but yield remains visually dominant and the page avoids multiple redundant visualizations.

# PART J — Homepage audit

Five-second questions:

- What is Metrik? Answered by hero/subcopy.
- What can I do? Search markets; find by budget; estimate property; read statistics.
- What first? Search field is visually dominant.
- Why trust? Updated-listing count/date, then footer provenance.

Competition: the six-step flow enumerates product detail that the search result itself would reveal; six market chips plus Find CTA plus annual-report CTA create many next steps, but hierarchy remains acceptable. The homepage is the best reference for the intended restrained identity.

# PART K — Mobile density audit

| Page | 375px evidence | 768px evidence | Desktop evidence |
|---|---|---|---|
| Home | ~1,876px; title, trust, search, budget CTA, chips fit first viewport; chips wrap 3 rows | ~1,484px; full nav occupies two lines | ~1,395px |
| Valuate | ~2,762px; CTA falls below initial viewport; all preview cards stack | ~2,271px; CTA near 861px | ~1,331px, two-column form/result competition |
| Find | ~1,642px; presets take most of first viewport | ~1,474px | ~1,074px |
| Statistics | ~14,816px; KPI begins near 714px; table/title/info-tip width pressure | ~9,856px; some width overflow | ~9,301px; extremely long even wide |
| Compare | ~1,897px empty | ~1,699px | ~987px empty |
| Rent yield | ~2,318px; heading overflow and 6-column table | ~1,667px | ~1,539px |
| Ulpiana market | ~5,460px; headline title only begins around 497px; width pressure in main/table | ~4,083px; chart pair/table overflow | ~3,087px; rail adds parallel density |

At 375px the navigation header uses brand row, hamburger/language row, then subnav, consuming 150–280px before each page’s answer. Market chips wrap into three rows before the market title. Statistics and market show measurable internal overflow even when the document itself does not widen beyond the viewport; these are dense child elements clipped or scroll-contained by ancestors.

# PART L — Trust vs clutter analysis

| Signal | Classification | Evidence/assessment |
|---|---|---|
| Asking-price vs transaction caveat | ESSENTIAL TRUST SIGNAL | Necessary for every decision surface; currently repeated multiple times per statistics experience |
| Sample n beside a primary metric | ESSENTIAL TRUST SIGNAL | Directly qualifies number |
| Confidence tier | USEFUL TRUST SIGNAL | Rapid interpretation; should remain available |
| Exact confidence thresholds | ADVANCED TRUST DETAIL | Repeated in methodology and market rail |
| Corpus freshness date | USEFUL TRUST SIGNAL | Useful once per page/context |
| Exact canonical/raw/removed footer counts | ADVANCED TRUST DETAIL | Global repetition on all pages |
| Dataset/version | ADVANCED TRUST DETAIL | Important for citation and reproducibility |
| Distribution range/percentiles | USEFUL TRUST SIGNAL | Supports interpretation of medians |
| Separate confidence badge + sample line + tooltip + panel | DUPLICATED TRUST SIGNAL | Four layers carry substantially same fact |
| Decorative tier `$$$$` without legend | LOW-VALUE TRUST DECORATION | Adds status-like noise but little verifiable meaning |
| Report-data control | USEFUL TRUST SIGNAL | Operational accountability, but need not precede headline answer |
| Dedup explanation | ADVANCED TRUST DETAIL | Essential methodology, excessive in global footer and About repetition |

# PART M — Technical-depth preservation map

| Feature | Technical value | Audience | Current location/prominence | Needed first-time? |
|---|---|---|---|---|
| Sample size | Reliability/denominator | All, especially analytical | Repeated near metrics/tables/tooltips | Yes near primary number |
| Confidence tier | Fast stability cue | All | Badge and full panel | Helpful, not full explanation |
| Methodology | Reproducibility | Technical | Dedicated page plus multiple local blocks | No, but discoverable |
| Distribution/percentiles | Shows spread/outliers | Analytical | Main charts + rail | Not always |
| Freshness | Timeliness | All | Home, hero, result, footer | Yes once |
| Dedup/canonical counts | Inventory integrity | Technical | Footer/About/Methodology | No |
| Historical trends | Direction over time | Analytical | Statistics/market | Secondary |
| Bedroom/size/type breakdowns | Segment heterogeneity | Analytical and serious shoppers | Market/statistics tables | Secondary |
| Comparables | Evidence behind valuation | Property users | Preview + details | Summary yes; full list no |
| Limitations | Prevents misuse | All/technical | Many pages and dedicated docs | Concise form yes |

In every case, **data should remain available**. The audit questions only default visibility and repeated presentation.

# PART N — Component overuse / style-system audit

## Panels/cards

Used on nearly every section. `.panel` combines background, border, radius, padding, margin, shadow (`style.css:468-474`). Statistics and market turn nearly every topic into a visually equal white box. About/Methodology become long sequences of identical boxes. The result is “boxes inside boxes” where chart panels, grid cards, badges, and tables sit inside outer panels.

## Rail panels

Market rail holds city comparison, distribution, confidence. All are useful supporting analysis, but identical panel weight and desktop side-by-side layout compete with the main column. When stacked on mobile they lose “supporting” status and become more primary sections.

## Chips

Popular-market chips navigate; property-summary chips describe; evidence chips explain method; preset buttons look chip-like and act. Similar compact rounded shapes carry different affordances. Ulpiana shows eight chip-like nodes before counting many badges.

## Badges

Confidence, score, status, sample, delta, and tier variants overlap. Market count of 23 badge-like nodes demonstrates semantic proliferation. `confidence.js:16-31` intentionally hides raw n in the visible badge and moves it to tooltip, yet other surfaces show n directly, producing inconsistent disclosure.

## Tooltips/info icons

Shared code dynamically attaches/refreshes tooltip nodes (`site.js:271-443`). Statistics and market use them on many headings. On mobile audit measurements show `.info-tip` width anomalies/overflow. Tips are most justified for concise terminology; least justified where an explanatory paragraph immediately follows.

## Tables/charts

Tables are consistent, inspectable, and credible. Overuse occurs when identical metrics also appear in cards and charts. Statistics has nine tables plus many charts; Compare result has cards, charts, and table for the same neighborhood set.

## Page-specific duplication

Valuation invents `valuate-*` panels/cards/chips on top of global `.panel`; Compare/Find share `compare-*` patterns; market uses `pulse-*`, `typical-*`, chart-panel, rail-panel, and evidence/status patterns. Similar information receives different component names and sometimes different visual prominence.

# PART O — Current Metrik visual DNA

- Warm off-white canvas and white analytical surfaces.
- Dark forest-green accent; restrained sage fills.
- Georgia display titles paired with pragmatic system sans-serif body.
- Serious, quiet, non-promotional tone.
- Compact uppercase section labels and tabular numeric emphasis.
- Rounded but not playful geometry (mostly 6–10px).
- Thin warm-gray borders and very subtle shadows.
- Confidence expressed through muted green/ochre/tan/gray rather than saturated alerts.
- Data tables with clear headers, right-sized density, and conservative color.
- Explicit sample size, asking-price caveats, freshness, and methodology.
- Large outer gutters on desktop; narrow readable prose columns.
- Bilingual product identity and Kosovo/Prishtina specificity.

These traits should survive simplification. The audit does not support replacing the identity with a generic dashboard aesthetic.

# PART P — Clutter register

| ID | Page | Element | Type | Severity | Evidence | Why it may hurt UX | Information value |
|---|---|---|---|---|---|---|---|
| CLUTTER-001 | Statistics | 17-section annual page | EXCESSIVE_VERTICAL_LENGTH/METRIC_OVERLOAD | HIGH | `statistics.html:50-282`; ~14.8k px mobile | No singular story; fatigue | HIGH |
| CLUTTER-002 | Statistics | 9 tables + many charts | TABLE_OVERLOAD/CHART_OVERLOAD | HIGH | rendered counts; `annual.js:374-913` | Repeated scanning modes | HIGH |
| CLUTTER-003 | Statistics | Public formulas with internal IDs | TECHNICAL_DETAIL_TOO_EARLY | HIGH | `annual.js:921-990` | Implementation detail on narrative page | MEDIUM |
| CLUTTER-004 | Market | Toolbar and chips before answer | NAVIGATION/CHIP_OVERUSE | HIGH | title begins ~497px on phone | Delays primary number | MEDIUM |
| CLUTTER-005 | Market | 23 badge-like elements | BADGE_OVERUSE/TRUST_SIGNAL_REPETITION | HIGH | rendered Ulpiana count | Status noise across tables/cards | HIGH |
| CLUTTER-006 | Market | Main distribution + percentile rail | DUPLICATE_INFORMATION/CHART_OVERLOAD | MEDIUM | market sections | Same sale spread twice | HIGH |
| CLUTTER-007 | Market | Samples + confidence tooltip + panel | TRUST_SIGNAL_REPETITION | HIGH | `confidence.js`, i18n confidence keys | Same trust concept 3–4 times | HIGH |
| CLUTTER-008 | Market | Empty trend panel on low-data page | LOW_VALUE_EXPLANATION | MEDIUM | Marigona render | Full section conveys absence only | LOW |
| CLUTTER-009 | Valuate | Five preview/result panels before result | PANEL_OVERUSE/TECHNICAL_DETAIL_TOO_EARLY | HIGH | `valuate.html:119-196` | Splits focus from form | MEDIUM |
| CLUTTER-010 | Valuate | Evidence chips + drivers + comparables + method | REPETITION/WEAK_GROUPING | MEDIUM | `app.js:681-1013` | Parallel explanations of evidence | HIGH |
| CLUTTER-011 | Find | Fake recommendation cards | DUPLICATE_INFORMATION/LOW_VALUE_EXPLANATION | MEDIUM | `find.html:113-136` | Look like live results | LOW |
| CLUTTER-012 | Compare | Three repeated long selectors | EXCESSIVE_HORIZONTAL_DENSITY/UNNECESSARY_INTERACTION | MEDIUM | rendered option lists | High setup cost | HIGH |
| CLUTTER-013 | Compare | Cards + charts + table | DUPLICATE_INFORMATION/CARD_OVERUSE | HIGH | `compare.js:220-405` | Same facts repeated in 3 modes | HIGH |
| CLUTTER-014 | Rent yield | Six-column mobile table | MOBILE_DENSITY | MEDIUM | rendered table | Hard scan on 375px | HIGH |
| CLUTTER-015 | About | Engineering pipeline + architecture + method | TECHNICAL_DETAIL_TOO_EARLY/EXCESSIVE_VERTICAL_LENGTH | HIGH | `about.html` sections through `:278+` | About purpose obscured by internals | HIGH |
| CLUTTER-016 | Methodology | Ten identical panels | PANEL_OVERUSE/WEAK_HIERARCHY | MEDIUM | `methodology.html:26-106` | All topics look equal | HIGH |
| CLUTTER-017 | Alerts | Unavailable email panel | LOW_VALUE_EXPLANATION | MEDIUM | `alerts.html:48-61` | Promotes non-functionality | LOW |
| CLUTTER-018 | Global | Exact corpus/dedup line every footer | TECHNICAL_DETAIL_TOO_EARLY/REPETITION | MEDIUM | `site.js:125-145` | Adds technical noise everywhere | HIGH |
| CLUTTER-019 | Global | Primary + subnav + footer duplicates | NAVIGATION/REPETITION | MEDIUM | `site.js:57-120`; footer | Too many paths to same routes | MEDIUM |
| CLUTTER-020 | Global | Info icons on many headings | TOOLTIP_OVERUSE/MOBILE_DENSITY | MEDIUM | `site.js:271-443` | Interaction and layout noise | MEDIUM |
| CLUTTER-021 | Global | Nearly every section boxed | PANEL_OVERUSE/BORDER_OVERUSE | HIGH | `.panel`; page counts | Containment loses meaning | MEDIUM |
| CLUTTER-022 | Market | Report-error button in title row | CTA_COMPETITION | LOW | rendered pulse header | Competes with headline consumption | HIGH |
| CLUTTER-023 | Home | Six-step flow | LOW_VALUE_EXPLANATION | LOW | `index.html:60-68` | Explains all outputs before search | MEDIUM |
| CLUTTER-024 | Mobile | Stacked header/subnav | MOBILE_DENSITY | MEDIUM | 150–280px before content | Delays page identity/action | MEDIUM |
| CLUTTER-025 | English | Mixed-language dynamic content | COPY/INCONSISTENT_COMPONENT | HIGH | rendered EN annual/market | Breaks comprehension and trust | HIGH |

# PART Q — Duplication register

| ID | Information | Repeated locations | User impact | Evidence |
|---|---|---|---|---|
| DUP-001 | Asking prices, not transactions | Statistics disclaimer, distribution notes, summary, About, Methodology, Terms | Caveat fatigue | `statistics.html:50-63`; content pages |
| DUP-002 | Sample/confidence | Pulse sublines, table badges, tooltips, distribution prose, confidence rail | Trust overwhelms answer | `confidence.js`; market render |
| DUP-003 | Market sale median | Pulse, typical indicators, city comparison, distribution, segment tables | Hard to know canonical answer | market render |
| DUP-004 | City delta | Market title badge and city comparison rail | Same comparison twice | market render |
| DUP-005 | Sale distribution | Main chart and rail percentile strip | Repeated range story | market render |
| DUP-006 | Freshness | Home trust, statistics hero, compare results, every footer | Repeated status | `home.js`, `annual.js`, `compare.js`, `site.js` |
| DUP-007 | Methodology/confidence thresholds | About, Methodology, market rail, valuation details, statistics | Documentation repeated locally | respective HTML/i18n |
| DUP-008 | Compare metrics | Summary cards, charts, detail table | Three representations compete | `compare.js:220-405` |
| DUP-009 | Find results | Cards and detailed table | Same rows twice | `find.js:178-299` |
| DUP-010 | Valuation evidence | Evidence chips, drivers, comparable preview/details, methodology | Fragmented rationale | `app.js:681-1013` |
| DUP-011 | Navigation routes | Header/subnav/footer/in-page next steps | Choice overload | `site.js`, footer |
| DUP-012 | About vs Methodology | Corpus, normalization, dedup, statistics, confidence, limits | Two documents overlap | `about.html`, `methodology.html` |

# PART R — Hierarchy failure register

| ID | Page | Primary goal | Competing element | Why hierarchy is weakened |
|---|---|---|---|---|
| HIER-001 | Market | Read market prices | Search toolbar/popular chips | Appears before title and numbers |
| HIER-002 | Market | Read headline metrics | tier, report CTA, denominator paragraph, equal four-card grid | No single key answer |
| HIER-003 | Statistics | Understand market story | distribution, conclusions, quality, rankings, segments, formulas | All panels nearly equal |
| HIER-004 | Valuate | Submit property | result previews/evidence placeholders | Secondary content visible before action |
| HIER-005 | Compare | Select and compare | How-it-works + placeholder cards | Preview content competes with setup |
| HIER-006 | About | Understand Metrik | GroundTruth pipeline/architecture | Engineering depth dominates story |
| HIER-007 | Mobile market | See primary numbers | header + toolbar + chips + breadcrumb/title controls | Metrics pushed below fold |
| HIER-008 | Mobile statistics | See headline story | subnav, metadata, info tip, PDF, disclaimer | KPI panel barely enters first viewport |

# PART S — Copy problem register

| ID | Page | Exact label/copy | Issue | Source file/key | Severity |
|---|---|---|---|---|---|
| COPY-001 | Methodology SQ | “mesatarja (median)” | AMBIGUOUS/INCONSISTENT | `methodology_stats_li1` in `i18n.js` | HIGH |
| COPY-002 | Market SQ | “ÇMIMI MESATAR / SIPËRFAQJA MESATARE” | MISLEADING | property-type table labels | HIGH |
| COPY-003 | Compare | “Median asking sale price (€/m²)” backed by `average_sale_psm_eur` in card/chart path | MISLEADING/INCONSISTENT | `compare.js:270,324,382` | HIGH |
| COPY-004 | Market | `$$$$` | AMBIGUOUS | market header rendering | MEDIUM |
| COPY-005 | Market | long apartment/all-property denominator sentence | TOO_LONG/TOO_DEFENSIVE | market pulse copy | MEDIUM |
| COPY-006 | Statistics | formula “Shown in: kpi_total…” | TOO_TECHNICAL | annual formulas payload/render | HIGH |
| COPY-007 | Global footer | exact canonical/raw/dedup counts | TOO_TECHNICAL/REPEATED | `site.js:133-145` | MEDIUM |
| COPY-008 | Valuate | Experimental validation warning | TOO_DEFENSIVE but necessary | `valuate_validation_warning` | LOW |
| COPY-009 | Alerts | “Email alerts are not available yet…” | LOW_VALUE/REPEATED | `alerts_email_hint` | MEDIUM |
| COPY-010 | English annual | Albanian narrative under English headings | INCONSISTENT | API-derived narrative/`annual.js` | HIGH |
| COPY-011 | English market | “Bazuar në …”, “qira”, “dhoma”, Albanian confidence | INCONSISTENT | API/dynamic labels/`lookup.js` | HIGH |
| COPY-012 | Find preview | hard-coded illustrative €/month values | AMBIGUOUS | `find.html:113-136` | MEDIUM |

# PART T — UX friction register

| ID | Page | User task | Friction | Evidence | Severity |
|---|---|---|---|---|---|
| UX-001 | Market mobile | Find primary price | Must pass toolbar/chips/title controls first | value below initial viewport | HIGH |
| UX-002 | Statistics | Identify main story | 17 sections without clear priority | counts/9k–14.8k px | HIGH |
| UX-003 | Compare | Choose areas | Same ~45-option list repeated 3× | rendered selectors | MEDIUM |
| UX-004 | Compare mobile | Scan differences | cards/charts/table and wide data | `compare.js` result system | HIGH |
| UX-005 | Valuate | Enter property | Form plus visible result preview | empty-state layout | MEDIUM |
| UX-006 | English user | Read dynamic analysis | Mixed languages | rendered bilingual pass | HIGH |
| UX-007 | Market/statistics mobile | Use info tips | icon/title width pressure | overflow measurements | MEDIUM |
| UX-008 | Rent yield mobile | Compare row values | six columns | rendered table | MEDIUM |
| UX-009 | Low-data market | Understand insufficiency | Large normal-page structure remains | Marigona state | MEDIUM |
| UX-010 | Alerts | Set email alert | Feature visibly unavailable | alerts email panel | LOW |

# PART U — Preservation register

| ID | Element | Page | Why it works | Why preserve |
|---|---|---|---|---|
| KEEP-001 | Hero search | Home | Immediate and legible | Core product entry |
| KEEP-002 | Warm neutral/green palette | Global | Serious, distinctive, calm | Brand DNA |
| KEEP-003 | Georgia display + system body | Global | Editorial authority + readability | Brand DNA |
| KEEP-004 | Explicit asking-price caveat | Analytical pages | Prevents misuse | Essential trust |
| KEEP-005 | Sample size | Metrics | Grounds claims in evidence | Essential trust |
| KEEP-006 | Confidence color system | Market/statistics | Quick stability cue | Analytical credibility |
| KEEP-007 | Market segmentation data | Market | Answers real analytical questions | Technical depth |
| KEEP-008 | Valuation range, not only point | Valuate | Communicates uncertainty | Responsible output |
| KEEP-009 | Advanced filters disclosure | Find | Keeps initial form simpler | Good progressive disclosure |
| KEEP-010 | Contact tabs | Contact | Contains three different workflows | Effective interaction |
| KEEP-011 | Rent-yield direct table | Rent yield | Purpose-first, compact | Model for discipline |
| KEEP-012 | Methodology versioning/citation | Methodology | Reproducible and credible | Technical credibility |
| KEEP-013 | Data-error reporting | Market/contact | Accountability loop | Trust and quality |
| KEEP-014 | 404 simplicity | 404 | Clear recovery | Avoid adding clutter |

# PART V — Change-impact map

This is a dependency map, not an implementation plan.

| Area | HTML | JS | CSS/i18n | API/schema/backend |
|---|---|---|---|---|
| Global shell/nav/footer | all HTML mounts; `partials/site-footer.html` | `site.js` | global/nav/footer selectors; nav/footer keys in `i18n.js` | `services/web_shell.py`, `/api/corpus-meta` producer |
| Home hero/search/trust | `index.html` | `home.js`, `search.js` | hero/search/trust/chip selectors; home keys | search endpoints; corpus meta |
| Market pulse and sections | `market.html` | `lookup.js`, `distribution.js`, `charts.js`, `confidence.js`, `feedback.js`, `watchlist.js` | market/pulse/rail/table/chart/badge selectors; market keys | `schemas/lookup.py`, `services/lookup.py`, `services/lookup_cache.py`, `routes_markets.py` |
| Valuation form/result | `valuate.html` | `app.js`, `confidence.js`, `format.js` | `valuate-*`, chips, accordion; valuation keys | `schemas/valuation.py`, analytics valuation, valuation API route/service |
| Find | `find.html` | `find.js` | compare/find/form/card/table selectors; find keys | `schemas/budget_match.py`, `services/budget_match.py` |
| Statistics | `statistics.html` | `annual.js`, `charts.js`, `distribution.js`, `reports.js` | annual/chart/table/panel selectors; annual keys | `data/api/annual_report.json`, annual schemas/analytics/report services |
| Compare | `compare.html` | `compare.js`, `charts.js`, `confidence.js` | compare cards/workspace/table; compare keys | lookup/market compare endpoints and lookup payload fields |
| Rent yield | `rent-yield.html` | `rent-yield.js`, `charts.js` | yield/table/responsive selectors; yield keys | `schemas/rent_yield.py`, `services/rent_yield.py`, `data/api/rent_yield.json` |
| About/Methodology | `about.html`, `methodology.html` | `methodology.js` for citation metadata | prose/pipeline/accordion; about/method keys | methodology public service/version metadata |
| Contact/report/listing | `contact.html` | `contact.js`, `feedback.js` | form/tabs; contact keys | contact/feedback schemas and `routes_product_writes.py` |
| Alerts/watchlist | `alerts.html` | `alerts.js`, `watchlist.js` | alert/form styles; alert keys | `schemas/alerts.py`, `services/alerts.py` |
| Page routing/404 | all page files, `404.html` | shared site | shared | `api/routes_pages.py:60-198`, app 404 handling |

Changing default visibility should not delete or narrow backend fields. Market distributions, samples, confidence, breakdowns, comparables, formulas, and freshness can remain in payloads even if future presentation changes.

# PART W — Unknowns / unverified issues

- Contact/report/listing submissions were not sent; the audit inspected forms and visible states only, to preserve read-only behavior.
- Alerts were not persisted and watchlist state was not changed.
- Valuation submission was not executed because the current page clearly labels the model experimental and the audit did not need to mutate product state; result hierarchy was reconstructed from real markup/runtime code.
- Compare/Find result requests were not submitted during the final audit pass; their result structures were inspected in JS and HTML, and initial preview states were rendered.
- Hover tooltip bubbles were not exhaustively opened one by one; their keys, construction, and visible icon frequency were inspected.
- Exact chart count is approximate because DOM queries include chart wrappers/canvases and responsive representations.
- The dynamic count-up animation temporarily displays intermediate values during automated snapshots (`web/static/site.js:152-213`). Numeric claims in this report use stable payload/text evidence, not mid-animation snapshots.
- No external production deployment was inspected; findings describe the current local working tree and its bundled/current data artifacts.
- Chrome was unavailable through the browser-control provider, so rendered work used the Codex in-app browser. It supported explicit viewport overrides and the real local application.

## Self-check

- [x] Every public page inspected.
- [x] Global shell inspected.
- [x] SQ and EN inspected.
- [x] 375, 768, 1280, and 1440 widths considered.
- [x] Primary user goal identified per page.
- [x] Information density documented.
- [x] Copy density documented.
- [x] Redundancy documented.
- [x] Trust signals separated from clutter.
- [x] Technical depth mapped.
- [x] Existing strengths preserved.
- [x] CSS/design-system structure inspected.
- [x] Change dependencies mapped.
- [x] Findings tied to repository evidence.
- [x] No source code modified.
- [x] No redesign implemented.

AUDIT COMPLETE — NO CODE CHANGES MADE

READY FOR:
1. UX diagnosis
2. simplification brainstorming
3. direction selection
4. detailed implementation plan
