"""Keep pytest away from the research and production databases.

Tests only ever connect to GROUNDTRUTH_TEST_DATABASE_URL. Without it, every
database-backed test skips because DATABASE_URL points at a closed port. The
repository .env and the research host env file are never used by tests.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from pathlib import Path

from dotenv import dotenv_values
from sqlalchemy.engine import make_url

ROOT = Path(__file__).resolve().parents[1]
TEST_URL_KEY = "GROUNDTRUTH_TEST_DATABASE_URL"
DISABLED_DATABASE_URL = "postgresql+psycopg://tests-disabled@127.0.0.1:9/tests_disabled"


class UnsafeTestDatabaseError(RuntimeError):
    """Raised before any connection when a test URL could reach real data."""


def _identity(url: str) -> tuple[str, int, str]:
    parsed = make_url(url)
    host = (parsed.host or "localhost").lower()
    if host in {"127.0.0.1", "::1"}:
        host = "localhost"
    return host, parsed.port or 5432, (parsed.database or "").lower()


def _file_value(path: Path | None, key: str) -> str | None:
    if path is None or not path.is_file():
        return None
    return dotenv_values(path).get(key) or None


def resolve_test_database_url(
    environ: Mapping[str, str], *, dotenv_path: Path | None = ROOT / ".env"
) -> str:
    """Return the only database URL tests may use, or fail closed."""
    configured = environ.get(TEST_URL_KEY) or _file_value(dotenv_path, TEST_URL_KEY)
    if not configured:
        return DISABLED_DATABASE_URL
    database = make_url(configured).database or ""
    if "test" not in database.lower():
        raise UnsafeTestDatabaseError(
            f"{TEST_URL_KEY} must name a dedicated database containing 'test'"
        )
    research_env = environ.get("GROUNDTRUTH_ENV_FILE")
    protected = [
        _file_value(dotenv_path, "DATABASE_URL"),
        _file_value(Path(research_env) if research_env else None, "DATABASE_URL"),
    ]
    target = _identity(configured)
    if any(url and _identity(url) == target for url in protected):
        raise UnsafeTestDatabaseError(f"{TEST_URL_KEY} names the application or research database")
    return configured


def isolate_process_environment() -> str:
    """Point this pytest process at the test database before settings load."""
    url = resolve_test_database_url(os.environ)
    os.environ.pop("GROUNDTRUTH_ENV_FILE", None)
    os.environ["DATABASE_URL"] = url
    return url
