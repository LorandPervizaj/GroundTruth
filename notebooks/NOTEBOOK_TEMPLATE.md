# Notebook template

Save as `notebooks/YYYY-MM-DD_<question-slug>.ipynb`

Pin at top of notebook:

```python
METHODOLOGY_VERSION = "1.0.0"
PARSER_VERSION = "1.3.0"
ETL_DATE = "YYYY-MM-DD"
CLAIM_ID = "GT-XXX"  # register after verification
```

---

## 1. Question

(One sentence.)

## 2. Hypothesis

(Optional.)

## 3. Dataset

- Filters:
- n:
- `dataset_hash`: (from `uv run python scripts/manage_claims.py fingerprint`)

## 4. Facts (observations)

Direct measurements only. Always show **n**, median, IQR, bootstrap 95% CI.

```python
from groundtruth.analytics.stats import summarize, bootstrap_median_ci, compare_medians
from groundtruth.analytics.dataset_confidence import compute_dataset_confidence
from groundtruth.analytics.stability import MetricSnapshot, assess_stability
```

## 5. Interpretations (hypotheses)

Visually separate from facts. Prefix with "We interpret…" not "The market is…"

## 6. Negative findings

If no effect: record explicitly. Register as `claim_type=negative`.

## 7. Limitations

Scope, causality, missing fields, single source.

## 8. Future questions

```
- ...
- ...
```

## 9. Claim registration

```bash
uv run python scripts/manage_claims.py register \
  --statement "..." \
  --claim-type fact \
  --n 350 \
  --notebook notebooks/YYYY-MM-DD_slug.ipynb \
  --fingerprint-dataset
```
