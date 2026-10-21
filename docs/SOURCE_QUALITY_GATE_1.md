# Part 1 completion evidence — 2026-10-21

**Overall status: COMPLETE. Gate 1: PASS for the calculator and required focused regressions.**
The full working-tree suite has a pre-existing weekly-runner failure, recorded
below; this is not a claim that the entire repository is green.

## Implementation and inventory

- `src/groundtruth/analytics/source_quality_models.py`: versioned input, policy, assessment, report contracts.
- `src/groundtruth/analytics/source_quality.py`: six-dimension listing/source scoring, uncertainty, weights, duplicate diagnostics, deterministic JSON/CSV/schema emission.
- `src/groundtruth/analytics/source_quality_population.py`: raw-rooted pipeline reader covering successful, rejected, and pending outcomes.
- `src/groundtruth/commands/source_quality_commands.py`: read-only database/offline operator command.
- `src/groundtruth/cli.py`: two registration lines only; existing weekly-runner edits excluded from this mission's commit.
- `tests/test_source_quality.py`, `tests/test_source_quality_reporting.py`: scoring, reporting, CLI, registry extension, actual ORM-model SQLite integration, read-only query checks, sanitized failure handling.
- `tests/fixtures/source_quality/synthetic.json`: seven synthetic versions representing six unique listings across two sources.
- `docs/SOURCE_QUALITY_SCORING.md`: implementation map, formulas, population, schema, limitations, operator examples.
- `docs/examples/source_quality/source_quality_report.json`, `source_quality_summary.csv`, `source_quality_report.schema.json`: exact fixture-generated example outputs.
- This Gate 1 evidence record.

## Scoring and unknown evidence

Default weights: validity 25%, completeness 20%, independently checked location
25%, internal consistency 15%, freshness 10%, independently checked source history
5%. Unknown criteria remain null; only the provisional composite imputes neutral
50. Source quality averages listing composites, not just successful extractions.
Coverage/sample counts describe measured evidence separately. Mandatory existing
validation/exclusion rules are untouched.

Recommended weight is `clamp(1 + (quality - 70) / 100, .75, 1.25)` only after
minimum sample 30, measured coverage 90%, independent location verification 80%,
and processed coverage 95%; otherwise 1.00 with explicit reasons. No recommendation
is applied to existing analytics. See the scoring document for field definitions.

## Executed CLI and synthetic example

```powershell
.venv/Scripts/groundtruth.exe analytics source-quality report --as-of 2026-10-21T00:00:00Z --days 30 --segment --fixture tests/fixtures/source_quality/synthetic.json --output reports/generated/source_quality/example
```

Result: `Wrote 24 source/segment summaries and 6 listing assessments`.
Repeated with output directory `reports/generated/source_quality/repeat`; JSON,
CSV, and schema were byte-identical to the first run and the checked-in examples.

**Synthetic values only — not real portal ratings:**

| Fixture label | Versions | Unique listings | Quality | Measured coverage | Weight |
| --- | ---: | ---: | ---: | ---: | ---: |
| gjirafa | 4 | 3 | 67.916667 | 70% | 1.00 |
| merrjep | 3 | 3 | 70.833333 | 60% | 1.00 |

The remaining four registered sources are explicitly `no_data`, score null,
weight 1.00. The two populated sources also fail conservative weight eligibility.

## Test and lint evidence

Python 3.13.13 in the existing `.venv`; no dependencies or migrations added.

```powershell
.venv/Scripts/python.exe -m pytest tests/test_source_quality.py tests/test_source_quality_reporting.py -q --tb=short
```

Result: **36 passed**.

```powershell
.venv/Scripts/python.exe -m pytest tests/test_source_quality.py tests/test_source_quality_reporting.py tests/test_validation.py tests/test_confidence.py tests/test_parser_kpis.py tests/test_portal_registry.py tests/test_normalizers.py tests/test_pipeline_failure_safety.py tests/test_corpus.py tests/test_corpus_authority.py tests/test_cross_dedup.py tests/test_source_skew.py -q --tb=short
```

Result: **95 passed**. This includes processing, parser KPIs, registry, normalization,
ETL failure safety, corpus, cross-deduplication, and source-skew regressions.

```powershell
.venv/Scripts/python.exe -m pytest -q --tb=short
```

Full-suite result: **776 passed, 45 skipped, 1 failed**, with three deprecation
warnings. That run preceded the final additional database-error redaction test,
which passed in the 36/95-test runs above. The failure is
`tests/test_home_trust_snapshot.py::test_legacy_weekly_runners_keep_crawl_exit_code[run_weekly.ps1]`:
it requires literal `exit $LASTEXITCODE`, while the pre-existing modified
`scripts/run_weekly.ps1` uses `exit $result`. Both files were already modified before
this mission; neither was edited or staged by this task. Deferred as unrelated.
Environment-gated tests include dedicated-PostgreSQL tests and opt-in browser
tests. The dedicated test DB TCP endpoint was unavailable. No live private DB
was used for tests, and no production services were started.

Ruff `check` and `format --check` ran on all six new Python files plus the CLI:
**all checks passed; 7 files already formatted**. Report roundtrip validation,
non-finite rejection, and emitted schema tests passed. `git diff --check` also
passes for this mission's staged changes.

## Repository safety

Pre-work root: `C:/Projects/FartEstate`; branch `security-patch-up`;
HEAD `24f9036dc88f25a4566512f2786c25ce8aaf0e21`;
remote `https://github.com/LorandPervizaj/GroundTruth.git`.
There were 252 status entries, including existing CLI/pipeline edits and the plan
saved earlier in this chat. Created branch `codex/source-quality-calculator`
without discarding work. Local pre-work status and CLI diff are preserved under
ignored `.tmp/source-quality/`. All 242 pre-existing modified tracked files hashed
immediately before QA retained identical contents after QA.

Only the inventory above belongs to the implementation commit; the original plan
and README link from the earlier request remain preserved as pre-existing work.
The two CLI registration lines are staged separately from existing CLI edits.
Inspect the commit identification in the completion chat or `git log -1` on this
branch. No push, production DB access, migrations, frontend changes, analytics
publication, source-priority changes, scraping, Harta work, or deployment occurred.

## Gate decision and Part 2 readiness

**PASS:** all calculator-specific and required focused regression checks pass;
the real pipeline-model reader works on isolated synthetic data, outputs are
reproducible, insufficient evidence stays neutral, and no calculator-blocking
defect remains. The unrelated full-suite failure is explicit, not suppressed.

Part 2 can begin with this calculator. It must select a comparable actual DB
snapshot/window, verify parser versus publisher errors, attach independently
reviewed location/history evidence where available, and calibrate the initial
policy. Live PostgreSQL query execution and query performance still need validation
in that environment. Probable duplicate matches and human-verification sample
representativeness require review; this implementation supplies no real rankings
or calibrated error rates. Parts 2 and 3 have not started.
