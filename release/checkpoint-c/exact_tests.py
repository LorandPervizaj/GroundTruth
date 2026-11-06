"""Run focused regressions with image runtime dependencies and read-only test fixtures."""

import json
import os
import subprocess

from fixture import LABEL, NET, OUT, PG, ROOT, config

image = json.loads((OUT / "identity.json").read_text())["image_config_id"]
c = config()
tests = [
    "phase5_locations",
    "location_resolver",
    "pro_rks_parser",
    "merrjep_parser",
    "product_submissions",
    "table_submissions",
    "table_identity",
    "empty_public_coverage",
    "production_hardening",
    "production_cache_startup",
    "published_yield_boundary",
    "web_runtime_imports",
    "release_gazetteer_bootstrap",
    "market_integrity",
    "market_metrics",
    "api_security",
    "lookup_api",
    "ready_api",
]
env = {
    **os.environ,
    "GROUNDTRUTH_TEST_DATABASE_URL": f"postgresql+psycopg://checkpoint_test:{c['password']}@{PG}:5432/checkpoint_test",
    "TEST_TABLE_EMULATOR_CONNECTION_STRING": "DefaultEndpointsProtocol=http;AccountName=localmetrik;AccountKey="
    + c["tablekey"]
    + ";TableEndpoint=http://metrik-c-table:10002/localmetrik;",
}
args = [
    "docker",
    "run",
    "--rm",
    "--name",
    "metrik-c-exact-tests",
    "--label",
    LABEL,
    "--network",
    NET,
    "--user",
    "0",
    "-e",
    "APP_ENV=development",
    "-e",
    "PRODUCT_WRITE_BACKEND=jsonl",
    "-e",
    "GROUNDTRUTH_TEST_DATABASE_URL",
    "-e",
    "TEST_TABLE_EMULATOR_CONNECTION_STRING",
    "-e",
    "PYTHONPATH=/tools:/app",
    "-e",
    "PYTEST_DISABLE_PLUGIN_AUTOLOAD=1",
    "-v",
    "metrik-c-testtools:/tools:ro",
    "-v",
    str(ROOT.parents[1] / "tests") + ":/app/tests:ro",
    "-v",
    str(ROOT.parents[1] / "scripts/load_gazetteers.py") + ":/app/scripts/load_gazetteers.py:ro",
    "-v",
    str(OUT) + ":/evidence",
    "--entrypoint",
    "/app/.venv/bin/python",
    image,
    "-m",
    "pytest",
    "-p",
    "pytest_asyncio.plugin",
    "-q",
    "--override-ini=cache_dir=/tmp/pytest-cache",
    *[f"tests/test_{name}.py" for name in tests],
    "--junitxml=/evidence/exact-tests.xml",
]
with (OUT / "exact-tests.log").open("w", encoding="utf8") as log:
    result = subprocess.run(args, env=env, stdout=log, stderr=subprocess.STDOUT)
print("Exact-image regression exit:", result.returncode)
raise SystemExit(result.returncode)
