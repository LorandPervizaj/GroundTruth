import os
import subprocess
import sys

import pytest
from sqlalchemy.engine import make_url

from groundtruth.config import get_settings
from tests.db_isolation import (
    DISABLED_DATABASE_URL,
    ROOT,
    UnsafeTestDatabaseError,
    resolve_test_database_url,
)

RESEARCH = "postgresql+psycopg://rema:secret@localhost:15432/rema"
TEST = "postgresql+psycopg://groundtruth_test:x@127.0.0.1:15433/groundtruth_test"


def test_this_session_never_targets_a_non_test_database():
    database = make_url(str(get_settings().database_url)).database
    assert "test" in database.lower()
    assert "GROUNDTRUTH_ENV_FILE" not in os.environ


def test_no_test_url_disables_database_tests(tmp_path):
    assert resolve_test_database_url({}, dotenv_path=tmp_path / ".env") == DISABLED_DATABASE_URL


def test_research_database_is_refused_by_name(tmp_path):
    with pytest.raises(UnsafeTestDatabaseError):
        resolve_test_database_url(
            {"GROUNDTRUTH_TEST_DATABASE_URL": RESEARCH}, dotenv_path=tmp_path / ".env"
        )


def test_database_named_by_application_env_is_refused(tmp_path):
    dotenv = tmp_path / ".env"
    dotenv.write_text(
        "DATABASE_URL=postgresql+psycopg://other:y@localhost:15433/groundtruth_test\n"
    )
    with pytest.raises(UnsafeTestDatabaseError, match="application or research"):
        resolve_test_database_url({"GROUNDTRUTH_TEST_DATABASE_URL": TEST}, dotenv_path=dotenv)


def test_database_named_by_research_env_file_is_refused(tmp_path):
    research_env = tmp_path / "research.env"
    research_env.write_text(f"DATABASE_URL='{TEST}'\n")
    with pytest.raises(UnsafeTestDatabaseError):
        resolve_test_database_url(
            {"GROUNDTRUTH_TEST_DATABASE_URL": TEST, "GROUNDTRUTH_ENV_FILE": str(research_env)},
            dotenv_path=tmp_path / ".env",
        )


def test_dedicated_test_database_is_accepted(tmp_path):
    dotenv = tmp_path / ".env"
    dotenv.write_text(f"DATABASE_URL={RESEARCH}\nGROUNDTRUTH_TEST_DATABASE_URL={TEST}\n")
    assert resolve_test_database_url({}, dotenv_path=dotenv) == TEST


def test_pytest_refuses_to_start_against_the_research_database():
    env = {**os.environ, "GROUNDTRUTH_TEST_DATABASE_URL": RESEARCH}
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "tests/test_external_env.py",
            "-q",
            "-p",
            "no:cacheprovider",
        ],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert completed.returncode != 0
    assert "UnsafeTestDatabaseError" in completed.stdout + completed.stderr
    assert "passed" not in completed.stdout
