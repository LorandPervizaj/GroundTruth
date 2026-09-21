# Public metric registry

The executable source of truth is `src/groundtruth/analytics/metric_registry.py`. A public number is not complete unless its metric ID identifies its statistic, unit, population, required fields, rounding, minimum sample, and confidence method.

## Population boundaries

| Population | Purpose | Window |
|---|---|---|
| `recent.all` | Valid, canonical listing corpus | rolling 12 months |
| `recent.apartment_studio` | Headline apartment/studio indicators | rolling 12 months |
| `recent.sale.apartment_studio` | Sale-price metrics | rolling 12 months |
| `recent.rent.apartment_studio` | Rent metrics | rolling 12 months |
| `recent.sale.all_property_types` | Property-type sale table | rolling 12 months |
| `historical.apartment_studio` | Biweekly trend observations | 6–12 months |
| `valuation.*.comparables` | Estimate-specific comparable pools | valuation policy |

“Recent valid listings” is an analytical corpus count. It is not active inventory. Current inventory is a separate lifecycle-backed population and must never be inferred from age alone.

## Canonical headline metrics

The headline price fields are medians of asking prices: `median_sale_psm`, `median_rent_psm`, `median_sale_eur`, and `median_rent_eur`. Distribution metrics are explicitly registered as p10, p50, and p90. Area and bedroom indicators are medians, rounded only at the display boundary.

Legacy `average_*` JSON fields remain temporary compatibility aliases. They contain the same median value as their canonical `median_*` counterpart and are guarded by statistical QA. New consumers must not use them.

## Confidence

Confidence is computed per metric from its own usable sample, number of independent sources, freshness, and largest-source share. Headline cards and segmented tables must display the confidence belonging to the displayed metric, not a shared row-level badge. The deterministic boundaries are tested in `tests/test_metric_confidence.py`.

## Change procedure

1. Update the registry and its validation test.
2. Update producer and typed schema together.
3. Update every public consumer and cross-surface parity tests.
4. Rebuild lookup/release artifacts.
5. Run statistical QA before publishing.

Unknown metric or population IDs are release-blocking errors.
