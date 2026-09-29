import os

import pytest

from groundtruth.config import load_external_env


def test_external_env_loads_without_overriding_process(tmp_path, monkeypatch):
    env_file = tmp_path / "research.env"
    env_file.write_text(
        "GROUNDTRUTH_TEST_STATE_DIR='C:\\MetrikResearch\\state'\nGROUNDTRUTH_TEST_KEEP=file\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("GROUNDTRUTH_ENV_FILE", str(env_file))
    monkeypatch.setenv("GROUNDTRUTH_TEST_KEEP", "process")
    monkeypatch.delenv("GROUNDTRUTH_TEST_STATE_DIR", raising=False)
    try:
        assert load_external_env() == env_file
        assert os.environ["GROUNDTRUTH_TEST_STATE_DIR"] == "C:\\MetrikResearch\\state"
        assert os.environ["GROUNDTRUTH_TEST_KEEP"] == "process"
    finally:
        os.environ.pop("GROUNDTRUTH_TEST_STATE_DIR", None)


def test_missing_external_env_fails_loudly(tmp_path, monkeypatch):
    monkeypatch.setenv("GROUNDTRUTH_ENV_FILE", str(tmp_path / "absent.env"))
    with pytest.raises(FileNotFoundError):
        load_external_env()


def test_no_external_env_is_a_no_op(monkeypatch):
    monkeypatch.delenv("GROUNDTRUTH_ENV_FILE", raising=False)
    assert load_external_env() is None
