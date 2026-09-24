# Statistical QA shadow calibration

New release-to-release heuristics run in shadow mode by default for 3–5 verified weekly cycles. Deterministic integrity failures—database failure, source collapse, parser/ETL catastrophe, missing artifacts, hash mismatch, and production readiness failure—already block immediately.

Each verified run appends a bounded entry to `pipeline_state/state.json` under `statistical_shadow_runs`:

- release and run IDs;
- predicted GREEN/YELLOW/RED;
- metric evidence and sample counts;
- operator assessment;
- false-positive and false-negative fields.

After each of the first five releases, inspect the run JSON and fill the three assessment fields in the durable state copy. Do not edit a release manifest. Tune thresholds only from repeated evidence, not a single surprising week.

Promotion criteria:

1. At least three representative weekly cycles recorded.
2. No unexplained false negatives.
3. RED predictions correspond to changes an operator would have blocked.
4. Low-sample neighborhood noise does not create repeated false RED results.
5. Threshold changes have focused unit tests.

After calibration, set `GROUNDTRUTH_STATISTICAL_QA_SHADOW=false` on the research Job. The setting promotes predicted RED statistical results to publication-blocking failures. YELLOW remains publishable and is reported in notifications.

To return immediately to report-only behavior:

```powershell
az containerapp job update -g <research-rg> -n job-groundtruth-weekly `
  --set-env-vars GROUNDTRUTH_STATISTICAL_QA_SHADOW=true
```
