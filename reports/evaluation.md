# Valuation evaluation report

- **Evaluated at:** 2026-07-24T10:49:24.595300+00:00
- **Model:** DM-002/DM-003 v1.1.0
- **Dataset:** v2.0
- **Holdout:** `data\evaluation\valuation_holdout_v2.csv`
- **Rows:** 45/60 evaluated (15 skipped)
- **Valid-row coverage:** 75.0%
- **Invalid holdout labels:** 0
- **Confidence monotonic:** None

## Overall metrics

| Metric | Value |
|--------|------:|
| MAE | 34337.33 |
| RMSE | 52620.68 |
| Median AE | 27000.0 |
| MAPE | 43.71% |

## Error by confidence tier

| Tier | n | MAPE | MAE |
|------|--:|-----:|----:|
| medium | 45 | 43.71% | 34337.33 |

## Error by valuation type

| Type | n | MAPE | MAE |
|------|--:|-----:|----:|
| rent | 20 | 20.66% | 59.0 |
| sale | 25 | 62.15% | 61760.0 |

## Error by municipality

| Municipality | n | MAPE | MAE |
|--------------|--:|-----:|----:|
| Prishtina | 45 | 43.71% | 34337.33 |

## Error distribution

- ≤5%: 3
- 5–10%: 5
- 10–20%: 6
- 20–50%: 13
- >50%: 18
