# Evaluation results

JSON artifacts from `groundtruth evaluation valuate` (aggregated model metrics only — no raw listing HTML).

- `baseline.json` — frozen reference metrics for merge comparisons
- `candidate.json` — output from the current model run

Regenerate baseline (requires Postgres — on Windows if the published DB port times out, check `POSTGRES_PORT` / `DATABASE_URL`, or use `scripts/run_db_cli_docker.ps1`):

```bash
groundtruth evaluation valuate -o results/baseline.json --report reports/evaluation.md
```

**Current baseline** (2026-06-30 corpus): 20/60 holdout rows evaluated, MAPE 42.39%, MAE €42,350 (golden-derived holdout; many rows skip due to thin NH samples).

Merge gate:

```bash
groundtruth evaluation compare -b results/baseline.json -c results/candidate.json
```
