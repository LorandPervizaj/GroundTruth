# Metrik structured-minimalism refinement report

Date: 2026-09-18

## A. Problems confirmed

| Reported issue | Reproduced | Finding |
|---|---|---|
| Containers feel unfinished | Yes | First-pass About/Methodology rules removed nearly every surface distinction. |
| Disclosure affordance weak | Yes | Several summaries appeared as static headings with no reliable chevron, hover, or focus cue. |
| About feels incomplete | Yes | Long prose blocks floated between thin dividers and resembled an unstyled document. |
| Find skeleton removed | Yes | Result-shaped preview markup remained, but first-pass CSS permanently suppressed it. |
| Market KPI block still cluttered | Yes | Four equal cards repeated “based on” sentences and the denominator caveat led the section. |
| Charts inconsistent | Yes | Distribution charts had a separate axis/title/bar treatment from shared line/bar charts. |
| Spacing too tight | Yes | Disclosures, headline metrics, and major sections lacked distinct spacing levels. |
| Remaining copy excessive | Yes | Market scope/denominator prose appeared before the answer; sample metadata was sentence-form and repeated. |
| Remaining graphs unnecessary | Partly | KPI sparklines existed inside headline markup but were hidden. They were removed from the headline structure; trend, distribution, comparison, and composition charts remain optional or purposeful. |

## B. Changes implemented

| File | Purpose |
|---|---|
| `web/market.html` | Rebuilt headline as one dominant metric plus three supporting metrics; removed KPI canvases; moved scope caveat into an inline disclosure. |
| `web/find.html` | Converted the result preview into an announced loading region. |
| `web/static/lookup.js` | Emits compact localized sample metadata and combined primary confidence metadata. |
| `web/static/find.js` | Reveals result-shaped skeleton immediately on submit. |
| `web/static/compare.js` | Shows a result-shaped skeleton only during a real comparison request. |
| `web/static/charts.js` | Standardized grid, border, line width, point radius, bar radius, and hover color. |
| `web/static/distribution.js` | Aligned histogram bar radius and removed its unique vertical-axis title treatment. |
| `web/static/i18n.js` | Added SQ/EN compact sample, market-scope, inventory, and loading labels. |
| `web/static/style.css` | Added the three-level surface language, disclosure system, loaders, editorial About grouping, Methodology spacing, Market KPI hierarchy, and reduced-motion support. |
| Core page HTML files | Bumped changed static asset versions. |

## C. Container system

- Level A — primary surfaces: market answer, forms, results, major charts, and primary comparison tables retain a subtle white surface, intentional padding, restrained border/radius, and occasional subtle shadow.
- Level B — section surfaces: disclosure groups, About conceptual blocks, Statistics exploration gateway, and methodology citation use a lighter border/tint with little or no shadow.
- Level C — inline groups: ordinary prose, supporting metadata, and simple documentation sections rely on whitespace and dividers.

The result restores grouping without returning to nested cards or a panel around every paragraph.

## D. Disclosure system

- Primary disclosures use native `details/summary`, a full-width 56px-or-larger header, right chevron, supporting description, hover tint, visible keyboard focus, and a connected expanded surface.
- Secondary accordions (`accordion`, advanced filters, annual methodology, and About technical detail) now use the same chevron/hover/focus grammar at a quieter scale.
- The Market scope note uses a compact inline disclosure rather than leading with denominator prose.
- Statistics’ button-driven expansion is now housed in a Level-B surface with directional arrow state.
- Keyboard QA confirmed Tab/focus and Enter activation on the Market analysis disclosure.

## E. Skeleton system

- Find: result-shaped two-card skeleton is shown immediately after submit, keeps approximate result geometry, uses `role=status`, `aria-live=polite`, and `aria-busy=true`, and is replaced cleanly by results.
- Compare: its existing skeleton is now visible only during an actual compare request, not in the untouched empty state.
- Valuation: only the main appraisal-result skeleton is restored while a calculation is running; secondary fake evidence architecture stays hidden.
- Market and Statistics retain their existing page-level skeletons; Rent Yield retains its established loading treatment.
- Skeleton animation is disabled under `prefers-reduced-motion`.

Artificially delayed Find QA confirmed the skeleton was visible with `aria-busy=true` before results arrived. Screenshot: `after/find-loading-375.png`.

## F. Market headline redesign

Before:

`title → long denominator caveat → four equal cards → repeated full sample sentences → embedded KPI canvases`

After:

`title → dominant sale €/m² answer → compact sample + confidence → three-metric supporting strip → optional sample-scope disclosure → city context / detailed analysis`

The values remain API-driven. “Bazuar në X vëzhgime” is now compact `X vëzhgime` / `X observations`; inventory explicitly says “all property types.”

## G. Chart system

Shared rules: inherited Metrik typography; forest/sage palette; muted grid; no decorative chart border; 2px trend strokes; 1.5px points and 4px hover points; 4px bar radius; consistent external tooltips where supported; no x-grid on standard time-series charts; no separate histogram axis-title aesthetic.

| Page / chart | Purpose | Default | Shared style | Mobile | Tooltip | Legend |
|---|---|---:|---:|---:|---:|---:|
| Statistics activity | composition/change | Yes | Yes | Checked | Yes | Necessary (sale/rent) |
| Statistics sale/rent trends | trend | No, detailed analysis | Yes | Checked | Yes | Only when series need distinction |
| Statistics distribution | distribution | No, detailed analysis | Yes | Checked | Yes | Tail legend retained |
| Statistics ranking/segment charts | comparison/composition | No, detailed analysis | Yes | Checked | Yes | Minimal |
| Market sale/rent history | trend | No, detailed analysis | Yes | Checked | Yes | No redundant legend |
| Market sale/rent distributions | distribution | No, detailed analysis | Yes | Checked | Yes | Sale tail context retained |
| Compare metric charts | comparison | No, optional visual comparison | Yes | Checked | Yes | Labels provide entity context |
| Rent Yield chart | comparison | Yes | Yes | Checked | Yes | Minimal |
| Headline KPI sparklines | duplicated headline values | Removed from headline | N/A | N/A | N/A | N/A |

No calculation or distribution data was changed.

## H. Copy reduction

- Removed the full apartment/all-property denominator paragraph from the Market headline.
- Replaced four repeated sentence-form sample statements with compact metadata.
- Combined the primary sample and confidence into one line.
- Kept the exact denominator explanation available under “About this market sample.”
- Kept Statistics’ secondary narratives and formulas behind the existing detailed-analysis layer.

## I. Spacing changes

- Micro: labels, values, and metadata use the smallest spacing level.
- Component: metric internals and disclosure descriptions use 12–16px relationships.
- Group: supporting KPI columns and chart headings use roughly 20–24px separation.
- Section: Market blocks and disclosure groups use a clear 32–40px rhythm.
- Editorial: About and Methodology conceptual sections use the largest existing spacing tokens without creating decorative empty space.

## J. Screenshots

- Post-first-pass baseline: `reports/METRIK/ui-refinement/baseline/`
- Corrected result: `reports/METRIK/ui-refinement/after/`
- Loading state: `reports/METRIK/ui-refinement/after/find-loading-375.png`
- English expanded Market: `reports/METRIK/ui-refinement/after/market-neighborhood-ulpiana-en-1280.png`

## K. Visual QA

- Captured Home, Ulpiana Market, Valuation, Find, Statistics, Compare, About, Methodology, and Rent Yield at 375, 768, and 1280px.
- No horizontal overflow was found in the completed matrix.
- No new page/console errors occurred during representative capture.
- Market KPI hierarchy remains coherent when the three-column support strip becomes one divided mobile list.
- About now reads as deliberately composed: two main editorial surfaces, one obvious depth disclosure, an inline limitations section, and a tinted closing purpose surface.
- Methodology reads as technical documentation with generous dividers and one primary citation surface.

## L. Accessibility QA

- Native disclosure keyboard semantics retained.
- Full summary header is clickable/tappable; chevron does not overlap wrapped descriptions.
- `:focus-visible` is explicit on primary and secondary disclosure styles.
- Market disclosure focus + Enter activation verified in Chromium.
- Find loader announces status and busy state; no fake numeric data is visibly presented.
- Existing chart text equivalents and `aria-labelledby` distribution summaries retained.
- Reduced-motion rule disables shimmer and disclosure transitions.

## M. SQ/EN QA

- Added every new string in both language packs; parity tests pass.
- Verified compact samples, inventory qualifier, market scope, loading label, disclosure labels, and chart UI through runtime language switching.
- No hardcoded visible English was added to the Albanian experience.

## N. System QA

- Full suite: **593 passed, 7 skipped, 0 failed**; one existing Starlette/httpx deprecation warning; 210.25s.
- Browser E2E: **6 passed, 0 failed**.
- Targeted UI/i18n/distribution suite: **23 passed, 0 failed**.
- `git diff --check`: clean; only repository line-ending advisories.
- Routes visually verified: `/`, `/market/neighborhood/ulpiana`, `/valuate`, `/find`, `/statistics`, `/compare`, `/about`, `/methodology`, `/rent-yield`.
- Existing lookup, compare, valuation, budget-match, annual-report, search, rent-yield, methodology, and public-route contract tests are included in the full suite.

## O. Remaining issues

- **BLOCKER:** none.
- **IMPORTANT:** none introduced by this refinement.
- **OPTIONAL:** About remains intentionally substantive. A future copywriting-only pass could shorten the first two editorial sections without changing layout.
- **OPTIONAL:** Compare still uses three native selectors; replacing them with a single autocomplete/chip interaction remains a separate interaction change, not necessary for this visual correction.
