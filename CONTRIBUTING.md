# Contributing

Bug reports, documentation fixes, and focused improvements are welcome. For a
larger change, open an issue first to agree on scope and avoid duplicating work.

## Development setup

Use Python 3.12 and [uv](https://docs.astral.sh/uv/). From the repository root:

```bash
uv sync --all-extras
uv run pytest -q
uv run ruff check src tests scripts
uv run ruff format --check src tests scripts
```

Browser tests require Playwright Chromium and a running test target; see the
[README](README.md#local-development) and [performance testing guide](docs/PERFORMANCE_TESTING.md)
for project-specific setup.

## Data and generated files

Do not commit `.env` files, raw crawl captures, database exports, local logs,
screenshots, or generated evaluation candidates. Keep reproducible fixtures and
the verified `reports/generated/lookup_cache/` release bundle intact when
working on unrelated changes. See [data handling](docs/DATA_HANDLING.md) and
[the market data contract](docs/MARKET_DATA_CONTRACT.md) before changing data
flows or public output.

Keep pull requests focused, describe the behavior changed, and include the
commands used to verify it.
