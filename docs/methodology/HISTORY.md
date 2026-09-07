# Methodology version history

Methodology versions are **immutable**. Reports cite the version used at publication time.  
Supersede with a new semver — never edit a released version document.

| Version | Released | Status | Summary |
|---------|----------|--------|---------|
| [1.0.0](v1.0.0.md) | 2026-06-09 | **current** | Bootstrap median CI (5000). Median + IQR + MAD. Dataset confidence v1. Stability v1. Evidence grades A–E. |

## Retirement policy

When releasing **1.1.0**:

1. Copy current spec to `docs/methodology/v1.0.0.md` (frozen).
2. Mark row status `retired` in this table.
3. Add new row for 1.1.0 with `current`.
4. Claims published under 1.0.0 remain reproducible under that version.

## Reproducibility guarantee

A report stating *Methodology v1.0.0* must regenerate identical statistics given:

- Same `dataset_hash`
- Same `notebook_hash` / `sql_hash`
- Same parser version (`parser-v1.3.0`)
