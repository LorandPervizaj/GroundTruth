# Metrik UI/UX Harmony Refinement — Final Report

Date: 2026-09-18

## A. Harmony problems reproduced

| Issue | Page | Evidence | Cause |
|---|---|---|---|
| Major sections visually touched | Market | Baseline screenshots at all four widths; computed section margins were `0px` | Three rules referenced undefined `--space-7`, invalidating their margins |
| KPI support values read as separate fragments | Market | Baseline summary had weak containment and mobile stacked every value independently | No shared support surface and no deliberate mobile composition |
| Editorial pages felt ruled and sequential | About, Methodology | Baseline showed a hairline before nearly every narrative section | Generic documentation rule applied `border-top` to every panel |
| Charts and tables floated inside sections | Statistics and analytical pages | Baseline chart/table edges lacked a consistent secondary frame | Plot and tabular objects had no shared surface treatment |
| Loading could mix with stale output | Find | Throttled repeat search initially left old results beneath the loader | Request start did not hide prior results, empty state, and error state |
| Find loader was too sparse | Find | Only two placeholder cards were present | Skeleton geometry did not meet the 3–5 result guidance |

## B. Layout/grid changes

- Retained the established reading, wide-data, and market container modes.
- Constrained Methodology to a 64rem editorial reading grid and kept About on its shared 70rem composition grid.
- Aligned headings, prose, disclosures, charts, and tables to their parent section edges.
- Standardized workspace row rhythm for Valuation and Compare without changing their responsive two-column structure.

## C. Section hierarchy

- Primary answer: dominant Market value and restrained action/report control.
- Summary group: one cohesive supporting KPI strip.
- Analysis: heading/context plus a softly contained plot or table object.
- Disclosure: shared radius, chevron, hover, focus, collapsed spacing, and integrated expanded body.
- Editorial: open prose by default, with selective large/tinted conceptual chapters.

## D. Spacing system

Added semantic rhythm tokens separate from component padding:

- `--gap-group` for closely related groups.
- `--gap-section` for distinct sections.
- `--gap-section-major` for editorial chapter transitions.

Mobile preserves deliberate vertical separation with slightly tighter values. The broken `--space-7` references were removed, restoring Market section gaps.

## E. Surface hierarchy

- Primary surfaces remain reserved for forms, key answers, and result blocks.
- Secondary surfaces now frame grouped Market KPIs, plots, tables, disclosures, and selected Methodology chapters.
- Open surfaces are the default for straightforward narrative content.
- Existing forest, sage, neutral, border, radius, and shadow tokens were reused; no new hue system was introduced.

## F. Divider cleanup

- Removed the default top rule from every About and Methodology section.
- Removed the line between the Market primary metric and support strip; proximity and the tinted group now communicate the relationship.
- Replaced the inline disclosure top rule with a soft, rounded open surface.
- Removed generic workspace header underlines.
- Preserved rules where they still organize repeated data, such as table rows and the final mobile KPI subdivision.

## G. Find skeleton restoration

- The loader now appears immediately for both Rent and Sale submissions.
- Three skeleton cards reproduce the final result geometry: kicker/title, fit bar, three aligned data rows, and action region.
- Prior results, empty content, and errors are hidden when a request begins, preventing mixed old/new states.
- `aria-busy`, `role=status`, and `aria-live=polite` communicate loading semantically.
- Shimmer uses the shared skeleton gradient and becomes static under `prefers-reduced-motion`.
- Throttled visual evidence: `find-loading-rent-375.png` and `find-loading-sale-375.png`.

## H. Page-by-page changes

- **Home:** visually rechecked; intentionally left light.
- **Market:** restored major spacing, strengthened primary/support KPI hierarchy, added a 2+1 mobile KPI composition, softened inline methodology treatment, and separated downstream sections.
- **Valuation:** aligned workspace rhythm and retained the focused form/result path and existing result skeleton.
- **Find:** added a third geometry-matched skeleton, cleared stale output during requests, and validated both modes.
- **Statistics:** grouped visible content with a shared section gap and integrated chart/table surfaces; answer-first disclosure behavior remains intact.
- **Compare:** aligned workspace spacing and preserved distinct input, result, table, and optional chart roles.
- **Rent Yield:** inherited intentional table framing and shared section alignment without extra ornament.
- **About:** retained 3–4 large conceptual groups, removed repetitive rules, aligned prose widths, and kept the technical depth in a clear disclosure.
- **Methodology:** established an editorial reading width, generous chapter rhythm, and two restrained tinted technical chapters instead of repetitive boxes/lines.

## I. Screenshot evidence

- Before: `reports/METRIK/ui-harmony/baseline/` — 36 captures.
- After: `reports/METRIK/ui-harmony/after/` — 36 route/breakpoint captures plus 2 throttled Find loading captures.
- Routes: Home, Market/Ulpiana, Valuation, Find, Statistics, Compare, Rent Yield, About, and Methodology.

## J. Mobile QA

- 375px and 768px visually inspected.
- No horizontal document overflow across the 36-capture matrix.
- Market support metrics use a deliberate 2+1 layout at 375px.
- Editorial sections retain chapter separation rather than collapsing into dense text.
- Find Rent and Sale skeletons were visually captured under artificial 2-second latency.

## K. Desktop QA

- 1280px and 1440px captured for all nine routes.
- Market main/rail alignment, data workspace columns, content widths, section gaps, and footer transitions were checked.
- Capture run reported no console errors, failed static files, or overflow.

## L. Accessibility QA

- Existing skip link, semantic main landmark, headings, labels, and responsive controls remain intact.
- Disclosures retain visible focus rings and keyboard-native `details/summary` behavior.
- Find loading is announced politely without replacing form semantics.
- Reduced-motion skeleton behavior is explicitly supported.
- Target sizes and mobile navigation were visually checked at 375px.

## M. SQ/EN QA

- Existing automated browser test switched to English and verified translated footer output.
- The screenshot matrix ran in SQ; Find mode labels and loading copy were checked in both Rent and Sale states.
- No new user-facing untranslated copy was introduced; the additional skeleton content is visually suppressed while loading and uses existing i18n labels.

## N. System/test QA

- Full suite: **593 passed, 7 skipped, 1 warning** in 147.74s.
- Public-site browser E2E: **6 passed** in 15.10s.
- Final screenshot sweep: **36 captured, issues=none**.
- Find throttled QA: **Rent + Sale passed**, three skeleton cards in each state.
- Final route sweep found no horizontal overflow and no new browser console errors.

## O. Remaining issues

- **BLOCKER:** None.
- **IMPORTANT:** None found in the scoped visual/system QA.
- **OPTIONAL:** A future content-design pass could add explicit chapter labels to the deeper Statistics sections when product owners want more content exposed by default. Current answer-first disclosure remains the more restrained choice.
